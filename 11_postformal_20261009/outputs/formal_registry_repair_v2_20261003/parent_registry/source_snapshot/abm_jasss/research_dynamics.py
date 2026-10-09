"""Registered, development-only dynamic diagnostics for the research engine.

The alpha return path inherits the outgoing path's final state.  Independent
size/duration runs are explicitly separate checks, never continuation evidence.
Recovery is conditional on a registered healthy candidate; a small development
run does not establish that its reference is substantively healthy.
"""
from dataclasses import replace
import copy
import math
import re
import statistics

from .research_outcomes import recovery_diagnostic
from .research_world import ResearchWorld, canonical_hash, jsonable


def _integer(value, name, minimum=1):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _number(value, name, minimum=0., maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    value = float(value)
    if not math.isfinite(value) or value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"Invalid {name}")
    return value


def _window_metrics(rows, start, end):
    """Inclusive fixed window; explicitly retain measurement denominators."""
    selected = [row for row in rows if start <= row["step"] <= end]
    result = {"start_step": start, "end_step": end, "expected_ticks": end - start + 1,
              "observed_ticks": len(selected), "metrics": {}}
    for key in ("exposure_gap", "platform_representation_gap", "perception_error",
                "agenda_attention_share", "public_preference_on_agenda", "preference_shift",
                "trust_mean", "pending_count", "responses_executed"):
        values = [row[key] for row in selected if row.get(key) is not None
                  and (key != "perception_error" or row.get("has_data", False))]
        result["metrics"][key] = {"mean": statistics.fmean(values) if values else None,
                                   "valid_ticks": len(values),
                                   "coverage": len(values) / (end - start + 1)}
    return result


def run_continuation(config, seed, alphas=(.25, .5, .75), stage_ticks=20):
    """Run an ascending path and then descend from its terminal snapshot.

    Both endpoint stages are held for ``stage_ticks`` on the return path.  Every
    stage is a fork of the immediately preceding stage, including its queues,
    signal history, preferences, trust, content and addressed randomness.  The
    registered horizon is extended before initialization if necessary.
    """
    stage_ticks = _integer(stage_ticks, "stage_ticks")
    alphas = tuple(_number(value, "alpha", maximum=1.) for value in alphas)
    if len(alphas) < 2 or any(left >= right for left, right in zip(alphas, alphas[1:])):
        raise ValueError("alphas must contain at least two strictly increasing values")
    path = [("forward", value) for value in alphas] + [("reverse", value) for value in reversed(alphas)]
    total_steps = len(path) * stage_ticks
    registered = replace(config, steps=max(config.steps, total_steps), alpha=alphas[0])
    world = ResearchWorld(registered, seed)
    registration = {"kind": "state_preserving_alpha_continuation", "seed": seed,
                    "alphas": list(alphas), "stage_ticks": stage_ticks,
                    "path": [{"direction": direction, "alpha": alpha} for direction, alpha in path],
                    "config": registered.to_dict(), "source_hash": world.code_hash,
                    "initial_state_hash": world.initial_state_hash,
                    "registered_before_run": True}
    worlds, snapshots, records = {}, {"initial": world.snapshot()}, []
    for index, (direction, alpha) in enumerate(path):
        name = f"continuation_{index:02d}_{direction}"
        before = world.snapshot()
        start = world.tick
        branch = world.fork(name, {"alpha": alpha})
        # This is an actual full-state check before any new tick is simulated.
        inherited = branch.snapshot()
        preserved = (inherited["state"]["arrays"] == before["state"]["arrays"]
                     and inherited["state"]["queue"]["pending"] == before["state"]["queue"]["pending"]
                     and inherited["state"]["randomness"] == before["state"]["randomness"]
                     and inherited["state"]["logs"]["trajectory"] == before["state"]["logs"]["trajectory"])
        if not preserved:
            raise RuntimeError("Continuation did not preserve its parent state")
        branch.run(start + stage_ticks)
        after = branch.snapshot()
        worlds[name], snapshots[name] = branch, after
        snapshots[f"{name}_inherited"] = inherited
        records.append({"name": name, "direction": direction, "alpha": alpha,
                        "start_tick": start, "end_tick_exclusive": branch.tick,
                        "parent_world_id": world.world_id, "world_id": branch.world_id,
                        "input_snapshot_hash": before["state_hash"],
                        "inherited_snapshot_hash": branch.snapshot_id,
                        "output_snapshot_hash": after["state_hash"],
                        "state_preserved": preserved,
                        "window": _window_metrics(branch.trajectory, start, branch.tick - 1)})
        world = branch
    return {"worlds": worlds, "snapshots": snapshots,
            "diagnostics": {"registration": registration, "registration_hash": canonical_hash(registration),
                            "stages": records, "formal_ready": False,
                            "interpretation": "Finite development paths; no phase-transition or hysteresis claim."}}


