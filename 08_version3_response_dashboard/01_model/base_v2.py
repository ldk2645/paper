"""Version 2: UK Parliament e-petition case-constrained ABM.

This module intentionally leaves the frozen Version 1 model untouched.  It
extends a byte-for-byte snapshot of V1 with one focal petition, cumulative
support, one-time institutional thresholds, a petition-specific response, and
an auditable event log.

The model provides two trigger modes which must not be conflated:

``observed_calendar``
    Replays the observed calendar milestones of petition 700024.  No numerical
    conversion from 10,000 real signatures to 300 simulated agents is made.

``synthetic_unique_support``
    Uses the fraction of simulated public agents who have signed once.  Its
    threshold is a counterfactual design parameter, not a UK estimate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

try:  # Works both as a package import and as a direct file-path import.
    from .base_v1 import (
        ReverseBlackBoxSimulation,
        SimulationConfig,
        SimulationResult,
    )
except ImportError:  # pragma: no cover - exercised by CLI/tests
    from base_v1 import (
        ReverseBlackBoxSimulation,
        SimulationConfig,
        SimulationResult,
    )


MODEL_VERSION = "2.0.0-uk-petition-case"
V1_FROZEN_SHA256 = (
    "AB78E6C64AFB6FD487E40A48FBBCD1B09A84EE3FBC9085530F8833DE3543D7EC"
)


@dataclass(frozen=True)
class UKPetitionConfig(SimulationConfig):
    """Configuration for the UK petition case-constrained Version 2 model."""

    # V1 parameters retained unless explicitly changed below.
    alpha: float = 0.50
    steps: int = 300
    population_size: int = 300
    topic_names: tuple[str, ...] = (
        "经济",
        "法治",
        "公共服务",
        "公众发起议题",
    )
    agenda_topic_indices: tuple[int, ...] = (0, 1, 2)
    response_delay: int = 22
    response_strength: float = 1.00  # Legacy field; V2 uses the explicit field below.

    # Version and clock semantics.
    model_version: str = MODEL_VERSION
    step_unit: str = "day"

    # Focal petition metadata and lifecycle.
    petition_id: str = "700024"
    petition_title: str = "Ban fossil fuel advertising and sponsorship"
    petition_topic_index: int = 3
    petition_open_step: int = 0
    petition_close_step: int = 182
    petition_initial_heat: float = 1.0
    petition_emotional_intensity: float = 0.65

    # Real institutional quantities are metadata in observed-calendar mode.
    real_response_threshold_signatures: int = 10_000
    real_debate_threshold_signatures: int = 100_000
    observed_initial_signatures: int = 5
    observed_response_threshold_step: int = 14
    observed_debate_threshold_step: int = 177
    observed_debate_step: int = 237
    observed_final_signatures: int = 110_519

    # Trigger mode: the two modes have deliberately different denominators.
    trigger_mode: str = "observed_calendar"
    synthetic_support_threshold_fraction: float | None = 0.20
    signature_probability_on_exposure: float = 0.02

    # Response publication, policy position, heat and trust are separate.
    response_disposition: str = "no_policy_change"
    response_heat_multiplier: float = 1.00
    direct_response_trust_signal: float = 0.00
    response_information_emotional_intensity: float = 0.15
    response_information_initial_heat: float = 0.0

    # Routine V1 government publication and topic-share triggering are disabled.
    enable_routine_government_publication: bool = False
    enable_legacy_topic_response: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.model_version != MODEL_VERSION:
            raise ValueError(f"model_version must be {MODEL_VERSION!r}")
        if self.step_unit != "day":
            raise ValueError("Version 2 currently requires step_unit='day'")
        if self.response_delay < 1:
            raise ValueError("response_delay must be at least one day")
        if not 0 <= self.petition_topic_index < self.topic_count:
            raise ValueError("petition_topic_index is outside topic_names")
        if self.petition_open_step < 0:
            raise ValueError("petition_open_step cannot be negative")
        if self.petition_close_step <= self.petition_open_step:
            raise ValueError("petition_close_step must follow petition_open_step")
        if self.petition_close_step >= self.steps:
            raise ValueError("steps must extend beyond petition_close_step")
        if self.trigger_mode not in {
            "observed_calendar",
            "synthetic_unique_support",
        }:
            raise ValueError(
                "trigger_mode must be observed_calendar or synthetic_unique_support"
            )
        if self.trigger_mode == "observed_calendar":
            if not (
                self.petition_open_step
                <= self.observed_response_threshold_step
                < self.petition_close_step
            ):
                raise ValueError("observed response threshold must occur while open")
            if not (
                self.observed_response_threshold_step
                < self.observed_debate_threshold_step
                < self.petition_close_step
            ):
                raise ValueError("observed debate threshold must occur while open")
        if self.trigger_mode == "synthetic_unique_support":
            threshold = self.synthetic_support_threshold_fraction
            if threshold is None or not 0.0 < threshold <= 1.0:
                raise ValueError(
                    "synthetic_unique_support requires a threshold in (0, 1]"
                )
        if not 0.0 <= self.signature_probability_on_exposure <= 1.0:
            raise ValueError("signature_probability_on_exposure must be in [0, 1]")
        if self.response_heat_multiplier < 0.0:
            raise ValueError("response_heat_multiplier cannot be negative")
        if not -1.0 <= self.direct_response_trust_signal <= 1.0:
            raise ValueError("direct_response_trust_signal must be in [-1, 1]")
        if self.response_disposition not in {
            "accepted",
            "partially_accepted",
            "no_policy_change",
        }:
            raise ValueError("invalid response_disposition")
        if self.real_response_threshold_signatures <= 0:
            raise ValueError("real response threshold must be positive")
        if (
            self.real_debate_threshold_signatures
            <= self.real_response_threshold_signatures
        ):
            raise ValueError("real debate threshold must exceed response threshold")
        if self.observed_initial_signatures < 0:
            raise ValueError("observed_initial_signatures cannot be negative")
        if self.observed_final_signatures < self.real_debate_threshold_signatures:
            raise ValueError("observed final signatures must reach debate threshold")

    @classmethod
    def case_700024(
        cls,
        *,
        alpha: float = 0.50,
        seed: int = 42,
        response_delay: int = 22,
        **overrides: Any,
    ) -> "UKPetitionConfig":
        """Build the documented petition-700024 case configuration."""

        return cls(
            alpha=alpha,
            seed=seed,
            response_delay=response_delay,
            **overrides,
        )

    def parameter_sources(self) -> dict[str, str]:
        """Return the evidence class of the important Version 2 parameters."""

        return {
            "petition_open_step": "case_700024_observed",
            "petition_close_step": "case_700024_observed_rounded",
            "observed_response_threshold_step": "case_700024_observed_rounded",
            "observed_debate_threshold_step": "case_700024_observed_rounded",
            "observed_debate_step": "case_700024_observed_rounded",
            "observed_final_signatures": "case_700024_observed_snapshot",
            "observed_initial_signatures": (
                "uk_submission_supporter_rule_not_case_open_count"
            ),
            "response_delay": "case_700024_or_conditional_sample_scenario",
            "real_response_threshold_signatures": "uk_institutional_rule",
            "real_debate_threshold_signatures": "uk_institutional_rule",
            "alpha": "counterfactual_not_identified_by_case",
            "response_heat_multiplier": "counterfactual_not_identified_by_case",
            "direct_response_trust_signal": "counterfactual_not_identified_by_case",
            "synthetic_support_threshold_fraction": "research_design_assumption",
            "signature_probability_on_exposure": "research_design_assumption",
            "heat_decay": "inherited_from_v1_not_case_calibrated",
            "preference_drift_rate": "inherited_from_v1_not_case_calibrated",
        }


@dataclass
class PetitionState:
    petition_id: str
    petition_item_id: int
    opened_step: int
    close_step: int
    state: str = "open"
    observed_signature_count: int = 0
    response_threshold_step: int | None = None
    debate_threshold_step: int | None = None
    response_due_step: int | None = None
    response_executed_step: int | None = None
    response_disposition: str = "no_policy_change"


@dataclass(frozen=True)
class PendingPetitionResponse:
    petition_id: str
    trigger_step: int
    due_step: int


@dataclass
class UKPetitionSimulationResult:
    config: UKPetitionConfig
    metrics: pd.DataFrame
    storms: pd.DataFrame
    events: pd.DataFrame
    summary: dict[str, Any]


class UKPetitionSimulation(ReverseBlackBoxSimulation):
    """V1 dynamics plus the institutional lifecycle of one focal petition."""

    def __init__(self, config: UKPetitionConfig):
        super().__init__(config)
        self.config = config
        self.pending_responses: list[PendingPetitionResponse] = []
        self.has_signed_focal_petition = np.zeros(
            config.population_size, dtype=bool
        )
        self.event_records: list[dict[str, Any]] = []
        self._last_petition_exposures = 0
        self._last_petition_interactions = 0
        self._last_new_unique_signers = 0
        self._last_response_heat_delta = 0.0
        self._last_response_trust_signal = 0.0
        self._response_item_id: int | None = None
        self._closure_logged = False

        self._new_information(
            topic=config.petition_topic_index,
            emotional_intensity=config.petition_emotional_intensity,
            source="petition",
            step=config.petition_open_step,
            heat=config.petition_initial_heat,
        )
        petition_item_id = self.information_pool[-1].item_id
        self.petition = PetitionState(
            petition_id=config.petition_id,
            petition_item_id=petition_item_id,
            opened_step=config.petition_open_step,
            close_step=config.petition_close_step,
            observed_signature_count=config.observed_initial_signatures,
            response_disposition=config.response_disposition,
        )
        self._log_event(
            "petition_opened",
            config.petition_open_step,
            value=config.observed_initial_signatures,
            evidence="case_open_time_plus_uk_submission_rule",
        )

    def _log_event(
        self,
        event_type: str,
        step: int,
        *,
        value: Any = None,
        evidence: str,
    ) -> None:
        self.event_records.append(
            {
                "petition_id": self.config.petition_id,
                "event_type": event_type,
                "step": int(step),
                "value": value,
                "evidence": evidence,
            }
        )

    def _petition_item(self):
        for item in self.information_pool:
            if item.item_id == self.petition.petition_item_id:
                return item
        raise RuntimeError("the persistent focal petition is missing")

    def _petition_is_visible(self, step: int | None = None) -> bool:
        current = self.step if step is None else step
        return self.config.petition_open_step <= current < self.config.petition_close_step

    def _pool_arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        topics = np.fromiter(
            (item.topic for item in self.information_pool), dtype=int
        )
        emotions = np.fromiter(
            (item.emotional_intensity for item in self.information_pool),
            dtype=float,
        )
        sources = np.fromiter(
            (
                1 if item.source in {"government", "government_response"} else 0
                for item in self.information_pool
            ),
            dtype=int,
        )
        return topics, emotions, sources

    def _recommend(self, topics: np.ndarray) -> np.ndarray:
        """Apply the unchanged alpha formula to currently visible information."""

        item_count = len(self.information_pool)
        if item_count == 0:
            return np.empty((self.config.population_size, 0), dtype=int)

        visible_indices = np.asarray(
            [
                index
                for index, item in enumerate(self.information_pool)
                if item.item_id != self.petition.petition_item_id
                or self._petition_is_visible()
            ],
            dtype=int,
        )
        if visible_indices.size == 0:
            return np.empty((self.config.population_size, 0), dtype=int)

        heat = np.fromiter(
            (self.information_pool[index].heat for index in visible_indices),
            dtype=float,
        )
        heat_signal = np.log1p(heat)
        maximum = float(heat_signal.max(initial=0.0))
        if maximum > 0.0:
            heat_signal /= maximum

        visible_topics = topics[visible_indices]
        preference_norm = np.linalg.norm(self.preferences, axis=1)
        preference_norm = np.maximum(preference_norm, 1e-12)
        similarity = self.preferences[:, visible_topics] / preference_norm[:, None]
        scores = (
            self.config.alpha * heat_signal[None, :]
            + (1.0 - self.config.alpha) * similarity
        )
        scores += self.rng.uniform(0.0, 1e-10, size=scores.shape)

        count = min(self.config.attention_budget, visible_indices.size)
        if count == visible_indices.size:
            local_candidates = np.tile(
                np.arange(visible_indices.size, dtype=int),
                (self.config.population_size, 1),
            )
        else:
            local_candidates = np.argpartition(scores, -count, axis=1)[:, -count:]
        candidate_scores = np.take_along_axis(scores, local_candidates, axis=1)
        order = np.argsort(candidate_scores, axis=1)[:, ::-1]
        local_ranked = np.take_along_axis(local_candidates, order, axis=1)
        return visible_indices[local_ranked]

    def _apply_observed_milestones(self, step: int) -> None:
        config = self.config
        if step >= config.petition_close_step:
            self.petition.observed_signature_count = config.observed_final_signatures
        elif step >= config.observed_debate_threshold_step:
            self.petition.observed_signature_count = max(
                self.petition.observed_signature_count,
                config.real_debate_threshold_signatures,
            )
        elif step >= config.observed_response_threshold_step:
            self.petition.observed_signature_count = max(
                self.petition.observed_signature_count,
                config.real_response_threshold_signatures,
            )

    def _update_petition_support(
        self, step: int, recommendations: np.ndarray
    ) -> None:
        self._last_new_unique_signers = 0
        if self.config.trigger_mode == "observed_calendar":
            self._apply_observed_milestones(step)
            return
        if not self._petition_is_visible(step) or recommendations.shape[1] == 0:
            return

        petition_index = next(
            index
            for index, item in enumerate(self.information_pool)
            if item.item_id == self.petition.petition_item_id
        )
        exposed = np.any(recommendations == petition_index, axis=1)
        eligible = exposed & ~self.has_signed_focal_petition
        random_draws = self.rng.random(self.config.population_size)
        new_signers = eligible & (
            random_draws < self.config.signature_probability_on_exposure
        )
        self.has_signed_focal_petition[new_signers] = True
        self._last_new_unique_signers = int(new_signers.sum())

    def _public_action(
        self,
        recommendations: np.ndarray,
        topics: np.ndarray,
        emotions: np.ndarray,
        sources: np.ndarray,
    ) -> dict[str, Any]:
        petition_item = self._petition_item()
        heat_before = petition_item.heat
        result = super()._public_action(
            recommendations, topics, emotions, sources
        )
        heat_after = petition_item.heat
        self._last_petition_interactions = int(round(heat_after - heat_before))

        if recommendations.shape[1] == 0:
            exposures = 0
        else:
            petition_index = next(
                index
                for index, item in enumerate(self.information_pool)
                if item.item_id == self.petition.petition_item_id
            )
            exposures = int(np.any(recommendations == petition_index, axis=1).sum())
        self._last_petition_exposures = exposures
        self._update_petition_support(self.step, recommendations)
        return result

    def _trigger_condition_met(self, step: int) -> bool:
        if self.config.trigger_mode == "observed_calendar":
            return (
                step >= self.config.observed_response_threshold_step
                and self.petition.observed_signature_count
                >= self.config.real_response_threshold_signatures
            )
        threshold = self.config.synthetic_support_threshold_fraction
        assert threshold is not None
        support_fraction = float(np.mean(self.has_signed_focal_petition))
        return support_fraction >= threshold

    def _monitor_and_schedule(
        self,
        *,
        step: int,
        organic_attention_by_topic: np.ndarray,
        total_attention: float,
    ) -> int:
        del organic_attention_by_topic, total_attention
        scheduled = 0

        if self.petition.response_threshold_step is None and self._trigger_condition_met(step):
            due_step = step + self.config.response_delay
            self.petition.response_threshold_step = step
            self.petition.response_due_step = due_step
            self.pending_responses.append(
                PendingPetitionResponse(
                    petition_id=self.config.petition_id,
                    trigger_step=step,
                    due_step=due_step,
                )
            )
            self.responses_scheduled += 1
            scheduled = 1
            trigger_source = (
                "case_observed"
                if self.config.trigger_mode == "observed_calendar"
                else "synthetic_counterfactual"
            )
            self._log_event(
                "response_threshold_reached",
                step,
                value=(
                    self.petition.observed_signature_count
                    if self.config.trigger_mode == "observed_calendar"
                    else int(self.has_signed_focal_petition.sum())
                ),
                evidence=trigger_source,
            )
            self._log_event(
                "government_response_scheduled",
                step,
                value=due_step,
                evidence="model_rule",
            )

        if (
            self.config.trigger_mode == "observed_calendar"
            and self.petition.debate_threshold_step is None
            and step >= self.config.observed_debate_threshold_step
            and self.petition.observed_signature_count
            >= self.config.real_debate_threshold_signatures
        ):
            self.petition.debate_threshold_step = step
            self._log_event(
                "debate_threshold_reached",
                step,
                value=self.petition.observed_signature_count,
                evidence="case_observed",
            )

        return scheduled

    def _government_action(self, step: int) -> tuple[float, int]:
        config = self.config
        self._last_response_heat_delta = 0.0
        self._last_response_trust_signal = 0.0

        if (
            config.enable_routine_government_publication
            and step % config.publish_interval == 0
        ):
            sequence_index = (step // config.publish_interval) % len(
                config.agenda_topic_indices
            )
            topic = config.agenda_topic_indices[sequence_index]
            self._new_information(
                topic=topic,
                emotional_intensity=config.official_emotional_intensity,
                source="government",
                step=step,
            )

        if config.enable_legacy_topic_response:
            raise RuntimeError(
                "legacy topic-share responses are intentionally unavailable in V2"
            )

        due = [
            response
            for response in self.pending_responses
            if response.due_step <= step
        ]
        if not due:
            return 0.0, 0
        if self.petition.response_executed_step is not None:
            raise RuntimeError("the focal petition response would execute twice")

        petition_item = self._petition_item()
        heat_before = petition_item.heat
        petition_item.heat *= config.response_heat_multiplier
        heat_after = petition_item.heat
        self._last_response_heat_delta = heat_after - heat_before
        self._last_response_trust_signal = config.direct_response_trust_signal

        self._new_information(
            topic=config.petition_topic_index,
            emotional_intensity=config.response_information_emotional_intensity,
            source="government_response",
            step=step,
            heat=config.response_information_initial_heat,
        )
        self._response_item_id = self.information_pool[-1].item_id
        self.petition.response_executed_step = step
        self.pending_responses = []
        self.responses_executed += 1
        self._log_event(
            "government_response_published",
            step,
            value=config.response_disposition,
            evidence="case_position_and_model_timing",
        )
        return config.direct_response_trust_signal, 1

    def _petition_state_label(self, step: int) -> str:
        if step >= self.config.petition_close_step:
            return "closed"
        if self.petition.debate_threshold_step is not None:
            return "debate_eligible"
        if self.petition.response_executed_step is not None:
            return "responded"
        if self.petition.response_threshold_step is not None:
            return "response_pending"
        return "open"

    def _decay_and_prune(self, step: int) -> None:
        self.petition.state = self._petition_state_label(step)
        if step >= self.config.petition_close_step and not self._closure_logged:
            self._closure_logged = True
            self._log_event(
                "petition_closed",
                step,
                value=self.petition.observed_signature_count,
                evidence=(
                    "case_observed"
                    if self.config.trigger_mode == "observed_calendar"
                    else "model_calendar"
                ),
            )

        petition_item = self._petition_item()
        support_fraction = float(np.mean(self.has_signed_focal_petition))
        response_pending = int(bool(self.pending_responses))
        queue_age = (
            step - self.petition.response_threshold_step
            if response_pending and self.petition.response_threshold_step is not None
            else 0
        )
        if self.records:
            self.records[-1].update(
                {
                    "model_version": MODEL_VERSION,
                    "petition_id": self.config.petition_id,
                    "trigger_mode": self.config.trigger_mode,
                    "petition_state": self.petition.state,
                    "petition_visible": int(self._petition_is_visible(step)),
                    "petition_heat": float(petition_item.heat),
                    "petition_exposures": self._last_petition_exposures,
                    "petition_interactions": self._last_petition_interactions,
                    "new_unique_signers": self._last_new_unique_signers,
                    "cumulative_unique_signers": int(
                        self.has_signed_focal_petition.sum()
                    ),
                    "synthetic_support_fraction": support_fraction,
                    "observed_signature_count": self.petition.observed_signature_count,
                    "response_pending": response_pending,
                    "response_queue_age_days": queue_age,
                    "response_due_step": self.petition.response_due_step,
                    "petition_response_executed": int(
                        self.petition.response_executed_step == step
                    ),
                    "response_disposition": self.config.response_disposition,
                    "response_heat_multiplier": self.config.response_heat_multiplier,
                    "response_heat_delta": self._last_response_heat_delta,
                    "direct_response_trust_signal": self._last_response_trust_signal,
                    "debate_threshold_reached": int(
                        self.petition.debate_threshold_step is not None
                    ),
                }
            )

        for item in self.information_pool:
            item.heat *= self.config.heat_decay
        self.information_pool = [
            item
            for item in self.information_pool
            if item.item_id == self.petition.petition_item_id
            or item.heat >= self.config.minimum_heat
            or step - item.created_at < 1
        ]

    def _summarize(
        self, metrics: pd.DataFrame, storms: pd.DataFrame
    ) -> dict[str, Any]:
        summary = super()._summarize(metrics, storms)
        response_step = self.petition.response_executed_step
        pre_7_auc = None
        post_7_auc = None
        if response_step is not None:
            pre = metrics[
                (metrics["step"] >= response_step - 7)
                & (metrics["step"] < response_step)
            ]
            post = metrics[
                (metrics["step"] >= response_step)
                & (metrics["step"] < response_step + 7)
            ]
            pre_7_auc = float(pre["petition_heat"].sum())
            post_7_auc = float(post["petition_heat"].sum())

        summary.update(
            {
                "model_version": MODEL_VERSION,
                "petition_id": self.config.petition_id,
                "trigger_mode": self.config.trigger_mode,
                "response_delay_days": self.config.response_delay,
                "response_threshold_step": self.petition.response_threshold_step,
                "response_due_step": self.petition.response_due_step,
                "response_executed_step": response_step,
                "realized_response_delay_days": (
                    response_step - self.petition.response_threshold_step
                    if response_step is not None
                    and self.petition.response_threshold_step is not None
                    else None
                ),
                "debate_threshold_step": self.petition.debate_threshold_step,
                "petition_close_step": self.config.petition_close_step,
                "final_observed_signature_count": (
                    self.petition.observed_signature_count
                ),
                "final_unique_signers": int(
                    self.has_signed_focal_petition.sum()
                ),
                "final_synthetic_support_fraction": float(
                    np.mean(self.has_signed_focal_petition)
                ),
                "response_disposition": self.config.response_disposition,
                "response_heat_multiplier": self.config.response_heat_multiplier,
                "direct_response_trust_signal": (
                    self.config.direct_response_trust_signal
                ),
                "petition_heat_auc_pre_7_days": pre_7_auc,
                "petition_heat_auc_post_7_days": post_7_auc,
            }
        )
        return summary

    def run(self, steps: int | None = None) -> UKPetitionSimulationResult:
        base_result: SimulationResult = super().run(steps=steps)
        events = pd.DataFrame.from_records(
            self.event_records,
            columns=["petition_id", "event_type", "step", "value", "evidence"],
        )
        return UKPetitionSimulationResult(
            config=self.config,
            metrics=base_result.metrics,
            storms=base_result.storms,
            events=events,
            summary=base_result.summary,
        )


def run_case_700024(
    *,
    alpha: float = 0.50,
    seed: int = 42,
    response_delay: int = 22,
    **overrides: Any,
) -> UKPetitionSimulationResult:
    """Convenience entry point for one complete petition-700024 run."""

    config = UKPetitionConfig.case_700024(
        alpha=alpha,
        seed=seed,
        response_delay=response_delay,
        **overrides,
    )
    return UKPetitionSimulation(config).run()


__all__ = [
    "MODEL_VERSION",
    "V1_FROZEN_SHA256",
    "PendingPetitionResponse",
    "PetitionState",
    "UKPetitionConfig",
    "UKPetitionSimulation",
    "UKPetitionSimulationResult",
    "run_case_700024",
]
