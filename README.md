# Automotive R&D Spec-to-Code: Agentic RAG Platform

> **Joint Solution: Google Cloud + MongoDB Atlas**  
> Autonomous, safety-critical software engineering for Software-Defined Vehicles (SDVs) using **MongoDB Atlas Vector Search**, **Google Cloud Run**, the **Google Antigravity (AGY) SDK**, **Gemini 3.8 Flash**, and **Argo Workflows on GKE**.

---

## Executive Overview

Modern Software-Defined Vehicles (SDVs) demand strict adherence to safety and quality standards, specifically **ASPICE (Automotive SPICE 4.0)** and **ISO 26262 (ASIL-B/D)**. Transitioning open-source or foundation software components (such as **Eclipse S-CORE**) into automotive-grade production code requires:
1. Formulating formal software requirements specifications (ASPICE SWE.1).
2. Hardening architecture and detailed design against concurrency failure modes and dynamic memory restrictions (ASPICE SWE.3).
3. Authoring comprehensive unit verification suites with bi-directional requirement traceability (ASPICE SWE.4).

This repository presents the complete end-to-end joint solution:
* **Knowledge Plane (MongoDB Atlas)**: Ingests automotive standards, Sphinx-Needs templates, and Eclipse S-CORE specifications into MongoDB Atlas using Voyage AI embeddings, executed locally or as a serverless **Google Cloud Run Job**.
* **Agentic Reasoning (Google Antigravity SDK)**: Employs the **Google Antigravity SDK** and **Gemini 3.8 Flash** with a co-located FastMCP server to ground autonomous engineering decisions against MongoDB Atlas Vector Search.
* **Infrastructure as Code (Terraform & GKE)**: Provisions the private VPC, Cloud NAT, Artifact Registry, Workload Identity, and **GKE Autopilot** cluster from scratch.
* **Enterprise Orchestration (Argo Workflows)**: Runs the end-to-end spec-to-code pipeline as a containerized **Argo Workflow on GKE**, generating production-grade C++ deliverables and OpenTelemetry traces in under 5 minutes.

---

## End-to-End Workflow

The solution is divided into cooperative phases that integrate the data plane, infrastructure, and agent runtime:

```
+----------------------------------------------------------------------------------------------------+
|                                    PHASE 1: KNOWLEDGE INGESTION                                     |
|                                                                                                    |
|   Eclipse S-CORE Docs       +---------------------------+        Voyage AI       +---------------+  |
|   ASPICE Standards (.rst) ->|   Google Cloud Run Job    |-----> (1024-dim emb) ->| MongoDB Atlas |  |
|   PlantUML Architecture     |   (ingest-pipeline/)      |                        |  score_db     |  |
|   C++ Policies (.md)        +---------------------------+                        +-------+-------+  |
+------------------------------------------------------------------------------------------|---------+
                                                                                           |
                                                   Grounding & Vector Retrieval            |
+------------------------------------------------------------------------------------------v---------+
|                                    PHASE 2: AGENTIC SPEC-TO-CODE PIPELINE                           |
|                                                                                                    |
|    Unhardened Source       +---------------------------+        FastMCP        +-----------------+  |
|    timed_command_queue.h ->|     Argo Workflow Pod     |<--------------------->| Atlas Tools     |  |
|                            |  • Antigravity SDK Agent  |       (stdio)         | • vector_search |  |
|                            |  • Gemini 3.8 Flash       |                       | • get_document  |  |
|                            +-------------+-------------+                       | • find          |  |
|                                          |                                     | • aggregate     |  |
|                                          v                                     +-----------------+  |
|                        +------------------------------------+                                       |
|                        |      Verified ASPICE Deliverables   |                                      |
|                        |  • SWE.1: Sphinx-Needs Spec        |                                      |
|                        |  • SWE.3: Hardened C++ Header      |                                      |
|                        |  • SWE.4: GoogleTest Suite         |                                      |
|                        |  • Trace: OpenTelemetry JSON       |                                      |
|                        +------------------------------------+                                       |
+----------------------------------------------------------------------------------------------------+
```

---


## Step-by-Step Execution Guide

### Phase 1: Ingest Automotive Knowledge into MongoDB Atlas

The `ingest-pipeline/` component reads Sphinx-Needs specifications, ASPICE standards, and C++ policies, generates Voyage AI embeddings, and stores them in MongoDB Atlas.

#### Option A: Run Ingestion Locally
```bash
cd ingest-pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Configure MONGO_URI and VOYAGE_API_KEY in .env

python main.py --source-dir sample_data
```

#### Option B: Run Ingestion as a Google Cloud Run Job
As detailed in [`ingest-pipeline/README.md`](ingest-pipeline/README.md), build and trigger the batch job directly on Google Cloud:
```bash
gcloud builds submit --tag europe-west1-docker.pkg.dev/$PROJECT_ID/ingest-pipeline/ingest-pipeline:latest
gcloud run jobs create ingest-pipeline \
  --image europe-west1-docker.pkg.dev/$PROJECT_ID/ingest-pipeline/ingest-pipeline:latest \
  --region europe-west1 \
  --set-secrets=MONGO_URI=mongo-uri:latest,VOYAGE_API_KEY=voyage-api-key:latest

gcloud run jobs execute ingest-pipeline --region europe-west1 --wait
```