def run_healthy_reference(config, seed, start_step, end_step, tolerance=.05, window=5, consecutive=3):
    """Register an independent candidate phase and recovery rule before running.

    The reference is the exposure-gap mean over the entire registered inclusive
    interval, with complete coverage required.  Its selection cannot inspect a
    treatment branch, and no branch's already-misaligned terminal window is used.
    """
    start_step = _integer(start_step, "reference start_step", 0)
    end_step = _integer(end_step, "reference end_step", 0)
    window = _integer(window, "recovery window")
    consecutive = _integer(consecutive, "recovery consecutive")
    tolerance = _number(tolerance, "recovery tolerance")
    if end_step < start_step or end_step >= config.steps:
        raise ValueError("Reference interval must lie within configured steps")
    world = ResearchWorld(config, seed)
    initial = world.snapshot()
    registration = {"kind": "independent_development_healthy_candidate", "seed": seed,
                    "config": config.to_dict(), "source_hash": world.code_hash,
                    "initial_state_hash": world.initial_state_hash,
                    "reference_start": start_step, "reference_end": end_step,
                    "key": "exposure_gap", "tolerance": tolerance, "window": window,
                    "consecutive": consecutive, "registered_before_run": True,
                    "substantive_health_validated": False}
    world.run(end_step + 1)
    metrics = _window_metrics(world.trajectory, start_step, end_step)
    target = metrics["metrics"]["exposure_gap"]
    reference = {"registration": registration, "registration_hash": canonical_hash(registration),
                 "value": target["mean"] if target["coverage"] == 1. else None,
                 "source_snapshot_hash": world.snapshot()["state_hash"], "window_summary": metrics,
                 "interpretation": "Recovery is conditional on this development healthy candidate."}
    reference["reference_hash"] = canonical_hash(reference)
    return {"world": world, "initial_snapshot": initial, "reference": reference}


def run_recovery_branches(parent, reference, interventions, observation_end):
    """Apply shared-reference interventions at one parent boundary.

    ``observation_end`` is an exclusive run boundary.  Time zero for recovery is
    the last completed common tick (parent.tick - 1), so initial health uses no
    post-intervention information.  Existing plans retain their action settings.
    ``reference=None`` explicitly limits interpretation to improvement/rebound.
    """
    observation_end = _integer(observation_end, "observation_end")
    if not parent.tick < observation_end <= parent.config.steps:
        raise ValueError("Recovery horizon must follow the fork within configured steps")
    if not interventions or any(not isinstance(name, str) or not name for name in interventions):
        raise ValueError("Named recovery interventions are required")
    if reference is None:
        settings = {"key": "exposure_gap", "window": 1, "consecutive": 1, "tolerance": 0.}
        value, reference_hash = None, None
    else:
        expected = canonical_hash({key: value for key, value in reference.items() if key != "reference_hash"})
        if expected != reference.get("reference_hash"):
            raise ValueError("Healthy reference hash mismatch")
        settings = reference["registration"]
        if settings["seed"] == parent.seed:
            raise ValueError("Healthy candidate must use an independent development seed")
        if settings["config"]["n_topics"] != parent.config.n_topics:
            raise ValueError("Healthy candidate has incompatible topic count")
        value, reference_hash = reference["value"], reference["reference_hash"]
    if parent.tick < settings["window"]:
        raise ValueError("Recovery needs a complete pre-intervention rolling window")
    registration = {"kind": "same_state_recovery", "intervention_tick": parent.tick,
                    "recovery_time_origin": parent.tick - 1, "observation_end_exclusive": observation_end,
                    "reference_hash": reference_hash, "interventions": interventions,
                    "registered_before_branch_runs": True}
    parent_snapshot = parent.snapshot()
    worlds, diagnostics, snapshots = {}, {}, {"parent": parent_snapshot}
    for name, changes in interventions.items():
        branch = parent.fork(name, changes)
        snapshots[f"{name}_inherited"] = branch.snapshot()
        branch.run(observation_end)
        result = recovery_diagnostic(branch.trajectory, settings["key"], value,
                                     settings["tolerance"], settings["window"],
                                     settings["consecutive"], parent.tick - 1)
        result.update(reference_hash=reference_hash,
                      parent_snapshot_hash=branch.snapshot_id,
                      conditional_on_candidate_reference=reference is not None,
                      window_summary=_window_metrics(branch.trajectory, parent.tick, observation_end - 1))
        worlds[name], snapshots[name], diagnostics[name] = branch, branch.snapshot(), result
    return {"worlds": worlds, "snapshots": snapshots,
            "diagnostics": {"registration": registration, "registration_hash": canonical_hash(registration),
                            "branches": diagnostics, "formal_ready": False}}


