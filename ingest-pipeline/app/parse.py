from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List


SUPPORTED_EXTENSIONS = {".trlc", ".rst", ".md", ".puml"}


def detect_format(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".trlc", ".rst", ".md", ".puml"}:
        return suffix.lstrip(".")
    return "unknown"


def read_text(path: str | Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def parse_version(value: Any) -> Any:
    if value is None or value == "":
        return 1
    try:
        numeric_value = float(str(value))
    except (TypeError, ValueError):
        return value
    return int(numeric_value) if numeric_value.is_integer() else numeric_value


def parse_trlc(text: str, source_path: str) -> Dict[str, Any]:
    lines = text.splitlines()
    requirement_blocks: List[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("requirement") or stripped.startswith("req"):
            if current:
                requirement_blocks.append(current)
            current = {"raw": stripped, "title": stripped}
            continue

        if current is not None:
            current.setdefault("details", []).append(stripped)

    if current:
        requirement_blocks.append(current)

    return {
        "item_type": "trlc_requirement",
        "source_file": source_path,
        "requirements": requirement_blocks,
    }


def parse_rst(text: str, source_path: str) -> Dict[str, Any]:
    blocks: List[Dict[str, Any]] = []
    lines = text.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]
        match = re.match(r"^\.\.\s+(?P<directive>[A-Za-z0-9_]+)::\s*(?P<title>.*)$", line)
        if not match:
            i += 1
            continue

        directive = match.group("directive")
        title = match.group("title").strip()
        i += 1

        metadata: Dict[str, Any] = {}
        body_lines: List[str] = []
        notes: List[str] = []
        in_note_block = False
        current_note: List[str] = []

        while i < len(lines):
            current = lines[i]

            if re.match(r"^\.\.\s+[A-Za-z0-9_]+::", current):
                break

            if re.match(r"^\s*:\w+:\s*", current):
                key, _, value = current.strip()[1:].partition(":")
                metadata[key.strip()] = value.strip()
                i += 1
                continue

            if re.match(r"^\s*\.\.\s+note::", current) or re.match(r"^\s*\.\.\s+attention::", current):
                in_note_block = True
                current_note = []
                i += 1
                continue

            if in_note_block:
                if current.strip() == "":
                    if current_note:
                        notes.append(" ".join(current_note).strip())
                        current_note = []
                    i += 1
                    continue

                if current.startswith("   ") or current.startswith("      ") or current.startswith("\t"):
                    current_note.append(current.strip())
                    i += 1
                    continue

                notes.append(" ".join(current_note).strip())
                current_note = []
                in_note_block = False

            if current.strip():
                body_lines.append(current.strip())
            i += 1

        if current_note:
            notes.append(" ".join(current_note).strip())

        description = " ".join(body_lines).strip()

        if ":" in title and directive.lower() in {"std_req", "comp_req", "aou_req"}:
            code, _, title_value = title.partition(":")
            code_value = code.strip()
            final_title = title_value.strip() if title_value.strip() else code_value
        else:
            code_value = title.strip() if title.strip() else directive
            final_title = title.strip() if title.strip() else directive

        blocks.append(
            {
                "directive": directive,
                "code": code_value,
                "title": final_title,
                "external_id": metadata.get("id"),
                "status": metadata.get("status", "unknown"),
                "version": parse_version(metadata.get("version")),
                "description": description,
                "notes": notes,
                "metadata": metadata,
            }
        )

    return {
        "item_type": "rst_requirement",
        "source_file": source_path,
        "requirements": blocks,
    }


def parse_markdown(text: str, source_path: str) -> Dict[str, Any]:
    lines = text.splitlines()
    return {
        "item_type": "markdown_document",
        "source_file": source_path,
        "requirements": [{
            "title": Path(source_path).stem,
            "description": "\n".join(lines[:200]).strip(),
            "metadata": {"format": "markdown"},
        }],
    }


def parse_puml(text: str, source_path: str) -> Dict[str, Any]:
    return {
        "item_type": "puml_diagram",
        "source_file": source_path,
        "requirements": [{
            "title": Path(source_path).stem,
            "description": text.strip(),
            "metadata": {"format": "puml"},
        }],
    }


def parse_file(path: str | Path) -> Dict[str, Any]:
    path = str(path)
    text = read_text(path)
    fmt = detect_format(path)

    if fmt == "trlc":
        return parse_trlc(text, path)
    if fmt == "rst":
        return parse_rst(text, path)
    if fmt == "md":
        return parse_markdown(text, path)
    if fmt == "puml":
        return parse_puml(text, path)

    return {
        "item_type": "unknown",
        "source_file": path,
        "requirements": [{
            "title": Path(path).stem,
            "description": text.strip(),
            "metadata": {"format": fmt},
        }],
    }
