UV ?= uv
ENV_FILE ?= .env

include $(ENV_FILE)

.PHONY: help install local test clean upload-source deploy run logs

help:
	@echo "make local          Generate JSON from the local dataset"
	@echo "make test           Run parser and schema tests"
	@echo "make upload-source  Upload the single RST source object"
	@echo "make deploy         Build and deploy the Cloud Run Job"
	@echo "make run            Execute the Cloud Run Job and wait"
	@echo "make logs           Read recent Job execution logs"

install:
	$(UV) sync --frozen

local: install
	$(UV) run --frozen --env-file "$(ENV_FILE)" python -m ingestion.main --mode local

test: install
	$(UV) run --frozen python -m unittest discover -s tests -v

clean:
	rm -rf ".venv" "$(LOCAL_OUTPUT_ROOT)"

upload-source:
	gcloud storage cp "$(LOCAL_ROOT)/$(SOURCE_PATH)" \
		"gs://$(BUCKET)/$(SOURCE_PATH)"

deploy:
	gcloud builds submit . --tag="$(IMAGE)" --project="$(PROJECT_ID)"
	gcloud run jobs deploy "$(JOB_NAME)" \
		--image="$(IMAGE)" \
		--region="$(REGION)" \
		--project="$(PROJECT_ID)" \
		--service-account="$(SERVICE_ACCOUNT)" \
		--set-env-vars="INGESTION_MODE=gcs,GCS_BUCKET=$(BUCKET),SOURCE_PATH=$(SOURCE_PATH),OUTPUT_PREFIX=$(OUTPUT_PREFIX),VOYAGE_MODEL=$(VOYAGE_MODEL)" \
		--set-secrets="VOYAGE_API_KEY=$(VOYAGE_SECRET):latest" \
		--cpu=1 \
		--memory=1Gi \
		--task-timeout=15m \
		--max-retries=1

run:
	gcloud run jobs execute "$(JOB_NAME)" \
		--region="$(REGION)" --project="$(PROJECT_ID)" --wait

logs:
	gcloud logging read \
		'resource.type="cloud_run_job" AND resource.labels.job_name="$(JOB_NAME)"' \
		--project="$(PROJECT_ID)" --limit=50 --format="value(textPayload)"
