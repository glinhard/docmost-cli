# docmost-cli — Project Specification

> **Purpose**: A Python CLI tool for interacting with Docmost wiki instances.
> Designed to be used both by humans on the terminal and by Claude Code as an automation interface.
>
> **Target repo**: This file lives at the root of the `docmost-cli` GitHub repository.
> Claude Code should treat it as the authoritative specification for all implementation work.

---

## 1. Project Overview

### 1.1 What This Is

A command-line tool (`docmost-cli`) that provides full CRUD access to a Docmost wiki instance:
reading pages, creating content, managing spaces, searching, handling comments,
and performing bulk operations — all from the terminal.

### 1.2 Primary Users

1. **Claude Code** — as an automation tool to read/write documentation programmatically
2. **Human operators** — for quick wiki management without opening a browser

### 1.3 Design Principles

- **Markdown-native**: All page content is presented as Markdown and accepted as Markdown.
  ProseMirror JSON conversion happens internally and is never exposed to the user by default.
- **Edition-agnostic**: Works with both Docmost Enterprise (API key auth) and
  Community/AGPL (session-based email/password auth), with auto-detection.
  Both editions share the same server codebase and internal API endpoints.
  Enterprise may expose additional endpoints; the CLI detects and adapts.
- **Unix-native output**: Follows stdout/stderr separation. Content goes to stdout
  (capturable), status messages go to stderr (visible but not captured). No global
  `--json` flag — each command category uses the output format that makes sense.
- **Fail-safe**: Destructive operations require confirmation unless `--yes` is passed.
  Errors produce clear, actionable messages.

---

## 2. Technology Stack

| Component | Choice | Rationale |
|---|---|---|
| Language | Python ≥ 3.11 | Maintainer expertise, ecosystem maturity |
| CLI framework | `typer` | Modern, type-hint-driven, auto-generates help |
| HTTP client | `httpx` | Async support, connection pooling, HTTP/2 |
| Terminal output | `rich` | Tables, syntax highlighting, progress bars |
| Config management | `pydantic-settings` | Typed config with env var + file support |
| ProseMirror→MD | Custom converter | Based on proven patterns from existing MCP servers |
| MD→ProseMirror | Custom converter | For page creation/update from Markdown input |
| Packaging | `uv` / `pip` | Standard Python packaging with pyproject.toml |
| Testing | `pytest` + `pytest-httpx` | Mock HTTP for unit tests, real calls for integration |

---

## 3. Authentication & Configuration

### 3.1 Configuration File

Location: `~/.config/docmost-cli/config.toml` (XDG-compliant, overridable via `--config`)

```toml
[default]
url = "https://docs.example.com"
# For Enterprise edition:
api_key = "dm_xxxxxxxxxxxxxxxxxxxx"
# For Community edition (used if api_key is absent):
email = "user@example.com"
password = "secret"

# Optional profile for a second instance
[staging]
url = "https://staging-docs.example.com"
api_key = "dm_yyyyyyyyyyyyyyyyyyyy"
```

### 3.2 Environment Variable Overrides

All config values can be overridden via environment variables (higher precedence than config file):

```
DOCMOST_URL=https://docs.example.com
DOCMOST_API_KEY=dm_xxxxxxxxxxxxxxxxxxxx
DOCMOST_EMAIL=user@example.com
DOCMOST_PASSWORD=secret
DOCMOST_PROFILE=staging
```

### 3.3 Auth Detection Logic

```
1. If api_key is set → use Bearer token auth (Enterprise)
2. If email+password are set → use session auth:
   a. POST /api/auth/login with {email, password}
   b. Extract JWT from Set-Cookie header
   c. Cache token in ~/.cache/docmost-cli/session.json
   d. On 401 → re-authenticate automatically
3. If both are set → prefer api_key
4. If neither → error with setup instructions
```

### 3.4 CLI Global Options

```
--version, -V       Print the version and exit
--profile, -p       Config profile name (default: "default")
--url               Override Docmost URL
--api-key           Override API key
--yes, -y           Skip confirmation prompts
--verbose, -v       Debug logging (HTTP requests/responses)
--config            Path to config file
--no-session-cache  Keep the session JWT in memory; never touch the cache file
```

Every list command shares the same pagination flags:

```
--limit N        Max total results across all pages (default: all)
--page-size N    Results per request, 1-100 (default: 100, the server maximum)
--cursor <c>     Fetch a single page starting at this cursor
--no-follow      Fetch a single page instead of following pagination
--json           Output as a JSON array of complete server objects
--envelope       With --json, emit {"items": [...], "meta": {...}} instead
--fields a,b,c   Project output to these fields; also replaces the table columns
```

---

## 4. Command Structure

### 4.1 Top-Level Commands

