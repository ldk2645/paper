"""Configuration for the separately versioned identification engine.

The v0.4 model remains importable from model.py for historical reproduction.
This engine changes tick order and information access; its runs cannot be pooled
with that model's outputs.
"""
from dataclasses import asdict, dataclass, fields
import math

from .model import Config as LegacyConfig

RESEARCH_VERSION = "0.5.0-dev"
SCHEMA_VERSION = "research-1"


@dataclass(frozen=True)
class ResearchConfig:
    n_agents: int = 60
    n_topics: int = 4
    steps: int = 160
    final_window: int = 60
    alpha: float = .5
    attention_budget: int = 5
    initial_items: int = 24
    arrivals_per_step: int = 4
    preference_concentration: float = 1.
    population_concentration: float = 3.
    population_weights: tuple = (1., 1., 1., 1.)
    supply_weights: tuple = ()
    emotion_mean: float = .4
    emotion_concentration: float = 5.
    emotion_advantage: float = .25
    advantaged_topic: int = 3
    interaction_mean: float = .3
    interaction_sd: float = .1
    heat_retention: float = .95
    heat_floor: float = .01
    max_item_age: int = 100
    cold_start_rounds: int = 2
    ranking: str = "topk"
    temperature: float = .15
    full_heat_off: bool = False
    drift_rate: float = .03
    drift_threshold: int = 4
    observation_window: int = 5
    observation_delay: int = 0
    sampling_rate: float = 1.
    observation_noise: float = 0.
    update_frequency: int = 5
    smoothing: float = 1.
    pref_info: bool = False
    rule_info: bool = False
    disclosure_delay: int = 0
    survey_size: int = 12
    survey_interval: int = 5
    survey_delay: int = 0
    survey_noise_sd: float = 0.
    survey_selection_bias: float = 0.
    survey_nonresponse: float = 0.
    inference_grid: int = 4
    reference_agents: int = 4
    reference_seed: int = 1729
    opaque_alpha: tuple = (0., .5, 1.)
    regularization: float = .01
    survey_weight: float = 1.
    government_interval: int = 1
    government_delay: int = 3
    agenda_topics: tuple = (0, 1, 2)
    agenda_target_share: float = .7
    routine_publication_interval: int = 10
    official_emotion_mean: float | None = .15
    response_enabled: bool = True
    response_publish: bool = True
    response_threshold: float = .15
    response_heat_retention: float = .7
    response_strategy: str = "hard"
    response_wait_observations: int = 3
    response_capacity: int = 1
    storm_threshold: float = .3
    initial_trust_mean: float = .69
    initial_trust_sd: float = .12
    trust_update_rate: float = .06
    trust_feedback_strength: float = .25
    trust_rule: str = "exposure"
    trust_official_gain: float = .45
    trust_offagenda_penalty: float = .6
    trust_response_gain: float = 0.
    trust_alignment_gain: float = 1.
    min_signal_coverage: float = .8
    completion_start: int = 0
    completion_end: int | None = None
    completion_followup: int = 20

    def __post_init__(self):
        # Reuse validation of retained physical mechanisms, not legacy timing.
        shared = {f.name: getattr(self, f.name) for f in fields(LegacyConfig)
                  if hasattr(self, f.name)}
        shared["government_delay"] = max(1, self.government_delay)
        LegacyConfig(**shared)
        for key in ("government_delay", "disclosure_delay", "survey_delay", "reference_seed",
                    "completion_start"):
            v = getattr(self, key)
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise ValueError(f"{key} must be a nonnegative integer")
        for key in ("update_frequency", "survey_interval", "inference_grid", "reference_agents",
                    "completion_followup"):
            v = getattr(self, key)
            if isinstance(v, bool) or not isinstance(v, int) or v < 1:
                raise ValueError(f"{key} must be a positive integer")
        for key in ("sampling_rate", "survey_nonresponse", "min_signal_coverage", "smoothing"):
            v = getattr(self, key)
            if not math.isfinite(v) or not 0 <= v <= 1:
                raise ValueError(f"{key} must be in [0,1]")
        if self.smoothing == 0:
            raise ValueError("smoothing must be positive")
        for key in ("observation_noise", "regularization", "survey_weight"):
            v = getattr(self, key)
            if not math.isfinite(v) or v < 0:
                raise ValueError(f"{key} must be finite and nonnegative")
        for key in ("pref_info", "rule_info", "full_heat_off", "response_enabled", "response_publish"):
            if not isinstance(getattr(self, key), bool):
                raise ValueError(f"{key} must be boolean")
        if self.completion_end is not None and (isinstance(self.completion_end, bool)
                or not isinstance(self.completion_end, int) or self.completion_end < self.completion_start
                or self.completion_end >= self.steps):
            raise ValueError("Invalid completion cohort window")
        if not self.opaque_alpha or any(not math.isfinite(x) or not 0 <= x <= 1 for x in self.opaque_alpha):
            raise ValueError("Invalid opaque rule prior")

    def to_dict(self):
        return asdict(self)

    def analysis_config(self):
        out = self.to_dict()
        if self.completion_end is None:
            out["completion_end"] = max(self.completion_start,
                                        self.steps - self.completion_followup - 1)
        return out

    @classmethod
    def from_dict(cls, value):
        value = dict(value)
        for name in ("population_weights", "supply_weights", "agenda_topics", "opaque_alpha"):
            if name in value:
                value[name] = tuple(value[name])
        return cls(**value)
