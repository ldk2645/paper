"""A new model, not a reconstruction or replication of the legacy manuscript."""
from collections import deque
from dataclasses import asdict, dataclass
import math

import numpy as np


ARMS = ("platform", "survey", "fused", "oracle")
STREAMS = ("initialization", "content", "ranking", "interaction", "survey", "panel", "government")


@dataclass(frozen=True)
class Config:
    n_agents: int = 300
    n_topics: int = 4
    steps: int = 1000
    final_window: int = 300
    alpha: float = 0.5
    attention_budget: int = 5
    initial_items: int = 24
    arrivals_per_step: int = 4
    preference_concentration: float = 1.0
    population_concentration: float = 3.0
    population_weights: tuple = ()
    supply_weights: tuple = ()
    emotion_mean: float = 0.4
    emotion_concentration: float = 5.0
    emotion_advantage: float = 0.25
    advantaged_topic: int = 3
    interaction_mean: float = 0.3
    interaction_sd: float = 0.1
    heat_retention: float = 0.95
    heat_floor: float = 0.01
    max_item_age: int = 200
    cold_start_rounds: int = 1
    ranking: str = "topk"
    temperature: float = 0.15
    drift_rate: float = 0.0
    drift_threshold: int = 4
    observation_window: int = 20
    observation_interval: int = 10
    observation_delay: int = 0
    signal: str = "exposure"
    survey_size: int = 30
    survey_noise_sd: float = 0.0
    survey_selection_bias: float = 0.0
    platform_panel_size: int = 0
    fusion_weight: float = 0.5
    government_policy: str = "none"
    government_interval: int = 10
    government_delay: int = 3
    active_arm: str = "platform"

    def __post_init__(self):
        positive = ("n_agents", "n_topics", "steps", "final_window", "attention_budget",
                    "initial_items", "arrivals_per_step", "max_item_age", "cold_start_rounds", "drift_threshold",
                    "observation_window", "observation_interval", "survey_size", "government_interval")
        for key in positive:
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{key} must be a positive integer")
        if self.n_topics < 2 or self.final_window > self.steps:
            raise ValueError("Need >=2 topics and final_window <= steps")
        for key in ("alpha", "interaction_mean", "heat_retention", "drift_rate", "fusion_weight"):
            if not 0 <= getattr(self, key) <= 1:
                raise ValueError(f"{key} must be in [0,1]")
        for key in ("preference_concentration", "population_concentration", "emotion_concentration", "temperature"):
            if not math.isfinite(getattr(self, key)) or getattr(self, key) <= 0:
                raise ValueError(f"{key} must be finite and positive")
        for key in ("interaction_sd", "heat_floor", "survey_noise_sd"):
            if not math.isfinite(getattr(self, key)) or getattr(self, key) < 0:
                raise ValueError(f"{key} must be finite and nonnegative")
        if not math.isfinite(self.survey_selection_bias):
            raise ValueError("survey_selection_bias must be finite")
        if not 0 < self.emotion_mean < 1 or not 0 < self.emotion_mean + self.emotion_advantage < 1:
            raise ValueError("Both emotion means must be strictly between 0 and 1")
        for key in ("advantaged_topic", "platform_panel_size", "observation_delay", "government_delay"):
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{key} must be a nonnegative integer")
        if self.advantaged_topic >= self.n_topics:
            raise ValueError("advantaged_topic out of range")
        if self.survey_size > self.n_agents or self.platform_panel_size > self.n_agents:
            raise ValueError("Sample size cannot exceed population")
        if self.government_delay < 1:
            raise ValueError("Government action must use a previous time step")
        if self.ranking not in ("topk", "softmax") or self.signal not in ("exposure", "interaction"):
            raise ValueError("Unknown ranking or signal")
        if self.government_policy not in ("none", "communicate") or self.active_arm not in ARMS:
            raise ValueError("Unknown government policy or information arm")
        if self.supply_weights:
            weights = np.asarray(self.supply_weights, dtype=float)
            if weights.shape != (self.n_topics,) or not np.isfinite(weights).all() or (weights < 0).any() or weights.sum() <= 0:
                raise ValueError("Invalid supply_weights")
        if self.population_weights:
            weights = np.asarray(self.population_weights, dtype=float)
            if weights.shape != (self.n_topics,) or not np.isfinite(weights).all() or (weights <= 0).any():
                raise ValueError("population_weights must be finite and strictly positive")


def normalize(values):
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("Expected a finite nonnegative vector")
    total = values.sum()
    return values / total if total > 0 else np.full(values.size, 1 / values.size)


def tv(a, b):
    return float(0.5 * np.abs(np.asarray(a) - np.asarray(b)).sum())


