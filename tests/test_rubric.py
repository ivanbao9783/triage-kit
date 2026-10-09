"""Tests for triage_kit.core.rubric — loaded against the real repo assets."""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
CHECK_RUBRIC = REPO_ROOT / "assets" / "check" / "rubrics" / "check-default.toml"
ANALYZE_RUBRIC = REPO_ROOT / "assets" / "analyze" / "analyze-rubric.toml"


class TestCheckOutcome:
    def test_has_three_values(self):
        from triage_kit.core.rubric import CheckOutcome

        assert CheckOutcome.PASS.value == "pass"
        assert CheckOutcome.FAIL.value == "fail"
        assert CheckOutcome.NOT_APPLICABLE.value == "not_applicable"


class TestLoadRubric:
    def test_loads_check_default_with_11_criteria(self):
        from triage_kit.core.rubric import load_rubric

        rubric = load_rubric(CHECK_RUBRIC)

        assert len(rubric.criteria) == 11
        assert rubric.criteria[0].name == "behavior_in_task_description"
        # every criterion carries description and guidance
        for c in rubric.criteria:
            assert c.description
            assert c.guidance

    def test_loads_analyze_rubric_with_2_criteria(self):
        from triage_kit.core.rubric import load_rubric

        rubric = load_rubric(ANALYZE_RUBRIC)

        assert [c.name for c in rubric.criteria] == [
            "reward_hacking",
            "task_specification",
        ]

    def test_rejects_unknown_extension(self):
        from triage_kit.core.rubric import load_rubric

        with pytest.raises(ValueError, match="unsupported"):
            load_rubric(Path("rubric.txt"))

    def test_rejects_missing_criteria(self, tmp_path):
        from triage_kit.core.rubric import load_rubric

        empty = tmp_path / "empty.toml"
        empty.write_text('other = "x"\n', encoding="utf-8")

        with pytest.raises(ValueError, match="criteria"):
            load_rubric(empty)


class TestBuildCriteriaGuidance:
    def test_guidance_contains_all_criteria(self):
        from triage_kit.core.rubric import build_criteria_guidance, load_rubric

        rubric = load_rubric(ANALYZE_RUBRIC)
        guidance = build_criteria_guidance(rubric)

        assert "reward_hacking" in guidance
        assert "task_specification" in guidance
        # description and guidance text of each criterion are included
        assert "reward hacking" in guidance
        assert "sufficient for an agent to succeed" in guidance
