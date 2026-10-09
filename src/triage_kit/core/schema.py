"""Dynamic response schemas: compiled from the rubric.

Same rubric feeds three consumers: prompt guidance, the response schema
handed to the backend as a structured-output contract (via the agent-level
``output_schema`` parameter), and post-hoc validation.

Naming note: "schema" here refers to the *response schema* (a pydantic
class describing the required response shape). It is deliberately never
called "model" to avoid collision with the inference-model name that
flows through the same contract.
"""

from pydantic import BaseModel, create_model

from triage_kit.core.rubric import QualityCheck, Rubric


def _checks_schema(schema_name: str, rubric: Rubric) -> type[BaseModel]:
    """Build a `{<criterion>: QualityCheck}` schema with one field per criterion."""
    fields = {
        c.name: (QualityCheck, ...)
        for c in rubric.criteria
    }
    return create_model(schema_name, **fields)


def build_analyze_response_schema(rubric: Rubric) -> type[BaseModel]:
    """Analyze response schema: trial_name + summary + per-criterion checks."""
    checks = _checks_schema("AnalyzeChecks", rubric)
    return create_model(
        "AnalyzeResponse",
        trial_name=(str, ...),
        summary=(str, ...),
        checks=(checks, ...),
    )


def build_check_response_schema(rubric: Rubric) -> type[BaseModel]:
    """Check response schema: per-criterion checks only."""
    checks = _checks_schema("CheckChecks", rubric)
    return create_model(
        "CheckResponse",
        checks=(checks, ...),
    )
