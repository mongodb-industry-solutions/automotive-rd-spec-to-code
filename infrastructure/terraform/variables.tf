variable "gcp_project_id" {
  type        = string
  description = "Target GCP project ID for the Horizon Agentic Dev Environment"
  default     = "hrzn-agentic-framework-1"
}

variable "gcp_region" {
  type        = string
  description = "GCP Region for GKE and Artifact Registry"
  default     = "europe-west3"
}

variable "gcp_zone" {
  type        = string
  description = "GCP Zone for GKE Cluster"
  default     = "europe-west3-a"
}

variable "gke_cluster_name" {
  type        = string
  description = "Name of the minimal GKE Cluster"
  default     = "hrzn-agentic-dev-gke"
}

variable "artifact_repository_id" {
  type        = string
  description = "Artifact Registry Docker repository ID"
  default     = "sdlc-agentic-repo"
}

variable "storage_bucket_name" {
  type        = string
  description = "GCS Storage bucket for agent run artifacts and build logs"
  default     = "hrzn-agentic-dev-artifacts"
}
