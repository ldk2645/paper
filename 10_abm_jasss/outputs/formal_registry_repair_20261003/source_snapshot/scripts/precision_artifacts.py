"""New-output-only compressed precision-pilot artifacts and read-only reconstruction.

The model stays in abm_jasss at its frozen version.  This module exports one
world and reconstructs its legal decisions and summaries without stepping it.
Batch registration, donor identity and paired estimands belong to the runner.
"""
from dataclasses import asdict, replace
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from abm_jasss.research_config import ResearchConfig, RESEARCH_VERSION, SCHEMA_VERSION
from abm_jasss.research_s1_cli import LOG_FILES as S1_LOG_FILES, build_derived
from abm_jasss.research_world import ResearchWorld, canonical_hash, jsonable, source_hash
from scripts.validate_s1_outputs import (no_latent_fields, require, snapshot_state,
                                         unique_object, reject_constant, validate_government)

STAGE = "precision_pilot"
ARTIFACT_SCHEMA = "precision-artifacts-1"
LOG_FILES = {field: relative + ".gz" for field, relative in S1_LOG_FILES.items()}
SNAPSHOT_FILE = "evaluator/snapshot.json.gz"
ACTIONS_FILE = "government/actions.json.gz"
ANALYSIS_FIELDS = {"final_window", "min_signal_coverage", "completion_start",
                   "completion_end", "completion_followup"}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _finite_float(value):
    result = float(value)
    require(math.isfinite(result), f"Nonfinite JSON number: {value}")
    return result


def read(path):
    """Strict JSON reader for compressed raw data and ordinary metadata."""
    path = Path(path)
    payload = path.read_bytes()
    if path.suffix == ".gz":
        payload = gzip.decompress(payload)
    return json.loads(payload.decode("utf-8-sig"), object_pairs_hook=unique_object,
                      parse_constant=reject_constant, parse_float=_finite_float)


def _json_bytes(value):
    return (json.dumps(jsonable(value), sort_keys=True, ensure_ascii=False,
                       allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")


def _new_bytes(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)


def write_json(path, value):
    """Write a new ordinary JSON file; never replace a historical artifact."""
    _new_bytes(path, _json_bytes(value))


def write_gzip_json(path, value):
    """Level-one gzip with an empty filename and fixed timestamp."""
    payload = _json_bytes(value)
    compressed = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=compressed,
                       compresslevel=1, mtime=0) as stream:
        stream.write(payload)
    _new_bytes(path, compressed.getvalue())


def _identifier(value, name, path_component=False):
    require(isinstance(value, str) and bool(value.strip()), f"Invalid {name}")
    if path_component:
        require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value) is not None
                and not value.endswith("."), f"Unsafe {name}")
    return value


def _analysis_config(state, override):
    base = jsonable(ResearchConfig.from_dict(state["config"]).analysis_config())
    if override is None:
        return base
    require(isinstance(override, dict), "analysis_config must be a mapping")
    value = {**base, **jsonable(override)}
    require(set(value) == set(base), "Unknown analysis configuration fields")
    require(all(value[key] == base[key] for key in set(base) - ANALYSIS_FIELDS),
            "Analysis override changes model fields")
    validated = jsonable(ResearchConfig.from_dict(value).analysis_config())
    require(value == validated, "Analysis completion_end must be explicitly resolved")
    return value


