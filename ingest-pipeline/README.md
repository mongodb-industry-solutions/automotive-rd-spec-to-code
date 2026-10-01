# Ingest Pipeline

Ingest Pipeline is a Python batch application that reads requirement and specification files, normalizes them into MongoDB documents, creates Voyage AI embeddings, and stores the documents in MongoDB Atlas for vector search.

## Pipeline

```text
Input files -> parser -> normalized document -> Voyage embedding -> MongoDB Atlas
```

The application scans a source directory recursively. Each supported source file becomes one MongoDB document. Re-running the same source performs an upsert using a stable `_id`, so it updates existing documents instead of creating duplicates.

## Supported files

| Extension | Processing                                                                                             |
| --------- | ------------------------------------------------------------------------------------------------------ |
| `.rst`    | Extracts reStructuredText directives, titles, IDs, status, version, descriptions, notes, and metadata. |
| `.trlc`   | Groups requirement-style lines and following detail lines.                                             |
| `.md`     | Stores the first 200 lines as content.                                                                 |
| `.puml`   | Stores the complete PlantUML source as content.                                                        |

The bundled test data is under `sample_data/automotive-rd-spec-to-code-main/` and includes the ASPICE directory:

```text
sample_data/automotive-rd-spec-to-code-main/score_knowledge_base_dataset/01_eclipse_score/process_description/process/standards/aspice_40/swe/
```

## Requirements

- Python 3.12 or newer
- A MongoDB deployment, preferably MongoDB Atlas for Vector Search
- A Voyage AI API key for embeddings
- Docker is optional
- Google Cloud CLI is required only for Cloud Run deployment

## Local setup

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your own credentials. Do not paste secrets into GitHub or commit `.env`:

```env
MONGO_URI=mongodb+srv://USERNAME:PASSWORD@CLUSTER.mongodb.net/?retryWrites=true&w=majority&appName=Cluster1
MONGO_DB=score_db
MONGO_COLLECTION=requirements
VOYAGE_API_KEY=your_voyage_api_key
VOYAGE_MODEL=voyage-3.5
```

If the password contains characters such as `@`, `:`, `/`, `?`, or `#`, URL-encode them. For example, `@` becomes `%40`.

`VOYAGE_API_KEY` is optional for parser-only tests. When it is configured, the pipeline sends each document's content to Voyage AI and adds `embedding` and `embedding_model` fields.

## Test without MongoDB

This parses all bundled files and creates a local JSON export. No MongoDB or Voyage API key is required:

```bash
.venv/bin/python main.py \
  --source-dir sample_data \
  --json-output output/ingested_documents.json
```

To parse without writing JSON:

```bash
.venv/bin/python main.py --source-dir sample_data --dry-run
```

The generated output is ignored by Git. The bundled dataset currently produces 163 documents.

## Ingest into MongoDB Atlas

First confirm that:

1. The Atlas database user exists and has `readWrite` permission on `score_db`.
2. Your current IP address is allowed in Atlas Network Access.
3. The URI in `.env` uses the Atlas Database Access username and password.
4. `VOYAGE_API_KEY` is set if embeddings are required.

Run the live ingestion:

```bash
.venv/bin/python main.py --source-dir sample_data
```

The target is:

```text
Database:   score_db
Collection: requirements
```

A successful run prints messages similar to:

```text
Generated 163 embeddings with ... dimensions using voyage-3.5
Inserted to Mongo: score_db.requirements -> <document-id>
```

Without `VOYAGE_API_KEY`, the pipeline still parses and writes documents, but it does not create embeddings.

## MongoDB document structure

The normalized document has the following shape:

```json
{
  "_id": "score_process:...:v1",
  "domain": "score_process",
  "process_area": "SWE.1",
  "aspice_bp_mapping": ["SWE.1.BP1", "SWE.1.BP2"],
  "artifact_type": "sphinx_needs_template",
  "title": "Specify software requirements",
  "content": "normalized requirement text",
  "source_file": ".../swe/swe.1.rst",
  "source_format": "rst",
  "metadata": {
    "section": "requirements",
    "page": 1,
    "tags": [],
    "requirements": []
  },
  "embedding": [0.012, -0.043, 0.891],
  "embedding_model": "voyage-3.5"
}
```

