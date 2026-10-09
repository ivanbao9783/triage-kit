"""Resolve vendored assets (prompts, rubrics) shipped in the repo's assets/ tree."""

from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parents[3] / "assets"


def get_asset(rel_path: str) -> Path:
    """Return the absolute path of an asset file under assets/."""
    path = _ASSETS_DIR / rel_path
    if not path.is_file():
        raise FileNotFoundError(f"asset not found: {path}")
    return path
