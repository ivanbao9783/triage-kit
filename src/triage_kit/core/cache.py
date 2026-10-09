"""Shared cache/product persistence for the analyze & check workflows.

Both workflows follow the same protocol around their JSON products:

- reuse: a cached product is only reusable when its identity sidecar
  (rubric sha + model) matches the current run, and the cached JSON
  still passes the live response schema
- persist: product JSON (indent=2) + identity sidecar, so later runs
  can apply the same reuse rules
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def resolve_cache(
    *,
    cached_path: Path,
    sidecar_path: Path,
    force: bool,
    identity: dict,
    schema,
) -> dict | None:
    """Three-state resolution of a cached product.

    Returns the validated cached dict on a hit; None on a miss (no cache,
    forced rerun, or legacy product without a sidecar). Raises ValueError
    when the sidecar identity does not match the current run — the error
    message points at the --force remedy.
    """
    if not cached_path.is_file() or force:
        return None
    if not sidecar_path.is_file():
        logger.warning(
            "%s exists without %s in %s (legacy product); "
            "treating as a cache miss and re-running",
            cached_path.name, sidecar_path.name, cached_path.parent,
        )
        return None
    meta = json.loads(sidecar_path.read_text(encoding="utf-8"))
    if meta.get("rubric_sha256") != identity.get("rubric_sha256"):
        raise ValueError(
            f"cached {cached_path.name} in {cached_path.parent} was produced "
            f"with a different rubric (cached sha {meta.get('rubric_sha256')}, "
            f"requested {identity.get('rubric_sha256')}); "
            f"rerun with --force to overwrite"
        )
    if meta.get("model") != identity.get("model"):
        raise ValueError(
            f"cached {cached_path.name} in {cached_path.parent} was produced "
            f"with model {meta.get('model')!r}, "
            f"requested {identity.get('model')!r}; "
            f"rerun with --force to overwrite"
        )
    # Cached products must pass the same response schema as fresh backend
    # responses — a corrupted/hand-edited/half-written file must not flow
    # into job aggregation unchecked.
    return schema.model_validate(
        json.loads(cached_path.read_text(encoding="utf-8"))
    ).model_dump(mode="json")


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
