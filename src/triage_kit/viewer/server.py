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
from jinja2 import Undefined
from markdown_it import MarkdownIt
from starlette.requests import Request

from triage_kit.viewer import scanner, trajectory

HERE = Path(__file__).parent

# Single-trial tabs, in display order. Server-rendered per request and
# selected by the ``?tab=`` query param, so the viewer stays JS-free.
TABS = ("overview", "score", "trace", "tools", "diagnosis")

# 'commonmark' lacks the table/strikethrough rules, but real product
# markdown (job aggregates) uses pipe tables — enable them explicitly.
_md = MarkdownIt("commonmark", {"linkify": True}).enable(
    ["table", "strikethrough"]
)


def _fmt(value, nd=0):
    # A missing key reaches the filter as Jinja's Undefined; treat it the
    # same as absent so optional CTRF summary keys render as an em dash.
    if isinstance(value, Undefined) or value is None or value == "":
        return "—"
    try:
        return f"{value:,.{nd}f}" if isinstance(value, float) else f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def _secs(value):
    return "—" if isinstance(value, Undefined) or value is None else f"{value:.1f}s"


def _pct(value):
    return "—" if isinstance(value, Undefined) or value is None else f"{value * 100:.1f}%"


def _templates() -> Jinja2Templates:
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.filters["fmt"] = _fmt
    templates.env.filters["secs"] = _secs
    templates.env.filters["pct"] = _pct
    return templates


def _to_html(text: str | None) -> str | None:
    return _md.render(text) if text else None


def create_app(root: Path) -> FastAPI:
    """Build the viewer app bound to a single trials root / single trial."""
    root = Path(root)
    templates = _templates()
    app = FastAPI(title="triage viewer")

    def render_trial(request: Request, trial_dir: Path, tab: str = "overview",
                     step: str | None = None):
        if not (trial_dir / "result.json").is_file():
            raise HTTPException(404, f"unknown trial: {trial_dir.name}")
        single = trial_dir == root
        tab = tab if tab in TABS else "overview"
        data = scanner.load_trial(trial_dir)
        data["root"] = root
        data["analysis_md"] = _to_html(data["analysis_md"])
        data["tab"] = tab
        # the trace tab's token bars deep-link to a step; the value is a
        # raw query string, so it is compared against step_id as text.
        data["step"] = step
        data["base_url"] = "/" if single else f"/trial/{trial_dir.name}"
        # The trajectory is only parsed for the tabs that render it, so
        # the overview stays cheap even on a multi-megabyte trajectory.
        data["trajectory"] = (trajectory.load_trajectory(trial_dir)
                              if tab in ("trace", "tools") else None)
        # Left nav: the sibling trial tree for a job input, or the lone
        # trial itself when the input is a single trial directory.
        data["nav_trials"] = [] if single else scanner.scan_trials(root)
        data["current"] = trial_dir.name
        data["job_name"] = None if single else root.name
        return templates.TemplateResponse(request, "trial.html", data)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, reward: str | None = None,
              tab: str = "overview", step: str | None = None):
        # A single-trial input is served as the trial page directly —
        # there is no trials list to show.
        if scanner.is_single_trial(root):
            return render_trial(request, root, tab, step)
        if not root.is_dir():
            raise HTTPException(404, f"directory not found: {root}")
        overview = scanner.load_overview(root)
        # The table is filtered, but the left rail always lists every
        # trial so the job's full set stays one click away.
        reward_sel = reward if reward in ("1", "0") else None
        visible = scanner.select_reward(overview["trials"], reward)
        return templates.TemplateResponse(request, "index.html", {
            "root": root,
            "root_name": root.name,
            "job_name": root.name,
            "current": None,
            "nav_trials": overview["trials"],
            "job_md": _to_html(overview["job_md"]),
            "trials": visible,
            "counts": overview["counts"],
            "summary": overview["summary"],
            "reward_sel": reward_sel,
        })

    @app.get("/trial/{name}", response_class=HTMLResponse)
    def trial(request: Request, name: str, tab: str = "overview",
              step: str | None = None):
        # single path segment only — reject any separator or traversal
        if "/" in name or "\\" in name or name in (".", ".."):
            raise HTTPException(404, f"unknown trial: {name}")
        return render_trial(request, root / name, tab, step)

    return app


def serve(root: Path, *, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the viewer until interrupted (blocking)."""
    import uvicorn

    root = Path(root)
    uvicorn.run(create_app(root), host=host, port=port)