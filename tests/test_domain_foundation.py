from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from deeper_dive.domain.clock import FrozenClock, format_timestamp, parse_timestamp
from deeper_dive.domain.errors import (
    AppError,
    ConfigurationError,
    ProviderError,
    RecoverableError,
    StorageError,
    UserError,
)
from deeper_dive.domain.ids import (
    new_chunk_id,
    new_episode_id,
    new_host_id,
    new_project_id,
    new_run_id,
    new_source_id,
    new_turn_id,
    parse_chunk_id,
    parse_episode_id,
    parse_host_id,
    parse_project_id,
    parse_run_id,
    parse_source_id,
    parse_turn_id,
)


@pytest.mark.parametrize(
    ("factory", "parser"),
    [
        (new_project_id, parse_project_id),
        (new_source_id, parse_source_id),
        (new_chunk_id, parse_chunk_id),
        (new_host_id, parse_host_id),
        (new_episode_id, parse_episode_id),
        (new_turn_id, parse_turn_id),
        (new_run_id, parse_run_id),
    ],
)
def test_ids_round_trip_in_canonical_uuid_form(factory, parser) -> None:  # type: ignore[no-untyped-def]
    value = factory()
    assert str(UUID(value)) == value
    assert parser(value) == value


def test_id_parser_rejects_noncanonical_uuid() -> None:
    value = str(new_project_id()).upper()
    with pytest.raises(ValueError, match="canonical UUID"):
        parse_project_id(value)


def test_frozen_clock_is_deterministic_and_normalizes_to_utc() -> None:
    local = datetime(2026, 9, 17, 12, 34, 56, 123456, tzinfo=timezone(timedelta(hours=-7)))
    clock = FrozenClock(local)
    expected = datetime(2026, 9, 17, 19, 34, 56, 123456, tzinfo=UTC)
    assert clock.now() == expected
    assert clock.now() == expected


def test_timestamp_serialization_round_trip_is_canonical_utc() -> None:
    local = datetime(2026, 9, 17, 12, 34, 56, 123456, tzinfo=timezone(timedelta(hours=-7)))
    serialized = format_timestamp(local)
    assert serialized == "2026-09-17T19:34:56.123456Z"
    assert parse_timestamp(serialized) == datetime(2026, 9, 17, 19, 34, 56, 123456, tzinfo=UTC)


def test_timestamp_helpers_reject_naive_values() -> None:
    naive = datetime(2026, 9, 17, 12, 0, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        FrozenClock(naive)
    with pytest.raises(ValueError, match="timezone-aware"):
        format_timestamp(naive)
    with pytest.raises(ValueError, match="include a timezone"):
        parse_timestamp("2026-09-17T12:00:00")


@pytest.mark.parametrize(
    "error_type",
    [UserError, ConfigurationError, ProviderError, StorageError, RecoverableError],
)
def test_expected_error_categories_share_app_error_base(error_type: type[AppError]) -> None:
    assert issubclass(error_type, AppError)
    assert isinstance(error_type("boom"), AppError)
