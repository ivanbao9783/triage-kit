"""Tests for core/assets.py — asset resolution + byte-frozen heritage.

The five vendored files below must stay byte-for-byte identical to their
pier originals (pier viewer compatibility contract). The sha256 snapshot
turns an accidental edit into an explicit test failure instead of a
silent viewer breakage downstream.
"""

import hashlib

import pytest

from tests.conftest import REPO_ROOT

FROZEN_ASSETS = {
    "assets/analyze/analyze.txt":
        "92df8e6cdd01561710b5d02e6147f8facd4b6b2bfb3f2ab1c2bea8c01695aabf",
    "assets/analyze/analyze-rubric.toml":
        "01425d85f806a394def342f3b051735061cdad9808c245eb3c196246cb1a8355",
    "assets/analyze/analyze-job.txt":
        "90fa509c2ff98466a309b6aacfc929dbaf375c8f57c20aa723065a84618ccfc2",
    "assets/check/check.txt":
        "61d152aa1e0885be86ac200dddf7a78e19bf8ab9d3f08a1bad2126c94dd66a34",
    "assets/check/rubrics/check-default.toml":
        "b0f01b9f91bee5eab5d8b1cd9b32797fc93f59e1a9b22d3fcc60aa43902b8e4a",
}


class TestAssetsResolution:
    def test_analyze_template_is_found(self):
        from triage_kit.core.assets import get_asset

        template = get_asset("analyze/analyze.txt")
        assert template.is_file()
        assert "{task_section}" in template.read_text(encoding="utf-8")

    def test_check_template_is_found(self):
        from triage_kit.core.assets import get_asset

        template = get_asset("check/check.txt")
        assert template.is_file()
        assert "{file_tree}" in template.read_text(encoding="utf-8")


class TestByteFrozenAssets:
    @pytest.mark.parametrize(
        "rel_path,expected_sha", sorted(FROZEN_ASSETS.items())
    )
    def test_asset_bytes_are_frozen(self, rel_path, expected_sha):
        data = (REPO_ROOT / rel_path).read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        assert actual == expected_sha, (
            f"{rel_path} differs from the pier original "
            f"(expected {expected_sha}, got {actual}); vendored assets "
            f"must stay byte-for-byte identical for pier viewer "
            f"compatibility"
        )
