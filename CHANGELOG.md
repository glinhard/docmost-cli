# Changelog

## Unreleased

- Add `attachment upload <page-id> --file <path>` command: upload a file (e.g.
  an image) and attach it to a page via the undocumented `POST /files/upload`
  endpoint (the same one the web editor uses for inline images/attachments).
  Prints the new attachment ID and the page-embeddable URL
  (`/api/files/{id}/{fileName}`) for embedding in Markdown.

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
