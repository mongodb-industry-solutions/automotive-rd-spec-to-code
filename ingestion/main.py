"""Ingest one S-CORE ASPICE RST file into embedding-enriched JSON documents."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

DEFAULT_SOURCE_PATH = (
    "01_eclipse_score/process_description/process/standards/"
    "aspice_40/swe/swe.1.rst"
)
DEFAULT_VOYAGE_MODEL = "voyage-3.5"
SCHEMA_VERSION = "1.0"

LOGGER = logging.getLogger("score-kb-ingestion")

HEADING_UNDERLINE = re.compile(r"^([=\-~^\"'`:+*#<>_])\1{2,}\s*$")
DIRECTIVE = re.compile(
    r"^\.\.\s+(?P<type>[\w-]+)::\s*(?P<title>.+?)\s*$"
)
OPTION = re.compile(r"^\s+:(?P<name>[\w+-]+):\s*(?P<value>.*?)\s*$")
BASE_PRACTICE = re.compile(r"\b(SWE\.\d+\.BP\d+)\b", re.IGNORECASE)
PROCESS_AREA = re.compile(r"^(SWE\.\d+)\s+(.+)$", re.IGNORECASE)


@dataclass
class Chunk:
    """A retrieval unit extracted from a source document."""

    key: str
    title: str
    chunk_type: str
    content: str
    directive_type: str | None = None
    base_practice: str | None = None
    need_id: str | None = None
    status: str | None = None
    version: int | str | None = None
    links: list[str] = field(default_factory=list)


@dataclass
class ParsedDocument:
    """Structured representation of the supported ASPICE RST source."""

    title: str
    process_area: str
    process_name: str
    tags: list[str]
    chunks: list[Chunk]


def _find_heading(lines: Sequence[str], start: int = 0) -> tuple[int, str]:
    for index in range(start, len(lines) - 1):
        title = lines[index].strip()
        underline = lines[index + 1].strip()
        if title and HEADING_UNDERLINE.match(underline):
            return index, title
    raise ValueError("No RST heading found")


def _section_bounds(
    lines: Sequence[str], title: str, start: int = 0
) -> tuple[int, int]:
    for index in range(start, len(lines) - 1):
        if (
            lines[index].strip().casefold() == title.casefold()
            and HEADING_UNDERLINE.match(lines[index + 1].strip())
        ):
            content_start = index + 2
            for candidate in range(content_start, len(lines) - 1):
                if (
                    lines[candidate].strip()
                    and HEADING_UNDERLINE.match(lines[candidate + 1].strip())
                ):
                    return content_start, candidate
            return content_start, len(lines)
    raise ValueError(f"Required RST section not found: {title}")


def _trimmed_block(lines: Sequence[str]) -> str:
    start = 0
    end = len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return "\n".join(lines[start:end]).rstrip() + "\n"


def _split_links(value: str) -> list[str]:
    return [link.strip() for link in value.split(",") if link.strip()]


def parse_aspice_rst(text: str) -> ParsedDocument:
    """Parse an ASPICE SWE process page into process and base-practice chunks."""

    lines = text.splitlines()
    title_index, title = _find_heading(lines)
    process_match = PROCESS_AREA.match(title)
    if not process_match:
        raise ValueError(f"Unsupported ASPICE process title: {title}")

    process_area = process_match.group(1).upper()
    process_name = process_match.group(2).strip()
    outcomes_start, outcomes_end = _section_bounds(lines, "Process outcomes")
    practices_start, _ = _section_bounds(lines, "Base practices", outcomes_end)

    overview = _trimmed_block(lines[title_index + 2 : outcomes_start - 2])
    outcomes = _trimmed_block(lines[outcomes_start:outcomes_end])
    chunks = [
        Chunk(
            key="process-overview",
            title=f"{process_area} purpose",
            chunk_type="process_overview",
            content=overview,
        ),
        Chunk(
            key="process-outcomes",
            title=f"{process_area} process outcomes",
            chunk_type="process_outcomes",
            content=outcomes,
        ),
    ]

    directive_starts: list[int] = []
    for index in range(practices_start, len(lines)):
        match = DIRECTIVE.match(lines[index])
        if match and match.group("type") == "std_req":
            directive_starts.append(index)

    for directive_index, start in enumerate(directive_starts):
        end = (
            directive_starts[directive_index + 1]
            if directive_index + 1 < len(directive_starts)
            else len(lines)
        )
        for index in range(start + 1, end):
            if lines[index].startswith(".. needextend::"):
                end = index
                break

        directive_match = DIRECTIVE.match(lines[start])
        if directive_match is None:  # pragma: no cover - guarded above
            continue
        directive_title = directive_match.group("title")
        bp_match = BASE_PRACTICE.search(directive_title)
        if not bp_match:
            raise ValueError(
                f"Base practice ID missing from directive: {directive_title}"
            )
        base_practice = bp_match.group(1).upper()

        options: dict[str, str] = {}
        for line in lines[start + 1 : end]:
            option_match = OPTION.match(line)
            if option_match:
                options[option_match.group("name")] = option_match.group("value")

        version: int | str | None = options.get("version")
        if isinstance(version, str) and version.isdigit():
            version = int(version)

        chunks.append(
            Chunk(
                key=base_practice.lower().replace(".", "-"),
                title=directive_title,
                chunk_type="base_practice",
                content=_trimmed_block(lines[start:end]),
                directive_type=directive_match.group("type"),
                base_practice=base_practice,
                need_id=options.get("id"),
                status=options.get("status"),
                version=version,
                links=_split_links(options.get("links", "")),
            )
        )

    if len(chunks) == 2:
        raise ValueError("No std_req base-practice directives found")

    return ParsedDocument(
        title=title,
        process_area=process_area,
        process_name=process_name,
        tags=[f"aspice40_{process_area.lower().replace('.', '')}"],
        chunks=chunks,
    )


def _stable_id(source_path: str, chunk_key: str) -> str:
    identity = f"{source_path}#{chunk_key}".encode()
    return f"score_process_{hashlib.sha256(identity).hexdigest()[:24]}"


def _embedding_text(parsed: ParsedDocument, chunk: Chunk) -> str:
    return (
        f"Standard: Automotive SPICE 4.0\n"
        f"Process: {parsed.title}\n"
        f"Section: {chunk.title}\n\n"
        f"{chunk.content}"
    )


def build_documents(
    parsed: ParsedDocument,
    source_path: str,
    source_uri: str,
    source_sha256: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build MongoDB-ready documents and the text that should be embedded."""

    documents: list[dict[str, Any]] = []
    embedding_inputs: list[str] = []
    hierarchy = list(PurePosixPath(source_path).parts[:-1])

    for index, chunk in enumerate(parsed.chunks):
        document: dict[str, Any] = {
            "_id": _stable_id(source_path, chunk.key),
            "schema_version": SCHEMA_VERSION,
            "collection": "score_process_docs",
            "domain": "score_process",
            "source_system": "eclipse_score",
            "source_path": source_path,
            "source_uri": source_uri,
            "source_sha256": source_sha256,
            "source_format": "rst",
            "hierarchy": hierarchy,
            "standard": "Automotive SPICE 4.0",
            "process_area": parsed.process_area,
            "process_name": parsed.process_name,
            "artifact_type": "aspice_process_definition",
            "chunk_type": chunk.chunk_type,
            "chunk_index": index,
            "title": chunk.title,
            "content": chunk.content,
            "directive_type": chunk.directive_type,
            "base_practice": chunk.base_practice,
            "need_id": chunk.need_id,
            "status": chunk.status,
            "version": chunk.version,
            "links": chunk.links,
            "tags": parsed.tags,
        }
        documents.append(document)
        embedding_inputs.append(_embedding_text(parsed, chunk))

    return documents, embedding_inputs