```
docmost-cli config      # Manage configuration
docmost-cli page        # Page operations
docmost-cli space       # Space operations
docmost-cli comment     # Comment operations
docmost-cli search      # Search across the wiki
docmost-cli attachment  # Attachment operations
docmost-cli workspace   # Workspace info
docmost-cli user        # Current user info
```

### 4.2 `docmost-cli config`

```
docmost-cli config init                   # Interactive setup wizard
docmost-cli config show                   # Show current config (masks secrets)
docmost-cli config set <key> <value>      # Set a config value
docmost-cli config test                   # Test connectivity and auth
```

### 4.3 `docmost-cli page`

```
docmost-cli page list <space-slug>                # List pages in a space
  --limit N                                   # Max total results (default: all)
  --page-size N                               # Results per request, 1-100
  --cursor <cursor>                           # Fetch a single page from this cursor
  --no-follow                                 # Fetch a single page
  --tree                                      # Show as indented tree
  --json                                      # Output as JSON array
  --envelope                                  # With --json, include pagination meta

docmost-cli page get <page-id>                    # Get page content as Markdown to stdout
  --raw                                       # Output ProseMirror JSON instead
  --meta                                      # Prepend YAML frontmatter (id, title, space, dates)

docmost-cli page create <space-slug>              # Create a new page
  --title "Page Title"                        # Required: page title
  --content "Markdown string"                 # Content as inline string
  --file path/to/content.md                   # Content from file
  --stdin                                     # Content from stdin
  --parent <page-id>                          # Nest under parent page
  --icon <emoji>                              # Page icon
  # stdout: page ID | stderr: human-friendly confirmation

docmost-cli page update <page-id>                 # Update existing page (in place)
  --title "New Title"                         # Update title
  --icon <emoji>                              # Update icon
  --content "New markdown"                    # Replace content (inline)
  --file path/to/content.md                   # Replace content (from file)
  --stdin                                     # Replace content (from stdin)
  --append                                    # Append instead of replacing
  --prepend                                   # Insert at the start instead of replacing
  # stdout: page ID | stderr: human-friendly confirmation
  # Page ID, slug, history, comments and inbound links are preserved.

docmost-cli page delete <page-id>                 # Delete a page (requires confirmation)
  # stdout: deleted page ID | stderr: confirmation message

docmost-cli page move <page-id>                   # Move a page
  --parent <page-id>                          # New parent page ID
  --space <space-slug>                        # Move to different space
  --root                                      # Move to the space root
  --position first|last|<key>                 # Placement among siblings (default: first)
  # Docmost requires an ordering key on every move. "first"/"last" read the
  # destination's children and compute a fractional index; an explicit
  # 5-12 character key is sent verbatim.

docmost-cli page duplicate <page-id>              # Duplicate a page

docmost-cli page copy <page-id>                   # Copy to different space
  --space <space-slug>                        # Target space

docmost-cli page children <page-id>               # List child pages
  --limit N --page-size N --cursor <c> --no-follow
  --json --envelope
  # Server default page size is 20; pagination is followed automatically.

docmost-cli page history <page-id>                # Show page version history
  --limit N --page-size N --cursor <c> --no-follow
  --json --envelope

docmost-cli page export <page-id>                 # Export page
  --format md|html                            # Output format (default: md)
  --output path/to/file                       # Write to file instead of stdout

docmost-cli page import <space-slug>              # Import content as new page
  --file path/to/file.md                      # Markdown file to import
  --title "Page Title"                        # Override title (else from filename/H1)
  --parent <page-id>                          # Nest under parent
```

### 4.4 `docmost-cli space`

```
docmost-cli space list                            # List all spaces
  --detail                                    # Include description, member count
  --json                                      # Output as JSON array

docmost-cli space get <space-slug>                # Get space details

docmost-cli space create                          # Create a new space
  --name "Space Name"                         # Required
  --slug "space-slug"                         # Auto-generated if omitted
  --description "..."

docmost-cli space update <space-slug>             # Update space
  --name "New Name"
  --description "New description"
```

### 4.5 `docmost-cli comment`

```
docmost-cli comment list <page-id>                # List comments on a page
  --json                                      # Output as JSON array

docmost-cli comment create <page-id>              # Add a comment
  --content "Comment text"

docmost-cli comment update <comment-id>           # Edit a comment
  --content "Updated text"
```

### 4.6 `docmost-cli search`

```
docmost-cli search <query>                        # Full-text search
  --space <space-slug>                        # Filter by space
  --limit N                                   # Max results (default: 20)
  --type page|attachment                      # Filter by result type
  --json                                      # Output as JSON array
```

### 4.7 `docmost-cli attachment`

```
docmost-cli attachment search <query>             # Search attachments
  --space <space-slug>
docmost-cli attachment upload <page-id>           # Upload a file to a page
  --file <path>
```

