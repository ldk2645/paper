"""Complete snapshot bundles plus pure read-only semantic reconstruction."""
from dataclasses import replace, asdict
from types import SimpleNamespace
import math
from .common import *
from .registry import authorize_job
from abm_jasss.research_config import ResearchConfig, RESEARCH_VERSION
from abm_jasss.research_world import ResearchWorld
from abm_jasss.research_replay import (make_replay_worlds, replay_diagnostics, rebuild_replay_diagnostics,
                                      REPLAY_SCHEMA, PLAN_FIELDS, _ReplayQueue)
from scripts.formal_artifacts import _ancestors, _validate_publication, _actions
from scripts.formal_numeric_repair import build_formal_derived
from scripts.validate_s1_outputs import snapshot_state, validate_government, no_latent_fields
from scripts.validate_precision_pilot import _prefix_matches, _unbranched_state

def metadata(snapshot, job, family, arm, batch_id, gate, provenance):
    state = snapshot['state']
    return {'schema': 'postformal-world-1', 'stage': 'postformal_supplement',
        'formal_ready': False, 'status': 'complete', 'run_id': f"{family}_{job['group_id']}_{arm}",
        'group_id': job['group_id'], 'variant': job['variant'], 'scenario': family, 'condition': arm,
        'alpha': job['alpha'], 'parent_id': job['seed'], 'batch_id': batch_id,
        'registry_hash': gate['registry_hash'], 'job_hash': canonical_hash(job),
        'source_hash': gate['source_hash'], 'extension_source_hash': gate['extension_source_hash'],
        'code_version': RESEARCH_VERSION, 'config': state['config'],
        'analysis_config': jsonable(ResearchConfig.from_dict(state['config']).analysis_config()),
        'final_snapshot_hash': snapshot['state_hash'], 'initial_state_hash': state['initial_state_hash'],
        'ordinary_supply_hash': canonical_hash(state['logs']['supply_log']), 'provenance': provenance,
        'raw_encoding': 'complete snapshot gzip-json-level1; all original logs and arrays retained'}

def _records(meta, derived):
    identity = {'family': meta['scenario'], 'arm': meta['condition'], 'variant': meta['variant'],
                'alpha': meta['alpha'], 'parent_id': meta['parent_id'], 'status': 'complete'}
    summary, mechanism = derived['summary'], derived['mechanisms']
    values = {k: summary[k] for k in AUXILIARY[:9]}
    values.update({k: mechanism[k] for k in AUXILIARY[9:12]})
    values.update(platform_signal_coverage=summary['metric_coverage']['platform_representation_gap']['coverage'],
                  perception_data_coverage=summary['metric_coverage']['perception_error']['coverage'])
    return dict(identity, metrics={k: summary[k] for k in PRIMARY}), dict(identity, values=values)

def _nodrift(state, initial):
    if state['config']['drift_rate'] != 0:
        return None
    current = state['arrays']['preferences']
    old = initial['preferences']
    n, topics = state['config']['n_agents'], state['config']['n_topics']
    require(len(current) == len(old) == n, 'No Drift population mismatch')
    vectors = list(current) + list(old) + [initial['initial_truth']] + [
        row['P_true'] for row in state['logs']['trajectory']]
    require(all(len(row) == topics and all(type(x) in (int, float) and math.isfinite(x) for x in row)
                for row in vectors), 'No Drift preference/truth dimensions or values invalid')
    individual = max(abs(x-y) for a,b in zip(current,old) for x,y in zip(a,b))
    truth = initial['initial_truth']
    aggregate = max(abs(x-y) for row in state['logs']['trajectory'] for x,y in zip(row['P_true'],truth))
    require(max(individual, aggregate) <= 1e-12, 'No Drift changed preferences')
    return {'individual_max_abs_difference': individual, 'aggregate_max_abs_difference': aggregate,
            'initial_preferences_hash': canonical_hash(old), 'final_preferences_hash': canonical_hash(current),
            'ticks_checked': state['tick'], 'absolute_tolerance': 1e-12}

def _save(world, output, job, family, arm, batch_id, gate, provenance):
    snapshot = world.snapshot()
    require(world.tick == world.config.steps, 'Incomplete endpoint')
    meta = metadata(snapshot, job, family, arm, batch_id, gate, provenance)
    folder = output / 'raw' / meta['run_id']
    write_gzip_json(folder / 'snapshot.json.gz', snapshot)
    write_json(folder / 'metadata.json', meta)
    derived = jsonable(build_formal_derived(snapshot['state'], meta))
    write_json(output / 'derived' / (meta['run_id'] + '.json'), derived)
    return meta['run_id']