For an ASPICE RST document, `metadata.requirements` contains the parsed requirement records, including `directive`, `code`, `title`, `external_id`, `status`, `version`, `description`, `notes`, and source metadata.

## Query the data in Atlas

### Find all documents

In Atlas Data Explorer, select the `score_db` database and `requirements` collection, then run:

```javascript
db.requirements.find({});
```

### Count documents

```javascript
db.requirements.countDocuments();
```

### Find SWE.1 documents

```javascript
db.requirements.find(
  { process_area: "SWE.1" },
  { title: 1, source_file: 1, aspice_bp_mapping: 1 },
);
```

### Find a specific base practice

```javascript
db.requirements.find({
  aspice_bp_mapping: "SWE.1.BP1",
});
```

### Find valid requirements

```javascript
db.requirements.find({
  "metadata.requirements.status": "valid",
});
```

### Search by source format

```javascript
db.requirements.find({
  source_format: "rst",
});
```

### Search text with a regular expression

```javascript
db.requirements.find({
  content: { $regex: "software requirements", $options: "i" },
});
```

## Atlas Vector Search

Create a Vector Search index on the `requirements` collection after documents with embeddings have been inserted. Use `embedding` as the vector field and use the dimension returned by the Voyage model. All vectors in one index must have the same dimensions.

Example index definition for a Voyage model returning 1024 dimensions:

```json
{
  "fields": [
    {
      "type": "vector",
      "path": "embedding",
      "numDimensions": 1024,
      "similarity": "cosine"
    },
    {
      "type": "filter",
      "path": "process_area"
    },
    {
      "type": "filter",
      "path": "source_format"
    }
  ]
}
```

In Atlas, create this from **Search & Vector Search** for the `requirements` collection. Name the index `requirements_vector_index`.

Run a vector query from `mongosh` after replacing the placeholder vector with a query embedding generated by the same Voyage model:

```javascript
db.requirements.aggregate([
  {
    $vectorSearch: {
      index: "requirements_vector_index",
      path: "embedding",
      queryVector: [0.012, -0.043, 0.891],
      numCandidates: 100,
      limit: 5,
    },
  },
  {
    $project: {
      _id: 1,
      title: 1,
      process_area: 1,
      source_file: 1,
      score: { $meta: "vectorSearchScore" },
    },
  },
]);
```

The example vector is illustrative. A real query vector must come from Voyage AI and must have exactly the same dimensions as the stored vectors.

## Command-line options

```text
--source-dir PATH       Directory to scan recursively
--mongo-uri URI         MongoDB connection string
--database NAME         MongoDB database name
--collection NAME       MongoDB collection name
--voyage-api-key KEY    Voyage AI API key
--voyage-model MODEL    Voyage AI embedding model
--dry-run               Parse without writing to MongoDB
--json-output PATH      Write documents to JSON instead of MongoDB
```

View all options:

```bash
.venv/bin/python main.py --help
```

## Docker

Build and run locally if Docker is available:

```bash
docker build -t ingest-pipeline .
docker run --rm \
  -e MONGO_URI='mongodb+srv://USERNAME:PASSWORD@CLUSTER.mongodb.net/?retryWrites=true&w=majority&appName=Cluster1' \
  -e MONGO_DB=score_db \
  -e MONGO_COLLECTION=requirements \
  -e VOYAGE_API_KEY='your_voyage_api_key' \
  -e VOYAGE_MODEL='voyage-3.5' \
  ingest-pipeline
```

Docker is not required for GCP deployment because Cloud Build can build the image remotely.

## Google Cloud Run Job

Cloud Run Jobs are appropriate because ingestion is a finite batch operation. The image includes the bundled `sample_data/` directory.

From the repository root, set variables:

