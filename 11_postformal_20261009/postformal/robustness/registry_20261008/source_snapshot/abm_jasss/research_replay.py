"""E3 controlled timing diagnostic, distinct from a live adaptive government.

A completed, unbranched donor supplies a legally reconstructed plan. Receiving
worlds use their own historical observations for diagnostic sensing only. The
external replay controller injects donor triggers; it never supplies donor
observations to receiving governments. Only execution dates change across arms.
"""
from dataclasses import dataclass, replace
import copy
import json

from .government_sensing import (GovernmentInformation, GovernmentSensing, PublicContent,
                                 RuleDisclosure, SurveyReport)
from .public_signals import ObservationPacket
from .research_config import ResearchConfig
from .research_governance import ResponseQueue
from .research_world import ResearchWorld, canonical_hash, jsonable, source_hash


REPLAY_SCHEMA = "fixed-response-replay-1"
PLAN_FIELDS = ("event_id", "topic", "trigger_step", "due_step", "signal_value",
               "information_ref", "action_parameters", "action_rule_version")


def _integer(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _information(record):
    record = copy.deepcopy(record)
    if record["public_packet"] is not None:
        record["public_packet"] = ObservationPacket.from_dict(record["public_packet"])
    if record["survey"] is not None:
        record["survey"]["estimate"] = tuple(record["survey"]["estimate"])
        record["survey"] = SurveyReport(**record["survey"])
    if record["rule"] is not None:
        record["rule"] = RuleDisclosure(**record["rule"])
    record["public_catalog"] = tuple(PublicContent(**item) for item in record["public_catalog"])
    return GovernmentInformation(**record)


@dataclass(frozen=True)
class FixedReplayPlan:
    """Immutable canonical JSON; dictionary access always returns a fresh copy."""
    _payload_json: str

    @property
    def plan_hash(self):
        return canonical_hash(self.to_dict())

    def to_dict(self):
        return json.loads(self._payload_json)

    @classmethod
    def from_dict(cls, value):
        value = copy.deepcopy(jsonable(value))
        if value.get("schema") != REPLAY_SCHEMA:
            raise ValueError("Unknown fixed replay schema")
        config = ResearchConfig.from_dict(value["donor_config"])
        _integer(value["donor_seed"], "donor_seed")
        if value["donor_source_hash"] != source_hash():
            raise ValueError("Replay donor source mismatch; regenerate the donor")
        seen, previous = set(), -1
        for ordinal, event in enumerate(value["events"]):
            if set(event) != set(PLAN_FIELDS):
                raise ValueError("Replay plan must contain scheduling fields only")
            trigger = _integer(event["trigger_step"], "trigger_step")
            topic = _integer(event["topic"], "topic")
            if (event["event_id"] in seen or trigger < previous or trigger >= config.steps
                    or topic >= config.n_topics or event["due_step"] != trigger + config.government_delay
                    or event["event_id"] != f"response:{trigger}:{topic}"):
                raise ValueError("Invalid donor plan identity, ordering or timing")
            if event["action_parameters"] != {"heat_retention": config.response_heat_retention,
                                              "publish": config.response_publish}:
                raise ValueError("Replay action parameters disagree with the donor")
            if event["information_ref"]["estimate_record"] != trigger:
                raise ValueError("Invalid donor information reference")
            seen.add(event["event_id"])
            previous = trigger
        return cls(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                              separators=(",", ":")))

    @classmethod
    def from_donor(cls, donor):
        if (type(donor) is not ResearchWorld or donor.tick != donor.config.steps
                or donor.parent_world_id is not None or donor.treatments
                or donor.code_hash != source_hash()):
            raise ValueError("Replay requires a complete, current-source, unbranched adaptive donor")
        if not (len(donor.information_log) == len(donor.government_estimates)
                == len(donor.trajectory) == donor.tick):
            raise ValueError("Donor history is incomplete")
        # Reconstruct decisions from permitted inputs, never from evaluator truth.
        sensing = GovernmentSensing(donor.sensing_settings())
        queue = ResponseQueue(donor.decision_settings())
        plans, execution_steps = [], {}
        for step, record in enumerate(donor.information_log):
            if record["now"] != step:
                raise ValueError("Donor information time mismatch")
            estimate = jsonable(sensing.update(_information(record)))
            if estimate != donor.government_estimates[step]:
                raise ValueError("Donor inference does not reconstruct from legal information")
            packet = record["public_packet"]
            reference = {"estimate_record": step, "information_hash": canonical_hash(record),
                         "latest_packet_id": None if packet is None else packet["packet_id"]}
            if donor.config.response_enabled and step % donor.config.government_interval == 0:
                plans.extend(queue.schedule(step, sensing.estimate, sensing.has_data,
                    donor.randomness.generator("response_decisions", step), reference))
            for event in queue.due(step):
                execution_steps[event["event_id"]] = step
        recorded = [{key: event[key] for key in PLAN_FIELDS} for event in donor.events]
        if recorded != plans or any(event["execution_step"] != execution_steps.get(event["event_id"])
                                    for event in donor.events):
            raise ValueError("Donor events do not reconstruct from legal government decisions")
        return cls.from_dict({"schema": REPLAY_SCHEMA, "donor_world_id": donor.world_id,
            "donor_seed": donor.seed, "donor_config": donor.config.to_dict(),
            "donor_source_hash": donor.code_hash, "donor_snapshot_hash": donor.snapshot()["state_hash"],
            "donor_information_hash": canonical_hash(donor.information_log),
            "events": recorded})


