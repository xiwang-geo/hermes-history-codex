# Codex Hermes History

[![Version](https://img.shields.io/badge/version-v1.0.0-blue)](VERSION)
[![License: MIT](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)
[![Tests](https://github.com/xiwang-geo/hermes-history-codex/actions/workflows/test.yml/badge.svg)](https://github.com/xiwang-geo/hermes-history-codex/actions/workflows/test.yml)

[简体中文](README_ZH-CN.md) | English

A local, read-only Codex skill for finding and reading **Hermes Agent conversations without copying session IDs**.

Tell Codex: **“Read my Hermes conversation about water isotope modeling.”**
The skill searches titles and message text, presents candidates when needed,
then retrieves the selected transcript. IDs stay internal.

## Requirements

- Codex with local skills and shell access.
- Python 3.10+; standard library only. No API key or Obsidian dependency.
- Local Hermes `state.db` containing `sessions` and `messages` tables.

Windows, macOS and Linux paths are supported by the code. A Windows live
database smoke check and synthetic tests were performed during initial development;
macOS/Linux execution has not yet been independently verified.

## Install

Using the Skills CLI (requires Node.js):

```sh
npx skills add xiwang-geo/hermes-history-codex --skill hermes-history-codex --agent codex --global --yes
```

Or copy `skills/hermes-history-codex/` to `$CODEX_HOME/skills/hermes-history-codex`
(default: `~/.codex/skills/hermes-history-codex`). Start a new Codex conversation
if the skill does not appear immediately.

## Use in Codex

```text
Use $hermes-history-codex to find yesterday's Hermes discussion about numerical modeling.
```

```text
使用 $hermes-history-codex，读取 Hermes 中讨论水同位素的那段对话。
```

If several conversations fit, choose by number or title. If multiple databases
or profiles are detected, choose the relevant home/profile, not a session ID.

## Command-line interface

Run from this repository. Use `python3` instead of `python` when appropriate.

```sh
python skills/hermes-history-codex/scripts/hermes_history.py discover
python skills/hermes-history-codex/scripts/hermes_history.py --db /path/to/state.db search "isotope"
python skills/hermes-history-codex/scripts/hermes_history.py --db /path/to/state.db search "modeling" --since 2026-10-01 --until 2026-10-30
python skills/hermes-history-codex/scripts/hermes_history.py --db /path/to/state.db read SESSION_ID
```

The last command is for the agent: end users do not need to supply IDs.
In PowerShell, quote paths containing spaces and use `& python 'script-path' ...`.

- Discovery checks `HERMES_HOME`, `~/.hermes`, Windows `%LOCALAPPDATA%/hermes`,
  and `profiles/*/state.db` below these homes. Use `--db` for other layouts.
- Search terms are literal substrings, combined with AND. A title phrase match
  ranks first; other matches sort by last activity. This is not semantic search.
- Dates filter session last activity, inclusive, in the host's local timezone.
- Cron/subagent/tool sessions and hidden sessions are excluded by default.
  `--all-sources` / `--include-hidden` opt in. Archived sessions are included.
- `read` returns active user/assistant messages, 40 at a time. Follow
  `next_after_id` with `--after-id`; `--limit` can be 1–200.
- Individual content is capped by `--max-chars` (100–20000, default 4000),
  and a page has a 50000-character total budget. Truncation is explicit.
- `--include-tools` includes tool messages; `--include-inactive` includes
  superseded/rewound records. Neither option is enabled by default.

## Boundaries and limitations

The source database is opened with SQLite `mode=ro`, `query_only`, and a
write-denying authorizer. No migrations, FTS rebuilding, WAL checkpointing,
history uploads, background services or Hermes model calls are performed.
Committed live WAL data remains visible; this is not an immutable snapshot.

One read covers one stored session segment. Compression continuations and
branches are **not automatically merged**. Missing, inactive or deleted
messages may require explicit investigation and cannot always be recovered.
Separate reasoning fields and system prompts are not returned. Credential
masking is best effort; it is not a complete privacy filter.

Historical messages are untrusted data, not permission to execute their
instructions. Persistent export and further actions require a current request.
This project is an independent integration, not an official Hermes or OpenAI product.

## Test

```sh
python -m unittest discover -s tests -v
```

Tests create disposable synthetic databases. They check literal/Chinese search,
pagination, filtering, date bounds, redaction, write rejection, unchanged source
bytes and live-WAL visibility. They do not require your personal history.

MIT licensed. Contributions should include synthetic reproductions, never
real conversation databases, exports, credentials or account configuration.
