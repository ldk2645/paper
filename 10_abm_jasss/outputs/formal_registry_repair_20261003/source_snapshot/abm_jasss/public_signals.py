"""Public engagement publication, without latent preferences or exposure logs.

The world owns panel membership, delivery queues and the noise RNG. This module
receives only aggregated counts. A packet generated after tick t cannot be used
before t + 1 + delay. Missing evidence is never replaced by a uniform signal.
"""
from collections import deque
from dataclasses import dataclass, fields
import hashlib
import json
import math
from numbers import Integral, Real
from typing import Mapping


SCHEMA_VERSION = "public-signals-1"


def _integer(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, Integral) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return int(value)


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite nonnegative number")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return 0.0 if result == 0 else result


def _vector(value, name, size=None):
    if isinstance(value, (str, bytes, Mapping)):
        raise ValueError(f"{name} must be a vector")
    try:
        result = tuple(_number(v, name) for v in value)
    except TypeError as exc:
        raise ValueError(f"{name} must be a vector") from exc
    if not result or (size is not None and len(result) != size):
        raise ValueError(f"{name} has the wrong taxonomy size")
    return result


def _sum(values):
    try:
        result = math.fsum(values)
    except OverflowError as exc:
        raise ValueError("Count total must be finite") from exc
    if not math.isfinite(result):
        raise ValueError("Count total must be finite")
    return result


def _same(left, right):
    return len(left) == len(right) and all(
        math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
        for a, b in zip(left, right))


