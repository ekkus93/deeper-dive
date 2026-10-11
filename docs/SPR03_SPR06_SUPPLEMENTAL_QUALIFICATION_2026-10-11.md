# SPR-03 / SPR-06 supplemental qualification evidence

This note records partial second post-review remediation evidence; it does **not** close the authoritative TODO.

- SPR-03: `guided_async_readiness.py` handles a closed Textual message pump raising `RuntimeError` as a rejected dispatch. Completion and timeout callers close the coordinator, releasing timers and pending callbacks. `tests/test_second_post_review_readiness_closed_pump.py` covers direct dispatch, completion and timeout.
- SPR-06: `diagnostics.py` inspects bounded decoding of nested URL query values before redaction. `tests/test_second_post_review_nested_url_redaction.py` covers nested sensitive query keys, double encoding and preservation of benign nested URLs.
- Qualified source/test head: `e1e5c25419d879aa60e411244af2a7c550891974`.
- [CI #2542](https://github.com/ekkus93/deeper-dive/actions/runs/38114310041) passed: quality job `114396040904` (**1,287 tests passed**, Ruff, mypy, build, CLI smoke); fresh-machine job `114396041107` (installed-wheel acceptance and real KittenTTS Micro CPU smoke).
- Remaining: full SPR-03 transport-deadline and responsiveness matrix, full SPR-06 nested userinfo/fragment and CLI/TUI canary matrix, independent review and final TODO reconciliation.

Documentation-only updates also require their own exact-head CI before qualification.
