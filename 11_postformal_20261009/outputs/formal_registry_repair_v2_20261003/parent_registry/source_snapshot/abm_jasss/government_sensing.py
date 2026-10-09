"""Restricted, deterministic inference from delivered public information only.

All four information cells fit the same simplex grid with the same loss and
regularizer.  A fixed synthetic reference population (independent of the world)
has mean preference equal to each grid candidate.  Public content topic, emotion,
heat and source enter the forward model; private interaction propensity and trust
are integrated approximately using fixed reference draws.  The opaque estimator
averages forward predictions across a registered rule prior; disclosure replaces
every prior slot by the disclosed rule.  Both use the same number of evaluations.

This is a deliberately limited numerical inverse, not an identified estimator of
the true population.  The latest delivered window-end content catalogue is an
approximation to an evolving historical window.  A finite grid/reference panel,
unobserved heterogeneity, unknown sampling selectivity and non-invertible Top-K
can produce bias or no improvement.  Missing catalogues use an explicitly logged
neutral reference catalogue and are unsuitable for the main formal experiment.
No world object, full simulation configuration, actual exposure probabilities,
latent preferences, or research-evaluator records are accepted by this module.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .public_signals import ObservationPacket


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _finite(value, name, minimum=0, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"{name} outside permitted range")


def _distribution(values, name, n_topics=None):
    if type(values) is not tuple or not values:
        raise ValueError(f"{name} must be a nonempty immutable tuple")
    if n_topics is not None and len(values) != n_topics:
        raise ValueError(f"{name} taxonomy mismatch")
    for value in values:
        _finite(value, name, 0, 1)
    if not math.isclose(sum(values), 1.0, abs_tol=1e-10, rel_tol=0):
        raise ValueError(f"{name} must sum to one")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class PublicContent:
    item_id: str
    topic: int
    emotion: float
    heat: float
    official: bool
    born: int

    def __post_init__(self):
        if not isinstance(self.item_id, (str, int)) or isinstance(self.item_id, bool):
            raise ValueError("item_id must be a public stable string or integer")
        _integer(self.topic, "topic")
        _finite(self.emotion, "emotion", 0, 1)
        _finite(self.heat, "heat")
        if type(self.official) is not bool:
            raise ValueError("official must be boolean")
        _integer(self.born, "born", -1)


@dataclass(frozen=True, slots=True)
class SurveyReport:
    report_id: str
    measured_at: int
    available_at: int
    sample_size: int
    estimate: tuple[float, ...]
    version: str = "1"

    def __post_init__(self):
        if (type(self.report_id) is not str or not self.report_id
                or type(self.version) is not str or not self.version):
            raise ValueError("Survey report requires identifiers")
        _integer(self.measured_at, "measured_at")
        _integer(self.available_at, "available_at")
        _integer(self.sample_size, "sample_size", 1)
        if self.available_at <= self.measured_at:
            raise ValueError("Survey cannot be delivered in its measurement tick")
        _distribution(self.estimate, "survey estimate")


@dataclass(frozen=True, slots=True)
class RuleDisclosure:
    version: str
    effective_at: int
    available_at: int
    alpha: float
    ranking: str = "topk"
    temperature: float = .15
    attention_budget: int = 5
    full_heat_off: bool = False

    def __post_init__(self):
        if not isinstance(self.version, str) or not self.version:
            raise ValueError("Rule disclosure requires a version")
        _integer(self.effective_at, "effective_at")
        _integer(self.available_at, "available_at")
        _finite(self.alpha, "alpha", 0, 1)
        _finite(self.temperature, "temperature")
        if self.temperature == 0 or self.ranking not in ("topk", "softmax"):
            raise ValueError("Unknown or invalid ranking rule")
        _integer(self.attention_budget, "attention_budget", 1)
        if type(self.full_heat_off) is not bool:
            raise ValueError("full_heat_off must be boolean")


@dataclass(frozen=True, slots=True)
class GovernmentInformation:
    now: int
    public_packet: ObservationPacket | None = None
    survey: SurveyReport | None = None
    rule: RuleDisclosure | None = None
    public_catalog: tuple[PublicContent, ...] = ()
    catalog_observed_at: int | None = None

    def __post_init__(self):
        _integer(self.now, "now")
        if type(self.public_catalog) is not tuple:
            raise ValueError("public_catalog must be immutable")
        if any(type(item) is not PublicContent for item in self.public_catalog):
            raise TypeError("Only whitelisted PublicContent is permitted")
        if self.public_catalog:
            _integer(self.catalog_observed_at, "catalog_observed_at")
            if self.catalog_observed_at >= self.now:
                raise ValueError("Current or future catalogues are not delivered history")
            if any(item.born > self.catalog_observed_at for item in self.public_catalog):
                raise ValueError("Catalogue contains unborn content")
            if len({item.item_id for item in self.public_catalog}) != len(self.public_catalog):
                raise ValueError("Duplicate catalogue content IDs")
        elif self.catalog_observed_at is not None:
            raise ValueError("Empty catalogue must not claim an observation time")


@dataclass(frozen=True, slots=True)
class SensingSettings:
    n_topics: int
    update_frequency: int = 1
    smoothing: float = 1.0
    pref_info: bool = False
    rule_info: bool = False
    grid_resolution: int = 6
    reference_agents: int = 8
    reference_seed: int = 1729
    reference_heterogeneity: float = .75
    reference_interaction_mean: float = .3
    reference_interaction_sd: float = .1
    reference_trust_mean: float = .69
    reference_trust_sd: float = .12
    reference_trust_feedback: float = 0.0
    opaque_alpha: tuple[float, ...] = (0.0, .5, 1.0)
    opaque_rankings: tuple[str, ...] = ("topk",)
    opaque_temperature: float = .15
    opaque_attention_budget: int = 5
    regularization: float = .01
    survey_weight: float = 1.0
    tie_tolerance: float = 1e-12

    def __post_init__(self):
        for key, minimum in (("n_topics", 2), ("update_frequency", 1), ("grid_resolution", 1),
                             ("reference_agents", 1), ("reference_seed", 0),
                             ("opaque_attention_budget", 1)):
            _integer(getattr(self, key), key, minimum)
        for key in ("pref_info", "rule_info"):
            if type(getattr(self, key)) is not bool:
                raise ValueError(f"{key} must be boolean")
        for key in ("smoothing", "reference_heterogeneity", "reference_interaction_mean",
                    "reference_trust_mean", "reference_trust_feedback"):
            _finite(getattr(self, key), key, 0, 1)
        if self.smoothing == 0:
            raise ValueError("smoothing must be positive")
        for key in ("reference_interaction_sd", "reference_trust_sd", "regularization",
                    "survey_weight", "tie_tolerance", "opaque_temperature"):
            _finite(getattr(self, key), key)
        if self.opaque_temperature == 0:
            raise ValueError("opaque_temperature must be positive")
        if type(self.opaque_alpha) is not tuple or not self.opaque_alpha:
            raise ValueError("opaque_alpha must be a nonempty immutable prior")
        for alpha in self.opaque_alpha:
            _finite(alpha, "opaque_alpha", 0, 1)
        if (type(self.opaque_rankings) is not tuple or not self.opaque_rankings
                or any(rule not in ("topk", "softmax") for rule in self.opaque_rankings)):
            raise ValueError("Invalid opaque ranking prior")
        if math.comb(self.grid_resolution + self.n_topics - 1, self.n_topics - 1) > 10000:
            raise ValueError("Candidate budget exceeds 10000; register a smaller grid")


def _compositions(total, parts):
    if parts == 1:
        yield (total,)
    else:
        for first in range(total + 1):
            for rest in _compositions(total - first, parts - 1):
                yield (first,) + rest


class GovernmentSensing:
    """An estimator whose only update boundary is GovernmentInformation."""

    def __init__(self, settings: SensingSettings):
        if type(settings) is not SensingSettings:
            raise TypeError("SensingSettings, not a complete simulation config, is required")
        self.settings = settings
        k, r = settings.n_topics, settings.reference_agents
        self._prior = np.full(k, 1 / k)
        candidates = [tuple(x / settings.grid_resolution for x in composition)
                      for composition in _compositions(settings.grid_resolution, k)]
        if not any(np.allclose(candidate, self._prior, atol=1e-12, rtol=0) for candidate in candidates):
            candidates.append(tuple(self._prior))
        self._candidates = np.asarray(candidates)
        generator = np.random.default_rng(settings.reference_seed)
        perturbations = generator.normal(size=(r, k))
        self._reference_preferences = np.empty((len(candidates), r, k))
        for index, preference in enumerate(self._candidates):
            active = preference > 0
            centered = perturbations[:, active].copy()
            centered -= centered.mean(axis=1, keepdims=True)
            centered -= centered.mean(axis=0, keepdims=True)
            bound = np.abs(centered).max()
            delta = np.zeros((r, k))
            if bound > 0:
                delta[:, active] = centered * (settings.reference_heterogeneity * preference[active].min() / bound)
            self._reference_preferences[index] = preference + delta
        self._reference_interaction = np.clip(generator.normal(settings.reference_interaction_mean,
                                                               settings.reference_interaction_sd, r), 0, 1)
        self._reference_trust = np.clip(generator.normal(settings.reference_trust_mean,
                                                         settings.reference_trust_sd, r), 0, 1)
        self._state = {"estimate": self._prior.tolist(), "has_data": False,
                       "estimate_updated_at": None, "evidence_signature": None,
                       "estimate_input_packet_id": None, "estimate_input_signal": None,
                       "estimate_input_survey_id": None, "estimate_input_rule_version": None,
                       "candidate_estimate": None, "fit_residual": None, "last_seen_at": None}

    @property
    def estimate(self):
        return tuple(self._state["estimate"])

    @property
    def has_data(self):
        return self._state["has_data"]

    def _validate(self, info):
        if type(info) is not GovernmentInformation:
            raise TypeError("Only the whitelisted GovernmentInformation envelope is accepted")
        if self._state["last_seen_at"] is not None and info.now < self._state["last_seen_at"]:
            raise ValueError("Government observation time cannot go backwards")
        if info.survey is not None:
            if type(info.survey) is not SurveyReport or not self.settings.pref_info:
                raise PermissionError("Survey information is not permitted in this cell")
            if info.survey.available_at > info.now or info.survey.measured_at >= info.now:
                raise ValueError("Survey is not yet available")
            _distribution(info.survey.estimate, "survey estimate", self.settings.n_topics)
        if info.rule is not None:
            if type(info.rule) is not RuleDisclosure or not self.settings.rule_info:
                raise PermissionError("Rule disclosure is not permitted in this cell")
            if info.rule.available_at > info.now or info.rule.effective_at > info.now:
                raise ValueError("Rule disclosure is not yet applicable and available")
        if info.public_packet is not None:
            from .public_signals import ObservationPacket
            if type(info.public_packet) is not ObservationPacket:
                raise TypeError("Only a publisher ObservationPacket is accepted")
            packet = info.public_packet
            if packet.available_at > info.now or packet.generated_at >= info.now:
                raise ValueError("Public packet is not yet delivered")
            if packet.window_end >= info.now:
                raise ValueError("Public packet contains current or future observations")
            if packet.signal is not None:
                _distribution(packet.signal, "public signal", self.settings.n_topics)
            if info.public_catalog and info.catalog_observed_at != packet.window_end:
                raise ValueError("Catalogue must describe the delivered window-end tick")
        elif info.public_catalog:
            raise ValueError("A public catalogue needs its delivered observation packet")
        if any(item.topic >= self.settings.n_topics for item in info.public_catalog):
            raise ValueError("Catalogue taxonomy mismatch")

    def _forward(self, catalog, rule):
        """Return C by K probability predictions; zero expected activity is NaN."""
        settings = self.settings
        topics = np.asarray([item.topic for item in catalog], dtype=int)
        emotions = np.asarray([item.emotion for item in catalog])
        heat = np.log1p([item.heat for item in catalog])
        if heat.max() > 0:
            heat /= heat.max()
        if rule.full_heat_off:
            heat[:] = 0
        reference = self._reference_preferences
        similarity = reference[:, :, topics] / np.linalg.norm(reference, axis=2)[:, :, None]
        scores = rule.alpha * heat[None, None, :] + (1 - rule.alpha) * similarity
        # Potential tie/softmax draws are stable by synthetic person and public item.
        uniform = np.asarray([[((int.from_bytes(hashlib.sha256(
            f"{settings.reference_seed}:{person}:{item.item_id}".encode()).digest()[:8], "big") >> 11) + .5) / 2**53
                               for item in catalog] for person in range(settings.reference_agents)])
        keys = (scores / rule.temperature - np.log(-np.log(uniform))[None, :, :]
                if rule.ranking == "softmax" else scores)
        order = np.lexsort((np.broadcast_to(uniform, keys.shape), -keys), axis=-1)
        selected = order[:, :, :min(rule.attention_budget, len(catalog))]
        official = np.asarray([item.official for item in catalog])
        factor = np.where(official[None, :],
                          1 + settings.reference_trust_feedback * (2 * self._reference_trust[:, None] - 1),
                          1 - settings.reference_trust_feedback * (2 * self._reference_trust[:, None] - 1))
        interaction = np.clip(self._reference_interaction[:, None] * emotions[None, :] * factor, 0, 1)
        expected = np.take_along_axis(np.broadcast_to(interaction, scores.shape), selected, axis=2)
        counts = np.stack([(expected * (topics[selected] == topic)).sum(axis=(1, 2))
                           for topic in range(settings.n_topics)], axis=1)
        totals = counts.sum(axis=1, keepdims=True)
        return np.divide(counts, totals, out=np.full_like(counts, np.nan), where=totals > 0)

    def _fit(self, info):
        s = self.settings
        packet = info.public_packet
        use_public = packet is not None and packet.signal is not None
        use_survey = info.survey is not None
        loss = s.regularization * ((self._candidates - self._prior) ** 2).sum(axis=1)
        public_residuals = None
        forward_calls = 0
        predictions = None
        neutral_catalog = False
        if use_public:
            catalog = info.public_catalog
            if not catalog:
                neutral_catalog = True
                catalog = tuple(PublicContent(f"neutral-{topic}", topic, .5, 1., False, 0)
                                for topic in range(s.n_topics))
            rules = [RuleDisclosure("registered-prior", 0, 0, alpha, ranking,
                                    s.opaque_temperature, s.opaque_attention_budget)
                     for alpha in s.opaque_alpha for ranking in s.opaque_rankings]
            applicable_rule = info.rule is not None and info.rule.effective_at <= packet.window_end
            if applicable_rule:
                rules = [info.rule for _ in rules]
            predictions = np.mean(np.stack([self._forward(catalog, rule) for rule in rules]), axis=0)
            forward_calls = len(rules) * len(self._candidates)
            public_residuals = ((predictions - np.asarray(packet.signal)) ** 2).sum(axis=1)
            finite = np.isfinite(public_residuals)
            if not finite.any():
                use_public = False
                public_residuals = None
            else:
                loss += np.where(finite, public_residuals, np.inf)
        if use_survey:
            loss += s.survey_weight * ((self._candidates - np.asarray(info.survey.estimate)) ** 2).sum(axis=1)
        if not use_public and not use_survey:
            return None, {"reason": "no_predictive_support", "forward_evaluations": forward_calls,
                          "catalog_mode": "neutral_fallback" if neutral_catalog else "window_end_approximation"}
        best = np.flatnonzero(loss <= loss.min() + s.tie_tolerance)
        estimate = self._candidates[best].mean(axis=0)
        estimate /= estimate.sum()
        fitted = predictions[best].mean(axis=0).tolist() if use_public else None
        return estimate, {"fit_loss": float(loss[best].mean()),
                          "fit_residual": float(public_residuals[best].mean()) if use_public else None,
                          "fitted_public_signal": fitted, "minimizer_count": len(best),
                          "candidate_count": len(self._candidates), "forward_evaluations": forward_calls,
                          "reference_agents": s.reference_agents,
                          "catalog_mode": ("neutral_fallback" if neutral_catalog else "window_end_approximation")
                          if use_public else "unused", "public_used": use_public, "survey_used": use_survey,
                          "rule_used": use_public and applicable_rule,
                          "rule_window_status": ("no_disclosure" if info.rule is None else
                              "not_applicable_to_source_window" if not applicable_rule else
                              "single_rule_window_approximation" if info.rule.effective_at > packet.window_start else
                              "applies_to_entire_window") if use_public else "unused"}

    def update(self, info: GovernmentInformation):
        self._validate(info)
        self._state["last_seen_at"] = info.now
        packet = info.public_packet
        public_valid = packet is not None and packet.signal is not None
        evidence = {"public": packet.evidence_signature if public_valid else None,
                    # Report ID alone is not evidence. Version and measured data are.
                    "survey": ({key: value for key, value in asdict(info.survey).items()
                                if key not in ("report_id", "available_at")}
                               if info.survey is not None else None),
                    "rule": ({key: value for key, value in asdict(info.rule).items()
                              if key != "available_at"} if info.rule is not None and public_valid
                             and info.rule.effective_at <= packet.window_end else None),
                    "catalog": [asdict(item) for item in info.public_catalog] if public_valid else None}
        signature = _digest(evidence)
        output = {"now": info.now, "updated": False, "available_packet_id": packet.packet_id if packet else None,
                  "input_evidence_signature": signature,
                  "allowed_fields": ["now", "public_packet", "public_catalog", "catalog_observed_at"]
                  + (["survey"] if self.settings.pref_info else []) + (["rule"] if self.settings.rule_info else []),
                  "consumed_fields": [], "forward_evaluations": 0}
        if info.now % self.settings.update_frequency:
            output["reason"] = "not_update_tick"
        elif not public_valid and info.survey is None:
            output["reason"] = "no_preference_observation"
        elif signature == self._state["evidence_signature"]:
            output["reason"] = "unchanged_evidence"
        else:
            candidate, fit = self._fit(info)
            output.update(fit)
            if candidate is not None:
                estimate = (1 - self.settings.smoothing) * np.asarray(self.estimate) + self.settings.smoothing * candidate
                estimate /= estimate.sum()
                used_public = fit["public_used"]
                self._state.update({"estimate": estimate.tolist(), "has_data": True,
                                    "estimate_updated_at": info.now, "evidence_signature": signature,
                                    "estimate_input_packet_id": packet.packet_id if used_public else None,
                                    "estimate_input_signal": list(packet.signal) if used_public else None,
                                    "estimate_input_survey_id": info.survey.report_id if fit["survey_used"] else None,
                                    "estimate_input_rule_version": info.rule.version if fit["rule_used"] else None,
                                    "candidate_estimate": candidate.tolist(), "fit_residual": fit["fit_residual"]})
                output.update({"updated": True, "reason": "updated"})
                output["consumed_fields"] = (["public_packet.signal", "public_packet.evidence_signature"] if used_public else [])
                if used_public and info.public_catalog:
                    output["consumed_fields"].append("public_catalog")
                if fit["survey_used"]:
                    output["consumed_fields"].append("survey.estimate")
                if fit["rule_used"]:
                    output["consumed_fields"].extend(["rule.alpha", "rule.ranking", "rule.temperature",
                                                      "rule.attention_budget", "rule.full_heat_off"])
        output.update(json.loads(json.dumps(self._state)))
        return output

    def snapshot(self):
        return {"schema_version": "government-sensing-1", "settings": asdict(self.settings),
                "state": json.loads(json.dumps(self._state))}

    @classmethod
    def from_snapshot(cls, snapshot):
        if set(snapshot) != {"schema_version", "settings", "state"} or snapshot["schema_version"] != "government-sensing-1":
            raise ValueError("Unknown government sensing snapshot schema")
        settings = dict(snapshot["settings"])
        for key in ("opaque_alpha", "opaque_rankings"):
            settings[key] = tuple(settings[key])
        instance = cls(SensingSettings(**settings))
        if set(snapshot["state"]) != set(instance._state):
            raise ValueError("Unknown or missing estimator state fields")
        state = json.loads(json.dumps(snapshot["state"], allow_nan=False))
        _distribution(tuple(state["estimate"]), "restored estimate", instance.settings.n_topics)
        if type(state["has_data"]) is not bool:
            raise ValueError("Invalid restored observation status")
        instance._state = state
        return instance
