"""Read-only experiment/review validation and safe local submission readiness.

No embedding provider calls, ingestion, vector search, approval inference or push.
Run from starter: .venv/Scripts/python -m src.submission
"""
import csv
import json
import math
import re
import subprocess
from pathlib import Path
from dotenv import dotenv_values
from .evaluation import summarize
from .human_review import aggregate_human_review
from .io_utils import digest, read_jsonl, write_json

ROOT=Path(__file__).resolve().parents[2]
EXPECTED={('A','dev'):(15,6,11),('B','dev'):(15,7,12),('C','dev'):(15,8,12),
          ('A','test'):(5,2,2),('B','test'):(5,2,3),('C','test'):(5,2,3)}


def _json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def validate(root=ROOT):
    private=root/'.agents'
    human=aggregate_human_review(root)
    if not human or human['status']!='FINAL_REVIEW_ACCEPTED_WITH_LIMITATIONS':
        raise ValueError('Final user decisions unavailable or inconsistent')
    receipt=_json(private/'review/finalization_receipt.json')
    for name,value in receipt['protected_sha256'].items():
        if digest((root/name).read_bytes())!=value:
            raise ValueError('Original experiment artifact changed: '+name)
    questions=read_jsonl(private/'benchmark/questions.jsonl')
    if len(questions)!=20 or sum(q['split']=='dev' for q in questions)!=15 or sum(q['split']=='test' for q in questions)!=5:
        raise ValueError('Benchmark split/count mismatch')
    if sum(bool(q['filter']) for q in questions)<3 or not any(q['filter'] and q['split']=='test' for q in questions):
        raise ValueError('Benchmark metadata questions missing')
    manifest=_json(root/'data/manifest.json')
    pages=read_jsonl(private/'processed/pages.jsonl')
    if manifest['physical_pages']!=42 or manifest['content_pages']!=42 or len(pages)!=42 or manifest['characters']!=sum(len(p['text']) for p in pages):
        raise ValueError('Manifest/corpus statistics mismatch')
    if digest((private/'corpus/kpi_ooad_uml_selected_42p_PRIVATE.pdf').read_bytes())!=manifest['sha256'] or not manifest['license_or_permission']:
        raise ValueError('Manifest source hash or permission missing')
    lock=_json(private/'benchmark/lock.json')
    if digest((private/'benchmark/questions.jsonl').read_bytes())!=lock['benchmark_sha256']:
        raise ValueError('Frozen benchmark hash mismatch')
    config=_json(private/'config.json')
    if config!=lock['config'] or config['model']!='google/gemini-embedding-2' or config['dimensions']!=768:
        raise ValueError('Locked model/dimensions/config mismatch')
    if _json(private/'results/selection_before_test.json')['selected']!='C':
        raise ValueError('Dev selection changed')
    traces=read_jsonl(private/'results/traces.jsonl')
    by_id={q['id']:q for q in questions}
    if len(traces)!=60 or len({(t['id'],t['strategy']) for t in traces})!=60:
        raise ValueError('Trace population mismatch')
    for t in traces:
        q=by_id[t['id']]
        if t['split']!=q['split'] or t['question']!=q['question']:
            raise ValueError('Trace/benchmark identity mismatch')
        for h in t['hits']:
            if not math.isfinite(h['score']) or not -1.000001<=h['score']<=1.000001:
                raise ValueError('Invalid cosine score')
    if sum(len(t['hits']) for t in traces)!=179:
        raise ValueError('Unexpected result count; do not invent third C/T05 hit')
    with (root/'results/metrics.csv').open(encoding='utf-8',newline='') as f:
        metrics=list(csv.DictReader(f))
    aggregated={(r['strategy'],r['split']):r for r in summarize(traces)}
    if len(metrics)!=6:
        raise ValueError('Expected six strategy/split rows')
    for r in metrics:
        key=(r['strategy'],r['split'])
        if tuple(int(r[k]) for k in ('n','hit_at_1_n','evidence_hit_at_3_n'))!=EXPECTED[key]:
            raise ValueError('Retrieval counts differ from frozen user-specified results')
        a=aggregated[key]
        if any(float(r[k])!=a[k] for k in ('n','hit_at_1_n','evidence_hit_at_3_n','hit_at_1','evidence_hit_at_3')):
            raise ValueError('Metrics differ from stored trace evaluations')
    with (root/'artifacts/experiment_log.csv').open(encoding='utf-8',newline='') as f:
        experiments=list(csv.DictReader(f))
    if len(experiments)!=3:
        raise ValueError('Experiment log strategy count mismatch')
    for row in experiments:
        s=row['strategy']
        for split in ('dev','test'):
            n,one,three=EXPECTED[(s,split)]
            if row[split+'_hit1']!=f'{one}/{n}' or row[split+'_hit3']!=f'{three}/{n}':
                raise ValueError('Experiment log/metric mismatch')
    for strategy in ('A','B','C'):
        c,g=human['coherence'][strategy],human['grounding'][strategy]
        if (c['n'],c['mean'])!=(10,1.0 if strategy=='A' else 1.5) or (g['n'],g['mean'])!=(5,1.8):
            raise ValueError('Confirmed manual summaries changed')
    usage=_json(root/'results/api_usage_summary.json')
    ledger=read_jsonl(private/'cache/api_usage.jsonl')
    if sum(r['usage']['prompt_tokens'] for r in ledger)!=usage['measured_prompt_tokens'] or not math.isclose(sum(r['usage']['cost'] for r in ledger),usage['provider_reported_cost_usd'],abs_tol=1e-12):
        raise ValueError('Usage summary/ledger mismatch')
    report=(root/'report/individual/2A202603606_NguyenBinhAn.md').read_text(encoding='utf-8')
    if 'USER_ACCEPTED_TECHNICAL_VERIFICATION' not in report or 'D10/trang106 đã được xác nhận' not in report:
        raise ValueError('Final report misses acceptance provenance or alternate limit')
    for r in metrics:
        if f"{r['hit_at_1_n']}/{r['n']}" not in report or f"{r['evidence_hit_at_3_n']}/{r['n']}" not in report:
            raise ValueError('Report/metrics disagree')
    tracked=subprocess.check_output(['git','ls-files'],cwd=root,text=True).splitlines()
    staged=subprocess.check_output(['git','diff','--cached','--name-only'],cwd=root,text=True).splitlines()
    extras=['data/ACCESS.md','starter/src/submission.py','results/submission_readiness.json']
    public_paths=sorted(set(tracked+staged+extras))
    denied=[]
    for name in public_paths:
        parts=Path(name).parts
        if any(p in ('.agents','.codex_private','.venv','__pycache__') for p in parts) or Path(name).name in ('AGENTS.md','Agents.md','Agent.md','Architecture.md','.env') or name.startswith(('data/raw/','data/processed/')):
            denied.append(name)
    if denied:
        raise ValueError('Private/secret paths tracked or staged: '+', '.join(denied))
    values=dotenv_values(root/'starter/.env')
    secrets=[v for k,v in values.items() if v and ('KEY' in k or 'TOKEN' in k or 'SECRET' in k)]
    snippets=[q['question'] for q in questions]+[q['evidence_quote'] for q in questions]
    snippets += [c['text'] for c in read_jsonl(private/'processed/chunks_B.jsonl') if len(c['text'])>100]
    scanned=0
    for name in public_paths:
        path=root/name
        if not path.is_file():
            if name=='results/submission_readiness.json': continue
            raise ValueError('Expected submission file missing: '+name)
        try: text=path.read_text(encoding='utf-8-sig')
        except UnicodeDecodeError: continue
        if any(s in text for s in secrets) or re.search(r'sk-or-v1-[A-Za-z0-9]{12,}',text):
            raise ValueError('Secret detected in '+name)
        # Check full source excerpts, not just file names; public code/schema keys are allowed.
        if any(s in text for s in snippets):
            raise ValueError('Private question/evidence/chunk found in '+name)
        scanned+=1
    for label in re.findall(r'\]\(([^)]+)\)',(root/'README.md').read_text(encoding='utf-8')):
        if not label.startswith(('http:','https:','#')) and not (root/label.split('#')[0]).exists():
            if label!='results/submission_readiness.json':
                raise ValueError('Broken README link: '+label)
    return {'status':'READY','scope':'Safe local submission preparation; not published/pushed or delivered',
        'blockers':[],'new_embedding_calls':0,'benchmark_rerun':False,'retroactive_rescoring':False,
        'checks':{'protected_original_artifacts':len(receipt['protected_sha256']),'all_protected_hashes_unchanged':True,
                  'report_metric_trace_review_consistent':True,'trace_queries':60,'returned_chunks':179,
                  'gold_confirmed':20,'coherence_confirmed':30,'grounding_confirmed':15,
                  'metadata_user_accepted_technical':44,'metadata_independently_human_scored':False,
                  'extraction_warning_pages_retained':29,'tracked_staged_files_privacy_scanned':scanned,
                  'usage_ledger_consistent':True,'readme_links_valid':True,'manifest_corpus_consistent':True,
                  'experiment_log_metrics_consistent':True},
        'reporting_source_sha256_utf8_lf':{str(p.relative_to(root)).replace('\\','/'):digest(p.read_text(encoding='utf-8')) for p in (root/'starter/src').glob('*.py')},
        'benchmark_sha256':lock['benchmark_sha256'],'selected_strategy':'C',
        'rubric_evidence':{'corpus_processing':'PRESENT','three_strategies_and_storage':'PRESENT',
            'benchmark_retrieval':'PRESENT_WITH_PRIVATE_ACCESS','five_evaluation_aspects':'PRESENT_WITH_METADATA_METHOD_LIMITATION',
            'reproducibility_and_report':'PRESENT_WITH_RESTRICTED_CORPUS_ACCESS'},
        'limitations':['Metadata accepted technical verification, not independent manual per-chunk scoring; rubric credit is grader decision',
            '29 extraction-warning pages retained, not exhaustively human-verified','Public checkout lacks restricted source/gold/full traces',
            'D10/page106 source passage confirmed as equivalent; not added to frozen official gold and no retrospective rescoring; other candidates qualitative only','Test set has only five questions'],
        'reviewer_access':'User authorized private source viewing; see data/ACCESS.md',
        'source_gold_trace_publication_authorized':False,'push_authorized':False,
        'final_report':'report/individual/2A202603606_NguyenBinhAn.md'}


def main():
    try:
        result=validate()
    except (ValueError,KeyError,FileNotFoundError) as exc:
        result={'status':'BLOCKED','scope':'Local submission readiness','blockers':[str(exc)],'new_embedding_calls':0}
    write_json(ROOT/'results/submission_readiness.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if result['status']!='READY': raise SystemExit(1)


if __name__=='__main__':
    main()
