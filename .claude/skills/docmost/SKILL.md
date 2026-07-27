---
name: docmost
description: "Read, create, update, and search Docmost wiki pages. Use when the user wants to interact with their Docmost wiki -- reading documentation, creating pages, searching for information, or updating content."
argument-hint: "[action] [details]"
allowed-tools: "Bash(docmost-cli *)"
---

# Docmost Wiki Interaction

You have access to `docmost-cli`, a CLI tool for managing Docmost wiki instances. Use it to read, create, update, search, and manage wiki content.

## Prerequisites

The user must have `docmost-cli` installed and configured (`docmost-cli config init`). Test with `docmost-cli config test` if unsure.

## Command Reference

### Reading Content

```bash
# List all spaces
docmost-cli space list --json

# List pages in a space
docmost-cli page list <space-slug> --json

# Get page content as Markdown
docmost-cli page get <page-id>

# Get page with YAML frontmatter (id, title, space, dates)
docmost-cli page get <page-id> --meta

# Search across all pages
docmost-cli search query "<search-term>" --json

# Search within a specific space
docmost-cli search query "<search-term>" --space <space-slug> --json

# Show page tree structure
docmost-cli page list <space-slug> --tree
```

### Writing Content

```bash
# Create a page from inline Markdown
docmost-cli page create <space-slug> --title "Page Title" --content "# Heading\n\nContent here"

# Create a page from a file
docmost-cli page create <space-slug> --title "Page Title" --file content.md

# Update page title
docmost-cli page update <page-id> --title "New Title"

# Delete a page (use -y to skip confirmation)
docmost-cli -y page delete <page-id>
```

### Other Operations

```bash
# Show current user info
docmost-cli user me

# Show workspace details
docmost-cli workspace info

# Add a comment to a page
docmost-cli comment create <page-id> --content "Comment text"

# List comments on a page
docmost-cli comment list <page-id> --json

# Export a page
docmost-cli page export <page-id> --format md
```

## Workflow Patterns

### Finding and Reading a Page

1. List spaces: `docmost-cli space list --json`
2. Find the space slug you need
3. Search or list pages: `docmost-cli search query "topic" --json`
4. Read the page: `docmost-cli page get <page-id>`

### Creating Documentation for Code

1. Analyze the code the user wants documented
2. Write Markdown content
3. Save to a temp file or use `--content` flag
4. Create the page: `docmost-cli page create <space-slug> --title "Title" --content "..."`
5. Report the page ID back to the user

### Updating Existing Documentation

1. Get current content: `docmost-cli page get <page-id>`
2. Modify the Markdown content as needed
3. Update: `docmost-cli page update <page-id> --file updated.md`
4. Content updates are applied in place — the page keeps its ID, slug, history
   and inbound links. Works on Community and Enterprise alike, from Docmost
   v0.71. Use `--append` / `--prepend` to add without replacing.

## Output Format

- **Content commands** (`page get`): Raw Markdown to stdout — directly usable
- **List commands** (`--json`): JSON array — parse with standard JSON tools.
  Pagination is followed automatically, so the array is complete; add
  `--envelope` if you need `hasNextPage` / `nextCursor`
- **Write commands** (`page create`, `delete`): Page ID to stdout, confirmation to stderr
- **Always use `--json`** for list/search commands when you need to parse the output programmatically

## Tips

- Use `--json` flag on list commands to get parseable output
- Page IDs are UUIDs like `019a2a69-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
- Space slugs are lowercase alphanumeric (e.g., `engineering`, `devtest`)
- Use `-y` flag to skip confirmation prompts for automated workflows
- Use `--verbose` for debugging connectivity issues

For detailed examples, see [examples.md](examples.md).
