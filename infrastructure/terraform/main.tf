terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
  zone    = var.gcp_zone
}

# 1. Enable Required GCP Service APIs
resource "google_project_service" "enabled_apis" {
  for_each = toset([
    "compute.googleapis.com",
    "container.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "aiplatform.googleapis.com",
    "iam.googleapis.com",
    "logging.googleapis.com",
    "storage.googleapis.com"
  ])

  project            = var.gcp_project_id
  service            = each.key
  disable_on_destroy = false
}

# 2. VPC Network and Subnet for Private GKE Autopilot
resource "google_compute_network" "agentic_vpc" {
  depends_on              = [google_project_service.enabled_apis]
  name                    = "sdv-agentic-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "agentic_subnet" {
  name                     = "sdv-agentic-subnet"
  ip_cidr_range            = "10.10.0.0/20"
  region                   = var.gcp_region
  network                  = google_compute_network.agentic_vpc.id
  private_ip_google_access = true

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.20.0.0/16"
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.30.0.0/20"
  }
}

# 3. Cloud Router and Cloud NAT for Private Node Egress (Satisfies Org Policy vmExternalIpAccess)
resource "google_compute_router" "nat_router" {
  name    = "sdv-agentic-router"
  region  = var.gcp_region
  network = google_compute_network.agentic_vpc.id
}

resource "google_compute_address" "nat_ip" {
  name   = "sdv-agentic-nat-ip"
  region = var.gcp_region
}

resource "google_compute_router_nat" "nat_gateway" {
  name                               = "sdv-agentic-nat"
  router                             = google_compute_router.nat_router.name
  region                             = var.gcp_region
  nat_ip_allocate_option             = "MANUAL_ONLY"
  nat_ips                            = [google_compute_address.nat_ip.self_link]
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}

# 4. Artifact Registry for ADK Harness and MCP Containers
resource "google_artifact_registry_repository" "agentic_repo" {
  depends_on    = [google_project_service.enabled_apis]
  location      = var.gcp_region
  repository_id = var.artifact_repository_id
  description   = "Docker repository for ADK 2.0 Agent Runtimes & MCP Tool Servers"
  format        = "DOCKER"
}

# 5. GCS Storage Bucket for Agent Run Logs and Diff Artifacts
resource "google_storage_bucket" "agent_artifacts_bucket" {
  depends_on    = [google_project_service.enabled_apis]
  name          = var.storage_bucket_name
  location      = var.gcp_region
  force_destroy = true

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }
}

# 6. GCP IAM Service Account for Workload Identity
resource "google_service_account" "agent_runner_sa" {
  depends_on   = [google_project_service.enabled_apis]
  account_id   = "sdlc-agent-runner"
  display_name = "SDLC Agent Runner Service Account"
  description  = "Service account utilized by Argo Workflow ADK Agent runner pods"
}

# Grant Vertex AI User & Storage Access to IAM Service Account
resource "google_project_iam_member" "agent_sa_vertex" {
  project = var.gcp_project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.agent_runner_sa.email}"
}

resource "google_project_iam_member" "agent_sa_storage" {
  project = var.gcp_project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.agent_runner_sa.email}"
}

# 7. GKE Autopilot Cluster with Private Nodes
resource "google_container_cluster" "agentic_gke" {
  depends_on = [google_project_service.enabled_apis, google_compute_router_nat.nat_gateway]
  name       = var.gke_cluster_name
  location   = var.gcp_region

  network    = google_compute_network.agentic_vpc.name
  subnetwork = google_compute_subnetwork.agentic_subnet.name

  enable_autopilot = true

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }

  release_channel {
    channel = "REGULAR"
  }

  workload_identity_config {
    workload_pool = "${var.gcp_project_id}.svc.id.goog"
  }
}

# 8. Workload Identity User IAM Binding (Depends on Cluster to ensure pool exists)
resource "google_service_account_iam_member" "workload_identity_user" {
  depends_on         = [google_container_cluster.agentic_gke]
  service_account_id = google_service_account.agent_runner_sa.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.gcp_project_id}.svc.id.goog[workflows/sdlc-agent-sa]"
}

output "gke_cluster_endpoint" {
  value = google_container_cluster.agentic_gke.endpoint
}

output "artifact_registry_uri" {
  value = "${var.gcp_region}-docker.pkg.dev/${var.gcp_project_id}/${google_artifact_registry_repository.agentic_repo.repository_id}"
}

output "nat_egress_ip" {
  description = "Static egress IP address of GKE Cloud NAT to whitelist in MongoDB Atlas"
  value       = google_compute_address.nat_ip.address
}