### 4.8 `docmost-cli workspace`

```
docmost-cli workspace info                        # Show workspace details
docmost-cli workspace members                     # List workspace members
  --limit N
  --json                                      # Output as JSON array
```

### 4.9 `docmost-cli user`

```
docmost-cli user me                               # Show authenticated user info
```

### 4.10 `docmost-cli sync`

Synchronize a space's pages with a local directory of Markdown files.
Enables documentation-as-code workflows with git version control.

```
docmost-cli sync pull <space>  [--dir PATH] [--force]     # Download pages → local Markdown files
docmost-cli sync push <space>  [--dir PATH] [--dry-run] [--delete] [--yes]  # Upload local changes
docmost-cli sync status <space> [--dir PATH]               # Show changes since last pull
```

**Local directory format:**
- Flat directory with `.docmost-manifest.json` tracking sync state
- Each page is `{title}--{id_prefix}.md` with YAML frontmatter (`id`, `title`, `parent_id`, `icon`)
- Change detection via SHA-256 content hash (not timestamps)

**Edition-aware content updates:**
- Enterprise: direct content update via REST (preserves page ID)
- Community: safe create-then-delete (new page created and verified before old page removed)

---

## 5. API Client Layer

### 5.1 Internal Architecture

```
docmost-cli/
├── pyproject.toml
├── README.md
├── SPECIFICATION.md              ← this file
├── CLAUDE.md                     ← Claude Code project instructions
├── src/
│   └── docmost_cli/
│       ├── __init__.py
│       ├── __main__.py           # Entry point: `python -m docmost_cli`
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── main.py           # Top-level typer app, global options
│       │   ├── page.py           # Page subcommands
│       │   ├── space.py          # Space subcommands
│       │   ├── comment.py        # Comment subcommands
│       │   ├── search.py         # Search subcommand
│       │   ├── attachment.py     # Attachment subcommands
│       │   ├── workspace.py      # Workspace subcommands
│       │   ├── user.py           # User subcommands
│       │   └── config_cmd.py     # Config management subcommands
│       ├── api/
│       │   ├── __init__.py
│       │   ├── client.py         # DocmostClient: HTTP session, auth, retry
│       │   ├── auth.py           # Auth strategies (API key vs session)
│       │   ├── pages.py          # Page API methods
│       │   ├── spaces.py         # Space API methods
│       │   ├── comments.py       # Comment API methods
│       │   ├── search.py         # Search API methods
│       │   ├── attachments.py    # Attachment API methods
│       │   ├── workspace.py      # Workspace API methods
│       │   └── users.py          # User API methods
│       ├── convert/
│       │   ├── __init__.py
│       │   ├── prosemirror_to_md.py   # ProseMirror JSON → Markdown
│       │   └── md_to_prosemirror.py   # Markdown → ProseMirror JSON
│       ├── config/
│       │   ├── __init__.py
│       │   ├── settings.py       # Pydantic settings model
│       │   └── store.py          # Config file read/write
│       ├── models/
│       │   ├── __init__.py
│       │   ├── page.py           # Page data models
│       │   ├── space.py          # Space data models
│       │   ├── comment.py        # Comment data models
│       │   └── common.py         # Shared models (pagination, etc.)
│       └── output/
│           ├── __init__.py
│           ├── formatter.py      # Output dispatch: print_content, print_result, print_error
│           ├── table.py          # Rich table + JSON array formatting for list commands
│           └── markdown.py       # Markdown + YAML frontmatter output helpers
├── tests/
│   ├── conftest.py               # Shared fixtures, mock client
│   ├── test_api/
│   │   ├── test_client.py
│   │   ├── test_pages.py
│   │   └── ...
│   ├── test_convert/
│   │   ├── test_prosemirror_to_md.py
│   │   └── test_md_to_prosemirror.py
│   ├── test_cli/
│   │   ├── test_page_commands.py
│   │   └── ...
│   └── fixtures/                 # Sample ProseMirror JSON, expected MD output
│       ├── simple_page.json
│       ├── simple_page.md
│       ├── complex_page.json
│       └── complex_page.md
└── docs/
    └── api-reference.md          # Discovered API endpoints (living document)
```

### 5.2 Known Docmost API Endpoints

These are the internal API endpoints used by the Docmost frontend and MCP servers.
All endpoints are `POST` unless noted. Base path: `/api/`.

> **Edition note**: All endpoints below are available on both Community and Enterprise
> editions (the frontend uses them), except those explicitly marked "Enterprise only".
> Feature availability is a function of the *server version*, not the edition.
> The CLI should attempt all endpoints and degrade gracefully if unavailable.
>
> **Validation note**: Docmost's global `ValidationPipe` uses `whitelist: true`
> without `forbidNonWhitelisted`, so a server too old to know a body field
> silently **strips** it and returns HTTP 200. Any feature gated on a newer
> server needs a positive confirmation signal, not just a 2xx.

