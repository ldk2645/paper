"""Fixed post-formal paired effects; no borrowing of old formal observations."""
import collections
import statistics
from .common import *
from .registry import validate_registry
from scripts.formal_inference import paired_t_inference, holm_adjust

def build_tables(records, auxiliary, spec):
    expected = {}
    for variant in spec['variants']:
        arm_keys = [('E2',a) for a in E2]+[('E4',a) for a in variant['branches']]
        if variant['closed']:
            arm_keys += [('E3_closed','baseline')]+[('E3_closed',a) for a in variant['closed']]
        arm_keys += [('E3_replay','delay'+str(d)) for d in variant['replay_delays']]
        for alpha in spec['alphas']:
            for seed in spec['seeds']:
                for family,arm in arm_keys:
                    expected[(variant['id'],alpha,seed,family,arm)] = None
    indexed = {}
    for r in records:
        key = (r['variant'],r['alpha'],r['parent_id'],r['family'],r['arm'])
        require(key in expected and key not in indexed and r['status']=='complete','Unexpected/duplicate/incomplete record')
        require(set(r['metrics'])==set(PRIMARY),'Wrong primary metrics')
        for value in r['metrics'].values():
            require(value is None or (type(value) in (float,int) and math.isfinite(value) and 0<=value<=1), 'Invalid distance')
        indexed[key] = r['metrics']
    require(set(indexed)==set(expected),'Missing study records')
    baseline = spec['variants'][0]
    baseline_contrasts = contrasts(baseline)
    rows,paired = [],[]
    for variant in spec['variants']:
        for alpha in spec['alphas']:
            for family, definitions in contrasts(variant).items():
                for contrast, weights in definitions.items():
                    for metric in PRIMARY:
                        for kind in ['within_variant']+(['effect_change'] if variant['id']!='baseline' else []):
                            terms = [(variant['id'],arm,weight) for arm,weight in weights.items()]
                            if kind=='effect_change':
                                require(baseline_contrasts[family][contrast]==weights,'Unmatched baseline contrast')
                                terms += [('baseline',arm,-weight) for arm,weight in weights.items()]
                            values,patterns = [],collections.Counter()
                            for seed in spec['seeds']:
                                measured = [(v,a,c,indexed[v,alpha,seed,family,a][metric]) for v,a,c in terms]
                                valid = all(x[3] is not None for x in measured)
                                pattern = ''.join('1' if x[3] is not None else '0' for x in measured)
                                patterns[pattern]+=1
                                value = math.fsum(c*x for _,_,c,x in measured) if valid else None
                                values.append(value)
                                paired.append({'analysis_family':kind,'variant':variant['id'],'alpha':alpha,
                                    'family':family,'contrast':contrast,'metric':metric,'parent_id':seed,
                                    'value':value,'support_pattern':pattern})
                            info = paired_t_inference(values)
                            n_none = patterns.get('0'*len(terms),0)
                            row = {'analysis_family':kind,'variant':variant['id'],'alpha':alpha,'family':family,
                                   'contrast':contrast,'metric':metric,**info,
                                   'n_none_valid':n_none,
                                   'n_partially_valid':len(values)-info['n_joint_valid']-n_none,
                                   'support_patterns':dict(patterns),'support_terms':[[v,a] for v,a,_ in terms]}
                            if info['confidence_half_width'] is not None:
                                row['observed_target_half_width_met'] = info['confidence_half_width']<=spec['inference']['target_half_width']
                            ci = row.pop('confidence_interval')
                            row.update(ci_lower=ci[0] if ci else None,ci_upper=ci[1] if ci else None)
                            rows.append(row)
    for kind in spec['inference']['holm_families']:
        selected = [r for r in rows if r['analysis_family']==kind]
        adjusted = holm_adjust([r['p_value_two_sided'] for r in selected])
        for r,p in zip(selected,adjusted):
            r.update(p_value_holm=p,reject_holm_0_05=r['status']=='estimated' and p<=.05,
                     holm_family_size=len(selected),target_half_width=spec['inference']['target_half_width'])
    aux_index,groups = set(),collections.defaultdict(list)
    for r in auxiliary:
        key = (r['variant'],r['alpha'],r['parent_id'],r['family'],r['arm'])
        require(key in expected and key not in aux_index and set(r['values'])==set(AUXILIARY),'Auxiliary identity/metrics mismatch')
        aux_index.add(key)
        for metric,value in r['values'].items():
            require(value is None or isinstance(value,(bool,int,float)) and math.isfinite(value),'Invalid auxiliary')
            groups[(r['variant'],r['alpha'],r['family'],r['arm'],metric)].append(value)
    require(aux_index==set(expected),'Missing auxiliary records')
    auxiliary_rows=[]
    for key,values in sorted(groups.items()):
        observed=[x for x in values if x is not None]
        auxiliary_rows.append(dict(zip(('variant','alpha','family','arm','metric'),key),
            n_total=len(values),n_valid=len(observed),mean=statistics.fmean(observed) if observed else None,
            scope='descriptive_equal_weight_mother_world_means'))
    return rows,auxiliary_rows,paired

import math

def build_analysis(registry,batch,validation_path,output):
    registry,batch = Path(registry).resolve(),Path(batch).resolve()
    gate = validate_registry(registry)
    manifest = read(batch/'manifest.json')
    require(manifest['status']=='complete' and manifest['registry_hash']==gate['registry_hash'],'Batch not complete/bound')
    validation_path = Path(validation_path).resolve()
    validation = read(validation_path)
    require(validation['status']=='passed' and validation['read_only'] is True and
            validation['batch_id']==manifest['batch_id'] and
            validation['registry_hash']==gate['registry_hash'] and
            validation['batch_manifest_hash']==sha256(batch/'manifest.json') and
            validation['batch_inventory_hash']==sha256(batch/'artifact_hashes.json'),'Unbound validation report')
    check_inventory(batch)
    records_path=validation_path.parent/'records.json.gz'
    require(sha256(records_path)==validation['records_hash'],'Validation records changed')
    data=read(records_path)
    rows,aux,paired=build_tables(data['records'],data['auxiliary_records'],read(registry/'configuration.json'))
    out=new_directory(output)
    write_csv(out/'primary.csv',rows)
    write_csv(out/'auxiliary.csv',aux)
    write_gzip_json(out/'paired_values.json.gz',paired)
    summary={'status':'complete','stage':'postformal_analysis','created_at':utc(),'batch_id':manifest['batch_id'],
             'registry_hash':gate['registry_hash'],'validation_hash':sha256(validation_path),
             'batch_inventory_hash':validation['batch_inventory_hash'],'source_hash':gate['source_hash'],
             'extension_source_hash':gate['extension_source_hash'],'primary_rows':len(rows),'auxiliary_rows':len(aux),
             'families':{kind:{'items':sum(r['analysis_family']==kind for r in rows),
                   'estimated':sum(r['analysis_family']==kind and r['status']=='estimated' for r in rows),
                   'holm_rejections':sum(r['analysis_family']==kind and r['reject_holm_0_05'] for r in rows),
                   'precision_met':sum(r['analysis_family']==kind and r['observed_target_half_width_met'] is True for r in rows)}
                  for kind in ('within_variant','effect_change')},
             'scope':'Post-formal sensitivity analysis designed after primary results; separate two Holm families; no old formal observations'}
    write_json(out/'summary.json',summary)
    inventory(out)
    return summary
