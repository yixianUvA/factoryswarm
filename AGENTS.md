# FactorySwarm Agent Instructions

- Inspect the repository before editing. It contains working Cerebras smoke scripts, sample images, generated visual-difference artifacts, and a large VisA-style dataset.
- Preserve the official `from cerebras.cloud.sdk import Cerebras` / `AsyncCerebras` integration. Do not introduce OpenAI SDK client logic.
- Never print, log, commit, or display `.env`, `CEREBRAS_API_KEY`, authorization headers, or request payloads that may contain secrets.
- Keep all runtime Cerebras calls behind `core/cerebras_client.py`; do not duplicate client setup in agent modules.
- Ordinary tests must not require network access. Live API tests must be opt-in with `RUN_LIVE_API_TESTS=1`.
- Run `conda run -n factoryswarm python -m pytest -q` and `conda run -n factoryswarm python -m compileall .` after behavior changes.
- Keep modules typed and focused. Prefer Pydantic validation for structured model output and user-visible report data.
- Do not treat OpenCV difference heatmaps or dataset masks as ground truth. Masks are evaluation metadata unless the user explicitly reveals them in the UI.
- Do not add unnecessary dependencies or large tooling during hackathon work.
- Update `README.md` when setup, runtime behavior, testing, or safety limitations change.
- Report changed files, verification commands, and remaining risks at the end of coding sessions.