def _signature(n_topics, steps, counts):
    # Generated time, window boundaries and packet ID are intentionally absent:
    # repeated packaging of identical source evidence is not new information.
    evidence = {"schema": SCHEMA_VERSION, "n_topics": n_topics,
                "sources": [[step, list(row)] for step, row in zip(steps, counts)]}
    payload = json.dumps(evidence, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _json_value(value):
    if isinstance(value, tuple):
        return [_json_value(v) for v in value]
    return value


def _to_dict(instance):
    return {field.name: _json_value(getattr(instance, field.name))
            for field in fields(instance)}


def _from_dict(cls, data):
    if not isinstance(data, Mapping):
        raise ValueError(f"{cls.__name__} requires a mapping")
    expected = {field.name for field in fields(cls)}
    if set(data) != expected:
        raise ValueError(f"{cls.__name__} fields must match the public schema exactly")
    return cls(**data)


@dataclass(frozen=True, slots=True)
class PublicTick:
    """Publisher audit record; raw counts contain aggregate engagements only."""

    step: int
    raw_counts: tuple[float, ...] | None
    public_counts: tuple[float, ...] | None
    denominator: float | None
    signal: tuple[float, ...] | None
    status: str

    def __post_init__(self):
        object.__setattr__(self, "step", _integer(self.step, "step"))
        if self.raw_counts is None:
            if (self.public_counts is not None or self.denominator is not None
                    or self.signal is not None or self.status != "no_panel"):
                raise ValueError("Missing panel must contain no counts or signal")
            return
        raw = _vector(self.raw_counts, "raw_counts")
        public = _vector(self.public_counts, "public_counts", len(raw))
        total = _number(self.denominator, "denominator")
        if not math.isclose(total, _sum(public), rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("Public denominator must equal the count total")
        raw_total = _sum(raw)
        expected_status = ("no_interactions" if raw_total == 0 else
                           "noise_erased" if total == 0 else "valid")
        if self.status != expected_status:
            raise ValueError("Public tick status conflicts with its counts")
        if raw_total == 0 and total != 0:
            raise ValueError("Noise cannot manufacture activity from zero raw counts")
        if total == 0:
            if self.signal is not None:
                raise ValueError("Empty publication must have a missing signal")
        else:
            signal = _vector(self.signal, "signal", len(raw))
            if not _same(signal, tuple(v / total for v in public)):
                raise ValueError("Signal must normalize the published counts")
            object.__setattr__(self, "signal", signal)
        object.__setattr__(self, "raw_counts", raw)
        object.__setattr__(self, "public_counts", public)
        object.__setattr__(self, "denominator", total)

    def to_dict(self):
        return _to_dict(self)

    @classmethod
    def from_dict(cls, data):
        return _from_dict(cls, data)


@dataclass(frozen=True, slots=True)
class ObservationPacket:
    """Immutable government-readable evidence; no evaluator fields are accepted.

    ``coverage`` divides valid source ticks by the configured window length,
    including unavailable startup ticks. Negative window_start marks warm-up.
    ``missing_steps`` includes only ticks that have actually been simulated.
    Weights align with valid_steps and use published engagement denominators.
    Receipt time belongs to the recipient's delivery log, not this source packet.
    """

    packet_id: str
    window_start: int
    window_end: int
    generated_at: int
    available_at: int
    valid_steps: tuple[int, ...]
    weights: tuple[float, ...]
    counts: tuple[float, ...]
    signal: tuple[float, ...] | None
    coverage: float
    evidence_signature: str
    source_counts: tuple[tuple[float, ...], ...]
    tick_denominators: tuple[float, ...]
    missing_steps: tuple[int, ...]
    warm_up: bool

    def __post_init__(self):
        if not isinstance(self.packet_id, str) or not self.packet_id:
            raise ValueError("packet_id must be a nonempty string")
        if isinstance(self.window_start, bool) or not isinstance(self.window_start, Integral):
            raise ValueError("window_start must be an integer")
        object.__setattr__(self, "window_start", int(self.window_start))
        for name in ("window_end", "generated_at", "available_at"):
            object.__setattr__(self, name, _integer(getattr(self, name), name))
        if (self.window_start > self.window_end or self.window_end != self.generated_at
                or self.available_at <= self.generated_at):
            raise ValueError("Packet timing must obey the end-of-tick publication contract")
        if not isinstance(self.warm_up, bool) or self.warm_up != (self.window_start < 0):
            raise ValueError("warm_up must identify an incomplete startup window")
        counts = _vector(self.counts, "counts")
        steps = tuple(_integer(s, "valid_steps") for s in self.valid_steps)
        missing = tuple(_integer(s, "missing_steps") for s in self.missing_steps)
        if steps != tuple(sorted(set(steps))) or missing != tuple(sorted(set(missing))):
            raise ValueError("Source steps must be unique and ordered")
        expected = set(range(max(0, self.window_start), self.window_end + 1))
        if set(steps) & set(missing) or set(steps) | set(missing) != expected:
            raise ValueError("Valid and missing source ticks must partition the actual window")
        sources = tuple(_vector(row, "source_counts", len(counts)) for row in self.source_counts)
        denominators = tuple(_number(v, "tick_denominators") for v in self.tick_denominators)
        weights = tuple(_number(v, "weights") for v in self.weights)
        if not len(steps) == len(sources) == len(denominators) == len(weights):
            raise ValueError("Source counts, weights and ticks must align")
        if any(d <= 0 for d in denominators) or not _same(denominators, tuple(_sum(row) for row in sources)):
            raise ValueError("Valid source ticks require positive matching denominators")
        pooled = tuple(_sum(row[k] for row in sources) for k in range(len(counts)))
        if not _same(counts, pooled):
            raise ValueError("Packet counts must pool its public source records")
        total = _sum(counts)
        if not steps:
            if self.signal is not None:
                raise ValueError("A packet without evidence must have signal=None")
        else:
            signal = _vector(self.signal, "signal", len(counts))
            if not _same(signal, tuple(v / total for v in counts)) or not _same(
                    weights, tuple(d / total for d in denominators)):
                raise ValueError("Signal and weights must normalize the source counts")
            object.__setattr__(self, "signal", signal)
        coverage = _number(self.coverage, "coverage")
        if not math.isclose(coverage, len(steps) / (self.window_end - self.window_start + 1),
                            rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("Coverage must use the complete configured window")
        if self.evidence_signature != _signature(len(counts), steps, sources):
            raise ValueError("Evidence signature does not match the public source records")
        for name, value in (("valid_steps", steps), ("missing_steps", missing),
                            ("counts", counts), ("source_counts", sources),
                            ("tick_denominators", denominators), ("weights", weights),
                            ("coverage", coverage)):
            object.__setattr__(self, name, value)

    def to_dict(self):
        return _to_dict(self)

    @classmethod
    def from_dict(cls, data):
        return _from_dict(cls, data)


class PublicSignalPublisher:
    """Create one immutable source record and one window packet per tick.

    Call publish for consecutive ticks starting at zero. RNG ownership remains
    with the world: saving this snapshot does not save the supplied noise RNG.
    """

    def __init__(self, n_topics, window, delay, noise_sd=0):
        self.n_topics = _integer(n_topics, "n_topics", 1)
        self.window = _integer(window, "window", 1)
        self.delay = _integer(delay, "delay")
        self.noise_sd = _number(noise_sd, "noise_sd")
        self._ticks = deque(maxlen=self.window)
        self.next_step = 0

    def publish(self, step, raw_counts, rng):
        step = _integer(step, "step")
        if step != self.next_step:
            raise ValueError(f"Expected consecutive publication at step {self.next_step}")
        if raw_counts is None:
            tick = PublicTick(step, None, None, None, None, "no_panel")
        else:
            raw = _vector(raw_counts, "raw_counts", self.n_topics)
            raw_total = _sum(raw)
            public = raw
            if raw_total > 0 and self.noise_sd > 0:
                noise = tuple(float(v) for v in rng.normal(0, self.noise_sd, self.n_topics))
                if len(noise) != self.n_topics or any(not math.isfinite(v) for v in noise):
                    raise ValueError("Noise RNG must return one finite draw per topic")
                public = tuple(max(0.0, v + e) for v, e in zip(raw, noise))
            total = _sum(public)
            signal = tuple(v / total for v in public) if total else None
            status = "no_interactions" if not raw_total else "valid" if total else "noise_erased"
            tick = PublicTick(step, raw, public, total, signal, status)
        # Assemble locally so a malformed publication never partially advances
        # the publisher (the caller is responsible for RNG rollback on errors).
        history = tuple(self._ticks)[-(self.window - 1):] if self.window > 1 else ()
        history += (tick,)
        valid = tuple(row for row in history if row.signal is not None)
        steps = tuple(row.step for row in valid)
        sources = tuple(row.public_counts for row in valid)
        denominators = tuple(row.denominator for row in valid)
        counts = tuple(_sum(row[k] for row in sources) for k in range(self.n_topics))
        total = _sum(counts)
        packet = ObservationPacket(
            packet_id=f"public-{step:010d}", window_start=step - self.window + 1,
            window_end=step, generated_at=step, available_at=step + 1 + self.delay,
            valid_steps=steps, weights=tuple(v / total for v in denominators),
            counts=counts, signal=tuple(v / total for v in counts) if total else None,
            coverage=len(valid) / self.window,
            evidence_signature=_signature(self.n_topics, steps, sources),
            source_counts=sources, tick_denominators=denominators,
            missing_steps=tuple(row.step for row in history if row.signal is None),
            warm_up=step < self.window - 1)
        self._ticks.append(tick)
        self.next_step += 1
        return tick, packet

    def snapshot(self):
        return {"schema_version": SCHEMA_VERSION, "n_topics": self.n_topics,
                "window": self.window, "delay": self.delay, "noise_sd": self.noise_sd,
                "next_step": self.next_step, "ticks": [tick.to_dict() for tick in self._ticks]}

    @classmethod
    def from_snapshot(cls, data):
        expected = {"schema_version", "n_topics", "window", "delay", "noise_sd", "next_step", "ticks"}
        if not isinstance(data, Mapping) or set(data) != expected or data["schema_version"] != SCHEMA_VERSION:
            raise ValueError("Unsupported or malformed publisher snapshot")
        result = cls(data["n_topics"], data["window"], data["delay"], data["noise_sd"])
        result.next_step = _integer(data["next_step"], "next_step")
        ticks = tuple(PublicTick.from_dict(row) for row in data["ticks"])
        expected_steps = tuple(range(max(0, result.next_step - result.window), result.next_step))
        if tuple(tick.step for tick in ticks) != expected_steps:
            raise ValueError("Snapshot source history does not match its publication boundary")
        if any(tick.raw_counts is not None and len(tick.raw_counts) != result.n_topics for tick in ticks):
            raise ValueError("Snapshot source records use a different taxonomy")
        result._ticks.extend(ticks)
        return result