**Authentication:**
```
POST /auth/login          → {email, password} → Set-Cookie JWT
POST /auth/logout
```

**Pages:**
```
POST /pages/info          → {pageId} → page metadata
POST /pages/create        → {title, spaceId, parentPageId?, icon?, content?}
POST /pages/update        → {pageId, title?, icon?,
                             content?, format?: json|markdown|html,
                             operation?: replace|append|prepend}
POST /pages/delete        → {pageId}
POST /pages/move          → {pageId, position (REQUIRED, 5-12 chars), parentPageId?, spaceId?}
POST /pages/duplicate     → {pageId}
POST /pages/copy          → {pageId, spaceId}
POST /pages/sidebar-pages → {spaceId?, pageId?, limit?, cursor?} → tree structure
POST /pages/recent        → {spaceId, limit?, cursor?}
POST /pages/history       → {pageId, limit?, cursor?}
POST /pages/import        → multipart: file (md/html), spaceId, parentPageId?
POST /pages/export         → {pageId, format: "md"|"html"}
```

> `POST /pages/move` requires `position` — `MovePageDto` declares it
> `@IsString @MinLength(5) @MaxLength(12)`. Omitting it is an HTTP 400.
> It is a base62 fractional index; see `src/docmost_cli/api/position.py`.

**Page content updates (Docmost v0.71+, both editions):**
```
POST /pages/update        → {pageId, content, format: "markdown", operation: "replace"}
```
> Content sent to `/pages/update` is applied **server-side through Docmost's
> collaboration gateway** (`PageService.update()` → `updatePageContent()` →
> `collaborationGateway.handleYjsEvent('updatePageContent', 'page.<id>', …)`).
> The page keeps its ID, slug, history, comments and inbound links, and the CLI
> needs no WebSocket or Yjs client of its own.
>
> There is **no `/pages/content/update` endpoint in Docmost** — earlier versions
> of this CLI called it and got a 404, which was misread as an edition
> restriction.
>
> Detecting an unsupported server: send `format: "markdown"` and inspect the
> returned `content`. A supporting server converts it with `jsonToMarkdown`, so
> it comes back as a **string**; a server that stripped the fields returns
> ProseMirror JSON (an **object**) or nothing.

**Page content read (Enterprise only, v0.70+):**
```
POST /pages/content       → {pageId} → ProseMirror JSON content
```
> Not available on Community edition; the CLI falls back to `/pages/info`,
> which can also convert content server-side via
> `{includeContent: true, format: "markdown"}`.

**Spaces:**
```
POST /spaces/list         → {limit?, cursor?}
POST /spaces/info         → {spaceSlug | spaceId}
POST /spaces/create       → {name, slug?, description?}
POST /spaces/update       → {spaceId, name?, description?}
POST /spaces/delete       → {spaceId}
```

**Comments:**
```
POST /comments/list       → {pageId, limit?, cursor?}
POST /comments/create     → {pageId, content}
POST /comments/update     → {commentId, content}
POST /comments/delete     → {commentId}
```

**Search:**
```
POST /search              → {query, spaceId?, type?, limit?, cursor?}
```

**Attachments:**
```
POST /attachments/search  → {query, spaceId?, limit?, cursor?}
GET  /attachments/...     → file download
POST /files/upload        → multipart {file, pageId} (undocumented; the endpoint
                            the web editor uses for inline images/attachments)
```

**Workspace:**
```
POST /workspace/info      → workspace details
POST /workspace/members   → {limit?, cursor?}
```

**Users:**
```
POST /users/me            → current user info
```

> **Note**: The API is not fully documented publicly. Endpoint signatures above are
> derived from the Docmost source code, MCP server implementations, and official
> MCP documentation. They may need adjustment during implementation — test against
> a real instance and update this section accordingly.

### 5.3 Pagination

Docmost uses cursor-based pagination (as of v0.25+). The server caps `limit` at
**100** and rejects anything larger with HTTP 400. Default page sizes vary by
endpoint (20 for `/pages/sidebar-pages`).

```json
// Request
{"spaceId": "...", "limit": 100, "cursor": "eyJpZCI6Ii..."}

// Response
{
  "data": {
    "items": [...],
    "meta": {
      "limit": 100,
      "hasNextPage": true,
      "hasPrevPage": false,
      "nextCursor": "eyJpZCI6Ii...",
      "prevCursor": null
    }
  }
}
```

The next cursor lives at **`data.meta.nextCursor`** — not `data.cursor`.

