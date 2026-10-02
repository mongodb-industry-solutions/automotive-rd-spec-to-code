# Infrastructure Deployment: GKE Cluster & Argo Workflows

This directory contains the **Infrastructure as Code (IaC)** required to provision the complete Google Cloud and Kubernetes environment to run the Automotive Spec-to-Code Agent.

---

## Architecture Components Provisioned

1. **Networking & Security**:
   * Custom VPC network (`sdv-agentic-vpc`) and private subnet (`10.10.0.0/20`).
   * Secondary IP ranges for Pods (`10.20.0.0/16`) and Services (`10.30.0.0/20`).
   * Cloud Router and Cloud NAT for secure outbound internet egress from private nodes (e.g. communicating with MongoDB Atlas and Vertex AI).
2. **Container & Artifact Storage**:
   * Google Artifact Registry (`sdlc-agentic-repo`) for Docker images.
   * Google Cloud Storage bucket (`hrzn-agentic-dev-artifacts`) for workflow run artifacts and logs.
3. **Identity & Access Management (Workload Identity)**:
   * Dedicated IAM Service Account (`sdlc-agent-runner`) with `roles/aiplatform.user` and `roles/storage.objectAdmin`.
   * Workload Identity binding allowing the in-cluster Kubernetes ServiceAccount (`workflows/sdlc-agent-sa`) to authenticate directly to Google Cloud without storing private keys.
4. **Compute Platform**:
   * **GKE Autopilot Cluster** (`hrzn-agentic-dev-gke`) with private nodes.
5. **Workflow Orchestration**:
   * **Argo Workflows** controller and server deployed into the `workflows` namespace.

---

## Prerequisites: Enable Google Cloud APIs

Ensure the required Google Cloud APIs are enabled for your project before running Terraform or creating cluster resources:

```bash
gcloud services enable \
  storage.googleapis.com \
  aiplatform.googleapis.com \
  container.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  logging.googleapis.com \
  --project="hrzn-agentic-framework-1"
```

### Pre-create GCS Artifact Bucket (Optional / Ahead of Time)
The Terraform template provisions the storage bucket automatically. If you prefer to pre-create it manually using the gcloud CLI:

```bash
gcloud storage buckets create gs://hrzn-agentic-dev-artifacts \
  --project="hrzn-agentic-framework-1" \
  --location=europe-west3 \
  --uniform-bucket-level-access
```

---

## Step 1: Provision GCP Infrastructure via Terraform

### 1. Initialize Terraform
```bash
cd infrastructure/terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your project parameters:
```hcl
gcp_project_id         = "hrzn-agentic-framework-1"
gcp_region             = "europe-west3"
gcp_zone               = "europe-west3-a"
gke_cluster_name       = "hrzn-agentic-dev-gke"
artifact_repository_id = "sdlc-agentic-repo"
storage_bucket_name    = "hrzn-agentic-dev-artifacts"
```

### 2. Apply Terraform
```bash
terraform init
terraform plan
terraform apply -auto-approve
```

---

## Step 2: Configure GKE Access & Install Argo Workflows

### 1. Connect kubectl to the newly provisioned GKE Cluster
```bash
gcloud container clusters get-credentials hrzn-agentic-dev-gke \
  --region europe-west3 \
  --project hrzn-agentic-framework-1
```

### 2. Create the `workflows` Namespace
```bash
kubectl create namespace workflows
```

### 3. Install Argo Workflows Server and Controller
```bash
kubectl apply -f ../k8s/argo-workflows-install.yaml -n workflows
```

### 4. Configure Workload Identity ServiceAccount
Edit `../k8s/sdlc-agent-sa.yaml` to ensure the annotation references your `gcp_project_id`, then apply:
```bash
kubectl apply -f ../k8s/sdlc-agent-sa.yaml -n workflows
```

### 5. Create MongoDB Atlas & Voyage AI Credentials Secrets
```bash
kubectl create secret generic mongodb-credentials \
  --from-literal=MONGO_URI="<YOUR_MONGODB_ATLAS_URI>" \
  --from-literal=MONGO_DB="score_db" \
  --from-literal=MONGO_COLLECTION="requirements" \
  --from-literal=VOYAGE_API_KEY="<YOUR_VOYAGE_AI_KEY>" \
  --from-literal=VOYAGE_MODEL="voyage-3.5" \
  -n workflows
