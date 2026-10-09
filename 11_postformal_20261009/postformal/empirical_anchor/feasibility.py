"""Rebuild a four-issue feasibility audit from archived public source bytes."""
import argparse
import csv
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
MONTHS = {name:i for i,name in enumerate(('Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'),1)}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.paragraphs = [], []
        self.row = self.cell = self.paragraph = None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr': self.row = []
        if tag in ('td','th'): self.cell = []
        if tag == 'p': self.paragraph = []

    def handle_data(self, data):
        if self.cell is not None: self.cell.append(data)
        if self.paragraph is not None: self.paragraph.append(data)

    def handle_endtag(self, tag):
        if tag in ('td','th') and self.cell is not None:
            if self.row is not None: self.row.append(' '.join(' '.join(self.cell).split()))
            self.cell = None
        if tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        if tag == 'p' and self.paragraph is not None:
            self.paragraphs.append(' '.join(' '.join(self.paragraph).split()))
            self.paragraph = None


def sources():
    result = {}
    for manifest in sorted((ROOT/'raw').glob('*/acquisition_manifest.json')):
        for record in json.loads(manifest.read_text(encoding='utf-8'))['records']:
            if record['status'] != 'downloaded': continue
            path = ROOT / record['body_path']
            if digest(path) != record['sha256'] or path.stat().st_size != record['bytes']:
                raise ValueError('Archived source identity mismatch: '+str(path))
            result[record['id']] = record
    return result


def page(record):
    parsed = Page()
    parsed.feed((ROOT/record['body_path']).read_text(encoding='utf-8'))
    return parsed