```bash
export PROJECT_ID='your-gcp-project-id'
export REGION='europe-west1'
export REPOSITORY='ingest-pipeline'
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ingest-pipeline:latest"
export JOB_NAME='ingest-pipeline'
export RUNTIME_SERVICE_ACCOUNT="ingest-pipeline@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud config set project "$PROJECT_ID"
```

Enable APIs:

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com
```

Create the Artifact Registry repository and service account. Skip commands for resources that already exist:

```bash
gcloud artifacts repositories create "$REPOSITORY" \
  --repository-format=docker \
  --location="$REGION"

gcloud iam service-accounts create ingest-pipeline \
  --display-name='Ingest Pipeline Cloud Run Job'
```

Store the MongoDB URI and Voyage API key in Secret Manager:

```bash
set_secret() {
  local name="$1" prompt="$2" val
  printf '%s' "$prompt" && read -r val
  if gcloud secrets describe "$name" >/dev/null 2>&1; then
    printf '%s' "$val" | gcloud secrets versions add "$name" --data-file=-
  else
    printf '%s' "$val" | gcloud secrets create "$name" --data-file=- --replication-policy='automatic'
  fi
}

set_secret mongo-uri 'Enter MongoDB URI: '
set_secret voyage-api-key 'Enter Voyage API Key: '
unset -f set_secret
```

Grant access:

```bash
# Grant Secret Manager access to the runtime service account
gcloud secrets add-iam-policy-binding mongo-uri \
  --member="serviceAccount:${RUNTIME_SERVICE_ACCOUNT}" \
  --role='roles/secretmanager.secretAccessor'
gcloud secrets add-iam-policy-binding voyage-api-key \
  --member="serviceAccount:${RUNTIME_SERVICE_ACCOUNT}" \
  --role='roles/secretmanager.secretAccessor'

# Grant Cloud Build service account permissions to read source, write logs, and push to Artifact Registry
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${COMPUTE_SA}" \
  --role='roles/storage.objectViewer'
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${COMPUTE_SA}" \
  --role='roles/logging.logWriter'
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${COMPUTE_SA}" \
  --role='roles/artifactregistry.writer'
```

Build remotely and deploy:

```bash
# 1. Build and push image via Cloud Build
gcloud builds submit . --tag="$IMAGE"

# 2. Deploy Cloud Run Job
gcloud run jobs deploy "$JOB_NAME" \
  --image="$IMAGE" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --service-account="$RUNTIME_SERVICE_ACCOUNT" \
  --set-env-vars='MONGO_DB=score_db,MONGO_COLLECTION=requirements,VOYAGE_MODEL=voyage-3.5' \
  --set-secrets='MONGO_URI=mongo-uri:latest,VOYAGE_API_KEY=voyage-api-key:latest' \
  --tasks=1 --max-retries=1 --task-timeout=15m \
  --memory=1Gi --cpu=1
```

Execute and inspect:

```bash
gcloud run jobs execute "$JOB_NAME" \
  --region="$REGION" --project="$PROJECT_ID" --wait

gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="ingest-pipeline"' \
  --project="$PROJECT_ID" --limit=50 --format='value(textPayload)'
```

## Troubleshooting

- `localhost:27017 connection refused`: `.env` is missing or `MONGO_URI` was not loaded.
- `Authentication failed`: verify the Atlas Database Access username/password and URL-encode special password characters.
- `ServerSelectionTimeoutError`: check Atlas Network Access and the current IP allowlist.
- `voyageai is required`: activate `.venv` and run `python -m pip install -r requirements.txt`.
- `Source directory not found`: run from the repository root or pass an absolute `--source-dir`.
- GCP `403`: check IAM permissions and Secret Manager access for the Cloud Run service account.

## Tests

Run the parser/CLI checks with:

```bash
.venv/bin/python main.py --help
.venv/bin/python main.py --source-dir sample_data --json-output output/ingested_documents.json
```

The JSON export does not write to MongoDB and is the safest first test.
