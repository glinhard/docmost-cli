# CLAUDE.md — Project Instructions for Claude Code

## Project

This is `docmost-cli`, a Python CLI tool for managing Docmost wiki instances from the terminal.
Read `SPECIFICATION.md` for the full project specification, API endpoints, command structure, and architecture.

## Tech Stack

- Python ≥ 3.11, using `typer`, `httpx`, `rich`, `pydantic-settings`
- Package manager: `uv` preferred, `pip` as fallback
- Test framework: `pytest` with `pytest-httpx` for HTTP mocking

## Development Commands

```bash
# Install in dev mode
uv pip install -e ".[dev]"

# Run the CLI
python -m docmost_cli
# or after install:
docmost-cli

# Run tests
pytest

# Run tests with coverage
pytest --cov=docmost_cli

# Type checking
mypy src/

# Linting
ruff check src/ tests/
ruff format src/ tests/
```

## Code Style

- Use type hints everywhere (Python 3.11+ syntax, e.g. `str | None` not `Optional[str]`)
- Docstrings on all public functions (Google style)
- Keep CLI commands thin — business logic lives in `api/` and `convert/` modules
- Use pydantic models for all API request/response types
- `httpx.Client` should be created once and reused (connection pooling)
- All API calls go through `DocmostClient` — never raw httpx in the CLI layer
- Use `__all__` exports in `__init__.py` files

## Architecture Rules

```
cli/     → depends on api/, sync/, output/ (never the reverse)
api/     → depends on models/, config/     (never on cli/)
sync/    → depends on api/, output/        (manifest, frontmatter, diff are standalone)
convert/ → standalone                      (no internal dependencies)
output/  → formats data only               (no API calls, no business logic)
         enforces stdout/stderr separation
models/  → standalone pydantic models      (no dependencies)
config/  → standalone                      (no dependencies except pydantic)
```

## Testing Approach

- **Conversion tests**: ProseMirror ↔ Markdown using fixture files in `tests/fixtures/`
- **API tests**: Mock HTTP responses with `pytest-httpx`
- **CLI tests**: Use typer's `CliRunner` for end-to-end command testing
- **Fixture pairs**: Every `.json` fixture has a matching `.md` expected output

## Important Patterns

- **Auth auto-detection**: Check for `api_key` first, then fall back to `email`+`password`
- **ProseMirror content**: Always convert to Markdown for display; use `--raw` for JSON
- **Pagination**: Cursor-based, at `data.meta.nextCursor` (**not** `data.cursor`).
  List commands auto-follow until `hasNextPage` is false. `--limit` caps the
  total across pages; `--page-size` sets the per-request size (server max 100);
  `--cursor`/`--no-follow` fetch a single page. Go through
  `cli/_list_opts.py`'s `fetch_list`/`emit_list` rather than calling the API
  function directly
- **Error handling**: Catch `httpx` exceptions → translate to user-friendly messages via `rich`
- **Confirmations**: Destructive operations prompt unless `--yes` / `-y` is passed
- **Page creation**: Prefer the import endpoint (server-side MD→ProseMirror) over client-side conversion
- **Page content updates**: `POST /pages/update` with `{content, format: "markdown", operation}`.
  The server does the Yjs write — never build a WebSocket/CRDT client. Requires
  Docmost v0.71+; older servers silently strip the field, so check that the
  returned `content` is a `str`, never trust the 200
- **Page positions**: `POST /pages/move` requires a 5-12 char base62 fractional
  index. Use `api/position.py`'s `generate_key_between` via
  `resolve_position()` — never hardcode a key
- **Output projection**: `--json` never filters; the `columns` list is a display
  choice for the Rich table only. `--fields` is the one thing that projects, and
  it drives the table columns too. Go through `cli/_list_opts.py`'s
  `emit_list`/`emit_item`, never `print_table`/`print_json` directly

### Output Strategy (no global `--json` flag)

The CLI follows Unix stdout/stderr separation. There is no global `--json` flag.
Each command category uses the format that fits its data shape:

| Command type | stdout | stderr | Example |
|---|---|---|---|
| **Content** (`page get`) | Raw Markdown | nothing | `docmost-cli page get abc123 > page.md` |
| **Content + meta** (`page get --meta`) | YAML frontmatter + Markdown | nothing | Parseable by any frontmatter tool |
| **Lists** (`page list`, `search`, ...) | Rich table (curated columns) or JSON array of **complete** objects (`--json`) | nothing | `docmost-cli page list eng --json \| jq` |
| **Lists, projected** (`--fields a,b,c`) | Only those fields, in both renderers | nothing | `docmost-cli page list eng --fields id,title` |
| **Lists + pagination meta** (`--json --envelope`) | `{"items": [...], "meta": {...}}` | nothing | `... --no-follow --json --envelope \| jq .meta` |
| **Single item** (`workspace info`, `user me`) | Key-value table, or the complete object with `--json` | nothing | `docmost-cli user me --json \| jq .role` |
| **Config** (`config show`) | Table, or masked JSON with `--json` | nothing | secrets stay masked in both |
| **Writes** (`page create`, `delete`, ...) | Resource ID only | Confirmation message | `ID=$(docmost-cli page create ...)` |
| **Sync status** (`sync status`) | Change summary | nothing | `docmost-cli sync status eng` |
| **Sync push dry-run** (`sync push --dry-run`) | Action plan | nothing | `docmost-cli sync push eng --dry-run` |
| **Sync ops** (`sync pull`, `sync push`) | nothing | Progress + summary | `docmost-cli sync pull eng --dir ./docs/` |
| **Errors** | nothing | Error message | Exit codes: 0=ok, 1=error, 3=auth, 4=not-found |

This means:
- `docmost-cli page get <id>` output is directly pipeable as Markdown
- `docmost-cli page list <space> --json` is directly parseable by jq or Claude Code,
  and lossless — a new server field shows up without a CLI change
- `PAGE_ID=$(docmost-cli page create ...)` captures just the ID with no extra parsing
- Human-readable messages never pollute captured output

## Key Reference Files

- `SPECIFICATION.md` — Full project spec (commands, API endpoints, architecture)
- `src/docmost_cli/api/client.py` — Central HTTP client, auth logic
- `src/docmost_cli/convert/` — ProseMirror ↔ Markdown converters
- `tests/fixtures/` — ProseMirror JSON + expected Markdown pairs
- `man/man1/` — Man pages in groff format (one hub + one per command group)

## When Starting a New Feature

1. Check `SPECIFICATION.md` section 4 for the command signature
2. Check `SPECIFICATION.md` section 5.2 for the API endpoint
3. Create/update the pydantic model in `models/`
4. Implement the API method in `api/`
5. Wire up the CLI command in `cli/`
6. Add tests (API mock + CLI runner)
7. Update the implementation phases checklist in `SPECIFICATION.md`
8. Update the corresponding man page in `man/man1/`