def embed_texts(
    texts: Sequence[str], api_key: str, model: str
) -> list[list[float]]:
    """Generate document embeddings with Voyage AI."""

    try:
        import voyageai
    except ImportError as exc:  # pragma: no cover - dependency failure
        raise RuntimeError(
            "voyageai is not installed; run `make install` first"
        ) from exc

    client = voyageai.Client(api_key=api_key)
    response = client.embed(list(texts), model=model, input_type="document")
    embeddings = response.embeddings
    if len(embeddings) != len(texts):
        raise RuntimeError(
            f"Voyage returned {len(embeddings)} embeddings for {len(texts)} inputs"
        )
    return embeddings


def attach_embeddings(
    documents: list[dict[str, Any]],
    embeddings: Sequence[Sequence[float]],
    model: str,
) -> int:
    """Attach vectors and return their common dimensionality."""

    if len(documents) != len(embeddings):
        raise ValueError("Document and embedding counts do not match")
    dimensions = len(embeddings[0]) if embeddings else 0
    if dimensions == 0 or any(len(vector) != dimensions for vector in embeddings):
        raise ValueError("Embeddings must be non-empty and have equal dimensions")

    for document, vector in zip(documents, embeddings, strict=True):
        document["embedding"] = {
            "model": model,
            "dimensions": dimensions,
            "vector": list(vector),
        }
    return dimensions


def serialize_outputs(
    documents: Sequence[dict[str, Any]],
    source_path: str,
    source_uri: str,
    source_sha256: str,
    model: str,
    dimensions: int,
) -> dict[str, bytes]:
    """Serialize one MongoDB insert array and its generation manifest."""

    output = {
        "insert.json": (
            json.dumps(list(documents), indent=2, ensure_ascii=False) + "\n"
        ).encode()
    }
    manifest_documents: list[dict[str, Any]] = []
    for document in documents:
        manifest_documents.append(
            {
                "_id": str(document["_id"]),
                "title": str(document["title"]),
                "chunk_index": int(document["chunk_index"]),
            }
        )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_path": source_path,
        "source_uri": source_uri,
        "source_sha256": source_sha256,
        "embedding": {
            "model": model,
            "dimensions": dimensions,
        },
        "insert_file": "insert.json",
        "document_count": len(documents),
        "documents": manifest_documents,
    }
    output["_manifest.json"] = (
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    ).encode()
    return output