def update_preferences(preferences, topic_counts, last_topic, streak, rate, threshold):
    """Only a unique modal topic qualifies; a tie resets the exposure streak."""
    maxima = topic_counts.max(axis=1)
    winners = topic_counts.argmax(axis=1)
    unique = ((topic_counts == maxima[:, None]).sum(axis=1) == 1) & (maxima > 0)
    dominant = np.where(unique, winners, -1)
    next_streak = np.where(unique, np.where(dominant == last_topic, streak + 1, 1), 0)
    eligible = unique & (next_streak >= threshold)
    updated = preferences.copy()
    updated[eligible] *= 1 - rate
    updated[np.flatnonzero(eligible), dominant[eligible]] += rate
    return updated, dominant, next_streak


def choose_items(scores, budget, ranking, temperature, rng):
    k = min(budget, scores.shape[1])
    if ranking == "softmax":
        # Gumbel top-k samples without replacement from exp(score / temperature).
        keys = scores / temperature + rng.gumbel(size=scores.shape)
    else:
        # Independent per-agent tie priorities; unequal scores remain unchanged.
        return np.lexsort((rng.random(scores.shape), -scores), axis=1)[:, :k]
    return np.argpartition(keys, keys.shape[1] - k, axis=1)[:, -k:]


def simulate(config: Config, seed: int):
    """Return a complete trajectory. All values are synthetic model outputs.

    No-feedback runs share one world across estimators. Feedback runs generate
    a world under active_arm; the other estimators are diagnostic only.
    """
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    streams = np.random.SeedSequence(seed).spawn(len(STREAMS))
    rng = {key: np.random.default_rng(stream) for key, stream in zip(STREAMS, streams)}
    n, m, horizon = config.n_agents, config.n_topics, config.steps
    population = (normalize(config.population_weights) if config.population_weights else
                  rng["initialization"].dirichlet(np.full(m, config.population_concentration)))
    preferences = rng["initialization"].dirichlet(population * m * config.preference_concentration, n)
    emotionality = np.clip(rng["initialization"].normal(config.interaction_mean, config.interaction_sd, n), 0, 1)
    initial_truth = preferences.mean(axis=0).copy()
    last_topic = np.full(n, -1, dtype=int)
    streak = np.zeros(n, dtype=int)
    supply = normalize(config.supply_weights or np.ones(m))
    panel = (rng["panel"].choice(n, config.platform_panel_size, replace=False)
             if config.platform_panel_size else np.arange(n))
    topics = np.empty(0, dtype=int)
    emotions = heat = np.empty(0, dtype=float)
    born = np.empty(0, dtype=int)
    sources = np.empty(0, dtype=bool)
    uniform = np.full(m, 1 / m)
    last_estimates = {arm: uniform.copy() for arm in ARMS}
    pending_observations = deque()
    pending_government = deque()
    signal_window = deque(maxlen=config.observation_window)
    rows = []
    last_observed_at = -1

    def add_items(count, t, probabilities, official=False):
        nonlocal topics, emotions, heat, born, sources
        stream = rng["government"] if official else rng["content"]
        new_topics = stream.choice(m, count, p=probabilities)
        means = config.emotion_mean + config.emotion_advantage * (new_topics == config.advantaged_topic)
        new_emotions = stream.beta(means * config.emotion_concentration, (1 - means) * config.emotion_concentration)
        topics = np.concatenate((topics, new_topics))
        emotions = np.concatenate((emotions, new_emotions))
        heat = np.concatenate((heat, np.zeros(count)))
        born = np.concatenate((born, np.full(count, t, dtype=int)))
        sources = np.concatenate((sources, np.full(count, official, dtype=bool)))

    add_items(config.initial_items, 0, supply)
    for t in range(horizon):
        official_arrivals = 0
        while pending_government and pending_government[0][0] <= t:
            _, probabilities = pending_government.popleft()
            add_items(1, t, probabilities, official=True)
            official_arrivals += 1
        add_items(config.arrivals_per_step, t, supply)
        truth = preferences.mean(axis=0)
        h = np.log1p(heat)
        if h.max() > 0:
            h = h / h.max()
        similarity = preferences[:, topics] / np.linalg.norm(preferences, axis=1)[:, None]
        scores = config.alpha * h[None, :] + (1 - config.alpha) * similarity
        selected = choose_items(scores, config.attention_budget, config.ranking, config.temperature, rng["ranking"])
        selected_topics = topics[selected]
        interaction = rng["interaction"].random(selected.shape) < emotionality[:, None] * emotions[selected]
        heat += np.bincount(selected[interaction], minlength=heat.size)
        counts = np.zeros((n, m), dtype=int)
        np.add.at(counts, (np.repeat(np.arange(n), selected.shape[1]), selected_topics.ravel()), 1)
        exposure = normalize(counts.sum(axis=0))
        panel_topics = selected_topics[panel]
        panel_signal = (np.bincount(panel_topics.ravel(), minlength=m) if config.signal == "exposure"
                        else np.bincount(panel_topics[interaction[panel]], minlength=m))
        signal_window.append(panel_signal)
        updated_now = False
        if t % config.observation_interval == 0:
            weights = None
            if config.survey_selection_bias != 0:
                log_weights = config.survey_selection_bias * preferences[:, config.advantaged_topic]
                weights = normalize(np.exp(np.maximum(log_weights - log_weights.max(), -700)))
            chosen = rng["survey"].choice(n, config.survey_size, replace=False, p=weights)
            reports = preferences[chosen].copy()
            if config.survey_noise_sd > 0:
                reports = np.maximum(reports + rng["survey"].normal(0, config.survey_noise_sd, reports.shape), 0)
                totals = reports.sum(axis=1)
                reports[totals == 0] = uniform
                reports /= reports.sum(axis=1)[:, None]
            survey = reports.mean(axis=0)
            platform = normalize(np.sum(signal_window, axis=0))
            fused = (1 - config.fusion_weight) * platform + config.fusion_weight * survey
            pending_observations.append((t + config.observation_delay, t, platform, survey, fused))
        while pending_observations and pending_observations[0][0] <= t:
            _, observed_at, *estimates = pending_observations.popleft()
            last_observed_at = observed_at
            for arm, value in zip(ARMS[:3], estimates):
                last_estimates[arm] = value
            updated_now = True
        last_estimates["oracle"] = truth.copy()
        if config.government_policy == "communicate" and t % config.government_interval == 0:
            pending_government.append((t + config.government_delay, last_estimates[config.active_arm].copy()))
        row = {"step": t, "attention_error": tv(exposure, truth), "preference_change": tv(truth, initial_truth),
               "uniform_prior_error": tv(uniform, truth),
               "interactions": int(interaction.sum()), "pool_size": int(heat.size),
               "official_exposure_share": float(sources[selected].mean()), "official_arrivals": official_arrivals,
               "observation_updated": int(updated_now), "last_observed_at": last_observed_at}
        for k in range(m):
            row[f"truth_{k}"] = float(truth[k])
            row[f"attention_{k}"] = float(exposure[k])
        true_maxima = np.flatnonzero(np.isclose(truth, truth.max(), rtol=0, atol=1e-12))
        for arm in ARMS:
            estimate = last_estimates[arm]
            row[f"error_{arm}"] = tv(estimate, truth)
            row[f"initial_error_{arm}"] = tv(estimate, initial_truth)
            estimated_maxima = np.flatnonzero(np.isclose(estimate, estimate.max(), rtol=0, atol=1e-12))
            # Chance of selecting a true maximizer under uniform random tie-breaking.
            row[f"top_accuracy_{arm}"] = len(np.intersect1d(true_maxima, estimated_maxima)) / len(estimated_maxima)
            for k in range(m):
                row[f"estimate_{arm}_{k}"] = float(estimate[k])
        rows.append(row)
        preferences, last_topic, streak = update_preferences(
            preferences, counts, last_topic, streak, config.drift_rate, config.drift_threshold)
        heat *= config.heat_retention
        # Every item is exposed to one recommendation round before removal.
        age_rounds = t - born + 1
        keep = ((heat >= config.heat_floor) | (age_rounds < config.cold_start_rounds)) & (age_rounds < config.max_item_age)
        topics, emotions, heat, born, sources = (x[keep] for x in (topics, emotions, heat, born, sources))
    return {"seed": seed, "config": asdict(config), "rows": rows}


def summarize(result):
    cfg = result["config"]
    rows = result["rows"]
    tail = rows[-cfg["final_window"]:]
    arms = ARMS if cfg["government_policy"] == "none" else (cfg["active_arm"],)
    out = []
    for arm in arms:
        errors = np.array([r[f"error_{arm}"] for r in tail])
        half = max(1, len(errors) // 2)
        out.append({"seed": result["seed"], "alpha": cfg["alpha"], "arm": arm,
                    "mean_error": float(errors.mean()), "sd_over_time": float(errors.std()),
                    "full_mean_error": float(np.mean([r[f"error_{arm}"] for r in rows])),
                    "initial_reference_error": float(np.mean([r[f"initial_error_{arm}"] for r in tail])),
                    "top_accuracy": float(np.mean([r[f"top_accuracy_{arm}"] for r in tail])),
                    "attention_error": float(np.mean([r["attention_error"] for r in tail])),
                    "uniform_prior_error": float(np.mean([r["uniform_prior_error"] for r in tail])),
                    "preference_change": float(np.mean([r["preference_change"] for r in tail])),
                    "late_window_shift": float(errors[-half:].mean() - errors[:half].mean())})
    return out