def csv_write(path, rows):
    with path.open('x',encoding='utf-8',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build(output):
    if output.exists(): raise ValueError('Refusing to overwrite '+str(output))
    src = sources()
    spec = json.loads((ROOT/'protocol/development_queries.json').read_text(encoding='utf-8'))
    history = src['ipsos_history']
    header = None
    monthly, coverage = {}, []
    for row in page(history).rows:
        if row and re.fullmatch('20[0-9]{2}',row[0]):
            header = row
            continue
        if not row or not re.fullmatch('[A-Z][a-z]{2}-[0-9]{2}',row[0]): continue
        label, year = row[0].split('-')
        month = f'20{year}-{MONTHS[label]:02d}'
        if month in monthly: raise ValueError('Duplicate survey month '+month)
        valid = header is not None and len(row) == len(header)
        monthly[month] = dict(zip(header,row)) if valid else None
        coverage.append({'month':month,'header_columns':len(header),'row_columns':len(row),
                         'shape_valid':valid,'source_sha256':history['sha256']})
    rows, methods = [], []
    for month in range(1,7):
        date = f'2018-{month:02d}'
        label = list(MONTHS)[month-1].lower()
        record = src['ipsos_'+label+'2018']
        text = ' '.join(page(record).paragraphs)
        sample = re.search(r'sample of ([0-9,]+) adults aged 18\+',text)
        fieldwork = re.search(r'between ([0-9]+) and ([0-9]+) ([A-Za-z]+) 2018',text)
        if not sample or not fieldwork or 'Great Britain' not in text or 'face-to-face' not in text:
            raise ValueError('Unresolved development survey methods '+date)
        method = {'month':date,'n':int(sample[1].replace(',','')),'geography':'Great Britain',
                  'age_min':18,'sampling':'quota','mode':'face_to_face_in_home','weighted':True,
                  'response':'spontaneous_unprompted_multiple_mentions',
                  'fieldwork_start':f'{date}-{int(fieldwork[1]):02d}',
                  'fieldwork_end':f'{date}-{int(fieldwork[2]):02d}',
                  'source_url':record['final_url'],'source_sha256':record['sha256']}
        methods.append(method)
        for topic in spec['topics']:
            token = monthly[date][topic['ipsos_code']]
            if not token.isdigit(): raise ValueError('Noninteger development value; do not coerce missing to zero')
            value = int(token)
            if not 0 <= value <= 100: raise ValueError('Invalid proportion')
            rows.append({'month':date,'issue':topic['id'],'ipsos_code':topic['ipsos_code'],
                         'mention_percent':value,'n':method['n'],'source_url':history['final_url'],
                         'source_sha256':history['sha256'],'google_query':topic['google_query'],
                         'digital_value':'','digital_status':'not_acquired_http_429',
                         'semantic_limit':topic['semantic_limit']})
    missing = [f'{y}-{m:02d}' for y in range(2018,2024) for m in range(1,13)
               if f'{y}-{m:02d}' <= max(monthly) and f'{y}-{m:02d}' not in monthly]
    output.mkdir(parents=True)
    csv_write(output/'development_survey.csv',rows)
    csv_write(output/'survey_methods.csv',methods)
    csv_write(output/'history_coverage.csv',coverage)
    summary = {'status':'feasibility_incomplete','source_bytes_validated':True,'survey_development_rows':len(rows),
               'paired_rows':0,'distance_metrics_computed':False,'full_panel_protocol_frozen':False,
               'history_first_month':min(monthly),'history_last_month':max(monthly),'history_month_rows':len(monthly),
               'history_missing_months_within_span':missing,
               'history_malformed_rows':[r['month'] for r in coverage if not r['shape_valid']],
               'issues':[t['id'] for t in spec['topics']],
               'blockers':['Trends first comparison request HTTP 429; bridge and repeated downloads not executed',
                           'Survey Great Britain vs planned Trends GB=United Kingdom: geographic mismatch unresolved',
                           'Broad survey categories vs English search terms: semantic mapping not frozen',
                           'No validated common scale or survey joint-response microdata/noise null',
                           'Historical HTML table does not cover the full requested 2018-to-current interval'],
               'scope':'Only the six-month four-issue development slice is extracted; history dates audited without full-panel outcome analysis',
               'script_sha256':digest(Path(__file__)),
               'protocol_sha256':digest(ROOT/'protocol/development_queries.json'),
               'sources':{k:{f:v[f] for f in ('final_url','body_path','sha256','finished_at_utc')} for k,v in src.items()}}
    (output/'validation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    text = f'''# 英国经验锚点可行性核查（2026-10-08）

结论：调查侧开发样本可以重建，完整配对分析尚不能冻结。已从留存的 Ipsos 官方 HTML 提取2018年1–6月经济、健康、移民、犯罪4项共24个调查比例；数字侧0个配对值，没有计算TV、JSD、秩相关或噪声显著性。

历史表实际识别 {len(monthly)} 个月度行，范围 {min(monthly)} 至 {max(monthly)}。范围内未列月份为 {', '.join(missing) or '无'}；这只说明当前归档表的覆盖，不能推断那些月份的调查不存在。更晚数据需要另行搜集与口径核对，不能把历史入口名称当作完整数据。见[官方历史入口]({history['final_url']})和 `history_coverage.csv`。

六个月调查均为Great Britain、18岁及以上、配额样本、入户面对面访问，回答为未提示的议题提及，比例经过加权。样本量和实际访问窗见 `survey_methods.csv`；月度搜索窗口与调查访问窗并不相同。2020年4月的官方方法说明记录了由面对面改为电话的变化，后续长面板必须显式处理模式断点，不能假定2018口径贯穿全期。见[2020年4月方法说明]({src['ipsos_apr2020']['final_url']})。

现有 `development_queries.json` 在取得搜索值前已指定四个英文搜索词及共同锚点economy。首次四词请求的归档状态为HTTP 429，按既有停止规则没有继续桥接或重复请求，因此共同尺度与重复性均未通过实测。Google说明页成功取得不等于取得Trends时间序列。查询码GB的英国范围与调查Great Britain尚未匹配；广义议题类别与单个搜索词也不是一一等价。候选NHS可能含服务查询，crime可能含娱乐内容，这些需在完整分析前定规则。

调查提及率是多选边际比例，不能将这些比例当作互斥多项抽样，也不能从汇总数伪造个体bootstrap。当前没有可验收的个体联合响应/权重数据和数字重复样本，无法判断差距是否超出测量噪声。没有配对值时，不将缺失填零或生成差距图。

下一步依次是解决合法取得Trends开发导出及地理匹配、验收共同锚点/重复性、冻结议题映射和噪声/缺失规则，再考虑完整面板。当前保留未通过状态；模拟补充研究可独立推进。

复建命令（从ABM_JASSS目录运行，输出必须为新目录）：

```text
python -B postformal/empirical_anchor/feasibility.py postformal/empirical_anchor/processed/another_feasibility_audit
```

`validation.json`记录所有来源URL、原始字节SHA256和获取时间，`artifact_hashes.json`绑定本次产物。首次源下载的网络失败和后续成功获取均留在raw目录。
'''
    (output/'report_zh.md').write_text(text,encoding='utf-8')
    hashes={p.name:digest(p) for p in sorted(output.iterdir()) if p.is_file()}
    (output/'artifact_hashes.json').write_text(json.dumps(hashes,indent=2)+'\n',encoding='utf-8')
    return {k:v for k,v in summary.items() if k!='sources'}


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(build(args.output),ensure_ascii=False))