def _metadata(snapshot, batch_id, run_id, group_id, scenario, condition,
              expected_source_hash, analysis_config, provenance, raw_hashes):
    state = snapshot["state"]
    config = ResearchConfig.from_dict(state["config"])
    for name, value in (("batch_id", batch_id), ("run_id", run_id), ("group_id", group_id),
                        ("scenario", scenario), ("condition", condition)):
        _identifier(value, name, name == "run_id")
    require(isinstance(provenance, dict), "provenance must be a mapping")
    return jsonable({
        "schema_version": ARTIFACT_SCHEMA, "engine_schema": SCHEMA_VERSION,
        "stage": STAGE, "formal_ready": False,
        "status": "complete" if state["tick"] == config.steps else "checkpoint",
        "failure": None, "retry": 0, "batch_id": batch_id, "run_id": run_id,
        "world_id": f"{batch_id}/{run_id}", "engine_world_id": state["world_id"],
        "group_id": group_id, "scenario": scenario, "condition": condition,
        "code_version": RESEARCH_VERSION, "source_hash": expected_source_hash,
        "config": state["config"], "config_hash": canonical_hash(state["config"]),
        "analysis_config": _analysis_config(state, analysis_config),
        "analysis_config_hash": canonical_hash(_analysis_config(state, analysis_config)),
        "seed": state["seed"], "initial_condition_id": state["initial_condition"],
        "initial_state_hash": state["initial_state_hash"],
        "parent_engine_world_id": state["parent_world_id"],
        "parent_world_id": None if state["parent_world_id"] is None
                           else f"{batch_id}/engine/{state['parent_world_id']}",
        "engine_reference_id": f"{batch_id}/engine/{state['world_id']}",
        "parent_snapshot_hash": state["snapshot_id"], "final_snapshot_hash": snapshot["state_hash"],
        "fork_phase": state["phase"], "treatments": state["logs"]["treatments"],
        "randomness": state["randomness"],
        "shock_tape_kind": "addressed_randomness_not_pregenerated_tape",
        "shock_tape_id": f"{state['randomness']['schema']}/seed{state['seed']}",
        "shock_tape_hash": canonical_hash(state["randomness"]),
        "ordinary_supply_hash": canonical_hash(state["logs"]["supply_log"]),
        "log_hashes": {field: canonical_hash(state["logs"][field]) for field in LOG_FILES},
        "packet_index_hash": canonical_hash(state["packet_index"]),
        "information_condition": {"PrefInfo": config.pref_info, "RuleInfo": config.rule_info},
        "taxonomy_version": f"synthetic-topics-{config.n_topics}-v1", "time_unit": "simulation_tick",
        "signal_schema": "public-signals-1", "outcome_schema": "research-outcomes-1",
        "raw_sha256": raw_hashes, "raw_encoding": "gzip-json-level1-mtime0",
        "provenance": provenance,
        "evaluation_scope": "Independent precision pilot; no formal inference or release",
    })


def _actions(state):
    return [{key: value for key, value in event.items() if key not in {"P_trigger", "P_execution"}}
            for event in state["logs"]["events"]]


def save_world(world, output, batch_id, run_id, group_id, scenario, condition,
               expected_source_hash, analysis_config=None, provenance=None):
    """Export one immutable world under output/raw and output/derived."""
    require(world.code_hash == expected_source_hash == source_hash(), "Source changed during pilot run")
    _identifier(run_id, "run_id", True)
    output = Path(output)
    folder = output / "raw" / run_id
    derived_path = output / "derived" / f"{run_id}.json"
    require(not folder.exists() and not derived_path.exists(), "World output must not exist")
    require(not any(path.is_symlink() for path in (output, output / "raw", output / "derived")),
            "Symlinks are not permitted in an artifact bundle")
    snapshot = world.snapshot()
    state = snapshot_state(snapshot, {"source_hash": expected_source_hash,
                                     "code_version": RESEARCH_VERSION}, run_id)
    values = {SNAPSHOT_FILE: snapshot, ACTIONS_FILE: _actions(state),
              **{relative: state["logs"][field] for field, relative in LOG_FILES.items()}}
    # Validate configuration and serialize all data before claiming a new folder.
    metadata = _metadata(snapshot, batch_id, run_id, group_id, scenario, condition,
                         expected_source_hash, analysis_config, provenance or {}, {})
    derived = jsonable(build_derived(state, metadata))
    _json_bytes(metadata)
    _json_bytes(derived)
    folder.mkdir(parents=True, exist_ok=False)
    for relative, value in values.items():
        write_gzip_json(folder / relative, value)
    metadata["raw_sha256"] = {relative: sha256(folder / relative) for relative in sorted(values)}
    write_json(folder / "metadata.json", metadata)
    write_json(derived_path, derived)
    require(source_hash() == expected_source_hash, "Source changed while exporting pilot world")
    return derived