List commands follow pagination transparently until `hasNextPage` is false.
`--limit` caps the total across pages; `--cursor` or `--no-follow` fetches a
single page. `--json` stays a bare array — of **complete server objects**, not
just the table columns; `--envelope` wraps it as `{"items": [...], "meta": {...}}`
so a caller can drive the cursor itself. `--fields a,b,c` projects the output and
replaces the table's columns.

`paginate_all`/`paginate_iter` guard against a server that ignores `cursor` by
stopping when a cursor or a page repeats, rather than looping forever.

### 5.4 Error Handling

```
HTTP 401 → Re-authenticate (session auth) or report invalid API key
HTTP 403 → Permission denied — include space/page context in error
HTTP 404 → Resource not found — suggest checking ID/slug
HTTP 422 → Validation error — show server's error message
HTTP 429 → Rate limited — retry with backoff
HTTP 5xx → Server error — show status + suggest checking Docmost logs
```

---

## 6. Content Conversion

### 6.1 ProseMirror → Markdown

This is the critical path for `page get`. The converter must handle all Docmost node types:

| ProseMirror Node | Markdown Output |
|---|---|
| `paragraph` | Plain text with newlines |
| `heading` (level 1-6) | `#` through `######` |
| `bulletList` / `listItem` | `- item` |
| `orderedList` / `listItem` | `1. item` |
| `taskList` / `taskItem` | `- [ ]` / `- [x]` |
| `codeBlock` | ` ```lang\ncode\n``` ` |
| `blockquote` | `> text` |
| `horizontalRule` | `---` |
| `table` / `tableRow` / `tableCell` / `tableHeader` | GFM table syntax |
| `image` | `![alt](src)` |
| `hardBreak` | `\n` or `<br>` |
| `callout` | `> **{type}**: text` (custom convention) |
| `details` / `detailsSummary` / `detailsContent` | `<details>` HTML |
| `mathInline` / `mathBlock` | `$...$` / `$$...$$` |
| `embed` | Link to embedded URL |
| `drawio` / `excalidraw` | `[Diagram: type]` placeholder |
| **Marks** | |
| `bold` | `**text**` |
| `italic` | `*text*` |
| `code` | `` `text` `` |
| `strike` | `~~text~~` |
| `link` | `[text](href)` |
| `highlight` | `==text==` or passthrough |
| `underline` | `<u>text</u>` |

### 6.2 Markdown → ProseMirror

For `page create` and `page update`. Two strategies available:

1. **Preferred: Use Docmost's import endpoint** (`POST /pages/import`)
   — Send Markdown as a file, let Docmost's server do the conversion.
   This guarantees compatibility with all Docmost features.

2. **Fallback: Client-side conversion** — Parse Markdown into ProseMirror JSON
   using `markdown-it` style parsing. Only needed if the import endpoint is
   unavailable or insufficient (e.g., for partial content updates).

> **Implementation guidance**: Start with strategy 1 (import endpoint) for creating pages.
> For updates, use `POST /pages/content/update` if available (Enterprise v0.70+),
> which accepts Markdown directly. Build client-side MD→ProseMirror only if these
> server-side approaches prove insufficient.
>
> **Edition note**: The import endpoint (`POST /pages/import`) is the reliable
> cross-edition path for creating pages with Markdown content. Content updates
> via `POST /pages/content/update` may only be available on Enterprise edition.
> On Community edition, content replacement requires delete+recreate via import.

---

## 7. Output Strategy

The CLI follows the Unix convention: **data to stdout, messages to stderr**.
This makes every command composable and pipeable without parsing gymnastics.

There is **no global `--json` flag**. Each command category uses the output
format that makes the most sense for its data shape.

### 7.1 Content Commands (`page get`, `page export`)

**stdout**: Raw Markdown. Nothing else. This is the default and the primary mode.
Claude Code and humans both read Markdown natively — wrapping it in JSON would
mean escaped newlines, escaped quotes, and a mandatory parse step for no benefit.

```bash
# Just the content
docmost-cli page get abc123

# Pipe to a file
docmost-cli page get abc123 > page.md

# Pipe to another tool
docmost-cli page get abc123 | grep "TODO"
```

**`--meta` flag**: Prepends YAML frontmatter with page metadata. This is still
valid Markdown and parseable by any frontmatter-aware tool:

```markdown
---
id: 019a2a69-xxxx-xxxx-xxxx-xxxxxxxxxxxx
title: My Page
space: engineering
space_id: 019b3c8f-yyyy
created: 2026-01-15T09:30:00Z
updated: 2026-03-20T14:30:00Z
creator: georg@example.com
---

# My Page

Actual page content here...
```

**`--raw` flag**: Outputs the ProseMirror JSON instead of Markdown.
For debugging conversion issues or accessing node types the converter doesn't handle.

### 7.2 List / Search Commands (`page list`, `space list`, `search`, etc.)

