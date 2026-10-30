# Changelog

All notable changes to this skill are documented here.
This project follows [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-10-30

### Added

- `hermes-history` skill for Codex: find and read local Hermes Agent
  conversations by title, keyword, or date without copying session IDs.
- `discover`, `search`, and `read` subcommands backed by a single read-only
  SQLite connection (`mode=ro`) to the Hermes `state.db`.
- Display projection that reproduces Hermes' own transcript view: active rows
  plus compaction-archived rows (`active=0, compacted=1`), deduplicated by
  `display_order`, so pre-compaction turns are not silently dropped.
- Keyword and date filtering, bounded output, and JSON output for agent use.
- Standard library only: no Hermes process, model call, API key, or third-party
  package is required.
- 21 unit tests and a cross-platform CI matrix (Ubuntu, Windows, macOS;
  Python 3.10 and 3.13).
- Bilingual README (English and Simplified Chinese).

### Known limitations

- macOS and Linux execution has not been independently verified against a live
  Hermes database; only Windows was smoke-tested end to end.
- Reading is limited to the Hermes database on the local machine.
