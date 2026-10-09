"""Independent study CLI. Production runs consume the entire frozen registry."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from postformal.simulation.common import *
from postformal.simulation.registry import resolve,freeze,validate_registry,extension_inventory,dependency_inventory
from abm_jasss.research_config import RESEARCH_VERSION
from concurrent.futures import ProcessPoolExecutor,as_completed
from datetime import datetime,timezone
import argparse
import shutil
import time
import traceback
import unittest
import uuid

def draft_config(output):
    base=read(ROOT/'configs/formal_design_20261003.json')
    definitions=[('baseline',{}),('grid6',{'inference_grid':6}),('reference8',{'reference_agents':8}),
        ('reference16',{'reference_agents':16}),('survey6',{'survey_size':6}),('survey24',{'survey_size':24}),
        ('prior5',{'opaque_alpha':[0.,.25,.5,.75,1.]}),('regularization0',{'regularization':0.}),
        ('regularization005',{'regularization':.05}),('survey_weight05',{'survey_weight':.5}),
        ('survey_weight2',{'survey_weight':2.}),('grid6_reference8',{'inference_grid':6,'reference_agents':8}),
        ('no_drift',{'drift_rate':0.}),('population200',{'n_agents':200}),
        ('horizon450',{'steps':450,'completion_start':300,'completion_end':429})]
    variants=[]
    for name,changes in definitions:
        extended=name in ('baseline','no_drift','population200','horizon450')
        branches=list(BRANCHES) if name in ('baseline','no_drift') else ['B0','B1','B2','B4'] if extended else ['B0','B1','B4']
        variants.append({'id':name,'changes':changes,'fork_tick':150,'branches':branches,
                         'closed':{'delay0':{'government_delay':0}} if extended else {},
                         'replay_delays':[0,3] if extended else []})
    spec={'schema':'postformal-design-1','phase':'supplement','created_at':utc(),
          'base_model':base['model'],'alphas':[.25,.75],'seeds':list(range(910001,910201)),
          'variants':variants,'inference':{'min_joint_valid':30,'sd_floor':1e-12,'confidence':.95,
          'target_half_width':.05,'holm_families':['within_variant','effect_change'],
          'additional_sampling':False,'budget_policy':'fixed_200_new_mother_seeds_per_alpha_setting; precision limitations retained'},
          'scope':'post-formal estimator, No Drift, population and horizon sensitivity; no E5/E6'}
    jobs=resolve(spec)
    write_json(output,spec)
    return {'groups':len(jobs),'world_records':sum(len(arms(j)) for j in jobs),'variants':len(variants),
            'seeds':len(spec['seeds'])}

def _pool_run(args):
    from postformal.simulation.runtime import run_group
    return run_group(*args)

def _pool_validate(args):
    from postformal.simulation.runtime import validate_group
    return validate_group(*args)

def run_batch(registry,output,workers=3):
    registry=Path(registry).resolve();gate=validate_registry(registry)
    rm=read(registry/'manifest.json')
    require(rm['phase']=='supplement','Development registry cannot launch production batch')
    require(type(workers) is int and 1<=workers<=8,'Invalid workers')
    out=new_directory(output)
    jobs=read(registry/'resolved_design.json')
    manifest={'schema':'postformal-batch-1','status':'running','stage':'postformal_supplement',
        'started_at':utc(),'batch_id':'postformal_'+uuid.uuid4().hex,'registry_path':str(registry),
        **gate,'status':'running','code_version':RESEARCH_VERSION,'expected_groups':len(jobs),
        'expected_world_records':rm['world_records'],'workers':workers,'completed_groups':0,'failures':[]}
    # Only this lifecycle manifest changes. Raw, derived and finalized inventories are write-once.
    write_json(out/'launch.json',manifest)
    completed=[];failures=[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(_pool_run,(job,str(out),manifest['batch_id'],gate['source_hash'],str(registry))):job
                 for job in jobs}
        with (out/'progress.jsonl').open('x',encoding='utf-8') as log:
            for future in as_completed(futures):
                job=futures[future]
                try:
                    result=future.result();completed.append(result)
                    row={'at':utc(),'status':'complete',**result}
                except Exception as exc:
                    row={'at':utc(),'status':'failed','group_id':job['group_id'],'error':str(exc),
                         'traceback':traceback.format_exc()}
                    failures.append(row)
                log.write(json.dumps(row,ensure_ascii=False)+'\n');log.flush()
                if len(completed)%50==0 or row['status']=='failed':
                    print(json.dumps({'stage':'run','completed':len(completed),'failed':len(failures),
                                      'total':len(jobs),'last_group':job['group_id']}),flush=True)
    validate_registry(registry)
    manifest.update(status='failed' if failures else 'complete',completed_at=utc(),
                    completed_groups=len(completed),failures=failures,
                    world_records=sum(x['world_records'] for x in completed))
    write_json(out/'manifest.json',manifest)
    inventory(out)
    require(not failures,'Batch contains failures; see preserved manifest')
    return manifest

def validate_batch(registry,batch,output,workers=3):
    registry,batch=Path(registry).resolve(),Path(batch).resolve()
    gate=validate_registry(registry);manifest=read(batch/'manifest.json')
    require(manifest['status']=='complete' and manifest['registry_hash']==gate['registry_hash'],'Incomplete/wrong batch')
    require(manifest['schema']=='postformal-batch-1' and manifest['stage']=='postformal_supplement' and
            manifest['code_version']==RESEARCH_VERSION and manifest['failures']==[], 'Invalid batch lifecycle')
    for field in ('registry_hash','inventory_hash','source_hash','extension_source_hash','specification_hash'):
        require(manifest[field]==gate[field], 'Batch registry binding mismatch: '+field)
    launch=read(batch/'launch.json')
    require(launch['status']=='running' and launch['completed_groups']==0 and launch['failures']==[], 'Invalid launch lifecycle')
    for field in ('schema','stage','batch_id','registry_path','registry_hash','inventory_hash','source_hash',
                  'extension_source_hash','specification_hash','code_version','expected_groups',
                  'expected_world_records','workers','started_at'):
        require(launch[field]==manifest[field], 'Launch/final manifest mismatch: '+field)
    digest,count=check_inventory(batch)
    jobs=read(registry/'resolved_design.json')
    expected_worlds=sum(len(arms(j)) for j in jobs)
    require(manifest['completed_groups']==manifest['expected_groups']==len(jobs) and
            manifest['world_records']==manifest['expected_world_records']==expected_worlds,'Incomplete roster')
    expected_progress={j['group_id']:len(arms(j)) for j in jobs}
    observed_progress={}
    with (batch/'progress.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line)
            require(row['status']=='complete' and row['group_id'] not in observed_progress and
                    row['group_id'] in expected_progress,'Invalid progress roster')
            observed_progress[row['group_id']]=row['world_records']
    require(observed_progress==expected_progress,'Progress counts differ from registry')
    expected_files={'launch.json','manifest.json','progress.jsonl'}
    for j in jobs:
        g=j['group_id']
        expected_files.update([f'groups/{g}.json',f'initial_arrays/{g}.json',f'mother_snapshots/{g}.json.gz',f'diagnostics/{g}.json'])
        for f,a,_ in arms(j):
            rid=f'{f}_{g}_{a}'
            expected_files.update([f'raw/{rid}/snapshot.json.gz',f'raw/{rid}/metadata.json',f'derived/{rid}.json'])
    require(set(read(batch/'artifact_hashes.json'))==expected_files,'Unexpected batch file set')
    out=new_directory(output)
    records=[];aux=[];worlds=ticks=events=done=0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(_pool_validate,(j,str(batch),manifest,str(registry))) for j in jobs]
        for future in as_completed(futures):
            r=future.result();done+=1
            records.extend(r['records']);aux.extend(r['auxiliary_records'])
            worlds+=r['world_records'];ticks+=r['trajectory_records'];events+=r['response_events']
            if done%100==0:print(json.dumps({'stage':'validate','groups':done,'total':len(jobs)}),flush=True)
    require(worlds==manifest['world_records'],'World count mismatch')
    require(check_inventory(batch)[0]==digest,'Batch inventory changed during validation')
    validate_registry(registry)
    key=lambda r:(r['variant'],r['alpha'],r['parent_id'],r['family'],r['arm'])
    write_gzip_json(out/'records.json.gz',{'records':sorted(records,key=key),'auxiliary_records':sorted(aux,key=key)})
    report={'status':'passed','stage':'postformal_read_only_validation','read_only':True,'completed_at':utc(),
            'batch_id':manifest['batch_id'],'registry_hash':gate['registry_hash'],
            'batch_manifest_hash':sha256(batch/'manifest.json'),'batch_inventory_hash':digest,
            'records_hash':sha256(out/'records.json.gz'),'hashed_files':count,'groups':done,
            'world_records':worlds,'trajectory_records':ticks,'response_events':events,
            'government_publication_fork_replay_rebuilt':True,'derived_and_no_drift_rebuilt':True}
    write_json(out/'validation.json',report);inventory(out)
    return report

def run_tests(output):
    import io
    stream=io.StringIO()
    extension_before=canonical_hash(extension_inventory())
    dependencies_before=canonical_hash(dependency_inventory())
    tests_before={p.relative_to(ROOT).as_posix():sha256(p) for p in sorted((ROOT/'tests').glob('test_*.py'))}
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_*.py')
    start=time.perf_counter()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    require(extension_before==canonical_hash(extension_inventory()) and
            dependencies_before==canonical_hash(dependency_inventory()) and
            tests_before=={p.relative_to(ROOT).as_posix():sha256(p) for p in sorted((ROOT/'tests').glob('test_*.py'))},
            'Source or tests changed during test run')
    out=new_directory(output)
    (out/'tests.log').write_text(stream.getvalue(),encoding='utf-8')
    report={'status':'passed' if result.wasSuccessful() and result.testsRun>0 else 'failed',
            'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
            'seconds':time.perf_counter()-start,'created_at':utc(),
            'extension_source_hash':canonical_hash(extension_inventory()),'physical_source_hash':source_hash(),
            'dependency_source_hash':canonical_hash(dependency_inventory()),
            'test_source_sha256':tests_before,
            'tests_log_hash':sha256(out/'tests.log')}
    write_json(out/'tests.json',report);inventory(out)
    print(stream.getvalue(),flush=True)
    require(report['status']=='passed','Tests failed')
    return report

def pipeline(registry,output,workers):
    from postformal.simulation.analysis import build_analysis
    from postformal.simulation.report import build_report
    out=new_directory(output)
    steps=[]
    try:
        for name,call in [('run',lambda:run_batch(registry,out/'batch',workers)),
                          ('validate',lambda:validate_batch(registry,out/'batch',out/'validation',workers)),
                          ('analyze',lambda:build_analysis(registry,out/'batch',out/'validation/validation.json',out/'analysis')),
                          ('report',lambda:build_report(out/'analysis',out/'report'))]:
            start=time.perf_counter();print(json.dumps({'stage':name,'started_at':utc()}),flush=True)
            result=call()
            steps.append({'stage':name,'status':'passed','seconds':time.perf_counter()-start,'completed_at':utc()})
            write_json(out/(name+'_completion.json'),steps[-1])
        report={'status':'passed','completed_at':utc(),'steps':steps,'registry':str(Path(registry).resolve()),
                'analysis':read(out/'analysis/summary.json'),'validation_hash':sha256(out/'validation/validation.json')}
    except Exception as exc:
        report={'status':'failed','at':utc(),'steps':steps,'error':str(exc),'traceback':traceback.format_exc()}
        write_json(out/'acceptance.json',report)
        raise
    write_json(out/'acceptance.json',report)
    return report

def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='command',required=True)
    q=s.add_parser('draft');q.add_argument('output')
    q=s.add_parser('test');q.add_argument('output')
    q=s.add_parser('freeze');q.add_argument('config');q.add_argument('output')
    for key in ('protocol','tests','seed-audit','benchmark'):q.add_argument('--'+key,required=True)
    q=s.add_parser('plan');q.add_argument('registry')
    for cmd in ('run','pipeline'):
        q=s.add_parser(cmd);q.add_argument('registry');q.add_argument('output');q.add_argument('--workers',type=int,default=3)
    q=s.add_parser('validate');q.add_argument('registry');q.add_argument('batch');q.add_argument('output');q.add_argument('--workers',type=int,default=3)
    args=p.parse_args()
    if args.command=='draft':result=draft_config(args.output)
    elif args.command=='test':result=run_tests(args.output)
    elif args.command=='freeze':result=freeze(args.config,args.output,args.protocol,args.tests,args.seed_audit,args.benchmark)
    elif args.command=='plan':
        result=validate_registry(args.registry)
        result.update(models_executed=0,**{k:read(Path(args.registry)/'manifest.json')[k] for k in ('groups','world_records','independent_seeds')})
    elif args.command=='run':result=run_batch(args.registry,args.output,args.workers)
    elif args.command=='validate':result=validate_batch(args.registry,args.batch,args.output,args.workers)
    else:result=pipeline(args.registry,args.output,args.workers)
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
