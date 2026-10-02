#!/usr/bin/env python3
"""MongoDB Atlas Stdio MCP Server for Automotive Spec-to-Code RAG.

Provides Model Context Protocol (MCP) tool bindings to:
- MongoDB Atlas Vector Search (using Voyage AI embeddings)
- Direct MQL query primitives (atlas_find, atlas_get_document, atlas_aggregate)
over standard I/O (stdio). Strictly queries MongoDB Atlas live.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional
from pathlib import Path

# Load environment variables if available (.env or .env.local)
env_paths = [
    Path(__file__).resolve().parent / ".env.local",
    Path(__file__).resolve().parent / ".env",
    Path(__file__).resolve().parent.parent / ".env.local",
    Path(__file__).resolve().parent.parent / ".env",
    Path(__file__).resolve().parent.parent / "ingest-pipeline" / ".env",
    Path.cwd() / ".env.local",
    Path.cwd() / ".env",
]
for ep in env_paths:
    if ep.exists():
        with open(ep) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() not in os.environ:
                        os.environ[k.strip()] = v.strip().strip("\"'")

from mcp.server.fastmcp import FastMCP
from pymongo import MongoClient
import voyageai

try:
    import certifi
    HAS_CERTIFI = True
except ImportError:
    HAS_CERTIFI = False

# Initialize FastMCP Server
mcp = FastMCP(
    name="mongodb-atlas",
    instructions=(
        "MongoDB Atlas tools for querying Eclipse S-CORE specifications, ASPICE standards, "
        "and automotive C++ guidelines. Use atlas_vector_search to find semantically relevant "
        "requirements, architectural designs, safety analysis, and coding policies. "
        "Use atlas_get_document, atlas_find, or atlas_aggregate to retrieve full specs."
    ),
)

# Configuration
MONGO_URI = os.environ.get("MONGO_URI", "")
MONGO_DB = os.environ.get("MONGO_DB", "score_db")
MONGO_COLLECTION = os.environ.get("MONGO_COLLECTION", "requirements")
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY", "")
VOYAGE_MODEL = os.environ.get("VOYAGE_MODEL", "voyage-3.5")
VECTOR_INDEX_NAME = os.environ.get("VECTOR_INDEX_NAME", "requirements_vector_index")

# Lazy clients
_mongo_client: Optional[MongoClient] = None
_voyage_client: Optional[voyageai.Client] = None


def get_mongo_collection(collection_name: str = MONGO_COLLECTION):
    global _mongo_client
    if _mongo_client is None:
        if not MONGO_URI:
            raise ValueError("MONGO_URI environment variable is required")
        client_kwargs: Dict[str, Any] = {
            "serverSelectionTimeoutMS": 10000,
            "connectTimeoutMS": 10000,
            "socketTimeoutMS": 20000,
        }
        if HAS_CERTIFI:
            client_kwargs["tlsCAFile"] = certifi.where()
        _mongo_client = MongoClient(MONGO_URI, **client_kwargs)
    return _mongo_client[MONGO_DB][collection_name]


def get_voyage_client() -> voyageai.Client:
    global _voyage_client
    if _voyage_client is None:
        if not VOYAGE_API_KEY:
            raise ValueError("VOYAGE_API_KEY environment variable is required")
        _voyage_client = voyageai.Client(api_key=VOYAGE_API_KEY)
    return _voyage_client


def embed_query(text: str) -> List[float]:
    """Generates 1024-dimension embedding for vector search using Voyage AI."""
    client = get_voyage_client()
    result = client.embed([text], model=VOYAGE_MODEL, input_type="query")
    return result.embeddings[0]


@mcp.tool()
def atlas_vector_search(
    query: str,
    limit: int = 5,
    process_area: Optional[str] = None,
    num_candidates: int = 50,
) -> str:
    """Performs semantic vector search over Eclipse S-CORE specifications in MongoDB Atlas.

    Args:
        query: Natural language query (e.g. 'thread safety queue overflow ASIL-B requirements')
        limit: Number of matching documents to return (default 5, max 20)
        process_area: Optional filter by ASPICE/S-CORE process area (e.g. 'requirements_engineering', 'implementation', 'verification')
        num_candidates: Vector search candidates to examine (default 50)

    Returns:
        JSON string of matched documents with relevance scores and metadata.
    """
    sys.stderr.write(f"\n🍃 [MongoDB Atlas Stdio] atlas_vector_search called:\n")
    sys.stderr.write(f"   • Query: \"{query}\"\n")
    sys.stderr.write(f"   • Parameters: limit={limit}, process_area={process_area}\n")
    sys.stderr.flush()

    col = get_mongo_collection()
    query_vector = embed_query(query)

    vector_stage: Dict[str, Any] = {
        "index": VECTOR_INDEX_NAME,
        "path": "embedding",
        "queryVector": query_vector,
        "numCandidates": max(num_candidates, limit * 5),
        "limit": min(limit, 20),
    }

    if process_area:
        vector_stage["filter"] = {"process_area": {"$eq": process_area}}

    pipeline: List[Dict[str, Any]] = [
        {"$vectorSearch": vector_stage},
        {
            "$project": {
                "_id": {"$toString": "$_id"},
                "doc_id": 1,
                "title": 1,
                "process_area": 1,
                "section": 1,
                "need_type": 1,
                "file_path": 1,
                "chunk_index": 1,
                "text": 1,
                "relevance_score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    results = list(col.aggregate(pipeline))

    sys.stderr.write(f"🍃 [MongoDB Atlas Stdio] Found {len(results)} matching document(s) from {MONGO_DB}.{MONGO_COLLECTION}:\n")
    for idx, r in enumerate(results[:3], 1):
        score = r.get("relevance_score", 0.0)
        doc_id = r.get("doc_id") or r.get("_id")
        title = r.get("title", "")
        text_snip = r.get("text", "").replace("\n", " ").strip()[:110]
        sys.stderr.write(f"   [{idx}] ID: {doc_id} (Score: {score:.4f}) | {title}\n")
        sys.stderr.write(f"       \"{text_snip}...\"\n")
    if len(results) > 3:
        sys.stderr.write(f"   ... ({len(results) - 3} more documents)\n")
    sys.stderr.flush()

    formatted = []
    for r in results:
        text_preview = r.get("text", "")
        if len(text_preview) > 1200:
            text_preview = text_preview[:1200] + "... [truncated]"
        formatted.append({
            "doc_id": r.get("doc_id") or str(r.get("_id", "")),
            "title": r.get("title", ""),
            "process_area": r.get("process_area", ""),
            "section": r.get("section", ""),
            "need_type": r.get("need_type", ""),
            "file_path": r.get("file_path", ""),
            "relevance_score": round(float(r.get("relevance_score", 0.0)), 4),
            "text": text_preview,
        })

    return json.dumps(formatted, indent=2)


@mcp.tool()
def atlas_get_document(doc_id: str, collection: str = MONGO_COLLECTION) -> str:
    """Retrieves full document content and metadata by ID or doc_id from MongoDB Atlas.

    Args:
        doc_id: The document identifier or ObjectId string.
        collection: The collection name (default: score_db requirements).

    Returns:
        JSON string of the document or error message.
    """
    sys.stderr.write(f"\n🍃 [MongoDB Atlas Stdio] atlas_get_document called: doc_id={doc_id}, collection={collection}\n")
    sys.stderr.flush()

    col = get_mongo_collection(collection)
    from bson import ObjectId

    doc = None
    try:
        doc = col.find_one({"_id": ObjectId(doc_id)})
    except Exception:
        pass

    if doc is None:
        doc = col.find_one({"_id": doc_id})

    if doc is None:
        doc = col.find_one({"doc_id": doc_id})

    if doc is None:
        sys.stderr.write(f"   ↳ [MongoDB Atlas Stdio] Document NOT found for id: {doc_id}\n")
        sys.stderr.flush()
        return json.dumps({"error": f"Document not found for id: {doc_id}"})

    doc["_id"] = str(doc["_id"])
    if "embedding" in doc:
        del doc["embedding"]

    title = doc.get("title", "")
    sys.stderr.write(f"   ↳ [MongoDB Atlas Stdio] Successfully retrieved document: {doc_id} | {title}\n")
    sys.stderr.flush()

    return json.dumps(doc, indent=2, default=str)


@mcp.tool()
def atlas_find(
    filter_json: str = "{}",
    limit: int = 5,
    projection_fields: Optional[List[str]] = None,
    collection: str = MONGO_COLLECTION,
) -> str:
    """Executes a MongoDB MQL find query against the Eclipse S-CORE collection.

    Args:
        filter_json: JSON string representing MongoDB filter query (e.g. '{"process_area": "implementation"}')
        limit: Max documents to return (default 5, max 20)
        projection_fields: Optional list of fields to include (e.g. ['title', 'process_area', 'file_path'])
        collection: The collection name (default: score_db requirements).

    Returns:
        JSON string of matching documents.
    """
    sys.stderr.write(f"\n🍃 [MongoDB Atlas Stdio] atlas_find called: filter={filter_json}, limit={limit}\n")
    sys.stderr.flush()

    try:
        filter_dict = json.loads(filter_json)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"   ↳ [MongoDB Atlas Stdio] Invalid filter JSON: {e}\n")
        sys.stderr.flush()
        return json.dumps({"error": f"Invalid filter JSON: {e}"})

    col = get_mongo_collection(collection)
    projection: Optional[Dict[str, int]] = None
    if projection_fields:
        projection = {f: 1 for f in projection_fields}
        projection["_id"] = 1
        projection["embedding"] = 0
    else:
        projection = {"embedding": 0}

    cursor = col.find(filter_dict, projection=projection).limit(min(limit, 20))
    results = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)

    sys.stderr.write(f"   ↳ [MongoDB Atlas Stdio] atlas_find matched {len(results)} document(s)\n")
    sys.stderr.flush()

    return json.dumps(results, indent=2, default=str)


@mcp.tool()
def atlas_aggregate(pipeline_json: str, collection: str = MONGO_COLLECTION) -> str:
    """Executes a custom MongoDB aggregation pipeline against Atlas.

    Args:
        pipeline_json: JSON string representing an array of pipeline stages.
        collection: Target collection name (default: score_db requirements).

    Returns:
        JSON string of the aggregation output.
    """
    sys.stderr.write(f"\n🍃 [MongoDB Atlas Stdio] atlas_aggregate called with pipeline:\n   {pipeline_json[:150]}...\n")
    sys.stderr.flush()

    try:
        pipeline = json.loads(pipeline_json)
        if not isinstance(pipeline, list):
            return json.dumps({"error": "pipeline_json must be a JSON array of stages"})
    except json.JSONDecodeError as e:
        sys.stderr.write(f"   ↳ [MongoDB Atlas Stdio] Invalid pipeline JSON: {e}\n")
        sys.stderr.flush()
        return json.dumps({"error": f"Invalid pipeline JSON: {e}"})

    col = get_mongo_collection(collection)
    cursor = col.aggregate(pipeline)
    results = []
    for doc in cursor:
        if "_id" in doc:
            doc["_id"] = str(doc["_id"])
        if "embedding" in doc:
            del doc["embedding"]
        results.append(doc)

    sys.stderr.write(f"   ↳ [MongoDB Atlas Stdio] atlas_aggregate produced {len(results)} result document(s)\n")
    sys.stderr.flush()

    return json.dumps(results, indent=2, default=str)


if __name__ == "__main__":
    mcp.run()
