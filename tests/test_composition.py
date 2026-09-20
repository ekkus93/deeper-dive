from __future__ import annotations

from deeper_dive.composition import ProductionComposition
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_production_composition_loads_persisted_providers(tmp_path) -> None:
    data_dir = tmp_path / "data"
    config_store = UserConfigStore(data_dir / "config.json")
    config_store.save(
        UserConfig(
            providers={
                "planner": ProviderConfig(provider_type="fake", default_model="fake-v1"),
                "speech": ProviderConfig(provider_type="fake-tts"),
            }
        )
    )

    composition = ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )

    assert composition.provider_controller.llm_registry.provider_ids() == ("planner",)
    assert tuple(composition.provider_controller.tts_providers) == ("speech",)
    assert composition.research_controller.database_for_project("abc").name == "project.db"
