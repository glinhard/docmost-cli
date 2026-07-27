# Changelog

## 0.5.0 (2026-07-26)

Fixes six gaps reported against Docmost Community 0.95, verified against the
upstream v0.95.0 server source.

### Behavior changes

- **List commands now return every result.** Pagination is followed
  automatically instead of stopping at the server's first page. `--limit` is now
  a cap on the *total* across pages rather than a per-request limit, so
  `--limit 200` fetches two pages of 100 instead of failing with HTTP 400.
- **`sync push` no longer recreates pages silently.** On a server too old to
  update content in place it aborts with an explanation; pass `--allow-recreate`
  to opt into the old delete+recreate behavior, which prints a warning naming the
  affected page count.
- **`page move --position` takes `first`, `last`, or an ordering key** instead of
  an integer, and defaults to `first`. `POSITION_FIRST` (`"aaaaa"`) is gone — it
  never meant "first" anyway: in ASCII `'a' > '0'`, so it sorted *after* every key
  Docmost's own generator produces.
- `move_page()`'s `position` argument is now required (the server requires it).

### Fixed

- **Pagination metadata was silently discarded.** `get_cursor()` looked for
  `data.cursor`, but Docmost returns `data.meta.nextCursor`, so it returned `None`
  every time — which is why the auto-follow documented since 0.2.0 never actually
  ran and `--cursor` was a write-only flag.
- **`page children` capped at 20.** It sent no `limit` or `cursor` to
  `/pages/sidebar-pages` and got the server default.
- **`page move --parent` returned HTTP 400 without `--position`.** Docmost's
  `MovePageDto` declares `position` as required (`@MinLength(5) @MaxLength(12)`);
  the CLI dropped it from the body when unset.
- **Content updates failed with a misleading message.** The CLI POSTed to
  `/pages/content/update`, an endpoint that does not exist in Docmost, and read
  the 404 as an Enterprise-only restriction. Content now goes through
  `POST /pages/update`, which Docmost applies server-side through its
  collaboration gateway. The page keeps its ID, slug, history, comments and
  inbound links — no WebSocket or Yjs client needed. Requires Docmost v0.71+.
- **Space slug resolution failed past the first page of spaces**, reporting a
  misleading `Space '<slug>' not found.` Now follows pagination, stopping at the
  first match.
- **`sync pull` fetched an incomplete tree** on spaces with more root pages or
  children than one server page, silently producing a partial local copy.
- **`sync push` lost the manifest when a phase aborted**, so the next push
  re-created every already-created page as a duplicate. The manifest is now saved
  in a `finally` block.
- `update_page_content` only intercepted HTTP 404; a 405 or 403 fell through to a
  bare "Unexpected error".

### Added

- `--version` / `-V` and a `version` subcommand. With `--verbose`, `version` also
  reports the Python version and platform. The version now has a single source of
  truth (`src/docmost_cli/__init__.py`), with `pyproject.toml` deriving it.
- `--no-session-cache` global flag, `DOCMOST_NO_SESSION_CACHE` environment
  variable and `no_session_cache` config key: the session JWT stays in memory and
  is never read from or written to `~/.cache/docmost-cli/session.json`.
- `docmost-cli config logout` deletes an existing cached session token.
- `--limit`, `--page-size`, `--cursor`, `--no-follow` and `--envelope` on all
  eight list commands. `--json` still emits a bare array; `--envelope` wraps it as
  `{"items": [...], "meta": {...}}` carrying `hasNextPage` and `nextCursor`.
- `page update --append` / `--prepend`.
- `page move --root` to move a nested page to the space root.
- `page list --tree --json` outputs the nested tree as JSON (it was previously
  ignored).
- `api/position.py`: base62 fractional indexing ported from the reference
  algorithm, with jitter to satisfy Docmost's 5-character minimum. Keys stay valid
  for Docmost's own JS generator, so dragging a sibling next to a CLI-placed page
  in the web editor still works.
- `models/common.py`: `PaginationMeta` and `PaginatedResult` pydantic models.
- Guards against a server that ignores `cursor`: pagination stops when a cursor or
  a page repeats, and warns, rather than looping forever.

### Changed

- `--tree` now rejects the pagination flags instead of silently ignoring them.
- `print_table()` gained a keyword-only `meta` argument; `print_table` and the new
  `print_warning` are exported from `docmost_cli.output`.
- Corrected `SPECIFICATION.md` §5.2/§5.3 (response envelope shape, `/pages/move`
  requirements, the non-existent content endpoint) and the `--position` docs in
  the man pages. A new doc test keeps the man-page `.TH` versions in sync.

## 0.4.0 (2026-03-22)

