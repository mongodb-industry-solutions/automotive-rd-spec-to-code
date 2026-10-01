from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

from .normalize import normalize_document
from .mongo_store import upsert_document
from .parse import parse_file


def embed_documents(documents: List[dict], api_key: str, model: str) -> int:
    if not api_key:
        return 0

    try:
        import voyageai
    except ImportError as exc:
        raise RuntimeError("voyageai is required when VOYAGE_API_KEY is configured") from exc

    texts = [document["content"] or document["title"] for document in documents]
    client = voyageai.Client(api_key=api_key)
    response = client.embed(texts, model=model, input_type="document")
    if len(response.embeddings) != len(documents):
        raise RuntimeError("Voyage AI returned a different number of embeddings than documents")

    for document, vector in zip(documents, response.embeddings, strict=True):
        document["embedding"] = list(vector)
        document["embedding_model"] = model
    return len(response.embeddings[0]) if response.embeddings else 0


def iter_source_files(root: str | Path) -> Iterable[Path]:
    root_path = Path(root)
    for path in sorted(root_path.rglob("*")):
        if path.is_file() and path.suffix.lower().lstrip(".") in {"trlc", "rst", "md", "puml"}:
            yield path


def ingest_directory(
    source_dir: str | Path,
    mongo_uri: str,
    db_name: str,
    collection_name: str,
    dry_run: bool = False,
    json_output_path: str | None = None,
    voyage_api_key: str = "",
    voyage_model: str = "voyage-3.5",
) -> None:
    documents: List[dict] = []

    for file_path in iter_source_files(source_dir):
        parsed = parse_file(file_path)
        doc = normalize_document(str(file_path), parsed)
        documents.append(doc)

    embedding_dimensions = embed_documents(documents, voyage_api_key, voyage_model)
    if embedding_dimensions:
        print(f"Generated {len(documents)} embeddings with {embedding_dimensions} dimensions using {voyage_model}")

    for doc in documents:
        print(f"Parsed: {doc['source_file']} -> {doc['_id']}")
        if not dry_run and json_output_path is None:
            upsert_document(doc, mongo_uri, db_name, collection_name)
            print(f"Inserted to Mongo: {db_name}.{collection_name} -> {doc['_id']}")

    if json_output_path:
        output_path = Path(json_output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(documents, f, indent=2, ensure_ascii=False)
        print(f"JSON export written to: {output_path}")