**Default (human mode)**: `rich` formatted table to stdout.

```
ID                                    Title              Updated
────────────────────────────────────  ─────────────────  ──────────────
019a2a69-xxxx-xxxx-xxxx-xxxxxxxxxx    Getting Started    2026-03-20
019a2a69-yyyy-yyyy-yyyy-yyyyyyyyyyyy  API Reference      2026-03-18
```

The columns above are a curated display choice. They do **not** describe `--json`.

**`--json` flag** (per-command, not global): JSON array to stdout, where each
element is the **complete object the server returned**.
Available on: `page list`, `page children`, `page history`, `space list`,
`search`, `comment list`, `attachment search`, `workspace members`.

```json
[
  {
    "id": "019a2a69-xxxx", "slugId": "nGgQxxxx", "title": "Getting Started",
    "icon": null, "position": "a0V8f", "parentPageId": null,
    "creatorId": "019a1111-...", "lastUpdatedById": "019a1111-...",
    "spaceId": "019a2222-...", "workspaceId": "019a3333-...",
    "isLocked": false, "createdAt": "2026-03-01T09:00:00Z",
    "updatedAt": "2026-03-20T14:30:00Z", "contributorIds": ["019a1111-..."]
  }
]
```

Page **content** is not part of the list payload (it is absent from Docmost's
`baseFields`), so lossless listings stay small. Fetch a body with `page get <id>`.

Narrow the output with `--fields`, which projects JSON and replaces the table's
columns:

```console
$ docmost-cli page list eng --json --fields id,title,updatedAt
```

An unknown field name is a usage error (exit 2) listing the fields the server
actually returned — a typo would otherwise yield a silent column of nulls.

**Single-item commands** (`workspace info`, `user me`) also accept `--json`,
emitting the complete object. `config show --json` emits the configuration with
`api_key`/`password` masked exactly as the table does.

### 7.3 Write Commands (`page create`, `page update`, `page delete`, etc.)

**stdout**: Just the resource ID. Nothing else. This is capturable:

```bash
PAGE_ID=$(docmost-cli page create engineering --title "New Page" --file content.md)
echo "Created page: $PAGE_ID"
```

**stderr**: Human-friendly confirmation message (visible in terminal, not captured):

```
Created page 'New Page' in space 'engineering' (019a2a69-xxxx)
```

### 7.4 Error Output

Errors always go to stderr with a non-zero exit code:

```
Exit 0  — success
Exit 1  — general error (API error, network failure)
Exit 2  — usage error (missing arguments, invalid flags)
Exit 3  — authentication error
Exit 4  — resource not found
```

Error messages are human-readable on stderr:

```
Error: Page 'abc123' not found. Check the page ID and your permissions.
```

### 7.5 Implementation: Output Helpers

The `output/` module provides helper functions that enforce this pattern:

```python
# Content output — raw to stdout
def print_content(content: str) -> None:
    """Print content (Markdown) directly to stdout."""
    sys.stdout.write(content)

# Metadata-enriched content — frontmatter + content to stdout
def print_content_with_meta(content: str, meta: dict) -> None:
    """Print YAML frontmatter + Markdown content to stdout."""

# The single JSON writer — every --json path goes through it
def print_json(payload: Any) -> None:
    """Print a JSON document to stdout."""

# List output — table (default) or JSON (--json) to stdout.
# `columns` is a display choice: it never narrows JSON. `fields` projects both.
def print_table(
    rows: list[dict[str, Any]],
    columns: list[str],
    json_mode: bool = False,
    *,
    meta: dict[str, Any] | None = None,
    fields: list[str] | None = None,
) -> None:
    """Print as a Rich table or JSON depending on mode."""

# Write result — ID to stdout, message to stderr
def print_result(resource_id: str, message: str) -> None:
    """Print resource ID to stdout, confirmation to stderr."""
    sys.stdout.write(resource_id + "\n")
    sys.stderr.write(message + "\n")

# Error — message to stderr, set exit code
def print_error(message: str, exit_code: int = 1) -> NoReturn:
    """Print error to stderr and exit."""
```

---

## 8. Implementation Phases

### Phase 1: Foundation (MVP)
- [x] Project scaffolding (pyproject.toml, src layout, typer app)
- [x] Configuration system (config file, env vars, profiles)
- [x] HTTP client with auth (API key + session, auto-detect)
- [x] Output helpers (stdout/stderr separation, table/JSON/content modes)
- [x] `docmost-cli config init` / `config test`
- [x] `docmost-cli space list` (with `--json`)
- [x] `docmost-cli page list <space>` (with `--json`)
- [x] `docmost-cli page get <id>` with ProseMirror→Markdown conversion (with `--meta`)
- [x] `docmost-cli search <query>` (with `--json`)
- [x] Basic error handling with exit codes