def _ancestors(snapshot, all_snapshots, manifest, context):
    """Validate referenced ancestors before their configurations are consulted."""
    snapshots = dict(all_snapshots or {})
    snapshots[snapshot["state_hash"]] = snapshot
    state, seen = snapshot["state"], {snapshot["state_hash"]}
    while state["snapshot_id"] is not None:
        parent_hash = state["snapshot_id"]
        require(parent_hash not in seen and parent_hash in snapshots, "Missing/cyclic ancestor snapshot")
        seen.add(parent_hash)
        parent = snapshot_state(snapshots[parent_hash], manifest, f"{context}/ancestor")
        require(snapshots[parent_hash]["state_hash"] == parent_hash, "Ancestor map key/hash mismatch")
        require(state["parent_world_id"] == parent["world_id"] and
                state["seed"] == parent["seed"] and state["initial_state_hash"] == parent["initial_state_hash"]
                and state["randomness"] == parent["randomness"], "Parent identity/randomness mismatch")
        treatments = state["logs"]["treatments"]
        require(len(treatments) == len(parent["logs"]["treatments"]) + 1 and
                treatments[:-1] == parent["logs"]["treatments"], "Treatment ancestry mismatch")
        treatment = treatments[-1]
        require(treatment["at"] == parent["tick"] <= state["tick"] and
                treatment["pre_treatment_state_hash"] == parent_hash and
                state["world_id"] == f"{parent['world_id']}/{treatment['branch_id']}",
                "Fork boundary/reference mismatch")
        allowed = {"pref_info", "government_delay", "response_capacity", "alpha", "ranking",
                   "response_heat_retention"}
        require(set(treatment["changes"]) <= allowed and state["config"] == jsonable(
            replace(ResearchConfig.from_dict(parent["config"]), **treatment["changes"]).to_dict()),
            "Fork configuration mismatch")
        inherited_pending = {event["topic"]: event for event in parent["queue"]["pending"]}
        require(treatment["inherited_queue_hash"] == canonical_hash(inherited_pending)
                and treatment["queue_policy"] == "existing plans unchanged; new plans use changed settings",
                "Inherited queue reference mismatch")
        for field in LOG_FILES:
            if field == "events":
                old = [{k: v for k, v in event.items() if event["execution_step"] is not None
                        or k not in {"execution_step", "P_execution"}}
                       for event in parent["logs"][field]]
                prefix = [{key: event.get(key) for key in previous}
                          for event, previous in zip(state["logs"][field], old)]
            else:
                old = parent["logs"][field]
                prefix = state["logs"][field][:len(old)]
            require(prefix == old, f"Fork inherited log mismatch: {field}")
        state = parent
    require(state["parent_world_id"] is None, "Unbranched ancestor has a parent world")
    return snapshots


def _validate_empty_government(state, context):
    """S1 reconstructs nonempty prefixes; a boundary-zero checkpoint is also valid."""
    from abm_jasss.government_sensing import GovernmentSensing, SensingSettings
    from abm_jasss.research_governance import DecisionSettings, ResponseQueue
    cfg = ResearchConfig.from_dict(state["config"])
    require(all(not state["logs"][field] for field in LOG_FILES if field != "supply_log"),
            f"Nonempty zero-tick logs: {context}")
    require(len(state["logs"]["supply_log"]) == cfg.initial_items and
            all(item["born"] == -1 and item["source"] == 0 for item in state["logs"]["supply_log"]),
            f"Invalid initial supply: {context}")
    require(not state["packet_index"] and not state["pending_packets"], f"Zero-tick packets: {context}")
    settings = dict(state["sensing"]["settings"])
    for key in ("opaque_alpha", "opaque_rankings"):
        settings[key] = tuple(settings[key])
    require(jsonable(GovernmentSensing(SensingSettings(**settings)).snapshot()) == state["sensing"],
            f"Invalid initial sensing state: {context}")
    if not state["queue"].get("queue_mode"):
        decision = DecisionSettings(cfg.n_topics, cfg.agenda_topics, cfg.response_threshold,
            cfg.response_strategy, cfg.response_wait_observations, cfg.response_capacity,
            cfg.government_delay, cfg.response_heat_retention, cfg.response_publish)
        require(jsonable(ResponseQueue(decision).snapshot()) == state["queue"],
                f"Invalid initial response queue: {context}")


