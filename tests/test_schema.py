"""Tests for triage_kit.core.schema — dynamic response schemas compiled from rubrics."""

import pytest

from tests.conftest import ANALYZE_RUBRIC, CHECK_RUBRIC


class TestBuildAnalyzeResponseSchema:
    def test_schema_has_trial_name_summary_checks(self):
        from triage_kit.core.rubric import load_rubric
        from triage_kit.core.schema import build_analyze_response_schema

        rubric = load_rubric(ANALYZE_RUBRIC)
        schema = build_analyze_response_schema(rubric)

        sample = {
            "trial_name": "some-trial",
            "summary": "Agent solved the task.",
            "checks": {
                "reward_hacking": {"outcome": "pass", "explanation": "legit"},
                "task_specification": {"outcome": "pass", "explanation": "clear"},
            },
        }
        parsed = schema.model_validate(sample)
        assert parsed.trial_name == "some-trial"
        assert parsed.checks.reward_hacking.outcome == "pass"

    def test_schema_rejects_invalid_outcome(self):
        from triage_kit.core.rubric import load_rubric
        from triage_kit.core.schema import build_analyze_response_schema

        rubric = load_rubric(ANALYZE_RUBRIC)
        schema = build_analyze_response_schema(rubric)

        bad = {
            "trial_name": "t",
            "summary": "s",
            "checks": {
                "reward_hacking": {"outcome": "bogus", "explanation": "x"},
                "task_specification": {"outcome": "pass", "explanation": "x"},
            },
        }
        with pytest.raises(Exception):
            schema.model_validate(bad)

    def test_schema_rejects_missing_criterion(self):
        from triage_kit.core.rubric import load_rubric
        from triage_kit.core.schema import build_analyze_response_schema

        rubric = load_rubric(ANALYZE_RUBRIC)
        schema = build_analyze_response_schema(rubric)

        incomplete = {
            "trial_name": "t",
            "summary": "s",
            "checks": {
                "reward_hacking": {"outcome": "pass", "explanation": "x"},
            },
        }
        with pytest.raises(Exception):
            schema.model_validate(incomplete)


class TestToJsonSchemaDict:
    """M5a: the coercion shared by both harnesses (#B) gets direct tests."""

    def test_pydantic_model_is_converted(self):
        from pydantic import BaseModel

        from triage_kit.core.schema import to_json_schema_dict

        class Mini(BaseModel):
            x: int

        schema = to_json_schema_dict(Mini)
        assert schema["properties"]["x"]["type"] == "integer"

    def test_plain_dict_passes_through(self):
        from triage_kit.core.schema import to_json_schema_dict

        plain = {"type": "object", "properties": {}}
        assert to_json_schema_dict(plain) == plain


class TestBuildCheckResponseSchema:
    def test_schema_has_checks_for_all_11_criteria(self):
        from triage_kit.core.rubric import load_rubric
        from triage_kit.core.schema import build_check_response_schema

        rubric = load_rubric(CHECK_RUBRIC)
        schema = build_check_response_schema(rubric)

        checks = {
            c.name: {"outcome": "not_applicable", "explanation": "n/a"}
            for c in rubric.criteria
        }
        parsed = schema.model_validate({"checks": checks})
        assert len(parsed.checks.model_dump()) == 11
        assert parsed.checks.typos.outcome == "not_applicable"

    def test_schema_follows_rubric_dynamically(self, tmp_path):
        """A 1-criterion rubric must produce a 1-field checks model."""
        from triage_kit.core.rubric import load_rubric
        from triage_kit.core.schema import build_check_response_schema

        rubric_file = tmp_path / "mini.toml"
        rubric_file.write_text(
            '[[criteria]]\nname = "my_check"\ndescription = "d"\nguidance = "g"\n',
            encoding="utf-8",
        )
        rubric = load_rubric(rubric_file)
        schema = build_check_response_schema(rubric)

        parsed = schema.model_validate(
            {"checks": {"my_check": {"outcome": "fail", "explanation": "why"}}}
        )
        assert parsed.checks.my_check.outcome == "fail"
