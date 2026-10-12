from __future__ import annotations

import pytest

from deeper_dive.provider_factory import ProviderConfigurationError, ProviderFactory
from deeper_dive.user_config import ProviderConfig, UserConfig


def test_factory_rejects_mutated_invalid_timeout() -> None:
    config = UserConfig(providers={"local": ProviderConfig(provider_type="fake")})
    config.providers["local"].timeout_seconds = -1
    with pytest.raises(ProviderConfigurationError):
        ProviderFactory(environ={}).build(config)
