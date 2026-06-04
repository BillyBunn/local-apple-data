---
name: Bug report
about: Report a reproducible problem without sharing private local data
title: ""
labels: bug
assignees: ""
---

## Summary


## Environment

- macOS version:
- Python version:
- Install method:
- MCP client:

## Surface

- [ ] Health/doctor
- [ ] Mail
- [ ] Messages
- [ ] Hide My Email inference
- [ ] Voice Memos
- [ ] Notes
- [ ] iCloud Drive
- [ ] Calendar
- [ ] Reminders
- [ ] Contacts
- [ ] Photos
- [ ] Packaging or install

## Reproduction

Use synthetic examples or redacted command shapes only. Do not paste live message text, note bodies, contact records, calendar details, file contents, aliases, handles, local paths, raw database rows, secrets, or screenshots containing private data.

```bash

```

## Expected Behavior


## Actual Behavior

Include warning codes and status fields where possible. Do not include raw private content or local store paths.


## Verification Already Run

- [ ] `uv run pytest`
- [ ] `uv run python scripts/redaction_scan.py .`
- [ ] `uv run python scripts/public_release_scan.py`
- [ ] `uv run python scripts/verify_runtime.py`