class _ReplayQueue:
    """External controller: event-keyed pending plans allow topic overlap."""
    def __init__(self, plan, delay):
        self.plan = plan
        self.delay = _integer(delay, "administrative_delay")
        self.pending = {}
        self.last_step = -1
        self._by_trigger = {}
        data = plan.to_dict()
        for ordinal, original in enumerate(data["events"]):
            event = copy.deepcopy(original)
            event.update(due_step=event["trigger_step"] + delay,
                donor_due_step=original["due_step"], donor_information_ref=event.pop("information_ref"),
                information_ref={"kind": "controlled_fixed_plan", "plan_hash": plan.plan_hash,
                                 "donor_world_id": data["donor_world_id"],
                                 "donor_event_id": original["event_id"]},
                decision_mode="controlled_fixed_plan", signal_value_origin="donor",
                replay_ordinal=ordinal, action_rule_version=REPLAY_SCHEMA,
                donor_action_rule_version=original["action_rule_version"])
            self._by_trigger.setdefault(event["trigger_step"], []).append(event)

    def enqueue(self, step):
        if step != self.last_step + 1:
            raise ValueError("Replay triggers must advance one tick at a time")
        self.last_step = step
        plans = copy.deepcopy(self._by_trigger.get(step, []))
        for event in plans:
            self.pending[event["event_id"]] = copy.deepcopy(event)
        return plans

    def due(self, step):
        ready = sorted((event for event in self.pending.values() if event["due_step"] <= step),
                       key=lambda event: (event["due_step"], event["topic"], event["replay_ordinal"]))
        for event in ready:
            del self.pending[event["event_id"]]
        return copy.deepcopy(ready)

    def snapshot(self):
        return {"queue_mode": REPLAY_SCHEMA, "plan": self.plan.to_dict(),
                "plan_hash": self.plan.plan_hash, "administrative_delay": self.delay,
                "last_step": self.last_step, "pending": list(copy.deepcopy(self.pending).values())}

    @classmethod
    def from_snapshot(cls, data):
        if data.get("queue_mode") != REPLAY_SCHEMA:
            raise ValueError("A replay world requires a controlled replay snapshot")
        plan = FixedReplayPlan.from_dict(data["plan"])
        if plan.plan_hash != data["plan_hash"]:
            raise ValueError("Replay plan hash mismatch")
        result = cls(plan, data["administrative_delay"])
        last = data["last_step"]
        if isinstance(last, bool) or not isinstance(last, int) or not -1 <= last < data["plan"]["donor_config"]["steps"]:
            raise ValueError("Invalid replay cursor")
        for step in range(last + 1):
            result.enqueue(step)
            result.due(step)
        if result.snapshot() != data:
            raise ValueError("Replay queue disagrees with the fixed plan")
        return result


class ControlledReplayWorld(ResearchWorld):
    def __init__(self, config, seed, plan, administrative_delay):
        expected = replace(ResearchConfig.from_dict(plan.to_dict()["donor_config"]),
                           government_delay=_integer(administrative_delay, "administrative_delay"))
        if config != expected or seed != plan.to_dict()["donor_seed"]:
            raise ValueError("Replay arms must preserve donor configuration and seed except delay")
        super().__init__(config, seed)
        self.queue = _ReplayQueue(plan, administrative_delay)
        self.world_id = f"{plan.to_dict()['donor_world_id']}/replay-delay-{administrative_delay}"
        self.treatments.append({"mode": "controlled_fixed_plan", "plan_hash": plan.plan_hash,
            "donor_world_id": plan.to_dict()["donor_world_id"], "administrative_delay": administrative_delay,
            "queue_policy": "fixed donor triggers; no live adaptation or pending-topic filtering"})

    @property
    def replay_plan(self):
        return self.queue.plan

    @property
    def administrative_delay(self):
        return self.queue.delay

    def _schedule_response_plans(self, reference):
        return self.queue.enqueue(self.tick)

    def _publish_response(self, plan):
        self.add_content(1, self.tick, 2, plan["topic"], response_identity=plan["replay_ordinal"])

    @classmethod
    def _restore_response_queue(cls, data):
        return _ReplayQueue.from_snapshot(data)

    @classmethod
    def from_snapshot(cls, snapshot):
        result = super().from_snapshot(snapshot)
        expected = replace(ResearchConfig.from_dict(result.replay_plan.to_dict()["donor_config"]),
                           government_delay=result.administrative_delay)
        if (result.config != expected or result.seed != result.replay_plan.to_dict()["donor_seed"]
                or result.queue.last_step != result.tick - 1):
            raise ValueError("Replay snapshot configuration or cursor mismatch")
        replay_diagnostics(result)
        return result

    def fork(self, branch_id, changes=None):
        raise ValueError("Use separate fixed-plan delay arms; adaptive fork interventions do not apply")


