"""Production dependency composition for Deeper Dive surfaces."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deeper_dive import model_roles
from deeper_dive.application.events import ProgressSink
from deeper_dive.application.service import DeeperDiveService
from deeper_dive.audio_playback import AudioPlaybackBackend, AudioPlaybackController
from deeper_dive.audio_timeline import AudioTimeline, AudioTimelineRepository, TimelineItem
from deeper_dive.director_decision import DirectorDecision
from deeper_dive.domain.clock import SystemClock, format_timestamp
from deeper_dive.domain.ids import new_run_id
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.episode_planner import EpisodePlanGenerator, EpisodePlannerService
from deeper_dive.export import EpisodeExporter
from deeper_dive.generation_monitor import GenerationMonitorController
from deeper_dive.host_turn import HostTurn, HostTurnService
from deeper_dive.host_turn_llm import LLMHostTurnProvider
from deeper_dive.llm import LLMMessage, LLMProvider, LLMRequest
from deeper_dive.pipeline import (
    DEFAULT_STAGES,
    PipelineContext,
    PipelineOrchestrator,
    PipelineResult,
    StageHandler,
)
from deeper_dive.preflight import PreflightService
from deeper_dive.preflight_screen import PreflightController
from deeper_dive.provider_factory import ProviderBuildResult, ProviderFactory
from deeper_dive.provider_tui import ProviderController
from deeper_dive.research_controller import PersistentResearchController
from deeper_dive.research_execution import execute_research_gaps
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import HostEpisodeRepository
from deeper_dive.storage.run_repositories import GenerationRunRecord, GenerationRunRepository
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.targeted_repair import RepairRechecker, SummaryUpdater, TargetedRepairService, TurnRepairProvider
from deeper_dive.tts_benchmark import TTSBenchmarkService
from deeper_dive.tts_generation import TTS_ARTIFACT_STATUS_COMPLETE
from deeper_dive.user_config import UserConfigStore

# Formatting-only follow-up for PCG-001; production behavior remains on this branch.
