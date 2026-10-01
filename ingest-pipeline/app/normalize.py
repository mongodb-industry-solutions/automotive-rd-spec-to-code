from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Dict, List


PROCESS_AREA_PATTERN = re.compile(r"\b([A-Z]+\.\d+)\b", re.IGNORECASE)
BASE_PRACTICE_PATTERN = re.compile(r"\b([A-Z]+\.\d+\.BP\d+)\b", re.IGNORECASE)


def _process_area(requirements: List[Dict[str, Any]], source_path: str) -> str | None:
    for requirement in requirements:
        match = PROCESS_AREA_PATTERN.search(str(requirement.get("code", "")))
        if match:
            return match.group(1).upper()
    match = PROCESS_AREA_PATTERN.search(source_path)
    return match.group(1).upper() if match else None


def _base_practice_mapping(requirements: List[Dict[str, Any]]) -> List[str]:
    mapping: List[str] = []
    for requirement in requirements:
        match = BASE_PRACTICE_PATTERN.search(str(requirement.get("code", "")))
        if match:
            value = match.group(1).upper()
            if value not in mapping:
                mapping.append(value)
    return mapping


def _artifact_type(source_format: str) -> str:
    return {
        "rst": "sphinx_needs_template",
        "trlc": "trlc_requirement_source",
        "md": "markdown_specification",
        "puml": "plantuml_diagram",
    }.get(source_format, "specification_source")


def _content(requirements: List[Dict[str, Any]]) -> str:
    sections: List[str] = []
    for requirement in requirements:
        title = requirement.get("title") or requirement.get("code") or ""
        description = requirement.get("description", "")
        details = requirement.get("details", [])
        notes = requirement.get("notes", [])
        text = "\n".join(str(item) for item in [description, *details, *notes] if item)
        sections.append(f"{title}\n{text}".strip())
    return "\n\n".join(sections).strip()


def normalize_document(source_path: str, parsed: Dict[str, Any]) -> Dict[str, Any]:
    requirements = list(parsed.get("requirements", []))
    source_format = Path(source_path).suffix.lower().lstrip(".")
    return {
        "_id": "score_process:" + str(Path(source_path)).replace("/", ":").replace(".", "_") + ":v1",
        "domain": "score_process",
        "process_area": _process_area(requirements, source_path),
        "aspice_bp_mapping": _base_practice_mapping(requirements),
        "artifact_type": _artifact_type(source_format),
        "title": next(
            (str(requirement.get("title")) for requirement in requirements if requirement.get("title")),
            Path(source_path).stem,
        ),
        "content": _content(requirements),
        "source_file": source_path,
        "source_format": source_format,
        "metadata": {
            "section": "requirements",
            "page": 1,
            "tags": [],
            "requirements": requirements,
        },
    }