def _size_duration_design(config, sizes, durations, initial_conditions,
                          supply_scaling, capacity_scaling):
    sizes = tuple(_integer(value, "size") for value in sizes)
    durations = tuple(_integer(value, "duration") for value in durations)
    if not sizes or not durations or not isinstance(initial_conditions, dict) or not initial_conditions:
        raise ValueError("Nonempty sizes, durations and initial_conditions are required")
    if len(set(sizes)) != len(sizes) or len(set(durations)) != len(durations):
        raise ValueError("Size and duration grids must be unique")
    if supply_scaling not in ("fixed", "proportional") or capacity_scaling not in ("fixed", "proportional"):
        raise ValueError("Supply and capacity scaling must be fixed or proportional")
    if any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", name) for name in initial_conditions):
        raise ValueError("Initial conditions require safe nonempty names")
    # Validate the complete design before starting any simulations.
    registrations = []
    for name, weights in initial_conditions.items():
        if (not isinstance(weights, (list, tuple)) or len(weights) != config.n_topics
                or any(_number(value, "population weight") <= 0 for value in weights)):
            raise ValueError("Initial population weights must be positive and match n_topics")
        for size in sizes:
            ratio = size / config.n_agents
            scale = lambda value: max(1, int(math.floor(value * ratio + .5)))
            for duration in durations:
                changes = {"n_agents": size, "steps": duration, "final_window": min(config.final_window, duration),
                           "population_weights": tuple(weights), "survey_size": min(config.survey_size, size)}
                if supply_scaling == "proportional":
                    changes.update(initial_items=scale(config.initial_items), arrivals_per_step=scale(config.arrivals_per_step))
                if capacity_scaling == "proportional":
                    changes["response_capacity"] = scale(config.response_capacity)
                variant = replace(config, **changes)
                registrations.append((f"size_duration_{name}_n{size}_t{duration}", name, variant))
    return sizes, durations, registrations