- Add `sync pull` command: download all pages from a space to local Markdown files with YAML frontmatter
- Add `sync push` command: upload local changes to server (create, update, move pages)
- Add `sync status` command: show changes between local files and last-pulled state
- Edition-aware content updates: Enterprise uses REST content update (preserves page ID), Community uses safe create-then-delete (new page created and verified before old page removed)
- Flat directory layout with `.docmost-manifest.json` tracking sync state and SHA-256 content hashes
- `--dry-run` flag on push to preview changes without executing
- `--delete` flag on push to remove server pages not found locally (opt-in safety)
- `--force` flag on pull to overwrite existing synced data
- Topological sort ensures parent pages are created before children
- ID remapping: when Community edition forces new page IDs, frontmatter and manifest are updated automatically
- 105 new tests (96 sync module + 9 CLI integration)

## 0.3.1 (2026-03-22)

- Fix `page list --tree` and `page children` on Community edition: use `/pages/sidebar-pages` instead of `/pages/children` (404 on v0.70.3)
- Tree recursion: only fetch children for pages with `hasChildren: true` (eliminates ~40 wasted API calls on a 50-page space)
- Narrow error handling in tree builder (auth failures no longer silently swallowed)
- Reduce API calls in `page get` (fetch page info once, not twice)
- Remove raw HTTP call from CLI layer (use API function instead)
- Deduplicate UTF-8 stdio reconfigure into `_ensure_utf8_stdio()`
- Use `build_body` helper consistently in all API functions
- Remove dead code: unused models, unused parameter

## 0.3.0 (2026-03-22)

- Add `parentPageId` to `page list --json` output columns
- Add `parent_id` to `page get --meta` YAML frontmatter
- Add `--icon` flag to `page update` command
- Add recursive tree fallback: `page list --tree` fills in missing children
- Add "See also" cross-references to all page command help text
- Fix `page children` and `--tree` on Community edition: use `/pages/sidebar-pages` instead of `/pages/children` (404 on v0.70.3)
- Fix emoji/Unicode crash: move UTF-8 encoding to correct entry point
- Fix `--parent` on `page create`: use fractional index position string
- Fix `--content` escape sequences: `\n` and `\t` now work as newline/tab

## 0.2.4 (2026-03-22)

- Fix emoji/Unicode crash for real: move UTF-8 reconfigure from `__main__.py` to `cli/main.py` (the actual entry point used by `docmost-cli` script bypasses `__main__.py`)

## 0.2.3 (2026-03-22)

- Fix `--parent` on `page create`: send fractional index position string (Docmost requires 5-12 char string, not integer)
- Fix emoji crash on all Windows terminals: remove `isatty()` guard, always reconfigure to UTF-8 on Windows
- Fix `--content` escape sequences: `\n` and `\t` now interpreted as actual newline/tab
- Position parameter on `page move` changed from `int` to `str` (fractional index format)

## 0.2.2 (2026-03-22)

- Fix `--parent` on `page create` silently ignored (import endpoint ignores parentPageId; now calls move_page as fallback)
- Fix `--help` crash on Windows (`OSError` from Rich's LegacyWindowsRenderer on cp1252 consoles)
- Fix `page get --meta` crash when page content contains emoji (✅❌⚠️📊)
- Reconfigure stdout/stderr to UTF-8 at startup on Windows interactive terminals

## 0.2.1 (2026-03-22)

- Fix tree view crash on Windows with emoji page icons (cp1252 encoding)
- Fix silent Enterprise endpoint probe leaking error messages on Community edition
- Fix API endpoints discovered during live integration testing:
  - `/spaces/list` → `/spaces`
  - `/comments/list` → `/comments`
  - `/pages/export` format `md` → `markdown`, response is ZIP not JSON
  - Auth token extracted from `authToken` cookie (not `token`)
  - Comment content JSON-stringified for API
- Consolidate duplicated code: shared `extract_items`, `extract_id`, `build_body` helpers
- Remove 6 dead stub files (-84 lines)
- Add `post_raw()` to DocmostClient for binary/probe responses
- Fix double file read in page import
- Add Claude Code skill (`/docmost`) for wiki interaction
- Prepare for PyPI: py.typed marker, CHANGELOG, dependency upper bounds, classifiers

## 0.2.0 (2026-03-22)

- Retry with exponential backoff for transient errors (429, 5xx)
- `--verbose` HTTP debug logging (request/response to stderr)
- Page duplicate, copy, children, history, export, import commands
- Tree view (`--tree`) for page listing
- Workspace info/members, user me, attachment search commands
- Pagination auto-follow with safety guard (max 1000 iterations)
- ProseMirror-to-Markdown converter (all block nodes and marks)
- Claude Code skill (`/docmost`) for wiki interaction
- Comprehensive README with command reference
- MIT LICENSE file
- Session cache file permissions (0600)
- 175 tests, 0 lint errors

## 0.1.0 (2026-03-22)

- Initial release
- Project scaffolding with typer CLI framework
- Configuration system with TOML profiles and environment variable overrides
- HTTP client with API key (Enterprise) and session (Community) auth auto-detection
- Page CRUD: create (via import endpoint), read, update, delete, move
- Space list, create, update
- Comment list, create, update (ProseMirror JSON wrapping)
- Full-text search with space filtering
- Output helpers enforcing stdout/stderr separation
- Edition-agnostic design (Community + Enterprise)
- 50 tests with pytest + pytest-httpx