def _validate_publication(state, context):
    """Rebuild publication and delivery from aggregate counts, without world steps."""
    from abm_jasss.public_signals import PublicSignalPublisher
    from abm_jasss.research_randomness import AddressedRandomness

    cfg = ResearchConfig.from_dict(state["config"])
    publisher = PublicSignalPublisher(cfg.n_topics, cfg.observation_window,
                                      cfg.observation_delay, cfg.observation_noise)
    randomness = AddressedRandomness.from_snapshot(state["randomness"])
    logs = state["logs"]
    require(all(len(logs[field]) == state["tick"] for field in
                ("public_signal_ticks", "trajectory", "information_log")),
            f"Incomplete publication prefix: {context}")
    packets, pending, delivered, latest = {}, [], [], None
    for step, (public, row, info) in enumerate(zip(logs["public_signal_ticks"],
                                                  logs["trajectory"], logs["information_log"])):
        remaining = []
        for packet in pending:
            if packet["available_at"] <= step:
                delivered.append({**packet, "received_at": step})
                if packet["signal"] is not None:
                    latest = packet
            else:
                remaining.append(packet)
        pending = remaining
        require(info["public_packet"] == latest,
                f"Available government packet reconstruction mismatch: {context}/{step}")
        expected_visible = (None if latest is None else latest["signal"],
                            None if latest is None else latest["packet_id"],
                            None if latest is None else step - latest["window_end"],
                            None if latest is None else latest["coverage"])
        require((row["S_available"], row["available_packet_id"], row["signal_age"],
                 row["signal_coverage"]) == expected_visible,
                f"Trajectory visible signal reconstruction mismatch: {context}/{step}")
        tick, generated = publisher.publish(step, public["raw_counts"],
                                           randomness.generator("signal_noise", step))
        require(jsonable(tick.to_dict()) == public,
                f"Public signal reconstruction mismatch: {context}/{step}")
        require(row["S_public"] == jsonable(tick.signal),
                f"Trajectory public signal reconstruction mismatch: {context}/{step}")
        packet = jsonable(generated.to_dict())
        packets[packet["packet_id"]] = packet
        pending.append(packet)
    require(packets == state["packet_index"], f"Published packet reconstruction mismatch: {context}")
    require(delivered == logs["observation_packets"] and pending == state["pending_packets"]
            and latest == state["latest_packet"], f"Packet delivery reconstruction mismatch: {context}")
    require(jsonable(publisher.snapshot()) == state["publisher"],
            f"Publisher state reconstruction mismatch: {context}")