def run_size_duration_checks(config, seed, sizes, durations, initial_conditions,
                             supply_scaling="proportional", capacity_scaling="fixed"):
    """Independent runs with registered population weights and explicit scales.

    Ordinary arrivals and initial stock scale together when supply is
    proportional; routine official publication keeps its configured interval.
    Scheduling capacity may independently be fixed or proportional.  Rounded
    integer realizations and actual per-capita quantities are all reported.
    """
    sizes, durations, registrations = _size_duration_design(
        config, sizes, durations, initial_conditions, supply_scaling, capacity_scaling)
    registration = {"kind": "independent_size_duration_initial_condition_checks", "seed": seed,
                    "sizes": list(sizes), "durations": list(durations), "initial_conditions": initial_conditions,
                    "supply_scaling": supply_scaling, "capacity_scaling": capacity_scaling,
                    "integer_scaling": "nearest integer, halves rounded up, minimum 1",
                    "routine_publication_scaling": "fixed interval", "registered_before_run": True,
                    "configs": {name: variant.to_dict() for name, _, variant in registrations}}
    worlds, snapshots, records = {}, {}, []
    for name, initial_name, variant in registrations:
        world = ResearchWorld(variant, seed).run()
        worlds[name], snapshots[name] = world, world.snapshot()
        records.append({"name": name, "initial_condition": initial_name,
                        "initial_state_hash": world.initial_state_hash,
                        "n_agents": variant.n_agents, "steps": variant.steps,
                        "ordinary_arrivals_per_agent": variant.arrivals_per_step / variant.n_agents,
                        "initial_items_per_agent": variant.initial_items / variant.n_agents,
                        "scheduling_capacity_per_agent": variant.response_capacity / variant.n_agents,
                        "survey_size": variant.survey_size,
                        "window": _window_metrics(world.trajectory, variant.steps - variant.final_window, variant.steps - 1)})
    return {"worlds": worlds, "snapshots": snapshots,
            "diagnostics": {"registration": registration, "registration_hash": canonical_hash(registration),
                            "runs": records, "formal_ready": False,
                            "interpretation": "Independent finite-run sensitivity; terminal windows are not established steady states."}}


def resolve_dynamics_spec(config, seed, spec=None):
    """Resolve and validate the complete design without constructing any world."""
    _integer(seed, "seed", 0)
    defaults = {"alphas": [.25, .5, .75], "stage_ticks": 20,
                "recovery_fork": 30, "recovery_end": 60,
                "reference_start": 10, "reference_end": 29,
                "reference_alpha": 0., "reference_seed": seed + 1_000_003,
                "recovery_window": 5, "recovery_consecutive": 3, "recovery_tolerance": .05,
                "sizes": [12, 24], "durations": [60, 90],
                "initial_conditions": {"balanced": [1.] * config.n_topics,
                                       "skewed": [1.] * (config.n_topics - 1) + [3.]},
                "supply_scaling": "proportional", "capacity_scaling": "fixed",
                "interventions": {"recovery_control": {}, "recovery_alpha0": {"alpha": 0.},
                                  "recovery_information": {"pref_info": True}}}
    if spec is not None:
        if not isinstance(spec, dict) or set(spec) - set(defaults):
            raise ValueError("Unknown dynamic diagnostic setting")
        defaults.update(copy.deepcopy(spec))
    spec = defaults
    for name in ("stage_ticks", "recovery_fork", "recovery_end", "recovery_window", "recovery_consecutive"):
        _integer(spec[name], name)
    for name in ("reference_start", "reference_end", "reference_seed"):
        _integer(spec[name], name, 0)
    for name in ("alphas", "sizes", "durations"):
        if not isinstance(spec[name], (list, tuple)) or not spec[name]:
            raise ValueError(f"{name} must be a nonempty sequence")
    spec["alphas"] = [_number(value, "alpha", maximum=1.) for value in spec["alphas"]]
    if len(spec["alphas"]) < 2 or any(a >= b for a, b in zip(spec["alphas"], spec["alphas"][1:])):
        raise ValueError("alphas must contain at least two strictly increasing values")
    spec["reference_alpha"] = _number(spec["reference_alpha"], "reference_alpha", maximum=1.)
    spec["recovery_tolerance"] = _number(spec["recovery_tolerance"], "recovery_tolerance")
    if not spec["recovery_fork"] < spec["recovery_end"]:
        raise ValueError("recovery_fork must precede recovery_end")
    if spec["reference_start"] > spec["reference_end"]:
        raise ValueError("reference_start must not exceed reference_end")
    if spec["reference_seed"] == seed:
        raise ValueError("Healthy candidate must use an independent development seed")
    if spec["recovery_fork"] < spec["recovery_window"]:
        raise ValueError("Recovery needs a complete pre-intervention rolling window")
    sizes, durations, registrations = _size_duration_design(
        config, spec["sizes"], spec["durations"], spec["initial_conditions"],
        spec["supply_scaling"], spec["capacity_scaling"])
    spec["sizes"], spec["durations"] = list(sizes), list(durations)
    interventions = spec["interventions"]
    allowed = {"pref_info", "government_delay", "response_capacity", "alpha", "ranking", "response_heat_retention"}
    if not isinstance(interventions, dict) or not interventions:
        raise ValueError("Named recovery interventions are required")
    reserved = {"healthy_candidate", "recovery_parent", "parent"}
    reserved.update(name for name, _, _ in registrations)
    for index in range(2 * len(spec["alphas"])):
        direction = "forward" if index < len(spec["alphas"]) else "reverse"
        reserved.add(f"continuation_{index:02d}_{direction}")
    for name, changes in interventions.items():
        if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", name)
                or name in reserved or name.endswith("_inherited")):
            raise ValueError("Invalid or conflicting recovery intervention name")
        if not isinstance(changes, dict) or set(changes) - allowed:
            raise ValueError("Unsupported intervention fields")
        for key, value in changes.items():
            if key in ("alpha", "response_heat_retention"):
                _number(value, key, maximum=1.)
            elif key in ("government_delay", "response_capacity"):
                _integer(value, key, 0 if key == "government_delay" else 1)
            elif key == "pref_info" and type(value) is not bool:
                raise ValueError("pref_info must be boolean")
            elif key == "ranking" and value not in ("topk", "softmax"):
                raise ValueError("Invalid ranking")
        replace(config, **changes)
    # Check every adjusted configuration now, before any output or simulation.
    replace(config, steps=max(config.steps, 2 * len(spec["alphas"]) * spec["stage_ticks"]), alpha=spec["alphas"][0])
    replace(config, steps=max(config.steps, spec["reference_end"] + 1), alpha=spec["reference_alpha"])
    replace(config, steps=max(config.steps, spec["recovery_end"]))
    return jsonable(spec)


