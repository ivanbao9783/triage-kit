"""Rubric data model: judgment criteria as data.

Rubrics are pure data (TOML/YAML/JSON). Output schemas and prompt guidance
are compiled from them at runtime (see schema.py), so adding evaluation
dimensions requires zero code changes.
"""

import hashlib
import json
import tomllib
from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class CheckOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"


class QualityCheck(BaseModel):
    outcome: CheckOutcome
    explanation: str


class RubricCriterion(BaseModel):
    name: str
    description: str
    guidance: str


class Rubric(BaseModel):
    criteria: list[RubricCriterion] = Field(min_length=1)
    # Content hash of the source file (set by load_rubric). Products embed
    # it in their sidecar so cached results are only reused under the same
    # judgment identity (rubric content + model).
    source_sha256: str | None = None


def load_rubric(path: Path) -> Rubric:
    """Load a rubric from a TOML/YAML/JSON file."""
    path = Path(path)
    if path.suffix.lower() not in {".toml", ".yaml", ".yml", ".json"}:
        raise ValueError(f"unsupported rubric file type: {path.suffix!r}")
    raw = path.read_bytes()
    match path.suffix.lower():
        case ".toml":
            data = tomllib.loads(raw.decode("utf-8"))
        case ".yaml" | ".yml":
            data = yaml.safe_load(raw.decode("utf-8"))
        case ".json":
            data = json.loads(raw.decode("utf-8"))
        case _:
            raise ValueError(f"unsupported rubric file type: {path.suffix!r}")

    criteria = data.get("criteria")
    if not criteria:
        raise ValueError(f"rubric {path} defines no [[criteria]]")
    return Rubric.model_validate({
        "criteria": criteria,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
    })


def build_criteria_guidance(rubric: Rubric) -> str:
    """Render rubric criteria into the {criteria_guidance} prompt section."""
    sections = []
    for c in rubric.criteria:
        sections.append(f"### {c.name}\n\n{c.description}\n\n{c.guidance}")
    return "\n\n".join(sections)