---

### Phase 2: Deploy GKE Cluster & Argo Workflows (IaC)

If you do not already have a GKE cluster with Argo Workflows provisioned, deploy the complete cloud stack via Terraform in [`infrastructure/`](infrastructure/):

```bash
cd infrastructure/terraform
cp terraform.tfvars.example terraform.tfvars
terraform init && terraform apply -auto-approve

# Connect kubectl and install Argo Workflows
gcloud container clusters get-credentials hrzn-agentic-dev-gke --region europe-west3
kubectl apply -f ../k8s/argo-workflows-install.yaml -n workflows
kubectl apply -f ../k8s/sdlc-agent-sa.yaml -n workflows

# Create MongoDB Atlas secret
kubectl create secret generic mongodb-credentials \
  --from-literal=MONGO_URI="<YOUR_MONGODB_URI>" \
  --from-literal=MONGO_DB="score_db" \
  --from-literal=MONGO_COLLECTION="requirements" \
  --from-literal=VOYAGE_API_KEY="<YOUR_VOYAGE_API_KEY>" \
  --from-literal=VOYAGE_MODEL="voyage-3.5" \
  -n workflows

# Configure MongoDB Atlas Network Access (Mandatory)
# Whitelist the Cloud NAT egress IP (34.179.208.3/32 or 0.0.0.0/0) in MongoDB Atlas Console
# Security > Network Access > IP Access List
```

---

### Phase 3: Autonomous Spec-to-Code Agent Execution

#### Option A: Run Locally (Antigravity SDK + Gemini 3.8 Flash)
```bash
cd agent
pip install -r requirements.txt

python agent_runner.py \
  --model gemini-3.8-flash \
  --project hrzn-agentic-framework-1 \
  --location global
```

The agent runs co-located with `mcp_mongo_server.py`, which exposes four tools directly matching the out-of-the-box MongoDB Atlas MCP server endpoints:
* `atlas_vector_search`: 1024-dimension cosine similarity search over `score_db.requirements`.
* `atlas_get_document`: Full document and metadata retrieval by ID.
* `atlas_find`: Direct MQL query filtering.
* `atlas_aggregate`: Multi-stage aggregation pipelines.

#### Option B: Run on GKE via Argo Workflows
Deploy the Argo WorkflowTemplate:
```bash
cd argo-workflows
kubectl apply -f templates/automotive-rag-workflow.yaml -n workflows
```

**Submit via CLI:**
```bash
argo submit --from wftmpl/automotive-rag-spec-to-code \
  -n workflows \
  --watch
```

**Submit via Web UI (Port-Forwarding Tunnel):**
1. Open a local port-forwarding tunnel to the Argo server:
   ```bash
   kubectl port-forward -n workflows svc/argo-server 2746:2746
   ```
2. Open the Argo Workflows UI in your browser:
   [http://localhost:2746/workflows/workflows](http://localhost:2746/workflows/workflows)
3. Click **+ SUBMIT NEW WORKFLOW** in the top navigation bar.
4. Select **`automotive-rag-spec-to-code`** from the template dropdown (parameters are pre-filled with validated production defaults).
5. Click **Submit** to trigger the execution and inspect real-time DAG steps, container logs, and generated artifacts.

---

## Verified Real-Life Deliverables

The agent ingests the unhardened `timed_command_queue.h` and generates production-ready deliverables saved in `output/score_enhanced/` (and automatically archived to GCS under `runs/<timestamp>_<workflow_id>/` when running on GKE):

1. **Standards Delta Analysis (`delta_analysis.md`)**: Dedicated engineering review detailing baseline standard deviations against ISO 26262-6 Clause 7.4.5 (dynamic memory), ASPICE SWE.1 / ISO 26262 Part 4 Clause 6.4.3 (unhandled saturation), and ISO 26262 Part 6 Clause 8.4.4 (deadlock hazards), with a side-by-side comparison matrix and rationale for safety auditors.
2. **ASPICE SWE.1 (Requirements Specification)**: Formal Sphinx-Needs specification (`requirements.rst`) defining `REQ_SCORE_TCQ_001` through `006` covering bounded buffer limits, drop-oldest overflow policy, overflow callback notifications, and thread-safety invariants.
3. **ASPICE SWE.3 (Software Detailed Design)**: 323 lines of MISRA-compliant C++ (`timed_command_queue.h`) featuring zero dynamic heap allocation in operational mode, circular buffer storage, and `noexcept` specifications on critical execution paths.
4. **ASPICE SWE.4 (Unit Verification Suite)**: 545 lines of GoogleTest suite (`timed_command_queue_enhanced_test.cpp`) testing buffer boundaries, concurrency stress, and timeout edge cases, with explicit requirement traceability tags on every test case.
5. **Audit Trace**: Complete OpenTelemetry trace (`agent_trace_score_timed_queue.json` or `trace.json`) capturing tool calls, execution timings, and token metrics.

---

## Architecture & Design Documentation

For an architectural breakdown and sequence flow of the multi-tier agent system, refer to [**`docs/architecture.md`**](docs/architecture.md).