def run_group(job, output_name, batch_id, expected_hash, registry_path):
    gate = authorize_job(registry_path, job, expected_hash)
    out = Path(output_name)
    cfg = ResearchConfig.from_dict(job['model'])
    donor = ResearchWorld(cfg, job['seed'])
    initial = jsonable({k: getattr(donor,k) for k in ResearchWorld.ARRAY_FIELDS})
    write_json(out / 'initial_arrays' / (job['group_id'] + '.json'), initial)
    donor.run(until=job['fork_tick'])
    mother = donor.snapshot()
    write_gzip_json(out / 'mother_snapshots' / (job['group_id'] + '.json.gz'), mother)
    donor.run()
    run_ids, nd, diagnostics = [], {}, {}
    def save(w, f, a, p=None):
        require(w.initial_state_hash == donor.initial_state_hash, 'Within-setting initial arrays differ')
        require(w.supply_log == donor.supply_log, 'Within-setting ordinary supply differs')
        run_ids.append(_save(w,out,job,f,a,batch_id,gate,p or {}))
        check = _nodrift(w.snapshot()['state'], initial)
        if check is not None:
            nd[f + '/' + a] = check
    for arm, changes in E2.items():
        save(donor if arm == 'I00' else ResearchWorld(replace(cfg,**changes),job['seed']).run(), 'E2',arm)
    for arm, changes in job['branches'].items():
        world = ResearchWorld.from_snapshot(mother).fork(arm,changes).run()
        if arm == 'B0':
            require(_unbranched_state(world.snapshot()['state']) == _unbranched_state(donor.snapshot()['state']), 'B0 mismatch')
        save(world,'E4',arm,{'mother_snapshot_hash':mother['state_hash'],'fork_tick':job['fork_tick']})
    for arm,changes in job['closed'].items():
        save(ResearchWorld(replace(cfg,**changes),job['seed']).run(),'E3_closed',arm)
    if job['replay_delays']:
        for delay,world in make_replay_worlds(donor,job['replay_delays']).items():
            world.run()
            save(world,'E3_replay','delay'+str(delay),{'donor_run_id':f"E2_{job['group_id']}_I00",
                                                       'replay_plan_hash':world.replay_plan.plan_hash})
            diagnostics[str(delay)] = replay_diagnostics(world)
    write_json(out / 'diagnostics' / (job['group_id'] + '.json'), {'replay': diagnostics, 'no_drift': nd})
    files = [out / 'initial_arrays' / (job['group_id'] + '.json'),
             out / 'mother_snapshots' / (job['group_id'] + '.json.gz'),
             out / 'diagnostics' / (job['group_id'] + '.json')]
    for rid in run_ids:
        files.extend([out/'raw'/rid/'snapshot.json.gz',out/'raw'/rid/'metadata.json',out/'derived'/(rid+'.json')])
    result = {'group_id':job['group_id'],'job_hash':canonical_hash(job),'run_ids':run_ids,
              'files':{p.relative_to(out).as_posix():sha256(p) for p in files}}
    write_json(out / 'groups' / (job['group_id'] + '.json'),result)
    return {'group_id':job['group_id'],'world_records':len(run_ids)}

