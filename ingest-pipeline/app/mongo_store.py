from __future__ import annotations

from typing import Any, Dict

from pymongo import MongoClient


def upsert_document(document: Dict[str, Any], mongo_uri: str, db_name: str, collection_name: str) -> None:
    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db[collection_name]
    collection.update_one({"_id": document["_id"]}, {"$set": document}, upsert=True)
