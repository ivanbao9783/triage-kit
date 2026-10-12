"""Zero-build FastAPI + Jinja2 SSR app for the viewer.

The server only *reads* products through ``scanner`` and renders HTML:
no bundler, no npm, no write path. Templates ship inside the package
(``viewer/templates/``) and are resolved relative to this file, so both
``pip install -e`` and a built wheel work.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from markdown_it import MarkdownIt
from starlette.requests import Request

from triage_kit.viewer import scanner

HERE = Path(__file__).parent

# 'commonmark' lacks the table/strikethrough rules, but real product
# marksdown (job aggregates) uses pipe tables — enable them explicitly.
_md = MarkdownIt("commonmark", {"linkify": True}).enable(
    ["table", "strikethrough"]
)


def _fmt(value, nd=0):
    if value is None or value == "":
        return "—"
    try:
        return f"{value:,.{nd}f}" if isinstance(value, float) else f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def _secs(value):
    return "—" if value is None else f"{value:.1f}s"


def _templates() -> Jinja2Templates:
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.filters["fmt"] = _fmt
    templates.env.filters["secs"] = _secs
    return templates


def _to_html(text: str | None) -> str | None:
    return _md.render(text) if text else None


def create_app(root: Path) -> FastAPI:
    """Build the viewer app bound to a single trials root / single trial."""
    root = Path(root)
    templates = _templates()
    app = FastAPI(title="triage viewer")

    def render_trial(request: Request, trial_dir: Path):
        if not (trial_dir / "result.json").is_file():
            raise HTTPException(404, f"unknown trial: {trial_dir.name}")
        data = scanner.load_trial(trial_dir)
        data["root"] = root
        data["single"] = trial_dir == root
        data["analysis_md"] = _to_html(data["analysis_md"])
        return templates.TemplateResponse(request, "trial.html", data)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, reward: str | None = None):
        # A single-trial input is served as the trial page directly —
        # there is no trials list to show.
        if scanner.is_single_trial(root):
            return render_trial(request, root)
        if not root.is_dir():
            raise HTTPException(404, f"directory not found: {root}")
        overview = scanner.load_overview(root)
        return templates.TemplateResponse(request, "index.html", {
            "root": root,
            "root_name": root.name,
            "job_md": _to_html(overview["job_md"]),
            "trials": scanner.select_reward(overview["trials"], reward),
            "counts": overview["counts"],
            "reward_sel": reward if reward in ("1", "0") else None,
        })

    @app.get("/trial/{name}", response_class=HTMLResponse)
    def trial(request: Request, name: str):
        # single path segment only — reject any separator or traversal
        if "/" in name or "\\" in name or name in (".", ".."):
            raise HTTPException(404, f"unknown trial: {name}")
        return render_trial(request, root / name)

    return app


def serve(root: Path, *, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the viewer until interrupted (blocking)."""
    import uvicorn

    root = Path(root)
    uvicorn.run(create_app(root), host=host, port=port)