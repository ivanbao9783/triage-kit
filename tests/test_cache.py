"""Tests for core/cache.py — the shared three-state cache resolution.

M5a: the module extracted in round-2 (#A) gets its own contract tests,
so future cache-semantics changes fail here first instead of only
through the Analyzer/Checker consumers.
"""

import hashlib
import json

import pytest

from tests.conftest import ANALYZE_RUBRIC, write_sidecar


def _identity(model="m1", rubric_path=ANALYZE_RUBRIC):
    sha = hashlib.sha256(rubric_path.read_bytes()).hexdigest()
    return {"rubric_sha256": sha, "model": model}


def _schema():
    from triage_kit.core.rubric import load_rubric
    from triage_kit.core.schema import build_analyze_response_schema

    return build_analyze_response_schema(load_rubric(ANALYZE_RUBRIC))


def _valid_payload(trial_name="t__x"):
    return {
        "trial_name": trial_name,
        "summary": "s",
        "checks": {
            "reward_hacking": {"outcome": "pass", "explanation": "x"},
            "task_specification": {"outcome": "pass", "explanation": "x"},
        },
    }


def _resolve(tmp_path, *, force=False, identity=None, payload=None,
             cached_name="analysis.json", sidecar_name="analysis.meta.json"):
    from triage_kit.core.cache import resolve_cache

    if payload is not None:
        (tmp_path / cached_name).write_text(
            json.dumps(payload), encoding="utf-8"
        )
    return resolve_cache(
        cached_path=tmp_path / cached_name,
        sidecar_path=tmp_path / sidecar_name,
        force=force,
        identity=identity if identity is not None else _identity(),
        schema=_schema(),
    )


class TestResolveCache:
    def test_no_cache_file_is_miss(self, tmp_path):
        assert _resolve(tmp_path, payload=None) is None

    def test_force_is_miss_even_with_valid_cache(self, tmp_path):
        write_sidecar(tmp_path, "analysis.meta.json", model="m1",
                      rubric_path=ANALYZE_RUBRIC)
        assert _resolve(tmp_path, force=True, payload=_valid_payload()) is None

    def test_missing_sidecar_is_miss(self, tmp_path):
        """Legacy product without a sidecar: treat as a cache miss."""
        assert _resolve(tmp_path, payload=_valid_payload()) is None

    def test_identity_match_returns_validated_dict(self, tmp_path):
        write_sidecar(tmp_path, "analysis.meta.json", model="m1",
                      rubric_path=ANALYZE_RUBRIC)
        result = _resolve(tmp_path, payload=_valid_payload())
        assert result is not None
        assert result["trial_name"] == "t__x"
        assert result["checks"]["reward_hacking"]["outcome"] == "pass"

    def test_rubric_mismatch_raises_with_force_hint(self, tmp_path):
        write_sidecar(tmp_path, "analysis.meta.json", model="m1",
                      rubric_path=ANALYZE_RUBRIC)
        with pytest.raises(ValueError, match="force"):
            _resolve(tmp_path, payload=_valid_payload(),
                     identity={"rubric_sha256": "other", "model": "m1"})

    def test_model_mismatch_raises_with_force_hint(self, tmp_path):
        write_sidecar(tmp_path, "analysis.meta.json", model="m1",
                      rubric_path=ANALYZE_RUBRIC)
        with pytest.raises(ValueError, match="force"):
            _resolve(tmp_path, payload=_valid_payload(),
                     identity={"rubric_sha256":
                               _identity()["rubric_sha256"],
                               "model": "other"})

    def test_corrupted_cache_fails_schema(self, tmp_path):
        """Corrupted payload with a matching sidecar must not pass through."""
        write_sidecar(tmp_path, "analysis.meta.json", model="m1",
                      rubric_path=ANALYZE_RUBRIC)
        bad = _valid_payload()
        bad["checks"]["reward_hacking"]["outcome"] = "bogus"
        with pytest.raises(Exception):
            _resolve(tmp_path, payload=bad)


class TestWriteJson:
    def test_writes_indented_json(self, tmp_path):
        from triage_kit.core.cache import write_json

        path = tmp_path / "out.json"
        write_json(path, {"a": 1})
        assert path.read_text(encoding="utf-8") == '{\n  "a": 1\n}'
