# Automotive Spec-to-Code: Argo Workflows on GKE

This directory contains the Kubernetes orchestration manifests to deploy and execute the Automotive Spec-to-Code Agent as an Argo Workflow on Google Kubernetes Engine (GKE).

---

## Architecture Overview

```
                      +------------------------------------------+
                      |         Argo Workflows Controller        |
                      +--------------------+---------------------+
                                           | triggers
                                           v
                             +---------------------------+
                             |  Agent Runtime Pod (GKE)  |
                             |  • Antigravity SDK        |
                             |  • Gemini 3.8 Flash       |
                             |  • FastMCP Mongo Server   |
                             +------+-------------+------+
                                    |             |
                   stdio Tool Calls |             | Vector Queries
                                    v             v
                    +-------------------+     +---------------------+
                    | MCP MongoDB Stdio |     | MongoDB Atlas       |
                    | Local Subprocess  |     | score_db.requirements|
                    +-------------------+     +---------------------+
```

---

## Prerequisites

1. **GKE Cluster** with Argo Workflows installed in namespace `workflows`.
2. **Kubernetes Secret** configured in the `workflows` namespace:
   ```bash
   kubectl create secret generic mongodb-credentials \
     --from-literal=MONGO_URI="<YOUR_MONGODB_URI>" \
     --from-literal=MONGO_DB="score_db" \
     --from-literal=MONGO_COLLECTION="requirements" \
     --from-literal=VOYAGE_API_KEY="<YOUR_VOYAGE_API_KEY>" \
     --from-literal=VOYAGE_MODEL="voyage-3.5" \
     -n workflows
   ```
3. **MongoDB Atlas IP Access List (Mandatory Prerequisite)**:
   Add the GKE Cloud NAT external egress IP (`34.179.208.3/32` or static NAT IP `34.185.148.118/32`) to MongoDB Atlas Console under **Security** > **Network Access** > **IP Access List**. Local fallbacks are disabled; live MongoDB Atlas connectivity is required for ASPICE RAG tools (`atlas_vector_search`, `atlas_get_document`, `atlas_find`).

---

## Deployment & Execution

### 1. Apply the Workflow Template
```bash
kubectl apply -f templates/automotive-rag-workflow.yaml -n workflows
```

### 2. Submit a Workflow Run
```bash
argo submit --from wftmpl/automotive-rag-spec-to-code \
  -n workflows \
  --watch
```

### 3. Access Argo Workflows Web UI & Submit from Browser
Open a port-forwarding tunnel to the Argo server:
```bash
kubectl port-forward -n workflows svc/argo-server 2746:2746
```

Open [http://localhost:2746/workflows/workflows](http://localhost:2746/workflows/workflows) in your browser:
* **To submit a run from the UI**: Click **+ SUBMIT NEW WORKFLOW**, select **`automotive-rag-spec-to-code`** from the dropdown, review the pre-populated parameters, and click **Submit**.
* **To monitor progress**: Inspect real-time DAG execution steps, container stdout/stderr logs, and download generated ASPICE artifacts directly from the web interface.

---

## Artifact Archiving in GCS

Upon completion, each workflow automatically archives all generated deliverables into a timestamped directory in Google Cloud Storage:
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

* **`trace.json`**: End-to-end execution telemetry.
* **`delta_analysis.md`**: Human-readable delta analysis and standards deviation review.
* **`assessment.md`**: Autonomous reasoning report and ASPICE traceability.
* **`code/`**: Source files (`timed_command_queue.h`, `timed_command_queue_enhanced_test.cpp`, `requirements.rst`).


