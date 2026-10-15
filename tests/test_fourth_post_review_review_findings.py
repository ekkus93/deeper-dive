"""Findings from the independent fourth-cycle review (FPR-910)."""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from pathlib import Path

import pytest
from test_generation_start import _episode

from deeper_dive.diagnostics import redact
from deeper_dive.episode_config import EpisodeConfiguration
from deeper_dive.generation_start import select_or_create_generation_run
from deeper_dive.storage.episode_errors import GenerationRunStillStopping
from deeper_dive.storage.run_repositories import GenerationRunRecord

CANARY = "CANARY9x"

LEAKS = {
    "later at in query": f"https://u:{CANARY}@h/x?e=a@b",
    "later at in query 2": f"https://u:{CANARY}@h/x?next=a@b&x=1",
    "username only, later at": f"https://{CANARY}@h/x?e=a@b",
    "scope path segment": f"redis://{CANARY}@h/@s/x",
    "amqp scope": f"amqp://{CANARY}@host.com/@s/x",
    "nothing after at": f"https://u:{CANARY}@",
    "non-ascii host": f"https://u:{CANARY}@éxample.com",
    "port only": f"https://u:{CANARY}@:80",
    "slash after at": f"https://u:{CANARY}@/x",
    "quote after at": f'{{"u": "https://u:{CANARY}@"}}',
    "long userinfo": f"https://u:{CANARY}{'x' * 3000}@h/x",
    "unquoted subscription key": f"subscription_key={CANARY}",
    "azure header": f"Ocp-Apim-Subscription-Key: {CANARY}",
    "private key": f"private_key={CANARY}",
    "camel private key": f"privateKey={CANARY}",
}


@pytest.mark.parametrize("name", sorted(LEAKS))
def test_review_leaks_are_redacted(name: str) -> None:
    assert CANARY not in str(redact(LEAKS[name])), name


def test_long_userinfo_stays_fast() -> None:
    text = "https://u:" + "x" * 200_000 + "@h/"
    start = time.perf_counter()
    redact(text)
    assert time.perf_counter() - start < 2.0


def test_paused_cancel_requested_run_does_not_block_a_new_run(tmp_path: Path) -> None:
    """A paused run is not executing, so it can never reach the stage boundary."""

    service, project_id, episode_id = _episode(tmp_path)
    paused = GenerationRunRecord(
        "paused-1",
        episode_id,
        "sources",
        "paused",
        "2026-01-01T00:00:00Z",
        "2026-01-01T00:00:00Z",
        cancel_requested=True,
    )
    service.runs(project_id).create(paused)
    result = select_or_create_generation_run(service, project_id, episode_id)
    assert result.created and result.run.id != paused.id


def test_still_stopping_message_says_how_to_finish_stopping(tmp_path: Path) -> None:
    service, project_id, episode_id = _episode(tmp_path)
    running = GenerationRunRecord(
        "running-1",
        episode_id,
        "sources",
        "running",
        "2026-01-01T00:00:00Z",
        "2026-01-01T00:00:00Z",
        cancel_requested=True,
    )
    service.runs(project_id).create(running)
    with pytest.raises(GenerationRunStillStopping, match="episode cancel"):
        select_or_create_generation_run(service, project_id, episode_id)


@pytest.mark.parametrize("audience", ["[/x]", "[/]", "a [link=http://x]b[/link]", "[on-call]"])
def test_markup_in_a_custom_audience_does_not_crash_the_guided_form(
    tmp_path: Path, audience: str
) -> None:
    from guided_pilot import reach_hosts
    from textual.widgets import Select

    from deeper_dive.application.service import DeeperDiveService
    from deeper_dive.guided_app import GuidedDeeperDiveApp
    from deeper_dive.storage.workspace import WorkspaceManager

    async def run() -> None:
        app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
        async with app.run_test(size=(100, 45)) as pilot:
            await reach_hosts(pilot)
            wizard = app.screen
            wizard._show_audience(audience)
            assert app.is_running
            assert wizard.query_one("#guided-episode-audience", Select).value == audience

    asyncio.run(run())


def test_malformed_override_values_raise_value_error() -> None:
    config = EpisodeConfiguration(title="T")
    for bad in (
        replace(config, model_overrides={"llm": {"model": None}}),  # type: ignore[dict-item]
        replace(config, model_overrides={"llm": None}),  # type: ignore[dict-item]
        replace(config, source_overrides={"s1": "false"}),  # type: ignore[dict-item]
    ):
        with pytest.raises(ValueError):
            bad.normalized()
    ok = replace(config, source_overrides={" s1 ": True}, model_overrides={"llm": {"model": " m "}})
    assert ok.normalized().model_overrides == {"llm": {"model": "m"}}