def validate_group(job, output_name, manifest, registry_path=None):
    out = Path(output_name)
    gate = authorize_job(registry_path or manifest['registry_path'],job,manifest['source_hash'])
    group = read(out/'groups'/(job['group_id']+'.json'))
    expected_ids = [f"{f}_{job['group_id']}_{a}" for f,a,_ in arms(job)]
    require(group['group_id']==job['group_id'] and group['job_hash']==canonical_hash(job) and
            group['run_ids']==expected_ids,'Group identity mismatch')
    expected_files = {f"{folder}/{job['group_id']}{suffix}" for folder,suffix in
                      [('initial_arrays','.json'),('mother_snapshots','.json.gz'),('diagnostics','.json')]}
    for rid in expected_ids:
        expected_files.update([f'raw/{rid}/snapshot.json.gz',f'raw/{rid}/metadata.json',f'derived/{rid}.json'])
    require(set(group['files'])==expected_files,'Group file list mismatch')
    for rel,digest in group['files'].items():
        path = out/rel
        require(not path.is_symlink() and sha256(path)==digest,'Group artifact corruption: '+rel)
    base = ResearchConfig.from_dict(job['model'])
    initial = read(out/'initial_arrays'/(job['group_id']+'.json'))
    mother_snapshot = read(out/'mother_snapshots'/(job['group_id']+'.json.gz'))
    mother = snapshot_state(mother_snapshot,manifest,job['group_id'])
    require(mother['tick']==job['fork_tick'] and mother['config']==jsonable(base.to_dict()) and
            mother['seed']==job['seed'] and mother['snapshot_id'] is None,'Mother mismatch')
    require(canonical_hash(initial)==mother['initial_state_hash'],'Initial arrays hash mismatch')
    parents = {mother_snapshot['state_hash']:mother_snapshot}
    validate_government(mother,parents,job['group_id']+'/mother')
    donor_snapshot = read(out/'raw'/f"E2_{job['group_id']}_I00"/'snapshot.json.gz')
    donor = snapshot_state(donor_snapshot,manifest,job['group_id']+'/donor')
    _prefix_matches(mother,donor,job['group_id'])
    records,aux,nd,diagnostics = [],[],{},{}
    ticks = events = 0
    for family,arm,changes in arms(job):
        rid = f"{family}_{job['group_id']}_{arm}"
        snapshot = read(out/'raw'/rid/'snapshot.json.gz')
        state = snapshot_state(snapshot,manifest,rid)
        cfg = replace(base,**changes)
        require(state['config']==jsonable(cfg.to_dict()) and state['tick']==cfg.steps and
                state['seed']==job['seed'],'Endpoint config/time/seed mismatch')
        require(state['initial_state_hash']==donor['initial_state_hash'] and
                state['randomness']==donor['randomness'] and state['logs']['supply_log']==donor['logs']['supply_log'],
                'Within-setting initial/randomness/supply mismatch')
        provenance = {}
        replay = family=='E3_replay'
        if family=='E4':
            require(state['snapshot_id']==mother_snapshot['state_hash'],'Wrong branch mother')
            provenance = {'mother_snapshot_hash':mother_snapshot['state_hash'],'fork_tick':job['fork_tick']}
            require(state['logs']['treatments'][-1]['branch_id']==arm and
                    state['logs']['treatments'][-1]['changes']==changes,'Wrong E4 treatment')
            if arm=='B0':
                require(_unbranched_state(state)==_unbranched_state(donor),'B0 not uninterrupted donor')
        elif replay:
            queue = state['queue']; plan = queue['plan']; delay = changes['government_delay']
            require(queue['queue_mode']==REPLAY_SCHEMA and queue['administrative_delay']==delay,'Wrong replay mode')
            require(plan['donor_snapshot_hash']==donor_snapshot['state_hash'] and
                    plan['donor_config']==donor['config'] and plan['donor_seed']==donor['seed'] and
                    plan['donor_world_id']==donor['world_id'] and plan['donor_source_hash']==manifest['source_hash'] and
                    plan['donor_information_hash']==canonical_hash(donor['logs']['information_log']) and
                    plan['events']==[{k:e[k] for k in PLAN_FIELDS} for e in donor['logs']['events']], 'Replay donor mismatch')
            require(state['world_id']==donor['world_id']+'/replay-delay-'+str(delay) and state['snapshot_id'] is None,
                    'Replay identity mismatch')
            _ReplayQueue.from_snapshot(queue)
            require(queue['last_step']==cfg.steps-1,'Replay cursor mismatch')
            provenance = {'donor_run_id':f"E2_{job['group_id']}_I00",'replay_plan_hash':queue['plan_hash']}
            diagnostics[str(delay)] = rebuild_replay_diagnostics(state['logs']['trajectory'],state['logs']['events'],plan,delay,cfg.steps)
        else:
            require(state['snapshot_id'] is None and state['parent_world_id'] is None and
                    not state['logs']['treatments'],'Unexpected adaptive ancestry')
        meta = metadata(snapshot,job,family,arm,manifest['batch_id'],gate,provenance)
        require(read(out/'raw'/rid/'metadata.json')==meta,'Metadata mismatch')
        snapshots = _ancestors(snapshot,parents,manifest,rid)
        _validate_publication(state,rid)
        owner = SimpleNamespace(config=cfg)
        require(state['sensing']['settings']==jsonable(asdict(ResearchWorld.sensing_settings(owner))), 'Sensing settings mismatch')
        if not replay:
            require(not state['queue'].get('queue_mode') and
                    state['queue']['settings']==jsonable(asdict(ResearchWorld.decision_settings(owner))), 'Queue settings mismatch')
        for value in (_actions(state),state['logs']['public_signal_ticks'],state['packet_index']):
            no_latent_fields(value,rid)
        validate_government(state,snapshots,rid,replay)
        derived = jsonable(build_formal_derived(state,meta))
        require(derived==read(out/'derived'/(rid+'.json')),'Derived values mismatch')
        check = _nodrift(state,initial)
        if check is not None: nd[family+'/'+arm]=check
        record,aux_record = _records(meta,derived)
        records.append(record);aux.append(aux_record)
        if family=='E2' and arm=='I00' and job['closed']:
            records.append(dict(record,family='E3_closed',arm='baseline'))
            aux.append(dict(aux_record,family='E3_closed',arm='baseline'))
        ticks += state['tick'];events += len(state['logs']['events'])
    require(read(out/'diagnostics'/(job['group_id']+'.json'))=={'replay':diagnostics,'no_drift':nd},'Diagnostics mismatch')
    return {'group_id':job['group_id'],'records':records,'auxiliary_records':aux,
            'world_records':len(expected_ids),'trajectory_records':ticks,'response_events':events}
