"""Core agent-based model for the government-platform-public information system.

The implementation follows the supplied PRD and adds a bounded trust mechanism
inspired by the supplied questionnaire study.  It is an exploratory simulation:
the empirical coefficients are behavioural priors, not a claim of causal
replication.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd


def _sigmoid(value: np.ndarray | float) -> np.ndarray | float:
    """Numerically stable logistic transform."""

    values = np.asarray(value, dtype=float)
    values = np.clip(values, -35.0, 35.0)
    result = 1.0 / (1.0 + np.exp(-values))
    if result.ndim == 0:
        return float(result)
    return result


@dataclass(frozen=True)
class SimulationConfig:
    """All tunable parameters for a single simulation."""

    alpha: float = 0.50
    steps: int = 300
    population_size: int = 300
    topic_names: tuple[str, ...] = ("经济", "法治", "公共服务", "娱乐热点")
    agenda_topic_indices: tuple[int, ...] = (0, 1, 2)
    attention_budget: int = 5
    initial_information: int = 24
    spontaneous_posts_per_step: int = 4
    preference_concentration: float = 1.0
    emotionality_mean: float = 0.30
    emotionality_sd: float = 0.10
    preference_drift_after: int = 4
    preference_drift_rate: float = 0.03
    heat_decay: float = 0.95
    minimum_heat: float = 0.01
    official_emotional_intensity: float = 0.15
    publish_interval: int = 10
    response_threshold: float = 0.15
    response_strength: float = 0.70
    response_delay: int = 3
    response_strategy: str = "hard"
    wait_observation_steps: int = 3
    agenda_target_share: float = 0.70
    storm_threshold: float = 0.30
    digital_government_level: float = 0.60
    digital_platform_complexity: float = 0.50
    digital_literacy_mean: float = 0.69
    digital_literacy_sd: float = 0.18
    initial_trust_mean: float = 0.69
    initial_trust_sd: float = 0.12
    learning_update_rate: float = 0.08
    trust_update_rate: float = 0.06
    trust_feedback_strength: float = 0.25
    seed: int = 42

    # Standardized coefficients reported in the supplied paper.  They enter a
    # bounded latent-score mechanism and therefore should not be interpreted as
    # a direct re-estimation of the paper's regression model.
    beta_digital_government_to_trust: float = -0.086
    beta_learning_cost_to_trust: float = -0.766
    beta_digital_government_to_learning: float = 0.036
    beta_digital_literacy_to_learning: float = -0.855
    beta_digital_government_literacy_interaction: float = -0.125

    def __post_init__(self) -> None:
        if not 0.0 <= self.alpha <= 1.0:
            raise ValueError("alpha must be between 0 and 1")
        if self.steps <= 0 or self.population_size <= 0:
            raise ValueError("steps and population_size must be positive")
        if len(self.topic_names) < 2:
            raise ValueError("at least two topics are required")
        if not self.agenda_topic_indices:
            raise ValueError("at least one government agenda topic is required")
        if any(
            topic < 0 or topic >= len(self.topic_names)
            for topic in self.agenda_topic_indices
        ):
            raise ValueError("agenda_topic_indices contains an invalid topic")
        if len(set(self.agenda_topic_indices)) != len(self.agenda_topic_indices):
            raise ValueError("agenda_topic_indices must be unique")
        if self.attention_budget <= 0:
            raise ValueError("attention_budget must be positive")
        if self.publish_interval <= 0:
            raise ValueError("publish_interval must be positive")
        if self.response_delay < 0:
            raise ValueError("response_delay cannot be negative")
        if self.response_strategy not in {"hard", "selective", "wait"}:
            raise ValueError("response_strategy must be hard, selective, or wait")
        probability_fields = {
            "heat_decay": self.heat_decay,
            "response_threshold": self.response_threshold,
            "response_strength": self.response_strength,
            "agenda_target_share": self.agenda_target_share,
            "storm_threshold": self.storm_threshold,
            "digital_government_level": self.digital_government_level,
            "digital_platform_complexity": self.digital_platform_complexity,
            "learning_update_rate": self.learning_update_rate,
            "trust_update_rate": self.trust_update_rate,
        }
        for name, value in probability_fields.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.agenda_target_share <= 0.0:
            raise ValueError("agenda_target_share must be greater than 0")

    @property
    def topic_count(self) -> int:
        return len(self.topic_names)

    @property
    def off_agenda_topic_indices(self) -> tuple[int, ...]:
        agenda = set(self.agenda_topic_indices)
        return tuple(index for index in range(self.topic_count) if index not in agenda)

    def to_dict(self) -> dict[str, Any]:
        values = asdict(self)
        values["topic_names"] = list(self.topic_names)
        values["agenda_topic_indices"] = list(self.agenda_topic_indices)
        return values


@dataclass
class InformationItem:
    item_id: int
    topic: int
    emotional_intensity: float
    heat: float
    source: str
    created_at: int


@dataclass
class PendingResponse:
    topic: int
    trigger_step: int
    due_step: int


@dataclass
class StormEpisode:
    start_step: int
    end_step: int
    duration: int
    peak_share: float


@dataclass
class SimulationResult:
    config: SimulationConfig
    metrics: pd.DataFrame
    storms: pd.DataFrame
    summary: dict[str, Any]


class ReverseBlackBoxSimulation:
    """Government-platform-public ABM with reproducible stochastic dynamics."""

    def __init__(self, config: SimulationConfig):
        self.config = config
        self.rng = np.random.default_rng(config.seed)
        self.step = 0
        self.next_information_id = 0
        self.information_pool: list[InformationItem] = []
        self.pending_responses: list[PendingResponse] = []
        self.response_threshold_streak = np.zeros(config.topic_count, dtype=int)
        self.responses_scheduled = 0
        self.responses_executed = 0
        self._has_run = False

        concentration = np.full(
            config.topic_count, config.preference_concentration, dtype=float
        )
        self.preferences = self.rng.dirichlet(
            concentration, size=config.population_size
        )
        self.emotionality = np.clip(
            self.rng.normal(
                config.emotionality_mean,
                config.emotionality_sd,
                config.population_size,
            ),
            0.0,
            1.0,
        )
        self.digital_literacy = np.clip(
            self.rng.normal(
                config.digital_literacy_mean,
                config.digital_literacy_sd,
                config.population_size,
            ),
            0.0,
            1.0,
        )
        self.learning_cost = self._initial_learning_cost()
        self.trust = np.clip(
            self.rng.normal(
                config.initial_trust_mean,
                config.initial_trust_sd,
                config.population_size,
            ),
            0.0,
            1.0,
        )

        self.last_dominant_topic = np.full(
            config.population_size, -1, dtype=int
        )
        self.dominant_topic_streak = np.zeros(
            config.population_size, dtype=int
        )
        self.records: list[dict[str, Any]] = []
        self.storm_episodes: list[StormEpisode] = []
        self._active_storm_start: int | None = None
        self._active_storm_duration = 0
        self._active_storm_peak = 0.0

        self._add_spontaneous_information(
            step=0, count=config.initial_information
        )

    def _initial_learning_cost(self) -> np.ndarray:
        config = self.config
        z_digital_government = 2.0 * config.digital_government_level - 1.0
        z_literacy = 2.0 * self.digital_literacy - 1.0
        latent = (
            0.10
            + config.beta_digital_government_to_learning * z_digital_government
            + config.beta_digital_literacy_to_learning * z_literacy
            + config.beta_digital_government_literacy_interaction
            * z_digital_government
            * z_literacy
            + 0.35 * config.digital_platform_complexity
        )
        return np.asarray(_sigmoid(latent), dtype=float)

    def _new_information(
        self,
        *,
        topic: int,
        emotional_intensity: float,
        source: str,
        step: int,
        heat: float = 0.0,
    ) -> None:
        self.information_pool.append(
            InformationItem(
                item_id=self.next_information_id,
                topic=int(topic),
                emotional_intensity=float(
                    np.clip(emotional_intensity, 0.0, 1.0)
                ),
                heat=max(0.0, float(heat)),
                source=source,
                created_at=step,
            )
        )
        self.next_information_id += 1

    def _sample_spontaneous_emotion(self, topic: int) -> float:
        if topic in self.config.off_agenda_topic_indices:
            # Off-agenda content is more likely to be affectively intense.  This
            # is the micro-level bridge from emotion to heat in the PRD.
            return float(self.rng.beta(4.0, 2.0))
        return float(self.rng.beta(2.0, 3.0))

    def _add_spontaneous_information(self, *, step: int, count: int) -> None:
        if count <= 0:
            return
        topics = self.rng.integers(0, self.config.topic_count, size=count)
        for topic in topics:
            self._new_information(
                topic=int(topic),
                emotional_intensity=self._sample_spontaneous_emotion(int(topic)),
                source="spontaneous",
                step=step,
            )

    def _government_action(self, step: int) -> tuple[float, int]:
        config = self.config
        if step % config.publish_interval == 0:
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

        due = [
            response
            for response in self.pending_responses
            if response.due_step <= step
        ]
        if not due:
            return 0.0, 0

        total_before = 0.0
        total_after = 0.0
        for response in due:
            affected = [
                item
                for item in self.information_pool
                if item.source == "spontaneous" and item.topic == response.topic
            ]
            before = sum(item.heat for item in affected)
            for item in affected:
                item.heat *= config.response_strength
            after = sum(item.heat for item in affected)
            total_before += before
            total_after += after

        due_ids = {id(response) for response in due}
        self.pending_responses = [
            response
            for response in self.pending_responses
            if id(response) not in due_ids
        ]
        self.responses_executed += len(due)
        effect = (
            (total_before - total_after) / total_before
            if total_before > 0.0
            else 0.0
        )
        return effect, len(due)

    def _pool_arrays(
        self,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        topics = np.fromiter(
            (item.topic for item in self.information_pool), dtype=int
        )
        emotions = np.fromiter(
            (item.emotional_intensity for item in self.information_pool),
            dtype=float,
        )
        sources = np.fromiter(
            (1 if item.source == "government" else 0 for item in self.information_pool),
            dtype=int,
        )
        return topics, emotions, sources

    def _recommend(self, topics: np.ndarray) -> np.ndarray:
        item_count = len(self.information_pool)
        if item_count == 0:
            return np.empty((self.config.population_size, 0), dtype=int)

        heat = np.fromiter(
            (item.heat for item in self.information_pool), dtype=float
        )
        heat_signal = np.log1p(heat)
        maximum = float(heat_signal.max(initial=0.0))
        if maximum > 0.0:
            heat_signal /= maximum

        preference_norm = np.linalg.norm(self.preferences, axis=1)
        preference_norm = np.maximum(preference_norm, 1e-12)
        similarity = self.preferences[:, topics] / preference_norm[:, None]

        scores = (
            self.config.alpha * heat_signal[None, :]
            + (1.0 - self.config.alpha) * similarity
        )
        scores += self.rng.uniform(0.0, 1e-10, size=scores.shape)

        count = min(self.config.attention_budget, item_count)
        if count == item_count:
            candidates = np.tile(
                np.arange(item_count, dtype=int),
                (self.config.population_size, 1),
            )
        else:
            candidates = np.argpartition(scores, -count, axis=1)[:, -count:]
        candidate_scores = np.take_along_axis(scores, candidates, axis=1)
        order = np.argsort(candidate_scores, axis=1)[:, ::-1]
        return np.take_along_axis(candidates, order, axis=1)

    def _public_action(
        self,
        recommendations: np.ndarray,
        topics: np.ndarray,
        emotions: np.ndarray,
        sources: np.ndarray,
    ) -> dict[str, Any]:
        config = self.config
        if recommendations.shape[1] == 0:
            zeros = np.zeros(config.topic_count, dtype=float)
            return {
                "attention_by_topic": zeros.copy(),
                "organic_attention_by_topic": zeros.copy(),
                "official_exposure": np.zeros(config.population_size),
                "off_agenda_exposure": np.zeros(config.population_size),
                "emotional_exposure": np.zeros(config.population_size),
                "total_interactions": 0,
            }

        consumed_topics = topics[recommendations]
        consumed_emotions = emotions[recommendations]
        consumed_sources = sources[recommendations]

        attention_by_topic = np.bincount(
            consumed_topics.ravel(), minlength=config.topic_count
        ).astype(float)
        spontaneous_mask = consumed_sources == 0
        organic_attention_by_topic = np.bincount(
            consumed_topics[spontaneous_mask],
            minlength=config.topic_count,
        ).astype(float)

        trust_centered = 2.0 * self.trust - 1.0
        official_factor = (
            1.0 + config.trust_feedback_strength * trust_centered
        )
        spontaneous_factor = (
            1.0 - config.trust_feedback_strength * trust_centered
        )
        source_factor = np.where(
            consumed_sources == 1,
            official_factor[:, None],
            spontaneous_factor[:, None],
        )
        interaction_probability = np.clip(
            self.emotionality[:, None] * consumed_emotions * source_factor,
            0.0,
            1.0,
        )
        interactions = (
            self.rng.random(interaction_probability.shape)
            < interaction_probability
        )
        interacted_items = recommendations[interactions]
        interaction_counts = np.bincount(
            interacted_items,
            minlength=len(self.information_pool),
        )
        for item, increment in zip(
            self.information_pool, interaction_counts, strict=True
        ):
            item.heat += int(increment)

        topic_counts = np.zeros(
            (config.population_size, config.topic_count), dtype=int
        )
        for topic in range(config.topic_count):
            topic_counts[:, topic] = np.sum(
                consumed_topics == topic, axis=1
            )
        dominant_topic = np.argmax(topic_counts, axis=1)
        same_topic = dominant_topic == self.last_dominant_topic
        self.dominant_topic_streak = np.where(
            same_topic, self.dominant_topic_streak + 1, 1
        )
        self.last_dominant_topic = dominant_topic
        eligible = (
            self.dominant_topic_streak >= config.preference_drift_after
        )
        if np.any(eligible) and config.preference_drift_rate > 0.0:
            rate = config.preference_drift_rate
            self.preferences[eligible] *= 1.0 - rate
            rows = np.flatnonzero(eligible)
            self.preferences[rows, dominant_topic[eligible]] += rate
            self.preferences /= self.preferences.sum(axis=1, keepdims=True)

        off_agenda = np.isin(
            consumed_topics, config.off_agenda_topic_indices
        )
        return {
            "attention_by_topic": attention_by_topic,
            "organic_attention_by_topic": organic_attention_by_topic,
            "official_exposure": consumed_sources.mean(axis=1),
            "off_agenda_exposure": off_agenda.mean(axis=1),
            "emotional_exposure": consumed_emotions.mean(axis=1),
            "total_interactions": int(interactions.sum()),
        }

    def _update_learning_and_trust(
        self,
        *,
        official_exposure: np.ndarray,
        off_agenda_exposure: np.ndarray,
        emotional_exposure: np.ndarray,
        response_effect: float,
    ) -> None:
        config = self.config
        z_digital_government = 2.0 * config.digital_government_level - 1.0
        z_literacy = 2.0 * self.digital_literacy - 1.0

        learning_latent = (
            0.10
            + config.beta_digital_government_to_learning * z_digital_government
            + config.beta_digital_literacy_to_learning * z_literacy
            + config.beta_digital_government_literacy_interaction
            * z_digital_government
            * z_literacy
            + 0.35 * config.digital_platform_complexity
            + 0.20 * emotional_exposure
        )
        learning_target = np.asarray(_sigmoid(learning_latent), dtype=float)
        self.learning_cost += config.learning_update_rate * (
            learning_target - self.learning_cost
        )
        self.learning_cost = np.clip(self.learning_cost, 0.0, 1.0)

        z_learning = 2.0 * self.learning_cost - 1.0
        trust_latent = (
            0.80
            + config.beta_digital_government_to_trust
            * z_digital_government
            + config.beta_learning_cost_to_trust * z_learning
            + 0.45 * (official_exposure - 0.25)
            + 0.75 * response_effect
            - 0.60 * off_agenda_exposure
        )
        trust_target = np.asarray(_sigmoid(trust_latent), dtype=float)
        self.trust += config.trust_update_rate * (
            trust_target - self.trust
        )
        self.trust = np.clip(self.trust, 0.0, 1.0)

    def _monitor_and_schedule(
        self,
        *,
        step: int,
        organic_attention_by_topic: np.ndarray,
        total_attention: float,
    ) -> int:
        if total_attention <= 0.0:
            return 0

        config = self.config
        shares = organic_attention_by_topic / total_attention
        already_pending = {
            response.topic for response in self.pending_responses
        }
        scheduled = 0
        for topic, share in enumerate(shares):
            if share > config.response_threshold:
                self.response_threshold_streak[topic] += 1
            else:
                self.response_threshold_streak[topic] = 0
                continue

            if config.response_strategy == "selective":
                should_schedule = topic in config.agenda_topic_indices
            elif config.response_strategy == "wait":
                should_schedule = (
                    self.response_threshold_streak[topic]
                    >= config.wait_observation_steps
                )
            else:
                should_schedule = True

            if not should_schedule or topic in already_pending:
                continue
            due_step = step + max(1, config.response_delay)
            self.pending_responses.append(
                PendingResponse(
                    topic=topic,
                    trigger_step=step,
                    due_step=due_step,
                )
            )
            already_pending.add(topic)
            scheduled += 1

        self.responses_scheduled += scheduled
        return scheduled

    def _update_storm_state(self, step: int, storm_share: float) -> bool:
        is_storm = storm_share > self.config.storm_threshold
        if is_storm:
            if self._active_storm_start is None:
                self._active_storm_start = step
                self._active_storm_duration = 0
                self._active_storm_peak = 0.0
            self._active_storm_duration += 1
            self._active_storm_peak = max(
                self._active_storm_peak, storm_share
            )
        elif self._active_storm_start is not None:
            self.storm_episodes.append(
                StormEpisode(
                    start_step=self._active_storm_start,
                    end_step=step - 1,
                    duration=self._active_storm_duration,
                    peak_share=self._active_storm_peak,
                )
            )
            self._active_storm_start = None
            self._active_storm_duration = 0
            self._active_storm_peak = 0.0
        return is_storm

    def _close_active_storm(self, final_step: int) -> None:
        if self._active_storm_start is None:
            return
        self.storm_episodes.append(
            StormEpisode(
                start_step=self._active_storm_start,
                end_step=final_step,
                duration=self._active_storm_duration,
                peak_share=self._active_storm_peak,
            )
        )
        self._active_storm_start = None
        self._active_storm_duration = 0
        self._active_storm_peak = 0.0

    def _decay_and_prune(self, step: int) -> None:
        for item in self.information_pool:
            item.heat *= self.config.heat_decay
        self.information_pool = [
            item
            for item in self.information_pool
            if item.heat >= self.config.minimum_heat
            or step - item.created_at < 1
        ]

    def run(self, steps: int | None = None) -> SimulationResult:
        """Run the model and return complete step-level and summary data."""

        if self._has_run:
            raise RuntimeError(
                "a simulation instance can only be run once; "
                "create a new instance for another run"
            )
        total_steps = self.config.steps if steps is None else int(steps)
        if total_steps <= 0:
            raise ValueError("steps must be positive")
        self._has_run = True

        agenda_topics = np.asarray(
            self.config.agenda_topic_indices, dtype=int
        )
        off_agenda_topics = np.asarray(
            self.config.off_agenda_topic_indices, dtype=int
        )

        for step in range(total_steps):
            self.step = step
            response_effect, executed = self._government_action(step)
            self._add_spontaneous_information(
                step=step,
                count=self.config.spontaneous_posts_per_step,
            )

            topics, emotions, sources = self._pool_arrays()
            recommendations = self._recommend(topics)
            public = self._public_action(
                recommendations, topics, emotions, sources
            )

            total_attention = float(
                np.sum(public["attention_by_topic"])
            )
            if total_attention > 0.0:
                agenda_share = float(
                    np.sum(public["attention_by_topic"][agenda_topics])
                    / total_attention
                )
                official_attention = float(
                    np.mean(public["official_exposure"])
                )
                off_agenda_shares = (
                    public["attention_by_topic"][off_agenda_topics]
                    / total_attention
                    if off_agenda_topics.size
                    else np.array([0.0])
                )
                storm_share = float(off_agenda_shares.max(initial=0.0))
            else:
                agenda_share = 0.0
                official_attention = 0.0
                storm_share = 0.0

            agenda_divergence = float(
                np.clip(
                    1.0
                    - agenda_share / self.config.agenda_target_share,
                    0.0,
                    1.0,
                )
            )
            is_storm = self._update_storm_state(step, storm_share)
            scheduled = self._monitor_and_schedule(
                step=step,
                organic_attention_by_topic=public[
                    "organic_attention_by_topic"
                ],
                total_attention=total_attention,
            )
            self._update_learning_and_trust(
                official_exposure=public["official_exposure"],
                off_agenda_exposure=public["off_agenda_exposure"],
                emotional_exposure=public["emotional_exposure"],
                response_effect=response_effect,
            )

            topic_shares = (
                public["attention_by_topic"] / total_attention
                if total_attention > 0.0
                else np.zeros(self.config.topic_count)
            )
            record: dict[str, Any] = {
                "step": step,
                "alpha": self.config.alpha,
                "agenda_share": agenda_share,
                "agenda_divergence": agenda_divergence,
                "official_attention_share": official_attention,
                "off_agenda_peak_share": storm_share,
                "storm": int(is_storm),
                "mean_trust": float(np.mean(self.trust)),
                "trust_p10": float(np.quantile(self.trust, 0.10)),
                "trust_p90": float(np.quantile(self.trust, 0.90)),
                "mean_learning_cost": float(
                    np.mean(self.learning_cost)
                ),
                "total_interactions": public["total_interactions"],
                "pool_size": len(self.information_pool),
                "responses_scheduled": scheduled,
                "responses_executed": executed,
                "response_effect": response_effect,
            }
            for topic_index, topic_name in enumerate(
                self.config.topic_names
            ):
                record[f"topic_share_{topic_index}_{topic_name}"] = float(
                    topic_shares[topic_index]
                )
            self.records.append(record)
            self._decay_and_prune(step)

        self._close_active_storm(total_steps - 1)
        metrics = pd.DataFrame.from_records(self.records)
        storms = pd.DataFrame(
            [asdict(storm) for storm in self.storm_episodes],
            columns=["start_step", "end_step", "duration", "peak_share"],
        )
        summary = self._summarize(metrics, storms)
        return SimulationResult(
            config=self.config,
            metrics=metrics,
            storms=storms,
            summary=summary,
        )

    def _summarize(
        self, metrics: pd.DataFrame, storms: pd.DataFrame
    ) -> dict[str, Any]:
        window_size = min(100, len(metrics))
        tail = metrics.tail(window_size)
        steps = len(metrics)
        tail_start = int(tail["step"].iloc[0])
        tail_end = int(tail["step"].iloc[-1])
        if storms.empty:
            tail_storms = storms
        else:
            tail_storms = storms[
                (storms["end_step"] >= tail_start)
                & (storms["start_step"] <= tail_end)
            ]
        storm_count = len(tail_storms)
        full_run_storm_count = len(storms)
        return {
            "alpha": self.config.alpha,
            "seed": self.config.seed,
            "steps": steps,
            "population_size": self.config.population_size,
            "mean_agenda_divergence": float(
                tail["agenda_divergence"].mean()
            ),
            "system_stability": float(
                tail["agenda_divergence"].var(ddof=0)
            ),
            "mean_agenda_share": float(tail["agenda_share"].mean()),
            "mean_official_attention_share": float(
                tail["official_attention_share"].mean()
            ),
            "mean_trust": float(tail["mean_trust"].mean()),
            "mean_learning_cost": float(
                tail["mean_learning_cost"].mean()
            ),
            "storm_count": storm_count,
            "storm_frequency_per_100_steps": float(
                storm_count / max(window_size, 1) * 100.0
            ),
            "storm_time_share": float(tail["storm"].mean()),
            "storm_mean_peak": float(
                tail_storms["peak_share"].mean() if storm_count else 0.0
            ),
            "storm_max_peak": float(
                tail_storms["peak_share"].max() if storm_count else 0.0
            ),
            "storm_mean_duration": float(
                tail_storms["duration"].mean() if storm_count else 0.0
            ),
            "full_run_storm_count": full_run_storm_count,
            "full_run_storm_frequency_per_100_steps": float(
                full_run_storm_count / max(steps, 1) * 100.0
            ),
            "full_run_storm_time_share": float(metrics["storm"].mean()),
            "responses_scheduled": self.responses_scheduled,
            "responses_executed": self.responses_executed,
            "total_interactions": int(
                metrics["total_interactions"].sum()
            ),
            "final_pool_size": len(self.information_pool),
        }
