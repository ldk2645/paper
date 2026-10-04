"""Explicit boundary state for the v0.5 identification experiments.

Observe history -> infer -> schedule -> execute -> publish/rank/consume ->
record public signal/evaluation -> update preferences, trust, heat and lifetime.
Only this simulation/evaluation layer can see latent citizen state.
"""
from dataclasses import asdict, replace
from pathlib import Path
import copy
import hashlib
import json

import numpy as np

from .model import normalize, tv, update_preferences
from .governance import trust_update
from .research_config import ResearchConfig, RESEARCH_VERSION, SCHEMA_VERSION
from .research_randomness import AddressedRandomness
from .research_governance import DecisionSettings, ResponseQueue
from .public_signals import PublicSignalPublisher, ObservationPacket
from .government_sensing import (GovernmentSensing, GovernmentInformation, SensingSettings,
                                 SurveyReport, RuleDisclosure, PublicContent)


def jsonable(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def canonical_hash(value):
    return hashlib.sha256(json.dumps(jsonable(value), sort_keys=True, ensure_ascii=False,
                                    allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def source_hash():
    return canonical_hash({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in sorted(Path(__file__).parent.glob("*.py"))})


def distance(a, b):
    return None if a is None or b is None else tv(a, b)


class ResearchWorld:
    ARRAY_FIELDS = ("preferences", "emotionality", "baseline_trust", "trust", "initial_truth",
                    "last_topic", "streak", "panel", "ids", "topics", "emotions", "heat",
                    "born", "sources")
    INT_FIELDS = {"last_topic", "streak", "panel", "ids", "topics", "born", "sources"}
    LOG_FIELDS = ("trajectory", "events", "public_signal_ticks", "observation_packets",
                  "government_estimates", "supply_log", "publication_log", "survey_log",
                  "information_log", "treatments")

    def __init__(self, config: ResearchConfig, seed: int):
        self.config = config
        self.randomness = AddressedRandomness(seed)
        self.seed = seed
        self.tick = 0
        self.phase = "boundary_before_delivery"
        self.code_hash = source_hash()
        self.parent_world_id = None
        self.snapshot_id = None
        self.world_id = f"dev-{seed}-{canonical_hash(config.to_dict())[:12]}"
        self.initial_condition = "dirichlet"
        n, m = config.n_agents, config.n_topics
        rng = self.randomness.generator("initialization")
        population = (normalize(config.population_weights) if config.population_weights else
                      rng.dirichlet(np.full(m, config.population_concentration)))
        self.preferences = rng.dirichlet(population * m * config.preference_concentration, n)
        self.emotionality = np.clip(rng.normal(config.interaction_mean, config.interaction_sd, n), 0, 1)
        self.baseline_trust = np.clip(self.randomness.generator("trust").normal(
            config.initial_trust_mean, config.initial_trust_sd, n), 0, 1)
        self.trust = self.baseline_trust.copy()
        self.initial_truth = self.preferences.mean(axis=0)
        self.last_topic = np.full(n, -1, dtype=int)
        self.streak = np.zeros(n, dtype=int)
        count = int(np.floor(n * config.sampling_rate))
        self.panel = np.sort(self.randomness.generator("panel").choice(n, count, replace=False))
        for key in ("ids", "topics", "born", "sources"):
            setattr(self, key, np.empty(0, dtype=int))
        for key in ("emotions", "heat"):
            setattr(self, key, np.empty(0, dtype=float))
        for key in self.LOG_FIELDS:
            setattr(self, key, [])
        self.publisher = PublicSignalPublisher(m, config.observation_window,
                                              config.observation_delay, config.observation_noise)
        self.sensing = GovernmentSensing(self.sensing_settings())
        self.queue = ResponseQueue(self.decision_settings())
        self.pending_packets = []
        self.latest_packet = None
        self.packet_index = {}
        self.catalogs = {}
        self.truth_history = {}
        self.pending_surveys = []
        self.latest_survey = None
        self.pending_rules = []
        self.latest_rule = None
        self.current_rule_version = "ranking:initial"
        if config.rule_info:
            self.pending_rules.append(self.rule_record(0, config.disclosure_delay,
                                                       self.current_rule_version))
        self.add_content(config.initial_items, -1, 0, initial=True)
        self.initial_state_hash = canonical_hash({key: getattr(self, key) for key in self.ARRAY_FIELDS})

    def sensing_settings(self):
        c = self.config
        return SensingSettings(n_topics=c.n_topics, update_frequency=c.update_frequency,
                               smoothing=c.smoothing, pref_info=c.pref_info, rule_info=c.rule_info,
                               grid_resolution=c.inference_grid, reference_agents=c.reference_agents,
                               reference_seed=c.reference_seed, opaque_alpha=c.opaque_alpha,
                               regularization=c.regularization, survey_weight=c.survey_weight)

    def decision_settings(self):
        c = self.config
        return DecisionSettings(c.n_topics, c.agenda_topics, c.response_threshold, c.response_strategy,
                                c.response_wait_observations, c.response_capacity, c.government_delay,
                                c.response_heat_retention, c.response_publish)

    def rule_record(self, effective_at, available_at, version):
        c = self.config
        return asdict(RuleDisclosure(version=version, effective_at=effective_at,
                                     available_at=available_at, alpha=c.alpha, ranking=c.ranking,
                                     temperature=c.temperature, attention_budget=c.attention_budget,
                                     full_heat_off=c.full_heat_off))

    def add_content(self, count, step, source, topic=None, initial=False):
        c = self.config
        stream = ("initial_content" if initial else "ordinary_content" if source == 0 else
                  "routine_content" if source == 1 else "response_content")
        # Reply identity is keyed by time and topic, not the number of prior replies.
        rng = self.randomness.generator(stream, step, topic)
        topics = (rng.choice(c.n_topics, count, p=normalize(c.supply_weights or np.ones(c.n_topics)))
                  if topic is None else np.full(count, topic, dtype=int))
        means = c.emotion_mean + c.emotion_advantage * (topics == c.advantaged_topic)
        if source > 0 and c.official_emotion_mean is not None:
            means = np.full(count, c.official_emotion_mean)
        emotions = rng.beta(means * c.emotion_concentration, (1 - means) * c.emotion_concentration)
        base_id = (step + 2) * 1_000_000 + source * 100_000 + (0 if topic is None else topic * 100)
        ids = np.arange(base_id, base_id + count, dtype=int)
        if np.intersect1d(self.ids, ids).size:
            raise RuntimeError("Duplicate stable content identity")
        self.ids = np.concatenate((self.ids, ids))
        self.topics = np.concatenate((self.topics, topics))
        self.emotions = np.concatenate((self.emotions, emotions))
        self.heat = np.concatenate((self.heat, np.zeros(count)))
        self.born = np.concatenate((self.born, np.full(count, step, dtype=int)))
        self.sources = np.concatenate((self.sources, np.full(count, source, dtype=int)))
        records = [{"item_id": int(i), "topic": int(k), "emotion": float(e), "born": step,
                    "source": source} for i, k, e in zip(ids, topics, emotions)]
        (self.supply_log if source == 0 else self.publication_log).extend(records)

    def _deliver(self):
        t = self.tick
        remaining = []
        for data in self.pending_packets:
            if data["available_at"] <= t:
                packet = ObservationPacket.from_dict(data)
                self.observation_packets.append({**data, "received_at": t})
                if packet.signal is not None:
                    self.latest_packet = packet
            else:
                remaining.append(data)
        self.pending_packets = remaining
        for pending_name, latest_name, klass in (("pending_surveys", "latest_survey", SurveyReport),
                                                  ("pending_rules", "latest_rule", RuleDisclosure)):
            remaining = []
            for data in getattr(self, pending_name):
                if data["available_at"] <= t:
                    if klass is SurveyReport:
                        data = {**data, "estimate": tuple(data["estimate"])}
                    setattr(self, latest_name, klass(**data))
                else:
                    remaining.append(data)
            setattr(self, pending_name, remaining)

    def _survey(self, truth_before_consumption):
        c, t = self.config, self.tick
        if not c.pref_info or t % c.survey_interval:
            return
        rng = self.randomness.generator("survey", t)
        weights = None
        if c.survey_selection_bias:
            values = c.survey_selection_bias * self.preferences[:, c.advantaged_topic]
            weights = normalize(np.exp(np.maximum(values - values.max(), -700)))
        chosen = rng.choice(c.n_agents, c.survey_size, replace=False, p=weights)
        respondents = chosen[rng.random(len(chosen)) >= c.survey_nonresponse]
        if not len(respondents):
            self.survey_log.append({"measured_at": t, "status": "no_respondents", "sample_size": 0})
            return
        reports = self.preferences[respondents].copy()
        if c.survey_noise_sd:
            reports = np.maximum(reports + rng.normal(0, c.survey_noise_sd, reports.shape), 0)
            reports = reports[reports.sum(axis=1) > 0]
        if not len(reports):
            self.survey_log.append({"measured_at": t, "status": "no_valid_reports", "sample_size": 0})
            return
        reports /= reports.sum(axis=1)[:, None]
        report = SurveyReport(report_id=f"survey:{t}", measured_at=t,
                              available_at=t + 1 + c.survey_delay,
                              sample_size=len(reports), estimate=tuple(reports.mean(axis=0)))
        self.pending_surveys.append(asdict(report))
        self.survey_log.append({**asdict(report), "status": "valid", "invited": len(chosen)})

    def step(self):
        if self.tick >= self.config.steps:
            raise StopIteration("Configured horizon reached")
        if self.phase != "boundary_before_delivery":
            raise RuntimeError("Not at an executable tick boundary")
        c, t = self.config, self.tick
        truth = self.preferences.mean(axis=0).copy()
        self.truth_history[str(t)] = truth.tolist()
        self._deliver()
        packet = self.latest_packet
        catalog_step = None if packet is None else packet.window_end
        catalog = tuple(PublicContent(**item) for item in self.catalogs.get(str(catalog_step), []))
        info = GovernmentInformation(now=t, public_packet=packet, survey=self.latest_survey,
                                     rule=self.latest_rule, public_catalog=catalog,
                                     catalog_observed_at=catalog_step)
        estimate_record = self.sensing.update(info)
        self.government_estimates.append(jsonable(estimate_record))
        # This is the exact permitted packet; evaluator truth is stored elsewhere.
        information_record = jsonable(asdict(info))
        self.information_log.append(information_record)
        reference = {"estimate_record": len(self.government_estimates) - 1,
                     "information_hash": canonical_hash(information_record),
                     "latest_packet_id": None if packet is None else packet.packet_id}
        plans = []
        if c.response_enabled and t % c.government_interval == 0:
            plans = self.queue.schedule(t, self.sensing.estimate, self.sensing.has_data,
                                        self.randomness.generator("response_decisions", t), reference)
            for p in plans:
                self.events.append({**p, "P_trigger": truth.tolist(), "execution_step": None,
                                    "P_execution": None})
        # Schedule before execute, including delay=0; old due topics remained blocked above.
        ready = self.queue.due(t)
        before_heat = after_heat = 0.
        for p in ready:
            mask = (self.topics == p["topic"]) & (self.sources == 0)
            before = float(self.heat[mask].sum())
            if not c.full_heat_off:
                self.heat[mask] *= p["action_parameters"]["heat_retention"]
            after = float(self.heat[mask].sum())
            before_heat += before
            after_heat += after
            if p["action_parameters"]["publish"]:
                self.add_content(1, t, 2, p["topic"])
            event = next(e for e in reversed(self.events) if e["event_id"] == p["event_id"])
            event.update(execution_step=t, P_execution=truth.tolist(), heat_before=before,
                         heat_after_immediate=after, waiting_time=t - p["trigger_step"],
                         heat_action_enabled=not c.full_heat_off)
        if t % c.routine_publication_interval == 0:
            topic = c.agenda_topics[(t // c.routine_publication_interval) % len(c.agenda_topics)]
            self.add_content(1, t, 1, topic)
        self.add_content(c.arrivals_per_step, t, 0)
        # Catalog is public, but only delivered with its historical signal later.
        self.catalogs[str(t)] = [asdict(PublicContent(item_id=int(i), topic=int(k), emotion=float(e),
                                      heat=float(h), official=bool(s), born=int(b)))
                                for i, k, e, h, s, b in zip(self.ids, self.topics, self.emotions,
                                                           self.heat, self.sources, self.born)]
        h = np.log1p(self.heat)
        if h.max() > 0:
            h /= h.max()
        if c.full_heat_off:
            h[:] = 0
        similarity = self.preferences[:, self.topics] / np.linalg.norm(self.preferences, axis=1)[:, None]
        scores = c.alpha * h[None, :] + (1 - c.alpha) * similarity
        keys = self.randomness.item_uniforms("ranking", t, np.arange(c.n_agents)[:, None], self.ids[None, :])
        budget = min(c.attention_budget, len(self.ids))
        if c.ranking == "topk":
            selected = np.lexsort((keys, -scores), axis=1)[:, :budget]
        else:
            gumbels = -np.log(-np.log(keys))
            selected = np.argsort(-(scores / c.temperature + gumbels), axis=1)[:, :budget]
        selected_topics = self.topics[selected]
        selected_sources = self.sources[selected]
        trust_factor = np.where(selected_sources > 0,
                               1 + c.trust_feedback_strength * (2 * self.trust[:, None] - 1),
                               1 - c.trust_feedback_strength * (2 * self.trust[:, None] - 1))
        prob = np.clip(self.emotionality[:, None] * self.emotions[selected] * trust_factor, 0, 1)
        uniforms = self.randomness.item_uniforms("interaction", t, np.arange(c.n_agents)[:, None],
                                                 self.ids[selected])
        interactions = uniforms < prob
        counts = np.zeros((c.n_agents, c.n_topics), dtype=int)
        np.add.at(counts, (np.repeat(np.arange(c.n_agents), budget), selected_topics.ravel()), 1)
        exposure = normalize(counts.sum(axis=0))
        if not c.full_heat_off:
            self.heat += np.bincount(selected[interactions], minlength=len(self.heat))
        raw_counts = (np.bincount(selected_topics[self.panel][interactions[self.panel]], minlength=c.n_topics)
                      if len(self.panel) else None)
        tick_signal, generated = self.publisher.publish(t, raw_counts,
                                              self.randomness.generator("signal_noise", t))
        self.public_signal_ticks.append(tick_signal.to_dict())
        data = generated.to_dict()
        self.pending_packets.append(data)
        self.packet_index[generated.packet_id] = data
        self._survey(truth)
        available = None if packet is None else packet.signal
        matched = None
        if packet is not None:
            matched = np.sum([w * np.asarray(self.truth_history[str(s)])
                              for s, w in zip(packet.valid_steps, packet.weights)], axis=0)
        used_id = estimate_record.get("estimate_input_packet_id")
        used = self.packet_index.get(used_id, {}).get("signal")
        estimate = self.sensing.estimate
        official = (selected_sources > 0).mean(axis=1)
        offagenda = (~np.isin(selected_topics, c.agenda_topics)).mean(axis=1)
        alignment = np.clip(1 - .5 * np.abs(counts / budget - self.preferences).sum(axis=1), 0, 1)
        response_effect = (before_heat - after_heat) / before_heat if before_heat else 0.
        self.trust = trust_update(self.trust, self.baseline_trust, official, offagenda, alignment,
                                 response_effect, rate=c.trust_update_rate, rule=c.trust_rule,
                                 official_gain=c.trust_official_gain, offagenda_penalty=c.trust_offagenda_penalty,
                                 response_gain=c.trust_response_gain, alignment_gain=c.trust_alignment_gain)
        row = {"step": t, "P_true": truth.tolist(), "E_exposure": exposure.tolist(),
               "S_public": tick_signal.signal, "S_available": available, "P_hat_gov": estimate,
               "platform_representation_gap": distance(truth, tick_signal.signal),
               "perception_error": distance(truth, estimate), "exposure_gap": distance(truth, exposure),
               "visible_signal_current_gap": distance(truth, available),
               "visible_signal_matched_gap": distance(matched, available),
               "signal_estimate_distance": distance(used, estimate),
               "has_data": self.sensing.has_data, "preference_shift": tv(truth, self.initial_truth),
               "available_packet_id": None if packet is None else packet.packet_id,
               "estimate_input_packet_id": used_id,
               "signal_age": None if packet is None else t - packet.window_end,
               "signal_coverage": None if packet is None else packet.coverage,
               "responses_scheduled": len(plans), "responses_executed": len(ready),
               "pending_count": len(self.queue.pending), "pool_size": len(self.ids),
               "interactions": int(interactions.sum()), "official_exposure_share": float(official.mean()),
               "response_exposure_share": float((selected_sources == 2).mean()),
               "agenda_attention_share": float(exposure[list(c.agenda_topics)].sum()),
               "public_preference_on_agenda": float(truth[list(c.agenda_topics)].sum()),
               "trust_mean": float(self.trust.mean()), "trust_spread": float(np.std(self.trust)),
               "response_effect_immediate": response_effect}
        self.trajectory.append(jsonable(row))
        self.preferences, self.last_topic, self.streak = update_preferences(
            self.preferences, counts, self.last_topic, self.streak, c.drift_rate, c.drift_threshold)
        if not c.full_heat_off:
            self.heat *= c.heat_retention
        age = t - self.born + 1
        keep = age < c.max_item_age
        if not c.full_heat_off:
            keep &= (self.heat >= c.heat_floor) | (age < c.cold_start_rounds)
        for key in ("ids", "topics", "emotions", "heat", "born", "sources"):
            setattr(self, key, getattr(self, key)[keep])
        self.tick += 1
        return self.trajectory[-1]

    def run(self, until=None):
        end = self.config.steps if until is None else until
        if end < self.tick or end > self.config.steps:
            raise ValueError("Invalid run boundary")
        while self.tick < end:
            self.step()
        return self

    def snapshot(self):
        state = {"schema": SCHEMA_VERSION, "code_version": RESEARCH_VERSION, "source_hash": self.code_hash,
                 "config": self.config.to_dict(), "seed": self.seed, "tick": self.tick, "phase": self.phase,
                 "world_id": self.world_id, "parent_world_id": self.parent_world_id,
                 "snapshot_id": self.snapshot_id, "initial_condition": self.initial_condition,
                 "initial_state_hash": self.initial_state_hash, "randomness": self.randomness.snapshot(),
                 "arrays": {k: getattr(self, k) for k in self.ARRAY_FIELDS},
                 "publisher": self.publisher.snapshot(), "sensing": self.sensing.snapshot(),
                 "queue": self.queue.snapshot(), "pending_packets": self.pending_packets,
                 "latest_packet": None if self.latest_packet is None else self.latest_packet.to_dict(),
                 "packet_index": self.packet_index, "catalogs": self.catalogs, "truth_history": self.truth_history,
                 "pending_surveys": self.pending_surveys, "pending_rules": self.pending_rules,
                 "latest_survey": None if self.latest_survey is None else asdict(self.latest_survey),
                 "latest_rule": None if self.latest_rule is None else asdict(self.latest_rule),
                 "current_rule_version": self.current_rule_version,
                 "logs": {k: getattr(self, k) for k in self.LOG_FIELDS}}
        state = copy.deepcopy(jsonable(state))
        return {"state": state, "state_hash": canonical_hash(state)}

    @classmethod
    def from_snapshot(cls, snapshot):
        state = copy.deepcopy(snapshot["state"])
        if canonical_hash(state) != snapshot["state_hash"]:
            raise ValueError("Snapshot hash mismatch")
        if (state["schema"] != SCHEMA_VERSION or state["code_version"] != RESEARCH_VERSION
                or state["source_hash"] != source_hash() or state["phase"] != "boundary_before_delivery"):
            raise ValueError("Snapshot source/schema/phase mismatch")
        obj = object.__new__(cls)
        obj.config = ResearchConfig.from_dict(state["config"])
        for key in ("seed", "tick", "phase", "world_id", "parent_world_id", "snapshot_id", "initial_condition",
                    "initial_state_hash", "pending_packets", "packet_index", "catalogs", "truth_history",
                    "pending_surveys", "pending_rules", "current_rule_version"):
            setattr(obj, key, state[key])
        obj.code_hash = state["source_hash"]
        for key in cls.ARRAY_FIELDS:
            setattr(obj, key, np.asarray(state["arrays"][key], dtype=int if key in cls.INT_FIELDS else float))
        for key in cls.LOG_FIELDS:
            setattr(obj, key, state["logs"][key])
        obj.randomness = AddressedRandomness.from_snapshot(state["randomness"])
        obj.publisher = PublicSignalPublisher.from_snapshot(state["publisher"])
        obj.sensing = GovernmentSensing.from_snapshot(state["sensing"])
        obj.queue = ResponseQueue.from_snapshot(state["queue"])
        obj.latest_packet = None if state["latest_packet"] is None else ObservationPacket.from_dict(state["latest_packet"])
        survey = state["latest_survey"]
        obj.latest_survey = None if survey is None else SurveyReport(**{**survey, "estimate": tuple(survey["estimate"])})
        obj.latest_rule = None if state["latest_rule"] is None else RuleDisclosure(**state["latest_rule"])
        return obj

    def fork(self, branch_id, changes=None):
        allowed = {"pref_info", "government_delay", "response_capacity", "alpha", "ranking",
                   "response_heat_retention"}
        changes = dict(changes or {})
        if set(changes) - allowed:
            raise ValueError("Unsupported intervention fields")
        snapshot = self.snapshot()
        branch = self.from_snapshot(snapshot)
        assert canonical_hash(branch.snapshot()["state"]) == snapshot["state_hash"]
        branch.parent_world_id = self.world_id
        branch.snapshot_id = snapshot["state_hash"]
        branch.world_id = f"{self.world_id}/{branch_id}"
        branch.config = replace(branch.config, **changes)
        branch.queue.settings = branch.decision_settings()
        # Change information access without resetting acquired estimates or their timing.
        if "pref_info" in changes:
            sensing_state = branch.sensing.snapshot()
            sensing_state["settings"]["pref_info"] = changes["pref_info"]
            branch.sensing = GovernmentSensing.from_snapshot(sensing_state)
        if "alpha" in changes or "ranking" in changes:
            branch.current_rule_version = f"ranking:{self.tick}:{branch_id}"
            if branch.config.rule_info:
                branch.pending_rules.append(branch.rule_record(self.tick, self.tick + branch.config.disclosure_delay,
                                                               branch.current_rule_version))
        branch.treatments.append({"branch_id": branch_id, "at": self.tick, "changes": changes,
                                  "pre_treatment_state_hash": snapshot["state_hash"],
                                  "inherited_queue_hash": canonical_hash(branch.queue.pending),
                                  "queue_policy": "existing plans unchanged; new plans use changed settings"})
        return branch