def _validate_relative_path(path: str, name: str) -> str:
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"{name} must be a safe relative POSIX path: {path}")
    normalized = str(candidate).strip("/")
    if not normalized or normalized == ".":
        raise ValueError(f"{name} cannot be empty")
    return normalized


def _read_local(local_root: Path, source_path: str) -> tuple[str, str]:
    source_file = (local_root / Path(*PurePosixPath(source_path).parts)).resolve()
    root = local_root.resolve()
    if root not in source_file.parents:
        raise ValueError("Source path escapes the local dataset root")
    return source_file.read_text(encoding="utf-8"), source_file.as_uri()


def _write_local(local_output_root: Path, outputs: dict[str, bytes]) -> str:
    destination = local_output_root.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent)
    )
    try:
        for filename, content in outputs.items():
            (temporary / filename).write_bytes(content)
        if destination.exists():
            shutil.rmtree(destination)
        temporary.replace(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return str(destination)


def _read_gcs(bucket_name: str, source_path: str) -> tuple[str, str]:
    try:
        from google.cloud import storage
    except ImportError as exc:  # pragma: no cover - dependency failure
        raise RuntimeError(
            "google-cloud-storage is not installed; run `make install` first"
        ) from exc

    client = storage.Client()
    blob = client.bucket(bucket_name).blob(source_path)
    return blob.download_as_text(encoding="utf-8"), f"gs://{bucket_name}/{source_path}"


def _write_gcs(
    bucket_name: str,
    output_prefix: str,
    outputs: dict[str, bytes],
) -> str:
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    object_dir = output_prefix.rstrip("/")
    desired_objects = {f"{object_dir}/{filename}" for filename in outputs}
    existing_objects = {
        blob.name for blob in client.list_blobs(bucket, prefix=f"{object_dir}/")
    }

    # Upload the insert file, remove stale output, and publish the manifest last.
    for filename, content in sorted(outputs.items()):
        if filename == "_manifest.json":
            continue
        bucket.blob(f"{object_dir}/{filename}").upload_from_string(
            content, content_type="application/json"
        )

    stale_objects = existing_objects - desired_objects
    for object_name in stale_objects:
        bucket.blob(object_name).delete()

    bucket.blob(f"{object_dir}/_manifest.json").upload_from_string(
        outputs["_manifest.json"], content_type="application/json"
    )

    return f"gs://{bucket_name}/{object_dir}/"


def run(args: argparse.Namespace) -> str:
    source_path = _validate_relative_path(args.source_path, "source path")
    output_prefix = _validate_relative_path(args.output_prefix, "output prefix")

    if args.mode == "local":
        text, source_uri = _read_local(Path(args.local_root), source_path)
    else:
        if not args.gcs_bucket:
            raise ValueError("GCS_BUCKET or --gcs-bucket is required in gcs mode")
        text, source_uri = _read_gcs(args.gcs_bucket, source_path)

    source_sha256 = hashlib.sha256(text.encode()).hexdigest()
    parsed = parse_aspice_rst(text)
    documents, embedding_inputs = build_documents(
        parsed, source_path, source_uri, source_sha256
    )
    embeddings = embed_texts(
        embedding_inputs, api_key=args.voyage_api_key, model=args.voyage_model
    )
    dimensions = attach_embeddings(documents, embeddings, args.voyage_model)
    outputs = serialize_outputs(
        documents,
        source_path,
        source_uri,
        source_sha256,
        args.voyage_model,
        dimensions,
    )

    if args.mode == "local":
        destination = _write_local(Path(args.local_output_root), outputs)
    else:
        destination = _write_gcs(args.gcs_bucket, output_prefix, outputs)

    LOGGER.info(
        "Generated %d documents (%d dimensions) at %s",
        len(documents),
        dimensions,
        destination,
    )
    return destination


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest one S-CORE ASPICE RST file"
    )
    parser.add_argument(
        "--mode",
        choices=("local", "gcs"),
        default=os.getenv("INGESTION_MODE", "local"),
    )
    parser.add_argument(
        "--source-path",
        default=os.getenv("SOURCE_PATH", DEFAULT_SOURCE_PATH),
    )
    parser.add_argument(
        "--local-root",
        default=os.getenv("LOCAL_ROOT", "score_knowledge_base_dataset"),
    )
    parser.add_argument(
        "--local-output-root",
        default=os.getenv(
            "LOCAL_OUTPUT_ROOT", "score_knowledge_base_dataset/generated"
        ),
    )
    parser.add_argument("--gcs-bucket", default=os.getenv("GCS_BUCKET"))
    parser.add_argument(
        "--output-prefix", default=os.getenv("OUTPUT_PREFIX", "generated")
    )
    parser.add_argument(
        "--voyage-model",
        default=os.getenv("VOYAGE_MODEL", DEFAULT_VOYAGE_MODEL),
    )
    parser.add_argument(
        "--voyage-api-key", default=os.getenv("VOYAGE_API_KEY")
    )
    args = parser.parse_args(argv)
    if not args.voyage_api_key:
        parser.error("VOYAGE_API_KEY or --voyage-api-key is required")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        run(parse_args(argv))
    except Exception:
        LOGGER.exception("Ingestion failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
