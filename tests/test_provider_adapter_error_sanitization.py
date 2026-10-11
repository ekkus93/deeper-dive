"""Regression coverage for unsupported adapter identifiers in public errors."""

from __future__ import annotations

import traceback

import pytest

from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.user_config import UserConfigStore


@pytest.mark.parametrize(
    "adapter",
    [
        "unsupported-adapter-marker",
        "unsupported-adapter-marker\nsecond-line",
        "https://example.test/path#unsupported-adapter-marker",
    ],
)
def test_untrusted_adapter_is_absent_from_public_errors(tmp_path, adapter: str) -> None:
    controller = ProviderController(
        UserConfigStore(tmp_path / "config.json"),
        LLMProviderRegistry(),
        {},
    )
    original = controller.config()

    for operation in (
        lambda: controller.configuration_fields(adapter),
        lambda: controller.save_provider("invalid", adapter),
    ):
        with pytest.raises(ValueError, match="unsupported provider adapter") as caught:
            operation()
        assert "unsupported-adapter-marker" not in str(caught.value)
        assert "unsupported-adapter-marker" not in "".join(
            traceback.format_exception(caught.value)
        )

    assert controller.config() == original
    assert not (tmp_path / "config.json").exists()
