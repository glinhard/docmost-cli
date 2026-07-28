# Changelog

## 0.7.0 (unreleased)

### Added

- **`attachment upload <page-id> --file <path>`** — upload a file and attach it
  to a page, closing the last "can the CLI do what the editor does" gap for
  images. Contributed by [@amanpatel](https://github.com/amanpatel) in
  [#1](https://github.com/glinhard/docmost-cli/pull/1).

  It posts a multipart upload to `POST /files/upload`, the undocumented endpoint
  the web editor itself uses, and prints the attachment ID to stdout with the
  page-embeddable URL on stderr — so `ID=$(docmost-cli attachment upload ...)`
  captures the ID alone, and the file can be embedded with
  `![alt](/api/files/<id>/<filename>)`. The MIME type is guessed from the
  filename and falls back to `application/octet-stream`.

  Verified end to end against Docmost Community: the file uploads, the returned
  URL renders in the page, and the endpoint answers with the attachment row
  bare, without the `{success, status, data}` envelope every other endpoint
  uses. The response is read both ways regardless, since an undocumented
  endpoint's shape is not a contract. A response carrying no usable record is a
  clear error rather than a traceback, and a filename is percent-escaped so it
  cannot reshape the URL path.

### Fixed

- **`page import --title` never reached the server.** The flag was auto-detected,
  printed in the confirmation message, and then dropped: the import endpoint has
  no title parameter, so the page kept whatever title Docmost derived from the
  file's first heading or its filename. The CLI said *"Imported 'X'"* about a
  page called something else. This is the same defect as #12 one command over —
  that fix landed inside `create_and_place_page`, which `page import` does not
  go through. An explicit `--title` is now applied after the import; omitting it
  still costs no extra call, since the server's own title is then the answer.
- **`sync status` and `sync push --dry-run` listed change types in an order that
  varied between runs.** `PageChange.changes` is a set of enum members, and
  `Enum.__hash__` hashes the member *name* — so iteration follows Python's
  per-process string hash seed. The same working tree could print
  `content_changed, title_changed` on one run and `title_changed,
  content_changed` on the next, which matters most for `--dry-run`, whose stdout
  is the scripting-facing action plan. Both now render through one helper that
  sorts by declaration order.
- **`page export` could not recover from an expired session.** `post_raw` built
  and sent its request directly instead of going through the shared retry path,
  so the one command that uses it got no 401 re-authentication and no backoff on
  429/5xx, unlike every other call in the CLI. On Community edition, where auth
  *is* a refreshable session, that made an expired token a hard failure. Silent
  endpoint probes keep their single-shot behaviour, which the
  Enterprise/Community content fallbacks depend on.
- `config test` no longer prints `Error: Configuration error: 1` underneath the
  real error. It caught the `SystemExit` that `get_client()` raises after
  reporting its own reason, and reformatted the exit *code* as the message.
- **`page create --title` was silently discarded when the Markdown began with
  its own heading** ([#12](https://github.com/glinhard/docmost-cli/issues/12)).
  The import endpoint derives the page title from the first H1, and the CLI
  never applied the explicit title afterwards — so it reported creating
  *"agt01 — Ferdl personal agent host"* while the page persisted as *"agt01"*.
  The title is now always applied after import, folded into the same request as
  `--icon` so it costs one call rather than two.

  Note that Docmost's import *consumes* the content's first heading — **at any
  level** — as the page title and removes it from the body. That is unchanged
  by this fix and applies with or without `--title`, but it means a page
  created from `# Heading` plus `--title "Other"` keeps that text neither in
  the body nor as the title. Put it in `--title` if you need it.

  Measured against Docmost Community, not inferred: content starting `##
  Subheading` loses that line exactly as an `# H1` does, so dropping a level is
  not a way to keep it.

  This also fixes `sync push`: a frontmatter title edited without touching the
  body's H1 used to be ignored on page creation.
- The man page's upload-and-embed example used `--content "![alt](...)"`, which
  dies in an interactive `bash` with *event not found*: Markdown image syntax
  starts with `!`, and history expansion applies inside double quotes. It now
  pipes through `--stdin`, with the single-quote form as an alternative. Found
  by running the documented command against a live instance.
- `docmost-cli.1` declares the `tbl` preprocessor, so its OUTPUT CONVENTIONS
  table renders as a table rather than as raw tbl source, and the table now fits
  an 80-column terminal instead of overflowing it. All ten pages are clean under
  `groff -ww`.

### Changed

- The release workflow no longer mistakes a null release body for hand-written
  notes. GitHub types a release body as nullable and `jq` renders a null as the
  text `null`, so the emptiness check read "no notes" as "notes a human wrote"
  and skipped filling them from this file.
- `upload-artifact` and `download-artifact` moved to their Node 24 majors, which
  the runners had begun force-migrating.
- CI lints the workflow files with actionlint, including shellcheck over every
  `run:` block. Nothing checked them before, which is how an unresolvable action
  pin, two deprecated runtimes and the null-body bug all reached `main` green.

### Internal

No behaviour change in any of these; they are the structural half of the same
review that found the fixes above.

- `SyncDiff.move_only` replaces three hand-written copies of "moved pages that
  are not already being updated". Two of them compared whole `PageChange`
  objects — every field, including the Markdown body — while the third compared
  page IDs, so the plan `sync push` *printed* and the plan it *executed* were
  two different computations that happened to agree.
- `require_manifest()` in `sync/manifest.py` replaces three copies of
  load-then-error-if-missing, and with them the two `return  # unreachable`
  lines that followed a `NoReturn` call.
- `output/formatter.py` now owns exactly one stdout and one stderr console, and
  exposes `print_progress()` and `print_rendered()`. There were five consoles
  before — two of them reached through `from ...formatter import _err_console`,
  a private name, and two more rebuilt on every table render.
- `sync/push.py` and `sync/pull.py` import at module level. Twenty-two imports
  sat inside function bodies without a cycle to justify them; `sync/__init__.py`
  imports the whole package eagerly regardless. `api/pages.py` likewise deferred
  imports from a module it already imports on line 7.
- `DocmostClient` gained a public `base_url` property, so `config test` stops
  reading `client._base_url`, and a `_rebuild()` helper that replaces the
  duplicated build-and-reauthenticate block in the retry loop.
- `page get` fetches the page once instead of once per branch, and the nine
  subcommand registrations in `cli/main.py` are one import block instead of nine
  `# noqa: E402` pairs.

## 0.6.0 (2026-07-27)

### Behavior changes

- **`--json` on list commands is now lossless.** It used to project each item
  onto the same hardcoded column list the Rich table uses, silently discarding
  every other field the server returned — `page list --json` dropped `slugId`,
  `spaceId`, `creatorId`, `lastUpdatedById`, `position`, `isLocked`,
  `createdAt` and `contributorIds`. Each element is now the complete server
  object. The table is unchanged: its column list was always a display choice.
  Page *content* is not part of the list payload (Docmost omits it from
  `baseFields`), so listings stay small.
- **`--json` no longer invents keys.** A column the server omitted used to be
  emitted as `null`; a missing field is now simply absent. An explicitly named
  `--fields` entry still yields `null`, which keeps projections rectangular.
- `page list --tree --json` and flat `--json` now agree on shape — the tree path
  already emitted complete objects.
- `page list --tree` now actually rejects `--page-size`, which its own error
  message has claimed since 0.5.0 while never checking it.
- Table cells render `None` as blank instead of the literal string `None`
  (visible in `page list`'s `parentPageId` column for every root page).
- `config show --json` emits `no_session_cache` as a real JSON boolean. The
  table still shows it.

### Added

- `--fields a,b,c` on all eight list commands: projects the JSON output *and*
  replaces the table's columns, so the table is configurable for the first time.
  Names are validated against the fields the server actually returned — an
  unknown name is a usage error listing what is available, because a typo would
  otherwise yield a silent full-length column of nulls.
- `--fields` under `page list --tree --json`, projecting every node recursively
  while always preserving the nested `children` array. It requires `--json`,
  since the indented tree view has no columns to replace.
- `--json` on `workspace info`, `user me` and `config show`, which previously had
  no machine-readable output at all. The first two emit the complete server
  object and also accept `--fields`. `config show --json` masks `api_key` and
  `password` exactly as the table does.
- `print_json()` in `output/`, now the single JSON writer — `page list --tree
  --json` and `page get --raw` route through it, which also gives `--raw` the
  `default=str` fallback it was missing.
- `emit_item()` in `cli/_list_opts.py`, the single-item mirror of `emit_list()`.

### Fixed

- `mypy src/` is clean under `strict = true`; it had been carrying 23 errors.
  Two were real defects rather than annotation noise: `extract_id()` was declared
  `-> str` but returned whatever the server put in `"id"`, so a numeric id would
  have propagated a non-string page ID into request bodies; and `_node_heading()`
  computed `"#" * level` from an unvalidated nested `.get()`, so a ProseMirror
  document with a string or null heading level raised `TypeError` mid-render.
- `config show` masking is now produced in exactly one place, so no future
  renderer can add a path that forgets to mask.

### Changed

- `print_table()` gained a keyword-only `fields` argument; `columns` no longer
  affects JSON output.
- Corrected `SPECIFICATION.md` §7.2, whose sample payload showed a projected
  three-key object and documented a field named `updated` that has never existed
  (the code emits `updatedAt`), and its stale `print_table` signature.
- Removed two README rows for things that were never implemented: a
  `space get` command and a `space list --detail` flag. Corrected `search` to
  `search query`.

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
