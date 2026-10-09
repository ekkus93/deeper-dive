"""Post-review defaults and model-role parity regressions."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from deeper_dive.guided_readiness import _assignment_targets_ready_llm, _llm_runtime_ready
from deeper_dive.model_roles import ModelAssignment
from deeper_dive.provider_tui import ProviderController
from deeper_dive.quick_deep_dive import QuickDeepDiveDefaults, QuickDeepDiveService
from deeper_dive.research_policy import ResearchMode
from deeper_dive.user_config import ProviderConfig


def test_quick_research_inherits_first_run_global_default() -> None:
    defaults = QuickDeepDiveDefaults()
    assert (
        QuickDeepDiveService._apply_overrides(defaults, {"research_policy": "off"}).research_mode
        is ResearchMode.OFF
    )
    assert (
        QuickDeepDiveService._apply_overrides(
            defaults, {"research_policy": "aggressive"}
        ).research_mode
        is ResearchMode.AGGRESSIVE
    )


def test_quick_research_explicit_override_beats_global_default() -> None:
    defaults = QuickDeepDiveDefaults()
    values = {"research_policy": "off", "quick_deep_dive_research_policy": "useful"}
    assert (
        QuickDeepDiveService._apply_overrides(defaults, values).research_mode is ResearchMode.USEFUL
    )


def test_valid_non_default_discovered_model_is_ready() -> None:
    provider = ProviderConfig(provider_type="fake", default_model="model-a")
    controller = ProviderController.__new__(ProviderController)
    assert _assignment_targets_ready_llm(
        controller,
        {"planner": provider},
        {"planner": frozenset({"model-a", "model-b"})},
        ModelAssignment("planner", "model-b"),
    )
    assert not _assignment_targets_ready_llm(
        controller,
        {"planner": provider},
        {"planner": frozenset({"model-a", "model-b"})},
        ModelAssignment("planner", "unknown-model"),
    )


def test_blank_quick_override_does_not_hide_global_research_policy() -> None:
    defaults = QuickDeepDiveDefaults()
    values = {"research_policy": "aggressive", "quick_deep_dive_research_policy": " "}
    assert (
        QuickDeepDiveService._apply_overrides(defaults, values).research_mode
        is ResearchMode.AGGRESSIVE
    )


def test_discovered_role_model_is_eligible_even_if_provider_default_is_unavailable() -> None:
    runtime = SimpleNamespace(
        health=lambda: SimpleNamespace(healthy=True),
        models=lambda: [SimpleNamespace(model="model-b")],
    )
    controller = cast(
        ProviderController,
        SimpleNamespace(llm=lambda provider_name: runtime, capability=lambda adapter: "llm"),
    )
    discovered = _llm_runtime_ready(controller, "planner")
    assert discovered == frozenset({"model-b"})
    provider = ProviderConfig(provider_type="fake", default_model="model-a")
    assert _assignment_targets_ready_llm(
        controller,
        {"planner": provider},
        {"planner": discovered},
        ModelAssignment("planner", "model-b"),
    )
