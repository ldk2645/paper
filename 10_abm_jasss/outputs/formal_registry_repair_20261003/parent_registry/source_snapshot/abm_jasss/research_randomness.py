"""Stable, stateless shock addresses and serializable named stream metadata.

World-specific seed + name + time/object address determine each draw. Adding a
stream or consuming extra draws for responses cannot shift ordinary supply.
Independent draws conditional on identity are coupled across treatment worlds;
endogenous content that exists in only one world has no forced counterpart.
"""
import hashlib
import numpy as np

STREAM_NAMES = ("initialization", "trust", "panel", "initial_content", "ordinary_content",
                "routine_content", "response_content", "survey", "signal_noise",
                "ranking", "interaction", "response_decisions")
RNG_SCHEMA = "sha256-seedsequence-pcg64-splitmix64-v1"


class AddressedRandomness:
    def __init__(self, seed):
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise ValueError("seed must be a nonnegative integer")
        self.seed = seed

    def words(self, stream, *address):
        if stream not in STREAM_NAMES:
            raise ValueError("Unknown random stream")
        data = repr((RNG_SCHEMA, self.seed, stream, tuple(address))).encode("utf-8")
        return np.frombuffer(hashlib.sha256(data).digest(), dtype="<u4").astype(np.uint32).tolist()

    def generator(self, stream, *address):
        return np.random.Generator(np.random.PCG64(np.random.SeedSequence(self.words(stream, *address))))

    def item_uniforms(self, stream, step, agent_ids, item_ids):
        """One potential uniform per (stream, tick, agent, item), vectorized."""
        words = self.words(stream, int(step))
        key = np.uint64(words[0]) | (np.uint64(words[1]) << np.uint64(32))
        a = np.asarray(agent_ids, dtype=np.uint64)
        i = np.asarray(item_ids, dtype=np.uint64)
        with np.errstate(over="ignore"):
            z = key ^ ((a + np.uint64(1)) * np.uint64(0xD2B74407B1CE6E93))
            z = z ^ ((i + np.uint64(1)) * np.uint64(0xCA5A826395121157))
            z = z + np.uint64(0x9E3779B97F4A7C15)
            z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
            z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
            z = z ^ (z >> np.uint64(31))
        return ((z >> np.uint64(11)).astype(np.float64) + .5) / (2.**53)

    def snapshot(self):
        return {"seed": self.seed, "schema": RNG_SCHEMA,
                "mode": "stateless-addressed; boundary tick and stable IDs are the cursors",
                "streams": {s: self.words(s) for s in STREAM_NAMES},
                "numpy_version": np.__version__}

    @classmethod
    def from_snapshot(cls, value):
        obj = cls(value["seed"])
        if value != obj.snapshot():
            raise ValueError("RNG schema, stream mapping or numpy version mismatch")
        return obj