def run_dynamics(config, seed, spec=None):
    """Small S1 suite; return serializable diagnostics plus worlds/snapshots.

    Alpha continuation and recovery use the base initial condition; the separate
    N/T matrix repeats every registered population-weight initial condition.
    """
    spec = resolve_dynamics_spec(config, seed, spec)
    reference_config = replace(config, alpha=spec["reference_alpha"],
                               steps=max(config.steps, spec["reference_end"] + 1))
    healthy = run_healthy_reference(reference_config, spec["reference_seed"], spec["reference_start"],
                                    spec["reference_end"], spec["recovery_tolerance"],
                                    spec["recovery_window"], spec["recovery_consecutive"])
    parent_config = replace(config, steps=max(config.steps, spec["recovery_end"]))
    parent = ResearchWorld(parent_config, seed).run(spec["recovery_fork"])
    recovery = run_recovery_branches(parent, healthy["reference"], spec["interventions"], spec["recovery_end"])
    continuation = run_continuation(config, seed, spec["alphas"], spec["stage_ticks"])
    sensitivity = run_size_duration_checks(config, seed, spec["sizes"], spec["durations"],
                                          spec["initial_conditions"], spec["supply_scaling"], spec["capacity_scaling"])
    worlds = {"healthy_candidate": healthy["world"], "recovery_parent": parent}
    snapshots = {"healthy_candidate_initial": healthy["initial_snapshot"],
                 "healthy_candidate": healthy["world"].snapshot(), "recovery_parent": parent.snapshot()}
    diagnostics = {"kind": "S1_development_dynamics", "spec": spec, "spec_hash": canonical_hash(spec),
                   "healthy_candidate": healthy["reference"], "formal_ready": False,
                   "limitations": ["Single development seed per matrix; no precision planning.",
                                   "Healthy reference is a candidate, not an established normative health criterion.",
                                   "No phase-transition, hysteresis, irreversibility or steady-state claim."]}
    for group, result in (("continuation", continuation), ("recovery", recovery), ("size_duration", sensitivity)):
        overlap = set(worlds).intersection(result["worlds"])
        if overlap:
            raise ValueError(f"Duplicate dynamic world names: {sorted(overlap)}")
        worlds.update(result["worlds"])
        snapshots.update({f"{group}_{name}": snapshot for name, snapshot in result["snapshots"].items()})
        diagnostics[group] = result["diagnostics"]
    return {"worlds": worlds, "snapshots": snapshots, "diagnostics": diagnostics}


