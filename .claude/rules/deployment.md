# Deployment & Development

## Repo Topology

- **Default branch is `master`** (not `main`). Personal repo at
  `github.com/janspoerer/mcp_browser_use`.
- No CI deploy. Users install from source: clone, `pip install -e .`, point an
  agent host at the resulting venv via `.mcp.json`.
- No database, no Docker, no server — the MCP runs as a subprocess of whatever
  agent host launched it.

## Install (local dev)

```bash
cd mcp_browser_use
python -m venv .venv
source .venv/bin/activate           # Linux/macOS
# .venv\Scripts\activate            # Windows
pip install -e ".[test]"
```

Smoke-check:

```bash
.venv/bin/python -m mcp_browser_use
# stderr: "mcp_browser_use from: <path>"
# Ctrl+C to stop (FastMCP holds stdio open waiting for an agent host).
```

## Agent Host Wiring

The MCP is launched by the agent host (Claude Code, Codex CLI, fast-agent, etc.)
via a per-project `.mcp.json`. See `SETUP_GUIDE.md` for full templates per OS.

The repo ships three reference configs (gitignored vs not — check git status):

| File | Purpose |
|------|---------|
| `.mcp.json` | Default reference config (gitignored may apply per branch). |
| `.mcp_nix.json` | Linux/macOS reference. |
| `.mcp_windows.json` | Windows reference. |

After editing `.mcp.json`, **the agent host must be restarted** — env vars are
baked into the subprocess at launch time.

## Git Workflow

Plain: `git status`, `git pull`, `git add <specific files>`, `git commit`,
`git push`. No CI, no hooks of significance, no enforced rebase.

**Branch is `master`**, not `main`. Push targets `origin master`.

## Sensitive / Gitignored Files (NEVER stage)

From `.gitignore`:

- `.env` — local environment overrides
- `fastagent.secrets.yaml` — fast-agent credentials
- `.claude/` — agent host state (this repo ignores `.claude/` at the moment,
  although docs files like `CLAUDE.md` and `.claude/rules/*.md` are committed
  intentionally — verify with `git check-ignore <path>` before staging if unsure)
- `.codex/`, `.gemini/` — other agent host caches
- `_OLD/` — archived code
- `*.ipynb`, `summary*.txt`, `*.jsonl` — local working files
- `start_mcp.bat` — local launcher
- Standard Python ignores: `__pycache__/`, `*.pyc`, `.venv/`, `*.egg-info/`, build artifacts

Always inspect `git status` and `git diff --staged` before committing. Use
explicit `git add <path>` — never `git add -A` or `git add .`.

## Logs to Look At When Things Break

| Location | Content |
|----------|---------|
| `<tempdir>/mcp_browser_logs/chrome_debug_<port>.log` | Chrome stderr/stdout. |
| `<tempdir>/mcp_browser_logs/extension_loading_debug.log` | Extension discovery + flags. |
| `logs/` (in repo) | Selenium / MCP logs if locally captured. Gitignored. |
| `selenium_mcp_log.log` | Sample log artifact in repo (not committed by default). |
| `tmp/mcp_locks/*.softlock.json` | Current action-lock owner + expiry (human-readable). |

## Testing

```bash
pip install -e ".[test]"
pytest                                      # full suite
pytest tests/tests_decorators -v            # decorator unit tests
pytest tests/tests_e2e -v                   # end-to-end (needs Chrome)
bash scripts/test_coverage.sh               # coverage run
```

**Do not introduce `pytest-asyncio`.** Async tests are managed manually; see
the `asyncio` marker in `pyproject.toml`.

## Debugging Live MCP

1. `curl http://127.0.0.1:<CHROME_REMOTE_DEBUG_PORT>/json/version` — verifies
   Chrome's DevTools endpoint is listening.
2. `mcp_browser_use__get_debug_diagnostics_info` from the agent — returns
   driver/session info, profile path, browser+driver+Selenium versions.
3. `ls tmp/mcp_locks/` — inspect current locks and window registry. Files are
   plain JSON.
4. Stuck? `mcp_browser_use__unlock_browser` releases this process's action lock.
   Truly wedged? `mcp_browser_use__force_close_all_chrome` (destructive — affects
   every agent on the same profile).
