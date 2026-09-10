from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ingestion.main import (
    DEFAULT_SOURCE_PATH,
    _write_local,
    attach_embeddings,
    build_documents,
    parse_aspice_rst,
    serialize_outputs,
)


REPOSITORY_ROOT = Path(__file__).parents[1]
SOURCE_FILE = REPOSITORY_ROOT / "score_knowledge_base_dataset" / DEFAULT_SOURCE_PATH


class AspiceIngestionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_text = SOURCE_FILE.read_text(encoding="utf-8")
        cls.parsed = parse_aspice_rst(cls.source_text)
        cls.source_hash = hashlib.sha256(cls.source_text.encode()).hexdigest()

    def test_parser_preserves_process_structure(self) -> None:
        self.assertEqual(self.parsed.process_area, "SWE.1")
        self.assertEqual(
            self.parsed.process_name, "Software Requirements Analysis"
        )
        self.assertEqual(len(self.parsed.chunks), 8)
        self.assertEqual(
            [chunk.chunk_type for chunk in self.parsed.chunks[:2]],
            ["process_overview", "process_outcomes"],
        )

        practices = self.parsed.chunks[2:]
        self.assertEqual(
            [chunk.base_practice for chunk in practices],
            [f"SWE.1.BP{number}" for number in range(1, 7)],
        )
        self.assertEqual(
            practices[0].need_id, "std_req__aspice_40__SWE-1-BP1"
        )
        self.assertIn("ISO IEEE 29148", practices[0].content)
        self.assertEqual(practices[0].version, 1)

    def test_documents_are_stable_and_mongodb_ready(self) -> None:
        documents, embedding_inputs = build_documents(
            self.parsed,
            DEFAULT_SOURCE_PATH,
            f"file:///{DEFAULT_SOURCE_PATH}",
            self.source_hash,
        )
        repeated_documents, _ = build_documents(
            self.parsed,
            DEFAULT_SOURCE_PATH,
            f"file:///{DEFAULT_SOURCE_PATH}",
            self.source_hash,
        )

        self.assertEqual(
            [document["_id"] for document in documents],
            [document["_id"] for document in repeated_documents],
        )
        self.assertEqual(len(embedding_inputs), len(documents))
        self.assertEqual(documents[2]["base_practice"], "SWE.1.BP1")
        self.assertEqual(documents[2]["domain"], "score_process")
        self.assertNotIn("embedding", documents[2])

        dimensions = attach_embeddings(
            documents, [[0.1, 0.2, 0.3] for _ in documents], "test-model"
        )
        self.assertEqual(dimensions, 3)
        self.assertEqual(
            documents[2]["embedding"],
            {
                "model": "test-model",
                "dimensions": 3,
                "vector": [0.1, 0.2, 0.3],
            },
        )

        output = serialize_outputs(
            documents,
            DEFAULT_SOURCE_PATH,
            f"file:///{DEFAULT_SOURCE_PATH}",
            self.source_hash,
            "test-model",
            dimensions,
        )
        self.assertEqual(len(output), 2)
        self.assertIn("_manifest.json", output)
        self.assertIn("insert.json", output)
        insert_documents = json.loads(output["insert.json"])
        self.assertEqual(len(insert_documents), 8)
        self.assertEqual(insert_documents[2]["base_practice"], "SWE.1.BP1")
        manifest = json.loads(output["_manifest.json"])
        self.assertEqual(manifest["insert_file"], "insert.json")
        self.assertEqual(manifest["document_count"], 8)

    def test_local_regeneration_replaces_stale_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_root = Path(temporary_directory) / "generated"
            destination = Path(
                _write_local(output_root, {"old.json": b"old"})
            )
            self.assertTrue((destination / "old.json").exists())

            _write_local(output_root, {"new.json": b"new"})
            self.assertFalse((destination / "old.json").exists())
            self.assertEqual((destination / "new.json").read_bytes(), b"new")


if __name__ == "__main__":
    unittest.main()
