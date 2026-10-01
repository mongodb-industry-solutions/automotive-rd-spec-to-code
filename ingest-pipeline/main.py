from __future__ import annotations

import argparse
import os
from pathlib import Path

from app.config import settings
from app.ingest import ingest_directory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ingest-pipeline", description="Read requirement/spec source files and push normalized documents to MongoDB or JSON.")
    parser.add_argument("--source-dir", type=str, default="sample_data", help="Directory containing spec files to ingest")
    parser.add_argument("--mongo-uri", type=str, default=settings.mongo_uri, help="MongoDB URI")
    parser.add_argument("--database", type=str, default=settings.mongo_db, help="MongoDB database name")
    parser.add_argument("--collection", type=str, default=settings.mongo_collection, help="MongoDB collection name")
    parser.add_argument("--voyage-api-key", type=str, default=settings.voyage_api_key, help="Voyage AI API key for embeddings")
    parser.add_argument("--voyage-model", type=str, default=settings.voyage_model, help="Voyage AI embedding model")
    parser.add_argument("--dry-run", action="store_true", help="Parse files without inserting to MongoDB")
    parser.add_argument("--json-output", type=str, default=None, help="Write normalized documents to a JSON file instead of MongoDB")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_dir = Path(args.source_dir)
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    ingest_directory(
        source_dir=source_dir,
        mongo_uri=args.mongo_uri,
        db_name=args.database,
        collection_name=args.collection,
        dry_run=args.dry_run or bool(args.json_output),
        json_output_path=args.json_output,
        voyage_api_key=args.voyage_api_key,
        voyage_model=args.voyage_model,
    )


if __name__ == "__main__":
    main()
