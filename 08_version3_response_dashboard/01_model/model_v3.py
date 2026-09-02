"""Version 3: response-effect experiment and dual-ranking dashboard.

Version 3 is isolated from Versions 1 and 2.  It adds exactly one routine
government information item per simulated day, keeps the petition-specific
response from V2, and records the gap between a heat-ranked information list
and a latent public-demand ranking.

The dashboard metrics are model diagnostics.  They must not be described as a
measurement of real Weibo or real Leader Message Board behaviour unless real,
time-matched external inputs are supplied to the separate index adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

try:  # Package and direct-path imports are both supported.
    from .base_v1 import SimulationConfig
    from .base_v2 import (
        UKPetitionConfig,
        UKPetitionSimulation,
        UKPetitionSimulationResult,
        V1_FROZEN_SHA256,
    )
except ImportError:  # pragma: no cover - used by CLI/tests
    from base_v1 import SimulationConfig
    from base_v2 import (
        UKPetitionConfig,
        UKPetitionSimulation,
        UKPetitionSimulationResult,
        V1_FROZEN_SHA256,
    )


MODEL_VERSION = "3.0.0-response-dashboard-pilot"
V2_FROZEN_SHA256 = (
    "83BCD501B5A22C59832CC5441FFDF1054361E46C75E1BEE39F70E8E8CA0FC8DF"
)


@dataclass(frozen=True)
class Version3Config(UKPetitionConfig):
    """Configuration for the V3 daily-publication and dashboard extension."""

    model_version: str = MODEL_VERSION

    # One routine government item is published at every step.  On the response
    # day, the petition-specific response is an additional official item.
    enable_routine_government_publication: bool = True
    publish_interval: int = 1

    # The pilot explicitly compares 1.00 with 0.70; 1.00 remains the neutral
    # baseline so publication does not silently imply cooling.
    response_heat_multiplier: float = 1.00

    # The dual ranking is diagnostic in this release and does not change which
    # routine government topic is published.  That preserves the pilot contrast.
    government_dashboard_mode: str = "compare_only"
    hotspot_demand_top_k: int = 2
    hotspot_demand_epsilon: float = 1e-12

    def __post_init__(self) -> None:
        # UKPetitionConfig validates its own fixed V2 model_version.  V3 repeats
        # those public validations while retaining a distinct version identity.
        SimulationConfig.__post_init__(self)
        if self.model_version != MODEL_VERSION:
            raise ValueError(f"model_version must be {MODEL_VERSION!r}")
        if self.step_unit != "day":
            raise ValueError("Version 3 requires step_unit='day'")
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
        if self.petition_initial_heat < 0.0:
            raise ValueError("petition_initial_heat cannot be negative")
        if not 0.0 <= self.petition_emotional_intensity <= 1.0:
            raise ValueError("petition_emotional_intensity must be in [0, 1]")
        if self.response_information_initial_heat < 0.0:
            raise ValueError("response information heat cannot be negative")
        if not 0.0 <= self.response_information_emotional_intensity <= 1.0:
            raise ValueError("response information emotional intensity must be in [0, 1]")
        if not self.enable_routine_government_publication:
            raise ValueError("V3 requires one routine government publication per day")
        if self.publish_interval != 1:
            raise ValueError("V3 publish_interval must equal one day")
        if self.enable_legacy_topic_response:
            raise ValueError("legacy topic-share responses remain disabled in V3")
        if self.government_dashboard_mode != "compare_only":
            raise ValueError("V3 currently supports government_dashboard_mode='compare_only'")
        if not 1 <= self.hotspot_demand_top_k <= self.topic_count:
            raise ValueError("hotspot_demand_top_k must be within the topic count")
        if self.hotspot_demand_epsilon <= 0.0:
            raise ValueError("hotspot_demand_epsilon must be positive")

    def parameter_sources(self) -> dict[str, str]:
        sources = super().parameter_sources()
        sources.update(
            {
                "model_version": "v3_release_identity",
                "enable_routine_government_publication": "v3_user_requested_mechanism",
                "publish_interval": "v3_user_requested_one_item_per_day",
                "response_heat_multiplier": "v3_factorial_counterfactual_1.00_or_0.70",
                "government_dashboard_mode": "v3_diagnostic_design",
                "hotspot_demand_top_k": "v3_diagnostic_design",
            }
        )
        return sources


class Version3Simulation(UKPetitionSimulation):
    """V2 petition model plus daily official information and ranking diagnostics."""

    def __init__(self, config: Version3Config):
        super().__init__(config)
        self.config = config
        self.initial_preferences = self.preferences.copy()
        self.routine_government_posts_published = 0
        self.response_government_posts_published = 0
        self._last_routine_government_posts = 0
        self._last_response_government_posts = 0
        self._last_routine_government_attention_share = 0.0
        self._last_routine_government_reach_share = 0.0
        self._last_response_government_attention_share = 0.0
        self._last_response_government_reach_share = 0.0
        self._last_response_heat_before_immediate = np.nan
        self._last_response_heat_after_immediate = np.nan
        self._last_realized_heat_reduction_fraction = np.nan

    def _government_action(self, step: int) -> tuple[float, int]:
        self._last_response_heat_before_immediate = np.nan
        self._last_response_heat_after_immediate = np.nan
        self._last_realized_heat_reduction_fraction = np.nan
        petition_heat_before = float(self._petition_item().heat)
        before = self.next_information_id
        response_signal, executed = super()._government_action(step)
        added = self.next_information_id - before
        routine_posts = added - executed
        if routine_posts != 1:
            raise RuntimeError(
                "V3 invariant failed: exactly one routine government item is required daily"
            )
        self._last_routine_government_posts = routine_posts
        self._last_response_government_posts = executed
        self.routine_government_posts_published += routine_posts
        self.response_government_posts_published += executed

        routine_items = [
            item
            for item in self.information_pool
            if item.item_id >= before and item.source == "government"
        ]
        if len(routine_items) != 1:
            raise RuntimeError("V3 could not identify the daily government item")
        self._log_event(
            "routine_government_information_published",
            step,
            value=self.config.topic_names[routine_items[0].topic],
            evidence="v3_daily_publication_rule",
        )

        if executed:
            petition_heat_after = float(self._petition_item().heat)
            self._last_response_heat_before_immediate = petition_heat_before
            self._last_response_heat_after_immediate = petition_heat_after
            if petition_heat_before > self.config.hotspot_demand_epsilon:
                reduction = 1.0 - petition_heat_after / petition_heat_before
            else:
                reduction = 0.0
            self._last_realized_heat_reduction_fraction = float(reduction)
        return response_signal, executed

    def _public_action(
        self,
        recommendations: np.ndarray,
        topics: np.ndarray,
        emotions: np.ndarray,
        sources: np.ndarray,
    ) -> dict[str, Any]:
        """Record actual exposure to routine and petition-response information."""

        if recommendations.size == 0:
            self._last_routine_government_attention_share = 0.0
            self._last_routine_government_reach_share = 0.0
            self._last_response_government_attention_share = 0.0
            self._last_response_government_reach_share = 0.0
        else:
            source_labels = np.asarray(
                [item.source for item in self.information_pool], dtype=object
            )
            consumed_sources = source_labels[recommendations]
            routine_mask = consumed_sources == "government"
            response_mask = consumed_sources == "government_response"
            self._last_routine_government_attention_share = float(
                routine_mask.mean()
            )
            self._last_routine_government_reach_share = float(
                np.any(routine_mask, axis=1).mean()
            )
            self._last_response_government_attention_share = float(
                response_mask.mean()
            )
            self._last_response_government_reach_share = float(
                np.any(response_mask, axis=1).mean()
            )
        return super()._public_action(recommendations, topics, emotions, sources)

    @staticmethod
    def _normalise(values: np.ndarray, epsilon: float) -> np.ndarray:
        clipped = np.clip(np.asarray(values, dtype=float), 0.0, None)
        total = float(clipped.sum())
        if total <= epsilon:
            return np.full(len(clipped), 1.0 / len(clipped), dtype=float)
        return clipped / total

    def _hotspot_and_demand_distributions(
        self,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        heat_by_topic = np.zeros(self.config.topic_count, dtype=float)
        for item in self.information_pool:
            if (
                item.item_id == self.petition.petition_item_id
                and not self._petition_is_visible(self.step)
            ):
                continue
            heat_by_topic[item.topic] += item.heat
        hotspot = self._normalise(
            heat_by_topic, self.config.hotspot_demand_epsilon
        )
        current_demand = self._normalise(
            self.preferences.mean(axis=0), self.config.hotspot_demand_epsilon
        )
        baseline_demand = self._normalise(
            self.initial_preferences.mean(axis=0),
            self.config.hotspot_demand_epsilon,
        )
        return hotspot, current_demand, baseline_demand

    def _ranking_diagnostics(
        self, hotspot: np.ndarray, demand: np.ndarray
    ) -> dict[str, Any]:
        epsilon = self.config.hotspot_demand_epsilon
        midpoint = 0.5 * (hotspot + demand)
        kl_hotspot = float(
            np.sum(
                np.where(
                    hotspot > 0.0,
                    hotspot * np.log((hotspot + epsilon) / (midpoint + epsilon)),
                    0.0,
                )
            )
        )
        kl_demand = float(
            np.sum(
                np.where(
                    demand > 0.0,
                    demand * np.log((demand + epsilon) / (midpoint + epsilon)),
                    0.0,
                )
            )
        )
        jsd_normalised = float(
            np.clip(0.5 * (kl_hotspot + kl_demand) / np.log(2.0), 0.0, 1.0)
        )
        total_variation = float(
            np.clip(0.5 * np.abs(hotspot - demand).sum(), 0.0, 1.0)
        )

        hotspot_order = np.argsort(-hotspot, kind="stable")
        demand_order = np.argsort(-demand, kind="stable")
        k = self.config.hotspot_demand_top_k
        top_overlap = len(set(hotspot_order[:k]) & set(demand_order[:k])) / k
        hotspot_rank = np.empty(self.config.topic_count, dtype=float)
        demand_rank = np.empty(self.config.topic_count, dtype=float)
        hotspot_rank[hotspot_order] = np.arange(self.config.topic_count)
        demand_rank[demand_order] = np.arange(self.config.topic_count)
        rank_correlation = float(np.corrcoef(hotspot_rank, demand_rank)[0, 1])

        names = self.config.topic_names
        return {
            "hotspot_demand_misalignment": total_variation,
            "hotspot_demand_jsd": jsd_normalised,
            "hotspot_demand_topk_overlap": float(top_overlap),
            "hotspot_demand_top1_agreement": float(
                hotspot_order[0] == demand_order[0]
            ),
            "hotspot_demand_rank_correlation": rank_correlation,
            "hotspot_top_topic": names[int(hotspot_order[0])],
            "demand_top_topic": names[int(demand_order[0])],
        }

    def _decay_and_prune(self, step: int) -> None:
        hotspot, current_demand, baseline_demand = (
            self._hotspot_and_demand_distributions()
        )
        diagnostics = self._ranking_diagnostics(hotspot, current_demand)
        baseline_diagnostics = self._ranking_diagnostics(
            hotspot, baseline_demand
        )
        super()._decay_and_prune(step)
        if not self.records:
            return
        record = self.records[-1]
        record.update(
            {
                "model_version": MODEL_VERSION,
                "government_dashboard_mode": self.config.government_dashboard_mode,
                "routine_government_posts_published": (
                    self._last_routine_government_posts
                ),
                "response_government_posts_published": (
                    self._last_response_government_posts
                ),
                "routine_government_attention_share": (
                    self._last_routine_government_attention_share
                ),
                "routine_government_reach_share": (
                    self._last_routine_government_reach_share
                ),
                "response_government_attention_share": (
                    self._last_response_government_attention_share
                ),
                "response_government_reach_share": (
                    self._last_response_government_reach_share
                ),
                "response_heat_before_immediate": (
                    self._last_response_heat_before_immediate
                ),
                "response_heat_after_immediate": (
                    self._last_response_heat_after_immediate
                ),
                "realized_heat_reduction_fraction": (
                    self._last_realized_heat_reduction_fraction
                ),
                "cumulative_routine_government_posts": (
                    self.routine_government_posts_published
                ),
                **diagnostics,
                "hotspot_baseline_demand_misalignment": baseline_diagnostics[
                    "hotspot_demand_misalignment"
                ],
                "hotspot_baseline_demand_jsd": baseline_diagnostics[
                    "hotspot_demand_jsd"
                ],
                "hotspot_baseline_demand_topk_overlap": baseline_diagnostics[
                    "hotspot_demand_topk_overlap"
                ],
                "hotspot_baseline_demand_top1_agreement": baseline_diagnostics[
                    "hotspot_demand_top1_agreement"
                ],
                "baseline_demand_top_topic": baseline_diagnostics[
                    "demand_top_topic"
                ],
            }
        )
        for topic_index, topic_name in enumerate(self.config.topic_names):
            record[f"hotspot_share_{topic_index}_{topic_name}"] = float(
                hotspot[topic_index]
            )
            record[f"current_demand_share_{topic_index}_{topic_name}"] = float(
                current_demand[topic_index]
            )
            record[f"baseline_demand_share_{topic_index}_{topic_name}"] = float(
                baseline_demand[topic_index]
            )

    def _summarize(self, metrics, storms) -> dict[str, Any]:
        summary = super()._summarize(metrics, storms)
        tail = metrics.tail(min(100, len(metrics)))
        open_period = metrics[
            (metrics["step"] >= self.config.petition_open_step)
            & (metrics["step"] < self.config.petition_close_step)
        ]
        threshold_step = self.petition.response_threshold_step
        if threshold_step is None:
            threshold_to_close = open_period.iloc[0:0]
        else:
            threshold_to_close = open_period[
                open_period["step"] >= threshold_step
            ]
        response_step = self.petition.response_executed_step
        if response_step is None:
            post_14 = metrics.iloc[0:0]
        else:
            post_14 = metrics[
                (metrics["step"] >= response_step)
                & (metrics["step"] < response_step + 14)
            ]
        response_rows = metrics[
            metrics["petition_response_executed"].eq(1)
        ]

        def _mean_or_nan(frame, column: str) -> float:
            return float(frame[column].mean()) if len(frame) else float("nan")

        def _sum_or_nan(frame, column: str) -> float:
            return float(frame[column].sum()) if len(frame) else float("nan")

        def _max_or_nan(frame, column: str) -> float:
            return float(frame[column].max()) if len(frame) else float("nan")

        summary.update(
            {
                "model_version": MODEL_VERSION,
                "v2_parent_sha256": V2_FROZEN_SHA256,
                "government_posts_per_day": 1,
                "routine_government_posts_published": (
                    self.routine_government_posts_published
                ),
                "response_government_posts_published": (
                    self.response_government_posts_published
                ),
                "response_heat_multiplier": self.config.response_heat_multiplier,
                "response_heat_before_immediate": (
                    float(response_rows.iloc[0]["response_heat_before_immediate"])
                    if len(response_rows)
                    else float("nan")
                ),
                "response_heat_after_immediate": (
                    float(response_rows.iloc[0]["response_heat_after_immediate"])
                    if len(response_rows)
                    else float("nan")
                ),
                "realized_heat_reduction_fraction": (
                    float(response_rows.iloc[0]["realized_heat_reduction_fraction"])
                    if len(response_rows)
                    else float("nan")
                ),
                "petition_heat_end_of_response_day": (
                    float(response_rows.iloc[0]["petition_heat"])
                    if len(response_rows)
                    else float("nan")
                ),
                "petition_heat_auc_post_14_days": _sum_or_nan(
                    post_14, "petition_heat"
                ),
                "petition_heat_peak_post_14_days": _max_or_nan(
                    post_14, "petition_heat"
                ),
                "petition_exposures_post_14_days": _sum_or_nan(
                    post_14, "petition_exposures"
                ),
                "petition_interactions_post_14_days": _sum_or_nan(
                    post_14, "petition_interactions"
                ),
                "mean_trust_post_14_days": _mean_or_nan(
                    post_14, "mean_trust"
                ),
                "mean_agenda_divergence_post_14_days": _mean_or_nan(
                    post_14, "agenda_divergence"
                ),
                "petition_heat_auc_open_period": float(
                    open_period["petition_heat"].sum()
                ),
                "petition_heat_auc_threshold_to_close": float(
                    threshold_to_close["petition_heat"].sum()
                ),
                "petition_heat_mean_threshold_to_close": float(
                    threshold_to_close["petition_heat"].mean()
                    if len(threshold_to_close)
                    else np.nan
                ),
                "petition_heat_peak_open_period": float(
                    open_period["petition_heat"].max()
                ),
                "mean_trust_open_period": float(open_period["mean_trust"].mean()),
                "mean_agenda_divergence_open_period": float(
                    open_period["agenda_divergence"].mean()
                ),
                "mean_agenda_divergence_threshold_to_close": _mean_or_nan(
                    threshold_to_close, "agenda_divergence"
                ),
                "mean_routine_government_attention_share_open_period": (
                    _mean_or_nan(
                        open_period, "routine_government_attention_share"
                    )
                ),
                "mean_routine_government_reach_share_open_period": (
                    _mean_or_nan(open_period, "routine_government_reach_share")
                ),
                "mean_response_government_attention_share_post_14_days": (
                    _mean_or_nan(
                        post_14, "response_government_attention_share"
                    )
                ),
                "mean_hotspot_demand_misalignment_open_period": float(
                    open_period["hotspot_demand_misalignment"].mean()
                ),
                "mean_hotspot_demand_misalignment_tail": float(
                    tail["hotspot_demand_misalignment"].mean()
                ),
                "mean_hotspot_demand_jsd_open_period": float(
                    open_period["hotspot_demand_jsd"].mean()
                ),
                "mean_hotspot_demand_topk_overlap_open_period": float(
                    open_period["hotspot_demand_topk_overlap"].mean()
                ),
                "mean_hotspot_baseline_demand_misalignment_open_period": float(
                    open_period["hotspot_baseline_demand_misalignment"].mean()
                ),
                "hotspot_demand_index_definition": (
                    "model_internal_total_variation_0_aligned_1_disjoint"
                ),
                "demand_proxy_definition": (
                    "simulated_current_latent_preferences_not_observed_public_demand"
                ),
            }
        )
        return summary


def run_case_700024_v3(
    *,
    alpha: float = 0.50,
    seed: int = 42,
    response_delay: int = 22,
    response_heat_multiplier: float = 1.00,
    **overrides: Any,
) -> UKPetitionSimulationResult:
    """Run one V3 case configuration."""

    config = Version3Config.case_700024(
        alpha=alpha,
        seed=seed,
        response_delay=response_delay,
        response_heat_multiplier=response_heat_multiplier,
        **overrides,
    )
    return Version3Simulation(config).run()


__all__ = [
    "MODEL_VERSION",
    "V1_FROZEN_SHA256",
    "V2_FROZEN_SHA256",
    "Version3Config",
    "Version3Simulation",
    "run_case_700024_v3",
]