### Phase 2: Write Operations
> **Edition-aware**: All write operations use frontend-internal endpoints (both editions).
> `page update --content` gracefully degrades on Community edition with a clear error
> message suggesting the delete+recreate workflow.
- [x] `docmost-cli page create` (via import endpoint — both editions)
- [x] `docmost-cli page update` (title: both editions; content: Enterprise only, graceful fallback)
- [x] `docmost-cli page delete` (with confirmation — both editions)
- [x] `docmost-cli page move` (both editions)
- [x] `docmost-cli space list` / `space create` / `space update` (both editions)
- [x] `docmost-cli comment` CRUD (both editions)

### Phase 3: Advanced Features
- [x] `docmost-cli page duplicate` / `page copy`
- [x] `docmost-cli page children` (with `--json`) / `page history` (with `--json`)
- [x] `docmost-cli page export` / `page import`
- [x] `docmost-cli attachment search` / `attachment upload`
- [x] `docmost-cli workspace` / `docmost-cli user`
- [x] Tree view (`--tree`) for page listing
- [x] Pagination auto-follow for full listings

### Phase 4: Polish
- [x] Comprehensive test suite (unit + integration)
- [x] Retry with exponential backoff
- [x] Tab completion (typer built-in)
- [x] `--verbose` HTTP debug logging
- [x] PyPI packaging and distribution
- [x] Man pages in `man/man1/` (one hub + one per command group)

### Phase 5: Sync
- [x] `sync/manifest.py` — manifest load/save, content hashing, filename sanitization
- [x] `sync/frontmatter.py` — YAML frontmatter parse/serialize (no PyYAML dependency)
- [x] `sync/pull.py` — pull algorithm (tree → flatten → fetch content → write files)
- [x] `sync/push.py` — push algorithm (diff → create/update/move)
- [x] `sync/diff.py` — change detection (new, modified, moved, deleted)
- [x] `cli/sync_cmd.py` — `sync pull`, `sync push`, `sync status` commands
- [x] Tests for all sync modules (96 sync tests + 9 CLI tests)

### Phase 6: Community gap fixes (0.5.0)
- [x] `models/common.py` — `PaginationMeta` / `PaginatedResult` pydantic models
- [x] Fix `get_cursor()` to read `data.meta.nextCursor` (it read `data.cursor`,
      so it always returned `None` and auto-follow never ran)
- [x] `paginate_all` / `paginate_iter` wired into every list command, with
      repeated-cursor and repeated-page guards
- [x] `--limit` / `--page-size` / `--cursor` / `--no-follow` / `--envelope` on
      all eight list commands
- [x] `page children` pagination (server default page size is 20)
- [x] Paginate the internal callers: `_find_space_by_slug` (slug resolution
      failed past page 1), `build_page_tree` / `_fill_children` (`sync pull`
      fetched an incomplete tree)
- [x] `api/position.py` — base62 fractional indexing with jitter, so
      `page move` always sends the required 5-12 character `position`
- [x] `page move --position first|last|<key>` and `--root`
- [x] In-place content updates via `POST /pages/update`, with a capability
      signal that detects a server silently ignoring the content
- [x] `page update --append` / `--prepend`
- [x] `sync push --allow-recreate` — delete+recreate is opt-in, never silent
- [x] `sync push` saves the manifest even when a phase aborts
- [x] `--version` / `-V` and a `version` subcommand; single-source version
- [x] `--no-session-cache`, `DOCMOST_NO_SESSION_CACHE`, `config logout`

---

## 9. CLAUDE.md Instructions

The following content should go into `CLAUDE.md` at the repo root.
Claude Code reads this file automatically when working in the project.

```markdown
# CLAUDE.md — Project Instructions for Claude Code

## Project
This is `docmost-cli`, a Python CLI tool for Docmost wiki management.
Read SPECIFICATION.md for the full project spec.

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
- Use type hints everywhere (Python 3.11+ syntax)
- Docstrings on all public functions (Google style)
- Keep CLI commands thin — business logic in api/ and convert/ modules
- Use pydantic models for all API request/response types
- httpx client should be created once and reused (connection pooling)
- All API calls go through DocmostClient — never raw httpx in CLI layer

## Architecture Rules
- `cli/` depends on `api/` and `output/` — never the reverse
- `api/` depends on `models/` and `config/` — never on `cli/`
- `convert/` is standalone — no dependencies on other internal modules
- `output/` formats data — no API calls, no business logic

## Testing Approach
- Unit tests for conversion (ProseMirror ↔ Markdown) using fixture files
- Unit tests for API methods using pytest-httpx mocks
- CLI tests using typer's CliRunner
- Fixture files in tests/fixtures/ (paired .json + .md files)

## Important Patterns
- Auth auto-detection: check for api_key first, then email+password
- ProseMirror content: always convert to Markdown for display
- Pagination: iterate cursor-based pagination automatically
- Errors: catch httpx exceptions, translate to user-friendly messages
- Output: data to stdout, messages to stderr (Unix convention)
- Content commands: raw Markdown to stdout, --meta for YAML frontmatter
- List commands: rich table by default, --json flag for JSON array
- Write commands: resource ID to stdout, confirmation to stderr
- Confirmations: destructive ops prompt unless `--yes` is passed
```

