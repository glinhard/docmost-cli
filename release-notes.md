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
