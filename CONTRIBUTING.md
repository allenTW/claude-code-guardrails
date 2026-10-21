# Contributing

Issues and pull requests are welcome.

## Run the tests

```bash
python3 -m pip install pytest      # only the tests need it
python3 -m pytest -q tests
```

The hooks target Python 3.9 and use the standard library only, so please keep `match` statements, `X | Y` type unions and third-party imports out of `guardrails/`.

## Pull request rules

- Keep a PR to one change. Describe what it blocks or allows and why.
- Add or update a test in `tests/` for every behaviour change. Do not delete or weaken an existing test.
- Tests must not touch the network, your real home directory, or real logs: use `tmp_path` and `monkeypatch` (the existing tests show how to point `GUARDRAILS_HOME` at a temporary folder).
- Hooks must keep failing open: any unexpected error means "allow", never a stuck session.
- No new dependencies. No secrets, personal paths or screenshots in commits.
- If you change a message or default, update `docs/configuration.md` and `CHANGELOG.md`.