```

### 6. Configure MongoDB Atlas Network Access (Mandatory Prerequisite)
> [!IMPORTANT]
> This is a **strict mandatory prerequisite**. The automotive-rag agent requires live MongoDB Atlas access for ASPICE SWE.1/SWE.3/SWE.4 requirements retrieval. Local fallbacks are disabled.

The private GKE cluster nodes route external internet traffic (including MongoDB Atlas and Voyage AI) through Google Cloud NAT (`sdv-agentic-nat`). When connecting to a MongoDB Atlas cluster, Atlas validates incoming IP addresses against its **Network Access** IP Access List. If the outbound NAT IP is not allowed, Atlas terminates the TLS handshake with `[SSL: TLSV1_ALERT_INTERNAL_ERROR] (SSL alert number 80)`.

**To allow the GKE cluster to connect to MongoDB Atlas:**
1. Determine the cluster's Cloud NAT external egress IP:
   ```bash
   gcloud compute routers get-status sdv-agentic-router \
     --region=europe-west3 \
     --project=hrzn-agentic-framework-1 \
     --format="value(result.natStatus[0].autoAllocatedNatIps[0])"
   ```
   *(Currently: `34.179.208.3`)*
2. In the **MongoDB Atlas Console**:
   * Navigate to **Security** > **Network Access** > **IP Access List**.
   * Click **+ Add IP Address**.
   * Enter `34.179.208.3/32` (or select `0.0.0.0/0` / *Allow Access From Anywhere* for quick evaluation).
   * Enter a comment (e.g. `GKE Cluster Cloud NAT Egress`) and click **Confirm**.

---

## Step 3: Verify the Infrastructure & Access Argo UI

Verify that all pods in the `workflows` namespace are running:
```bash
kubectl get pods -n workflows
```

Access the Argo Workflows UI locally via port-forwarding:
```bash
kubectl port-forward svc/argo-server 2746:2746 -n workflows
```
Open [http://localhost:2746/workflows](http://localhost:2746/workflows) in your browser.

---

## Step 4: GCS Run Artifacts & Storage Layout

When the Automotive Spec-to-Code Agent completes an autonomous enhancement run, all deliverables are systematically archived to the Google Cloud Storage bucket (`gs://hrzn-agentic-dev-artifacts`).

Each run generates a unique, timestamp-prefixed directory:
```text
gs://hrzn-agentic-dev-artifacts/runs/<timestamp>_<workflow_id>/
├── trace.json
├── assessment.md
├── delta_analysis.md
└── code/
    ├── timed_command_queue.h
    ├── timed_command_queue_enhanced_test.cpp
    └── requirements.rst
```

### Artifact Descriptions:
* **`trace.json`**: Complete end-to-end execution telemetry containing step timestamps, tool invocations, MongoDB Atlas queries and responses, and Gemini token usage.
* **`assessment.md`**: Complete diagnostic reasoning, failure mode analysis, and ASPICE traceability report generated by the agent.
* **`delta_analysis.md`**: Dedicated engineering delta analysis reviewing where the original implementation deviated from ISO 26262 (ASIL-B) and ASPICE (SWE.1/SWE.3/SWE.4), including the hazard comparison matrix and architectural rationale for safety reviewers.
* **`code/` Sub-folder**:
  * **`timed_command_queue.h`**: Hardened C++ header with compile-time bounded capacity (`template <size_t Capacity>`), deterministic drop-oldest overflow policy, overflow callback notification, and zero dynamic heap allocation in safety loops.
  * **`timed_command_queue_enhanced_test.cpp`**: Comprehensive GoogleTest verification suite testing boundary conditions, overflow, timeout deadlines, and thread-safety invariants.
  * **`requirements.rst`**: Sphinx-Needs requirements specification (`REQ_SCORE_TCQ_001` - `006`).

