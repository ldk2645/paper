"""Explicit, uncalibrated governance assumptions for mechanism experiments.

These helpers encode scheduling and measurement rules. They do not establish
that an intervention works, that a signal represents public welfare, or that
any episode was caused by a particular policy.
"""
from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class PendingResponse:
    topic: int
    trigger_step: int
    due_step: int
    signal_value: float


class ResponseController:
    """Schedule delayed responses to signals strictly above a threshold.

    ``hard`` considers every topic, ``selective`` considers only agenda topics,
    and ``wait`` requires successive above-threshold monitoring observations.
    Capacity is the maximum number of *new* plans per call to ``schedule``;
    existing pending plans do not consume that monitoring round's capacity.
    Call ``due`` before ``schedule`` in each simulation round. A pending topic
    cannot receive a duplicate plan; after delivery it may trigger again.
    """

    def __init__(self, n_topics, agenda_topics, threshold, strategy,
                 wait_observations, capacity, delay):
        for name, value in (("n_topics", n_topics),
                            ("wait_observations", wait_observations),
                            ("capacity", capacity), ("delay", delay)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not math.isfinite(threshold) or not 0 <= threshold <= 1:
            raise ValueError("threshold must be finite and in [0,1]")
        if strategy not in ("hard", "selective", "wait"):
            raise ValueError("Unknown response strategy")
        agenda = tuple(agenda_topics)
        if any(isinstance(k, bool) or not isinstance(k, (int, np.integer))
               or not 0 <= k < n_topics for k in agenda):
            raise ValueError("agenda_topics contains an invalid topic")
        if len(set(agenda)) != len(agenda):
            raise ValueError("agenda_topics must be unique")
        self.n_topics = n_topics
        self.agenda_topics = frozenset(int(k) for k in agenda)
        self.threshold = float(threshold)
        self.strategy = strategy
        self.wait_observations = wait_observations
        self.capacity = capacity
        self.delay = delay
        self.pending = {}
        self.streak = np.zeros(n_topics, dtype=int)

    @staticmethod
    def _check_step(step):
        if isinstance(step, bool) or not isinstance(step, (int, np.integer)) or step < 0:
            raise ValueError("step must be a nonnegative integer")

    def due(self, step):
        """Pop plans due by this round, in deterministic due-time/topic order."""
        self._check_step(step)
        ready = sorted((plan for plan in self.pending.values() if plan.due_step <= step),
                       key=lambda plan: (plan.due_step, plan.topic))
        for plan in ready:
            del self.pending[plan.topic]
        return ready

    def schedule(self, step, signal, rng):
        """Observe once and schedule highest qualifying signals, randomizing ties."""
        self._check_step(step)
        signal = np.asarray(signal, dtype=float)
        if (signal.shape != (self.n_topics,) or not np.isfinite(signal).all()
                or (signal < 0).any() or (signal > 1).any()):
            raise ValueError("signal must be a finite vector with entries in [0,1]")
        above = signal > self.threshold
        self.streak = np.where(above, self.streak + 1, 0)
        eligible = above.copy()
        if self.strategy == "selective":
            eligible &= np.array([k in self.agenda_topics for k in range(self.n_topics)])
        elif self.strategy == "wait":
            eligible &= self.streak >= self.wait_observations
        for topic in self.pending:
            eligible[topic] = False
        candidates = np.flatnonzero(eligible)
        # Lexicographic tie priorities preserve ordering of all unequal signals.
        order = np.lexsort((rng.random(candidates.size), -signal[candidates]))
        chosen = candidates[order[:self.capacity]]
        plans = [PendingResponse(int(topic), int(step), int(step + self.delay),
                                 float(signal[topic])) for topic in chosen]
        self.pending.update((plan.topic, plan) for plan in plans)
        return plans


def trust_update(trust, baseline, official_exposure, offagenda_exposure,
                 alignment, response_effect, *, rate, rule, official_gain,
                 offagenda_penalty, response_gain, alignment_gain):
    """Relax toward a bounded target anchored to baseline trust.

    ``exposure`` uses official exposure relative to 0.25, off-agenda exposure,
    and response effect. ``alignment`` uses alignment relative to 0.5 and
    response effect. These are alternative assumptions, not fitted empirical
    relationships. ``response_effect`` is the caller's measured effect, not a
    count of announcements. Setting rate to zero freezes trust exactly.
    Scalar and broadcast-compatible array inputs are supported.
    """
    if rule not in ("exposure", "alignment"):
        raise ValueError("Unknown trust rule")
    if not math.isfinite(rate) or not 0 <= rate <= 1:
        raise ValueError("rate must be finite and in [0,1]")
    for name, value in (("official_gain", official_gain),
                        ("offagenda_penalty", offagenda_penalty),
                        ("response_gain", response_gain),
                        ("alignment_gain", alignment_gain)):
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    arrays = np.broadcast_arrays(*[np.asarray(v, dtype=float) for v in
        (trust, baseline, official_exposure, offagenda_exposure, alignment, response_effect)])
    if any(not np.isfinite(v).all() for v in arrays):
        raise ValueError("Trust inputs must be finite")
    old, anchor, official, offagenda, align, effect = arrays
    if any(((v < 0) | (v > 1)).any() for v in (old, anchor, official, offagenda, align)):
        raise ValueError("Trust, baseline, exposure, and alignment must be in [0,1]")
    # Signed response effects are allowed so that a harmful effect is not
    # silently converted into a benefit. The caller defines its measurement.
    clipped = np.clip(anchor, 1e-12, 1 - 1e-12)
    logit = np.log(clipped) - np.log1p(-clipped)
    with np.errstate(over="ignore", invalid="raise"):
        if rule == "exposure":
            target_logit = (logit + official_gain * (official - .25)
                            - offagenda_penalty * offagenda + response_gain * effect)
        else:
            target_logit = logit + alignment_gain * (align - .5) + response_gain * effect
    target = 1 / (1 + np.exp(-np.clip(target_logit, -35, 35)))
    updated = np.clip(old + rate * (target - old), 0, 1)
    return float(updated) if updated.ndim == 0 else updated


def episodes(rows, key, threshold):
    """Describe consecutive rounds strictly above threshold, retaining censoring.

    Rows must cover consecutive integer steps. End steps are inclusive and the
    duration is the number of observed rounds, including for a terminal episode
    whose eventual end is unknown. An episode at the first row has an observed
    start there; no claim is made about unobserved rounds before the supplied data.
    """
    if not math.isfinite(threshold):
        raise ValueError("threshold must be finite")
    result, active, previous_step = [], None, None
    for row in rows:
        step, value = row["step"], float(row[key])
        ResponseController._check_step(step)
        if previous_step is not None and step != previous_step + 1:
            raise ValueError("Episode rows must have consecutive, increasing steps")
        if not math.isfinite(value):
            raise ValueError("Episode values must be finite")
        if value > threshold:
            if active is None:
                active = {"start_step": int(step), "end_step": int(step), "duration": 1,
                          "peak_value": value, "right_censored": False}
            else:
                active["end_step"] = int(step)
                active["duration"] += 1
                active["peak_value"] = max(active["peak_value"], value)
        elif active is not None:
            result.append(active)
            active = None
        previous_step = step
    if active is not None:
        active["right_censored"] = True
        result.append(active)
    return result
