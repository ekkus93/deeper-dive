"""Generation preflight checks for providers, sources, TTS, FFmpeg, and estimates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from deeper_dive.ffmpeg import FFmpegConfig, FFmpegError
from deeper_dive.hosts import HostProfile
from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.model_roles import ModelRoleAssignments, preflight_model_roles
from deeper_dive.tts import TTSProviderRegistry


class PreflightBlockedError(RuntimeError):
    """Raised when generation is attempted with a known hard blocker."""


@dataclass(frozen=True, slots=True)
class PreflightIssue:
    code: str
    message: str
    fatal: bool = True


@dataclass(frozen=True, slots=True)
class CloudPrice:
    """Explicit user/config supplied price per one million estimated output tokens."""

    provider: str
    model: str
    usd_per_million_output_tokens: float


@dataclass(frozen=True, slots=True)
class PreflightEstimate:
    target_minutes: float
    estimated_words: int
    estimated_output_tokens: int
    estimated_cloud_cost_usd: float | None
    cloud_cost_is_estimate: bool = True


@dataclass(frozen=True, slots=True)
class PreflightReport:
    issues: tuple[PreflightIssue, ...]
    estimate: PreflightEstimate

    @property
    def blockers(self) -> tuple[PreflightIssue, ...]:
        return tuple(issue for issue in self.issues if issue.fatal)

    @property
    def warnings(self) -> tuple[PreflightIssue, ...]:
        return tuple(issue for issue in self.issues if not issue.fatal)

    @property
    def ready(self) -> bool:
        return not self.blockers

    def require_ready(self) -> None:
        if self.blockers:
            summary = "; ".join(issue.message for issue in self.blockers)
            raise PreflightBlockedError(f"generation blocked by preflight: {summary}")


class PreflightService:
    """Perform deterministic checks before expensive generation begins."""

    def __init__(
        self, llm_registry: LLMProviderRegistry, tts_registry: TTSProviderRegistry
    ) -> None:
        self.llm_registry = llm_registry
        self.tts_registry = tts_registry

    def check(
        self,
        *,
        assignments: ModelRoleAssignments,
        hosts: tuple[HostProfile, ...],
        source_count: int,
        indexed_source_count: int,
        target_minutes: float,
        ffmpeg_executable: Path | None = None,
        words_per_minute: float = 150.0,
        cloud_prices: tuple[CloudPrice, ...] = (),
    ) -> PreflightReport:
        issues: list[PreflightIssue] = []
        role_result = preflight_model_roles(assignments, self.llm_registry)
        issues.extend(
            PreflightIssue("llm_assignment", item.message) for item in role_result.blockers
        )

        checked_llm: set[str] = set()
        for assignment in role_result.assignments.values():
            if assignment.provider in checked_llm:
                continue
            checked_llm.add(assignment.provider)
            health = self.llm_registry.get(assignment.provider).health()
            if not health.healthy:
                issues.append(
                    PreflightIssue(
                        "llm_unhealthy",
                        f"LLM provider {assignment.provider!r} is unhealthy: {health.message}",
                    )
                )

        if not hosts:
            issues.append(PreflightIssue("hosts_missing", "episode has no hosts"))
        checked_tts: set[str] = set()
        for host in hosts:
            try:
                provider, _voice = self.tts_registry.resolve_host(host)
            except (KeyError, ValueError) as exc:
                issues.append(PreflightIssue("tts_assignment", str(exc)))
                continue
            if provider.provider_id not in checked_tts:
                checked_tts.add(provider.provider_id)
                health = provider.health()
                if not health.healthy:
                    issues.append(
                        PreflightIssue(
                            "tts_unhealthy",
                            f"TTS provider {provider.provider_id!r} is unhealthy: {health.message}",
                        )
                    )

        if source_count <= 0:
            issues.append(PreflightIssue("sources_missing", "project has no included sources"))
        elif indexed_source_count < source_count:
            issues.append(
                PreflightIssue(
                    "sources_unindexed",
                    f"only {indexed_source_count} of {source_count} included sources are indexed",
                )
            )

        try:
            FFmpegConfig.detect(ffmpeg_executable)
        except FFmpegError as exc:
            issues.append(PreflightIssue("ffmpeg_unavailable", str(exc)))

        if target_minutes <= 0:
            issues.append(PreflightIssue("duration_invalid", "target duration must be positive"))
        if words_per_minute <= 0:
            raise ValueError("words_per_minute must be positive")
        estimated_words = max(0, round(target_minutes * words_per_minute))
        estimated_tokens = round(estimated_words / 0.75)
        explicit_prices = {(price.provider, price.model): price for price in cloud_prices}
        costs: list[float] = []
        for assignment in role_result.assignments.values():
            price = explicit_prices.get((assignment.provider, assignment.model))
            if price is not None:
                costs.append(price.usd_per_million_output_tokens * estimated_tokens / 1_000_000)
        estimate = PreflightEstimate(
            target_minutes=target_minutes,
            estimated_words=estimated_words,
            estimated_output_tokens=estimated_tokens,
            estimated_cloud_cost_usd=sum(costs) if costs else None,
        )
        return PreflightReport(tuple(issues), estimate)
