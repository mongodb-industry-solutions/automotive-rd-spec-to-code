# S-CORE knowledge-base ingestion

This first ingestion slice reads only:

`01_eclipse_score/process_description/process/standards/aspice_40/swe/swe.1.rst`

It parses the process purpose, outcomes, and each `std_req` base practice into
separate MongoDB-ready JSON documents. All documents receive Voyage AI
embeddings in a nested `embedding` object.

The cloud deployment is a **Cloud Run Job**, not an HTTP Cloud Run service. A
Job is a better fit for an on-demand batch operation: it has an explicit
success/failure result, can run longer than an HTTP request, and does not leave
an idle endpoint.

## Output layout

Generated output is flat:

```text
generated/
├── _manifest.json
└── insert.json
```

`insert.json` is a JSON array containing all MongoDB documents. The source
hierarchy remains available through each document's `source_path` and
`hierarchy` fields. Regeneration replaces the generated files, and the manifest
is uploaded last so it represents a complete output set.

Each JSON document includes:

- source path, URI, SHA-256, format, and directory hierarchy;
- MongoDB collection and domain metadata;
- ASPICE standard, process area, chunk type, and base-practice metadata;
- parsed Sphinx-Needs fields such as directive type, need ID, status, version,
  links, and tags;
- original RST content;
- embedding model, dimensions, and vector.

### Sample document

The following illustrates one element of `insert.json`. The content is
shortened and the vector uses three illustrative dimensions; generated
documents contain the complete values and report the model's actual dimensions.

```json
{
  "_id": "score_process_ab84804f3b358b31618c9e61",
  "schema_version": "1.0",
  "collection": "score_process_docs",
  "domain": "score_process",
  "source_system": "eclipse_score",
  "source_path": "01_eclipse_score/process_description/process/standards/aspice_40/swe/swe.1.rst",
  "source_uri": "gs://hrzn-score-knowledge-base/01_eclipse_score/process_description/process/standards/aspice_40/swe/swe.1.rst",
  "source_sha256": "735054fc4528406f135fdf86550eb0b53accb6f1327de5fd00ce534164a64de5",
  "source_format": "rst",
  "hierarchy": [
    "01_eclipse_score",
    "process_description",
    "process",
    "standards",
    "aspice_40",
    "swe"
  ],
  "standard": "Automotive SPICE 4.0",
  "process_area": "SWE.1",
  "process_name": "Software Requirements Analysis",
  "artifact_type": "aspice_process_definition",
  "chunk_type": "base_practice",
  "chunk_index": 2,
  "title": "SWE.1.BP1: Specify software requirements",
  "content": ".. std_req:: SWE.1.BP1: Specify software requirements\n   :id: std_req__aspice_40__SWE-1-BP1\n   ...",
  "directive_type": "std_req",
  "base_practice": "SWE.1.BP1",
  "need_id": "std_req__aspice_40__SWE-1-BP1",
  "status": "valid",
  "version": 1,
  "links": [
    "std_req__aspice_40__iic-17-00[version==1]"
  ],
  "tags": [
    "aspice40_swe1"
  ],
  "embedding": {
    "model": "voyage-3.5",
    "dimensions": 3,
    "vector": [
      0.012,
      -0.043,
      0.891
    ]
  }
}
```

## Run locally

Python 3.11 or later and
[uv](https://docs.astral.sh/uv/getting-started/installation/) are required.
Dependencies are declared in `pyproject.toml` and locked in `uv.lock`.

```bash
uv sync --frozen
cp .env.example .env
# Edit .env and set VOYAGE_API_KEY.
make local
```

The Makefile loads `.env` automatically. The file is excluded from Git,
Docker, and Cloud Build contexts so the API key is not copied into the image.

The generated files are written under
`score_knowledge_base_dataset/generated/`. Change `LOCAL_OUTPUT_ROOT` in
`.env` to use a different location.

Parser and schema tests do not call Voyage AI:

```bash
make test
```

## Deploy and execute on Google Cloud

The Makefile assumes the resources configured in `.env` already exist:

- the Cloud Storage bucket;
- the Artifact Registry repository used by `IMAGE`;
- the Cloud Run service account, with access to the bucket;
- the Secret Manager secret containing `VOYAGE_API_KEY`, with access granted
  to the service account.

Authenticate `gcloud`, then run:

```bash
make upload-source
make deploy
make run
```

Inspect recent execution logs with `make logs`. Change deployment settings in
`.env`, not in the Makefile.
