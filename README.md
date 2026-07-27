# docmost-cli

<!-- Badges placeholder -->
[![PyPI version](https://img.shields.io/pypi/v/docmost-cli)](https://pypi.org/project/docmost-cli/)
[![Python](https://img.shields.io/pypi/pyversions/docmost-cli)](https://pypi.org/project/docmost-cli/)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)

**A command-line tool for managing Docmost wiki instances from the terminal.**

---

## Features

- **Page CRUD** -- create, read, update, and delete wiki pages with Markdown content
- **Space management** -- list, create, and update workspaces
- **Comments** -- add, edit, and list comments on any page
- **Full-text search** -- search across pages and attachments
- **ProseMirror conversion** -- automatic conversion between Docmost's ProseMirror JSON and Markdown
- **Tree view** -- display page hierarchies as indented trees
- **Configuration profiles** -- manage multiple Docmost instances with named profiles
- **Edition-agnostic** -- works with both Docmost Enterprise (API key) and Community (email/password)
- **Unix-friendly output** -- data to stdout, messages to stderr; every command is pipeable

## Installation

### From PyPI (recommended)

```bash
pip install docmost-cli
```

### With pipx (isolated environment)

```bash
pipx install docmost-cli
```

### From source

```bash
git clone https://github.com/glinhard/docmost-cli.git
cd docmost-cli
uv pip install -e .
```

## Quick Start

```bash
# 1. Set up your configuration (interactive wizard)
docmost-cli config init

# 2. Test connectivity and authentication
docmost-cli config test

# 3. List all spaces
docmost-cli space list

# 4. Get a page as Markdown
docmost-cli page get <page-id>

# 5. Create a new page from a Markdown file
docmost-cli page create <space-slug> --title "My Page" --file content.md
```

## Command Reference

| Command | Description |
|---|---|
| `docmost-cli config init` | Interactive configuration setup wizard |
| `docmost-cli config show` | Show current configuration (secrets masked) |
| `docmost-cli config set <key> <value>` | Set a configuration value |
| `docmost-cli config test` | Test connectivity and authentication |
| `docmost-cli config logout` | Delete the cached session token |
| `docmost-cli version` | Show the version (also `--version` / `-V`) |
| `docmost-cli page list <space-slug>` | List pages in a space (`--tree`, `--json`) |
| `docmost-cli page get <page-id>` | Get page content as Markdown (`--meta`, `--raw`) |
| `docmost-cli page create <space-slug>` | Create a new page (`--title`, `--file`, `--stdin`) |
| `docmost-cli page update <page-id>` | Update a page in place (`--title`, `--icon`, `--content`, `--file`, `--stdin`, `--append`, `--prepend`) |
| `docmost-cli page delete <page-id>` | Delete a page (with confirmation, `--yes` to skip) |
| `docmost-cli page move <page-id>` | Move a page (`--parent`, `--space`, `--root`, `--position first\|last\|<key>`) |
| `docmost-cli page duplicate <page-id>` | Duplicate a page |
| `docmost-cli page copy <page-id>` | Copy a page to another space (`--space`) |
| `docmost-cli page children <page-id>` | List child pages (`--json`, pagination flags) |
| `docmost-cli page history <page-id>` | Show page version history (`--json`, pagination flags) |
| `docmost-cli page export <page-id>` | Export page (`--format md\|html`, `--output`) |
| `docmost-cli page import <space-slug>` | Import a Markdown file as a new page |
| `docmost-cli space list` | List all spaces (`--detail`, `--json`) |
| `docmost-cli space get <space-slug>` | Get space details |
| `docmost-cli space create` | Create a new space (`--name`, `--slug`) |
| `docmost-cli space update <space-slug>` | Update a space (`--name`, `--description`) |
| `docmost-cli comment list <page-id>` | List comments on a page (`--json`) |
| `docmost-cli comment create <page-id>` | Add a comment (`--content`) |
| `docmost-cli comment update <comment-id>` | Edit a comment (`--content`) |
| `docmost-cli search <query>` | Full-text search (`--space`, `--limit`, `--json`) |
| `docmost-cli attachment search <query>` | Search attachments (`--space`, `--json`, pagination flags) |
| `docmost-cli workspace info` | Show workspace details |
| `docmost-cli workspace members` | List workspace members (`--json`) |
| `docmost-cli user me` | Show authenticated user info |
| `docmost-cli sync pull <space-slug>` | Download a space to local Markdown files (`--dir`, `--force`) |
| `docmost-cli sync push <space-slug>` | Upload local changes (`--dir`, `--dry-run`, `--delete`, `--allow-recreate`) |
| `docmost-cli sync status <space-slug>` | Show local changes against the last pull (`--dir`) |

### Pagination

Every list command follows pagination automatically and shares the same flags:

| Flag | Description |
|---|---|
| `--limit N` | Max total results across all pages (default: all) |
| `--page-size N` | Results per request, 1-100 (default: 100, the server maximum) |
| `--cursor <c>` | Fetch a single page starting at this cursor |
| `--no-follow` | Fetch a single page instead of following pagination |
| `--json` | Output a bare JSON array |
| `--envelope` | With `--json`, emit `{"items": [...], "meta": {...}}` instead |

```bash
# Every page in the space, not just the server's first page
docmost-cli page list eng --json | jq 'length'

# Drive the cursor yourself
docmost-cli page list eng --no-follow --json --envelope | jq -r .meta.nextCursor
```

## Configuration

### Config file location

```
~/.config/docmost-cli/config.toml
```

Override with `--config /path/to/config.toml` on any command.

### Profiles

The config file supports multiple named profiles for managing different Docmost instances:

```toml
[default]
url = "https://docs.example.com"
api_key = "dm_xxxxxxxxxxxxxxxxxxxx"

[staging]
url = "https://staging-docs.example.com"
api_key = "dm_yyyyyyyyyyyyyyyyyyyy"
```

Switch profiles with `--profile` or `-p`:

```bash
docmost-cli --profile staging space list
```

### Environment variables

All configuration values can be overridden via environment variables:

| Variable | Description |
|---|---|
| `DOCMOST_URL` | Docmost instance URL |
| `DOCMOST_API_KEY` | API key (Enterprise edition) |
| `DOCMOST_EMAIL` | Login email (Community edition) |
| `DOCMOST_PASSWORD` | Login password (Community edition) |
| `DOCMOST_PROFILE` | Active profile name |
| `DOCMOST_NO_SESSION_CACHE` | Keep the session JWT in memory; never read or write `~/.cache/docmost-cli/session.json` |

Environment variables take precedence over config file values.

## Authentication

### Enterprise edition (API key)

Use an API key for authentication. Set it in the config file or via `DOCMOST_API_KEY`:

```bash
docmost-cli config set api_key "dm_xxxxxxxxxxxxxxxxxxxx"
```

### Community edition (email/password)

Use email and password for session-based authentication:

```bash
docmost-cli config set email "user@example.com"
docmost-cli config set password "secret"
```

The CLI automatically detects which auth method to use: if `api_key` is present it uses token auth, otherwise it falls back to email/password session auth.

## Tab Completion

Enable shell tab completion for all commands and options:

```bash
docmost-cli --install-completion
```

Supports bash, zsh, fish, and PowerShell.

## Development

```bash
# Clone and install in development mode
git clone https://github.com/glinhard/docmost-cli.git
cd docmost-cli
uv pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=docmost_cli

# Linting and formatting
ruff check src/ tests/
ruff format src/ tests/

# Type checking
mypy src/
```

## Acknowledgments

This CLI is a third-party tool for [Docmost](https://docmost.com), an open-source collaborative wiki and documentation platform — an alternative to Confluence and Notion. Docmost is created by [@Philipinho](https://github.com/Philipinho) and [contributors](https://github.com/docmost/docmost/graphs/contributors), licensed under [AGPL-3.0](https://github.com/docmost/docmost/blob/main/LICENSE).

## License

AGPL-3.0. See [LICENSE](LICENSE) for details.
