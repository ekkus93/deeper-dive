"""Guided draft lifecycle and optional host edit regression tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

from textual.widgets import Input

from deeper_dive.guided_draft import GuidedDraftStore
from deeper_dive.guided_host_wizard import GuidedHostWizard
from deeper_dive.guided_workflow import WizardKind
from deeper_dive.hosts import HostProfile


def test_checkpoint_clear_removes_only_checkpoint_file(tmp_path: Path) -> None:
    store = GuidedDraftStore(tmp_path)
    path = store._path(WizardKind.NEW_DEEP_DIVE)
    path.write_text("draft", encoding="utf-8")
    store.clear(WizardKind.NEW_DEEP_DIVE)
    assert not path.exists()
    store.clear(WizardKind.NEW_DEEP_DIVE)


def test_checkpoint_clear_does_not_follow_symlink(tmp_path: Path) -> None:
    store = GuidedDraftStore(tmp_path)
    target = tmp_path / "unrelated-data"
    target.write_text("keep", encoding="utf-8")
    link = store._path(WizardKind.NEW_DEEP_DIVE)
    link.symlink_to(target)
    store.clear(WizardKind.NEW_DEEP_DIVE)
    assert target.read_text(encoding="utf-8") == "keep"
    assert not link.is_symlink()


def test_edit_host_form_can_clear_optional_role_and_instructions() -> None:
    host = HostProfile(
        id="h", project_id="p", display_name="Existing",
        role="Host role", instructions="Old instructions",
    )
    values = {
        "#guided-host-name": "Existing",
        "#guided-host-role": "",
        "#guided-host-expertise": "",
        "#guided-host-instructions": "",
    }

    class FakeWizard:
        def query_one(self, selector: str, _widget_type: type[Input]) -> SimpleNamespace:
            return SimpleNamespace(value=values[selector])

    GuidedHostWizard._apply_host_form(
        cast(GuidedHostWizard, FakeWizard()), host, clear_optional=True
    )
    assert host.role == ""
    assert host.instructions == ""
    assert host.to_record().role == ""


def test_create_host_form_keeps_preset_text_when_controls_blank() -> None:
    host = HostProfile(
        id="h", project_id="p", display_name="Existing",
        role="Preset role", instructions="Preset instructions",
    )
    values = {
        "#guided-host-name": "",
        "#guided-host-role": "",
        "#guided-host-expertise": "",
        "#guided-host-instructions": "",
    }

    class FakeWizard:
        def query_one(self, selector: str, _widget_type: type[Input]) -> SimpleNamespace:
            return SimpleNamespace(value=values[selector])

    GuidedHostWizard._apply_host_form(cast(GuidedHostWizard, FakeWizard()), host)
    assert host.role == "Preset role"
    assert host.instructions == "Preset instructions"