---

## 10. Reference Implementations

These existing projects provide valuable reference code and patterns:

1. **MrMartiniMo/docmost-mcp** (TypeScript)
   - Best reference for ProseMirror→Markdown conversion
   - Shows all Docmost TipTap extensions and their structure
   - Uses WebSocket for page content updates
   - URL: https://github.com/MrMartiniMo/docmost-mcp

2. **aleksvin8888/local-docmost-mcp** (Python)
   - Proves the Python approach works
   - Shows session-based auth with JWT caching
   - ProseMirror→Markdown converter in Python
   - URL: https://github.com/aleksvin8888/local-docmost-mcp

3. **Docmost official MCP documentation**
   - Authoritative list of supported MCP tools (maps to API endpoints)
   - URL: https://docmost.com/docs/user-guide/mcp

4. **Docmost API docs** (Enterprise, Scalar/OpenAPI UI)
   - URL: https://docmost.com/api-docs
   - Note: The API docs page uses a JS-rendered UI (Scalar). The OpenAPI spec
     may be available at a JSON endpoint — try to fetch it during implementation.

5. **Docmost source code**
   - The server-side API routes live in `apps/server/src/`
   - URL: https://github.com/docmost/docmost
   - Key directories to study: controllers, services, DTOs

---

## 11. Open Questions & Discovery Tasks

These items need investigation during implementation. Update this section as answers are found.

> **Strategy for unresolved questions**: The CLI attempts REST endpoints first and
> degrades gracefully with clear error messages if unavailable. This avoids blocking
> implementation on answers that can only come from live testing.

- [x] **Content update endpoint**: Does `POST /pages/content/update` accept raw
      Markdown on Community edition, or is it Enterprise-only?
      *Resolved (0.5.0)*: Neither — **that endpoint does not exist in Docmost**,
      which is why it 404s. Content updates go through `POST /pages/update` with
      `{content, format: "markdown", operation: "replace"}`, available on both
      editions from v0.71. Verified against the v0.95.0 server source.
- [ ] **OpenAPI spec**: Is there a downloadable OpenAPI/Swagger JSON at
      `https://instance/api-docs/openapi.json` or similar? This would allow
      auto-generating type stubs.
- [x] **WebSocket for content updates**: Is a Hocuspocus/Y.js WebSocket client
      required for content changes?
      *Resolved (0.5.0)*: No. `PageService.update()` calls `updatePageContent()`,
      which dispatches `collaborationGateway.handleYjsEvent('updatePageContent',
      'page.<id>', …)` — **the server performs the Yjs write**. REST is
      sufficient; no WS client, no CRDT dependency.
- [ ] **Rate limiting**: Does Docmost implement rate limiting? If so, what are the limits?
- [x] **Attachment upload**: *Resolved*: `POST /files/upload` (multipart, fields
      `file` + `pageId`) is the undocumented endpoint the web editor uses for
      inline images and attachments. The page-embeddable URL is
      `/api/files/{id}/{fileName}`. Wired up as
      `docmost-cli attachment upload <page-id> --file <path>`.

      Verified against Docmost Community on 2026-07-28: it returns the
      attachment row **bare, without** the `{success, status, data}` envelope
      every other endpoint uses. Observed keys:

      ```
      aiChatId, createdAt, creatorId, deletedAt, fileExt, fileName, filePath,
      fileSize, id, mimeType, pageId, spaceId, type, updatedAt, workspaceId
      ```

      `build_attachment_url()` still routes through `unwrap_data()`, so it keeps
      working if the endpoint is ever brought under the standard interceptor.
      That costs nothing and the endpoint is undocumented, so its shape is not
      contractual.
- [x] **Space slug vs ID**: Some endpoints accept slug, others require ID.
      *Resolved*: `resolve_space_id()` helper in `api/spaces.py` calls
      `POST /spaces/info` with `{spaceSlug: slug}` and returns the ID.
- [ ] **Comment content format**: Does the comment API accept plain text or require
      ProseMirror JSON? *Current approach*: Send content as provided; wrap in
      minimal ProseMirror JSON if API rejects plain text.
- [ ] **Import endpoint field names**: Verify exact multipart field names for
      `POST /pages/import` (e.g., `file` vs `uploadFile`, `spaceId` field name).