def make_replay_worlds(donor, delays=(0, 1, 3, 10)):
    delays = tuple(delays)
    if not delays or any(_integer(delay, "administrative_delay") != delay for delay in delays):
        raise ValueError("At least one administrative delay is required")
    if len(set(delays)) != len(delays):
        raise ValueError("Replay delays must be unique")
    plan = FixedReplayPlan.from_donor(donor)
    return {delay: ControlledReplayWorld(replace(donor.config, government_delay=delay), donor.seed,
                                         plan, delay) for delay in delays}


def rebuild_replay_diagnostics(trajectory, events, plan_dict, administrative_delay, steps):
    """Pure reconstruction of plan conservation, execution and terminal censoring."""
    plan = FixedReplayPlan.from_dict(plan_dict)
    delay = _integer(administrative_delay, "administrative_delay")
    if steps != plan_dict["donor_config"]["steps"] or len(trajectory) > steps:
        raise ValueError("Replay horizon differs from the donor")
    if [row["step"] for row in trajectory] != list(range(len(trajectory))):
        raise ValueError("Replay trajectory must be a complete observed prefix")
    observed = len(trajectory)
    expected_queue = _ReplayQueue(plan, delay)
    expected = []
    for step in range(observed):
        expected.extend(expected_queue.enqueue(step))
        expected_queue.due(step)
    if len(events) != len(expected):
        raise ValueError("Replay did not conserve donor trigger counts")
    for event, scheduled in zip(events, expected):
        if any(event.get(key) != value for key, value in scheduled.items()):
            raise ValueError("Replay altered a fixed donor plan")
        executed = event["due_step"] if event["due_step"] < observed else None
        if event.get("execution_step") != executed:
            raise ValueError("Replay execution differs from its shifted due time")
        if event.get("P_trigger") != trajectory[event["trigger_step"]]["P_true"]:
            raise ValueError("Replay trigger truth must come from the receiving world")
        if event.get("P_execution") != (None if executed is None else trajectory[executed]["P_true"]):
            raise ValueError("Replay execution truth must come from the receiving world")
    for row in trajectory:
        step = row["step"]
        scheduled_count = sum(event["trigger_step"] == step for event in events)
        executed_count = sum(event["execution_step"] == step for event in events)
        pending_count = sum(event["trigger_step"] <= step < event["due_step"] for event in events)
        if (row["responses_scheduled"], row["responses_executed"], row["pending_count"]) != (
                scheduled_count, executed_count, pending_count):
            raise ValueError("Replay trajectory response counts disagree with its events")
    terminal = observed == steps
    statuses = [{"event_id": event["event_id"], "topic": event["topic"],
        "trigger_step": event["trigger_step"], "due_step": event["due_step"],
        "execution_step": event["execution_step"],
        "status": "executed" if event["execution_step"] is not None else
                  "right_censored" if terminal else "pending",
        "censor_step": steps - 1 if terminal and event["execution_step"] is None else None,
        "observed_wait": (event["execution_step"] if event["execution_step"] is not None
                          else observed - 1) - event["trigger_step"]} for event in events]
    executed = sum(event["execution_step"] is not None for event in events)
    return {"schema": REPLAY_SCHEMA, "mode": "controlled_fixed_plan", "plan_hash": plan.plan_hash,
        "donor_world_id": plan_dict["donor_world_id"], "administrative_delay": delay,
        "observed_ticks": observed, "horizon_complete": terminal,
        "fixed_plan_count": len(plan_dict["events"]), "triggered_count": len(events),
        "future_trigger_count": len(plan_dict["events"]) - len(events),
        "execution_count": executed, "pending_count": len(events) - executed,
        "right_censored_count": len(events) - executed if terminal else 0,
        "max_pending_count": max((row["pending_count"] for row in trajectory), default=0),
        "event_statuses": statuses}


def replay_diagnostics(world):
    return rebuild_replay_diagnostics(world.trajectory, world.events, world.replay_plan.to_dict(),
                                      world.administrative_delay, world.config.steps)
