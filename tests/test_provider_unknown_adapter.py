import pytest

from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.user_config import UserConfigStore


def test_adapter_errors_do_not_echo_unrecognized_values(tmp_path):
    controller = ProviderController(UserConfigStore(tmp_path / "config.json"), LLMProviderRegistry(), {})
    value = "not-a-real-adapter"
    with pytest.raises(ValueError) as caught:
        controller.configuration_fields(value)
    assert value not in str(caught.value)
    with pytest.raises(ValueError) as caught:
        controller.save_provider("bad", value)
    assert value not in str(caught.value)
