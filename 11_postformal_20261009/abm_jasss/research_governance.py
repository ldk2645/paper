"""Government-only scheduling state, independent of the evaluation world."""
from dataclasses import asdict, dataclass
import copy
import numpy as np


@dataclass(frozen=True)
class DecisionSettings:
    n_topics: int
    agenda_topics: tuple
    threshold: float
    strategy: str
    wait_observations: int
    capacity: int
    delay: int
    heat_retention: float
    publish: bool


class ResponseQueue:
    def __init__(self, settings):
        self.settings = settings
        self.pending = {}
        self.streak = [0] * settings.n_topics

    def schedule(self, step, estimate, has_data, rng, information_ref):
        if not has_data:
            return []
        cfg = self.settings
        values = np.asarray(estimate, dtype=float)
        if (values.shape != (cfg.n_topics,) or not np.isfinite(values).all()
                or (values < 0).any() or not np.isclose(values.sum(), 1)):
            raise ValueError("Invalid government estimate")
        above = values > cfg.threshold
        self.streak = [s + 1 if flag else 0 for s, flag in zip(self.streak, above)]
        eligible = above.copy()
        if cfg.strategy == "selective":
            eligible &= np.isin(np.arange(cfg.n_topics), cfg.agenda_topics)
        elif cfg.strategy == "wait":
            eligible &= np.asarray(self.streak) >= cfg.wait_observations
        for topic in self.pending:
            eligible[topic] = False
        candidates = np.flatnonzero(eligible)
        order = np.lexsort((rng.random(len(candidates)), -values[candidates]))
        plans = []
        for topic in candidates[order[:cfg.capacity]]:
            topic = int(topic)
            plan = {"event_id": f"response:{step}:{topic}", "topic": topic,
                    "trigger_step": step, "due_step": step + cfg.delay,
                    "signal_value": float(values[topic]),
                    "information_ref": copy.deepcopy(information_ref),
                    "action_parameters": {"heat_retention": cfg.heat_retention,
                                          "publish": cfg.publish},
                    "action_rule_version": "research-schedule-then-execute-1"}
            self.pending[topic] = plan
            plans.append(copy.deepcopy(plan))
        return plans

    def due(self, step):
        ready = sorted((p for p in self.pending.values() if p["due_step"] <= step),
                       key=lambda p: (p["due_step"], p["topic"]))
        for p in ready:
            del self.pending[p["topic"]]
        return copy.deepcopy(ready)

    def snapshot(self):
        return {"settings": asdict(self.settings), "pending": list(self.pending.values()),
                "streak": list(self.streak)}

    @classmethod
    def from_snapshot(cls, data):
        settings = dict(data["settings"])
        settings["agenda_topics"] = tuple(settings["agenda_topics"])
        result = cls(DecisionSettings(**settings))
        result.pending = {p["topic"]: copy.deepcopy(p) for p in data["pending"]}
        result.streak = list(data["streak"])
        return result