def rebuild_dynamics_diagnostics(config, seed, spec, world_snapshots, snapshots):
    """Recompute the complete dynamic evidence from archived states, without ticks.

    Keys match ``run_dynamics``: ``world_snapshots`` replaces each world object
    with its final snapshot, and ``snapshots`` is the archived auxiliary mapping.
    No saved summary or diagnostic number is used as an input.  The caller may
    compare this result's canonical hash with the recorded diagnostic document.
    """
    spec = resolve_dynamics_spec(config, seed, spec)

    def require(condition, message):
        if not condition:
            raise ValueError(message)

    for snapshot in list(world_snapshots.values()) + list(snapshots.values()):
        require(isinstance(snapshot, dict) and set(snapshot) == {"state", "state_hash"}, "Invalid dynamic snapshot")
        require(canonical_hash(snapshot["state"]) == snapshot["state_hash"], "Dynamic snapshot hash mismatch")

    def state_for(name, expected_config, expected_seed, tick, auxiliary_name=None):
        snapshot = world_snapshots[name]
        state = snapshot["state"]
        require(canonical_hash(state["config"]) == canonical_hash(expected_config.to_dict()),
                f"Dynamic configuration differs: {name}")
        require(state["seed"] == expected_seed and state["tick"] == tick, f"Dynamic seed/time differs: {name}")
        require([row["step"] for row in state["logs"]["trajectory"]] == list(range(tick)),
                f"Incomplete dynamic trajectory: {name}")
        if auxiliary_name is not None:
            require(snapshot == snapshots[auxiliary_name], f"Dynamic duplicate snapshot differs: {name}")
        return state

    def inherited_state(before, inherited, after, name, changes):
        prior, state, final = before["state"], inherited["state"], after["state"]
        tick = prior["tick"]
        require(state["tick"] == tick and state["snapshot_id"] == before["state_hash"], "Invalid fork boundary/hash")
        require(state["parent_world_id"] == prior["world_id"] and state["world_id"] == f"{prior['world_id']}/{name}",
                "Invalid dynamic parent lineage")
        require(state["config"] == jsonable({**prior["config"], **changes}), "Unexpected dynamic intervention")
        preserved = (state["arrays"] == prior["arrays"] and state["queue"]["pending"] == prior["queue"]["pending"]
                     and state["randomness"] == prior["randomness"]
                     and state["logs"]["trajectory"] == prior["logs"]["trajectory"])
        require(preserved, "Dynamic fork did not preserve inherited state")
        # Publisher, legal evidence and all historical logs also survive the fork.
        for key in ("publisher", "pending_packets", "latest_packet", "packet_index", "catalogs", "truth_history",
                    "pending_surveys", "latest_survey", "initial_state_hash", "seed", "source_hash"):
            require(state[key] == prior[key], f"Dynamic fork changed {key}")
        for key, rows in prior["logs"].items():
            if key != "treatments":
                require(state["logs"][key] == rows, f"Dynamic inherited history changed: {key}")
                # Pending events legitimately acquire execution fields later.
                if key != "events":
                    require(final["logs"][key][:len(rows)] == rows, f"Dynamic historical prefix changed: {key}")
        require(final["world_id"] == state["world_id"] and final["snapshot_id"] == before["state_hash"]
                and final["parent_world_id"] == prior["world_id"], "Dynamic final lineage changed")
        require(final["logs"]["treatments"] == state["logs"]["treatments"], "Unexpected mid-stage intervention")
        require(state["logs"]["treatments"][:-1] == prior["logs"]["treatments"], "Dynamic treatment prefix changed")
        treatment = state["logs"]["treatments"][-1]
        require(treatment["at"] == tick and treatment["branch_id"] == name and treatment["changes"] == changes
                and treatment["pre_treatment_state_hash"] == before["state_hash"], "Invalid dynamic treatment record")
        return preserved

    _, _, variants = _size_duration_design(config, spec["sizes"], spec["durations"], spec["initial_conditions"],
                                          spec["supply_scaling"], spec["capacity_scaling"])
    path = [("forward", alpha) for alpha in spec["alphas"]] + [("reverse", alpha) for alpha in reversed(spec["alphas"])]
    stage_names = [f"continuation_{index:02d}_{direction}" for index, (direction, _) in enumerate(path)]
    expected_names = {"healthy_candidate", "recovery_parent", *stage_names, *spec["interventions"],
                      *(name for name, _, _ in variants)}
    require(set(world_snapshots) == expected_names, "Dynamic world set differs from registration")
    reference_config = replace(config, alpha=spec["reference_alpha"], steps=max(config.steps, spec["reference_end"] + 1))
    healthy = state_for("healthy_candidate", reference_config, spec["reference_seed"], spec["reference_end"] + 1,
                        "healthy_candidate")
    initial = snapshots["healthy_candidate_initial"]["state"]
    require(initial["tick"] == 0 and initial["initial_state_hash"] == healthy["initial_state_hash"]
            and initial["initial_state_hash"] == canonical_hash(initial["arrays"]), "Invalid healthy candidate initial state")
    reference_registration = {"kind": "independent_development_healthy_candidate", "seed": spec["reference_seed"],
                              "config": reference_config.to_dict(), "source_hash": healthy["source_hash"],
                              "initial_state_hash": healthy["initial_state_hash"],
                              "reference_start": spec["reference_start"], "reference_end": spec["reference_end"],
                              "key": "exposure_gap", "tolerance": spec["recovery_tolerance"],
                              "window": spec["recovery_window"], "consecutive": spec["recovery_consecutive"],
                              "registered_before_run": True, "substantive_health_validated": False}
    metrics = _window_metrics(healthy["logs"]["trajectory"], spec["reference_start"], spec["reference_end"])
    target = metrics["metrics"]["exposure_gap"]
    reference = {"registration": reference_registration, "registration_hash": canonical_hash(reference_registration),
                 "value": target["mean"] if target["coverage"] == 1. else None,
                 "source_snapshot_hash": world_snapshots["healthy_candidate"]["state_hash"], "window_summary": metrics,
                 "interpretation": "Recovery is conditional on this development healthy candidate."}
    reference["reference_hash"] = canonical_hash(reference)

    continuation_config = replace(config, steps=max(config.steps, len(path) * spec["stage_ticks"]), alpha=spec["alphas"][0])
    before = snapshots["continuation_initial"]
    require(before["state"]["tick"] == 0 and before["state"]["seed"] == seed
            and canonical_hash(before["state"]["config"]) == canonical_hash(continuation_config.to_dict())
            and before["state"]["initial_state_hash"] == canonical_hash(before["state"]["arrays"]),
            "Invalid continuation initial state")
    continuation_registration = {"kind": "state_preserving_alpha_continuation", "seed": seed,
                                 "alphas": spec["alphas"], "stage_ticks": spec["stage_ticks"],
                                 "path": [{"direction": direction, "alpha": alpha} for direction, alpha in path],
                                 "config": continuation_config.to_dict(), "source_hash": before["state"]["source_hash"],
                                 "initial_state_hash": before["state"]["initial_state_hash"], "registered_before_run": True}
    stages = []
    for index, ((direction, alpha), name) in enumerate(zip(path, stage_names)):
        start, end = index * spec["stage_ticks"], (index + 1) * spec["stage_ticks"]
        state = state_for(name, replace(continuation_config, alpha=alpha), seed, end, f"continuation_{name}")
        after, inherited = world_snapshots[name], snapshots[f"continuation_{name}_inherited"]
        preserved = inherited_state(before, inherited, after, name, {"alpha": alpha})
        stages.append({"name": name, "direction": direction, "alpha": alpha, "start_tick": start,
                       "end_tick_exclusive": end, "parent_world_id": before["state"]["world_id"],
                       "world_id": state["world_id"], "input_snapshot_hash": before["state_hash"],
                       "inherited_snapshot_hash": state["snapshot_id"], "output_snapshot_hash": after["state_hash"],
                       "state_preserved": preserved, "window": _window_metrics(state["logs"]["trajectory"], start, end - 1)})
        before = after
    continuation = {"registration": continuation_registration, "registration_hash": canonical_hash(continuation_registration),
                    "stages": stages, "formal_ready": False,
                    "interpretation": "Finite development paths; no phase-transition or hysteresis claim."}

    parent_config = replace(config, steps=max(config.steps, spec["recovery_end"]))
    parent = state_for("recovery_parent", parent_config, seed, spec["recovery_fork"], "recovery_parent")
    recovery_registration = {"kind": "same_state_recovery", "intervention_tick": parent["tick"],
                             "recovery_time_origin": parent["tick"] - 1,
                             "observation_end_exclusive": spec["recovery_end"], "reference_hash": reference["reference_hash"],
                             "interventions": spec["interventions"], "registered_before_branch_runs": True}
    branches = {}
    for name, changes in spec["interventions"].items():
        state = state_for(name, replace(parent_config, **changes), seed, spec["recovery_end"], f"recovery_{name}")
        inherited_state(world_snapshots["recovery_parent"], snapshots[f"recovery_{name}_inherited"],
                        world_snapshots[name], name, changes)
        result = recovery_diagnostic(state["logs"]["trajectory"], "exposure_gap", reference["value"],
                                     spec["recovery_tolerance"], spec["recovery_window"],
                                     spec["recovery_consecutive"], parent["tick"] - 1)
        result.update(reference_hash=reference["reference_hash"], parent_snapshot_hash=state["snapshot_id"],
                      conditional_on_candidate_reference=True,
                      window_summary=_window_metrics(state["logs"]["trajectory"], parent["tick"], spec["recovery_end"] - 1))
        branches[name] = result
    recovery = {"registration": recovery_registration, "registration_hash": canonical_hash(recovery_registration),
                "branches": branches, "formal_ready": False}

    size_registration = {"kind": "independent_size_duration_initial_condition_checks", "seed": seed,
                         "sizes": spec["sizes"], "durations": spec["durations"], "initial_conditions": spec["initial_conditions"],
                         "supply_scaling": spec["supply_scaling"], "capacity_scaling": spec["capacity_scaling"],
                         "integer_scaling": "nearest integer, halves rounded up, minimum 1",
                         "routine_publication_scaling": "fixed interval", "registered_before_run": True,
                         "configs": {name: variant.to_dict() for name, _, variant in variants}}
    runs = []
    for name, initial_name, variant in variants:
        state = state_for(name, variant, seed, variant.steps, f"size_duration_{name}")
        runs.append({"name": name, "initial_condition": initial_name, "initial_state_hash": state["initial_state_hash"],
                     "n_agents": variant.n_agents, "steps": variant.steps,
                     "ordinary_arrivals_per_agent": variant.arrivals_per_step / variant.n_agents,
                     "initial_items_per_agent": variant.initial_items / variant.n_agents,
                     "scheduling_capacity_per_agent": variant.response_capacity / variant.n_agents,
                     "survey_size": variant.survey_size,
                     "window": _window_metrics(state["logs"]["trajectory"], variant.steps - variant.final_window, variant.steps - 1)})
    sensitivity = {"registration": size_registration, "registration_hash": canonical_hash(size_registration),
                   "runs": runs, "formal_ready": False,
                   "interpretation": "Independent finite-run sensitivity; terminal windows are not established steady states."}
    return jsonable({"kind": "S1_development_dynamics", "spec": spec, "spec_hash": canonical_hash(spec),
                     "healthy_candidate": reference, "formal_ready": False,
                     "limitations": ["Single development seed per matrix; no precision planning.",
                                     "Healthy reference is a candidate, not an established normative health criterion.",
                                     "No phase-transition, hysteresis, irreversibility or steady-state claim."],
                     "continuation": continuation, "recovery": recovery, "size_duration": sensitivity})
