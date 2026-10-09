"""Complete supplementary tables and fixed pointwise-interval figures."""
import csv
from .common import *

def build_report(analysis,output):
    analysis=Path(analysis).resolve()
    digest,_=check_inventory(analysis)
    summary=read(analysis/'summary.json')
    with (analysis/'primary.csv').open(encoding='utf-8',newline='') as f:
        rows=list(csv.DictReader(f))
    out=new_directory(output)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plots=[]
    for kind in ('within_variant','effect_change'):
        for alpha in ('.25','.75'):
            for metric in PRIMARY:
                selected=[r for r in rows if r['analysis_family']==kind and float(r['alpha'])==float(alpha) and r['metric']==metric]
                name=kind+'_a'+alpha[1:]+'_'+metric
                for page,start in enumerate(range(0,len(selected),35),1):
                    subset=selected[start:start+35]
                    fig,ax=plt.subplots(figsize=(11, max(4,.30*len(subset)+2)))
                    for i,r in enumerate(subset):
                        if r['ci_lower']:
                            lo,hi,mean=map(float,(r['ci_lower'],r['ci_upper'],r['mean']))
                            ax.plot([lo,hi],[i,i],color='#64748b',lw=1)
                            ax.plot(mean,i,'o',color='#075985',markerfacecolor='#075985' if r['reject_holm_0_05']=='True' else 'white',markersize=4)
                    ax.set_yticks(range(len(subset)),[r['variant']+' / '+r['family']+' / '+r['contrast'] for r in subset],fontsize=7)
                    ax.invert_yaxis();ax.axvline(0,color='black',lw=.7)
                    ax.set_xlabel('TV difference; pointwise 95% t CI')
                    ax.set_title(f'{kind}; alpha={alpha}; {metric}',fontsize=10)
                    fig.text(.5,.01,'Filled markers: Holm rejection within the registered analysis family. Unavailable intervals are omitted.',ha='center',fontsize=7)
                    fig.tight_layout(rect=(0,.035,1,1))
                    filename=f'{name}_{page}'
                    for suffix in ('png','pdf'):
                        fig.savefig(out/(filename+'.'+suffix),dpi=160)
                    plt.close(fig);plots.append(filename+'.pdf')
    lines=['# Post-formal results / 后续稳健性结果','',
           '结果由完整新增批次只读验收后生成；既有E2–E4及102项原分析保持冻结。',
           'within_variant是每个设定内的处理差；effect_change是同一批新母seed下替代设定的处理差减新baseline处理差。',
           '两类结果各自一次Holm；图为点态95%区间，不是同时区间。不以重现显著性定义稳健。',
           '两α层分开解释；No Drift不是关闭所有反馈；闭环与回放不作中介分解。',
           '所有指标为距离，不能解释为福利。支持和实际半宽不足保留，不追加样本。','',
           '## Fixed-family summary','',
           '|Analysis family|Items|Estimated|Holm rejections|Halfwidth target met|','|---|---:|---:|---:|---:|']
    for key,value in summary['families'].items():
        lines.append('|'+key+'|'+'|'.join(str(value[k]) for k in ('items','estimated','holm_rejections','precision_met'))+'|')
    lines+=['','Complete machine tables are linked from the analysis path recorded in summary.json.','',
            '## Forest plots','']+['- ['+p+']('+p+')' for p in plots]
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    write_json(out/'summary.json',dict(summary,analysis_path=str(analysis),analysis_inventory_hash=digest,plots=plots))
    inventory(out)
    return {'status':'complete','plots':len(plots),'output':str(out)}
