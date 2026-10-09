"""Minimal, versioned wizard checkpoints referencing only durable production IDs."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from deeper_dive.guided_readiness import ProductionWizardCompletion
from deeper_dive.guided_workflow import WizardContext, WizardKind, WizardNavigator, WizardState

if TYPE_CHECKING:
    from deeper_dive.composition import ProductionComposition

_ID = re.compile(r"[a-zA-Z0-9_-]{1,128}\Z")
_MAX_DRAFT_BYTES = 8192


class GuidedDraftStore:
    """Store navigation hints, never source text, credentials, or business records."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def _path(self, kind: WizardKind) -> Path:
        return self.data_dir / f"guided-{kind.value}-draft.json"

    def save(self, context: WizardContext) -> None:
        record = {
            "wizard": context.state.to_record(),
            "project_id": context.project_id,
            "episode_id": context.episode_id,
            "run_id": context.run_id,
        }
        payload = json.dumps(record, sort_keys=True, separators=(",", ":"))
        if len(payload.encode("utf-8")) > _MAX_DRAFT_BYTES:
            raise ValueError("wizard checkpoint exceeds size limit")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.data_dir,
                prefix=".guided-draft-",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._path(context.state.kind))
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def load(
        self,
        composition: ProductionComposition,
        kind: WizardKind,
        *,
        recover: bool = True,
    ) -> WizardContext | None:
        path = self._path(kind)
        try:
            if path.is_symlink() or path.stat().st_size > _MAX_DRAFT_BYTES:
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or set(payload) != {
                "wizard",
                "project_id",
                "episode_id",
                "run_id",
            }:
                return None
            raw_wizard = payload["wizard"]
            if not isinstance(raw_wizard, dict):
                return None
            state = WizardState.from_record(raw_wizard)
            if state.kind is not kind:
                return None
            refs = (payload["project_id"], payload["episode_id"], payload["run_id"])
            if not all(
                ref is None or (isinstance(ref, str) and _ID.fullmatch(ref)) for ref in refs
            ):
                return None
            project_id, episode_id, run_id = refs
            if kind is WizardKind.FIRST_RUN:
                if any(ref is not None for ref in refs):
                    return None
                context = WizardContext(composition, state)
                if recover:
                    context.state = WizardNavigator(
                        state, ProductionWizardCompletion(context)
                    ).recovered_state()
                return context
            if project_id is None:
                return WizardContext(composition, state.moved_to("project"))
            try:
                project = composition.service.open_project(project_id)
            except (OSError, ValueError, KeyError):
                project = None
            if project is None:
                # A deleted project is not recoverable; a fresh project is a new flow.
                self.clear(kind)
                return None
            if episode_id is not None:
                episode = composition.service.hosts(project_id).get_episode(episode_id)
                if episode is None or episode.project_id != project_id:
                    episode_id, run_id = None, None
            if run_id is not None and (
                episode_id is None
                or (run := composition.service.runs(project_id).get(run_id)) is None
                or run.episode_id != episode_id
            ):
                run_id = None
            if run_id is not None:
                active_run = composition.service.runs(project_id).get(run_id)
                if active_run is not None and active_run.state == "completed":
                    # A crash before the Ready screen cleared its checkpoint must
                    # not offer a finished workflow as recoverable incomplete work.
                    self.clear(kind)
                    return None
            context = WizardContext(
                composition,
                state,
                project_id=project_id,
                episode_id=episode_id,
                run_id=run_id,
            )
            # A stored position is only a navigation hint: production readiness
            # decides whether earlier prerequisites still permit that position.
            context.state = WizardNavigator(
                state, ProductionWizardCompletion(context)
            ).recovered_state()
            return context
        except (OSError, ValueError, TypeError, KeyError, UnicodeError):
            return None

    def clear(self, kind: WizardKind) -> None:
        """Remove only the fixed checkpoint path, never a symlink's target."""
        self._path(kind).unlink(missing_ok=True)

    def has_resume(self, composition: ProductionComposition) -> bool:
        context = self.load(composition, WizardKind.NEW_DEEP_DIVE)
        if context is None:
            return False
        if context.project_id and context.run_id:
            run = composition.service.runs(context.project_id).get(context.run_id)
            if run is not None and run.state == "completed":
                return False
        return True