def validate_world_folder(folder, expected_source_hash, all_snapshots=None):
    """Read-only raw/metadata integrity and legal decision/statistic reconstruction.

    all_snapshots maps parent state hashes to snapshot envelopes. No world.step,
    world.run, exporter, or file-writing function is invoked during validation.
    """
    require(source_hash() == expected_source_hash, "Live analysis source differs from the frozen pilot engine")
    folder = Path(folder)
    require(folder.is_dir() and folder.parent.name == "raw", "Expected a raw world folder")
    require(not folder.is_symlink(), "Symlinks are not permitted in an artifact bundle")
    paths = list(folder.rglob("*"))
    require(not any(path.is_symlink() for path in paths), "Symlinks are not permitted in an artifact bundle")
    actual = {path.relative_to(folder).as_posix(): path for path in paths if path.is_file()}
    expected_files = {SNAPSHOT_FILE, ACTIONS_FILE, *LOG_FILES.values()}
    require(set(actual) == expected_files | {"metadata.json"}, "World artifact file inventory mismatch")
    metadata = read(folder / "metadata.json")
    hashes = metadata["raw_sha256"]
    require(set(hashes) == expected_files, "World raw hash inventory mismatch")
    for relative in sorted(hashes):
        require(sha256(actual[relative]) == hashes[relative], f"Artifact hash mismatch: {relative}")
    snapshot = read(folder / SNAPSHOT_FILE)
    manifest = {"source_hash": expected_source_hash, "code_version": RESEARCH_VERSION}
    state = snapshot_state(snapshot, manifest, folder.name)
    require(metadata["run_id"] == folder.name, "World run/folder identity mismatch")
    rebuilt_metadata = _metadata(snapshot, metadata["batch_id"], metadata["run_id"], metadata["group_id"],
        metadata["scenario"], metadata["condition"], expected_source_hash,
        metadata["analysis_config"], metadata["provenance"], hashes)
    require(metadata == rebuilt_metadata, "World metadata reconstruction mismatch")
    for field, relative in LOG_FILES.items():
        require(read(folder / relative) == state["logs"][field], f"Snapshot/log mismatch: {field}")
    actions = read(folder / ACTIONS_FILE)
    require(actions == _actions(state), "Government action split mismatch")
    for field, value in (("actions", actions), ("public_signal_ticks", state["logs"]["public_signal_ticks"]),
                         ("packets", state["packet_index"])):
        no_latent_fields(value, f"{folder.name}/{field}")
    snapshots = _ancestors(snapshot, all_snapshots, manifest, folder.name)
    _validate_publication(state, folder.name)
    # These two factories read only config; no physical world is constructed.
    settings_owner = SimpleNamespace(config=ResearchConfig.from_dict(state["config"]))
    require(state["sensing"]["settings"] == jsonable(asdict(ResearchWorld.sensing_settings(settings_owner))),
            "Sensing settings/configuration mismatch")
    from abm_jasss.research_replay import REPLAY_SCHEMA, _ReplayQueue, rebuild_replay_diagnostics
    queue = state["queue"]
    replay = queue.get("queue_mode") == REPLAY_SCHEMA
    require(not queue.get("queue_mode") or replay, "Unknown response queue mode")
    if not replay:
        require(queue["settings"] == jsonable(asdict(ResearchWorld.decision_settings(settings_owner))),
                "Response settings/configuration mismatch")
    if state["tick"]:
        validate_government(state, snapshots, folder.name, replay)
    else:
        _validate_empty_government(state, folder.name)
    if replay:
        _ReplayQueue.from_snapshot(queue)
        require(queue["last_step"] == state["tick"] - 1, "Replay cursor/boundary mismatch")
        require(state["config"] == jsonable(replace(ResearchConfig.from_dict(queue["plan"]["donor_config"]),
                government_delay=queue["administrative_delay"]).to_dict()) and
                state["seed"] == queue["plan"]["donor_seed"], "Replay configuration/seed mismatch")
        if "replay_plan_hash" in metadata["provenance"]:
            require(metadata["provenance"]["replay_plan_hash"] == queue["plan_hash"], "Replay provenance mismatch")
        rebuild_replay_diagnostics(state["logs"]["trajectory"], state["logs"]["events"],
                                   queue["plan"], queue["administrative_delay"], state["config"]["steps"])
    derived = jsonable(build_derived(state, metadata))
    derived_path = folder.parent.parent / "derived" / f"{folder.name}.json"
    require(not derived_path.is_symlink(), "Symlinks are not permitted in an artifact bundle")
    require(derived == read(derived_path), "Derived reconstruction mismatch")
    require(source_hash() == expected_source_hash, "Analysis source changed during validation")
    return derived
