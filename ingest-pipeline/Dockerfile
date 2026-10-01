FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY main.py README.md .env.example ./
COPY sample_data ./sample_data

RUN useradd --create-home --uid 10001 ingest \
    && mkdir -p /app/output \
    && chown -R ingest:ingest /app

USER ingest

ENTRYPOINT ["python", "main.py"]
CMD ["--source-dir", "sample_data"]