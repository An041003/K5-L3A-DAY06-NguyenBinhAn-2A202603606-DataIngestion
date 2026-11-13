"""CLI for private ingestion, prelocked dev/test benchmark, and shareable aggregates."""
import argparse
import csv
import json
import os
import platform
import statistics
import time
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from dotenv import load_dotenv
from .chunking import fixed_size, by_paragraph
from .embeddings import MODEL, MyEmbedder
from .evaluation import compact, evaluate_query, summarize
from .ingestion import load_pdf
from .io_utils import digest, write_json, write_jsonl, read_jsonl
from .models import Chunk
from .store import PgVectorStore

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT/'.agents'
CONFIG = {'A':{'size':500,'overlap':50,'bounds':'page and source chapter'},
          'B':{'max_size':1100,'packing':'paragraph/line; word fallback','bounds':'page and source chapter'},
          'C':{'reuse':'B','filter':'question-supplied section only'},
          'model':MODEL,'dimensions':768,'metric':'cosine','backend':'PostgreSQL/pgvector exact'}


def now():
    return datetime.now(timezone.utc).isoformat()


def csv_write(path,rows):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    if not rows:
        return
    with path.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def corpus(args):
    return load_pdf(args.pdf,'kpi-v2','kpi-private',args.page_map)


def prepare(args):
    start=time.perf_counter()
    pages=corpus(args)
    if len(pages)!=42 or any(not p.text or len(p.text)<300 for p in pages):
        raise ValueError('Corpus quality gate failed: inspect page classification')
    # Independently inspected selected pages: all contain rules, design, APIs or design trace matrix.
    # p111 is a source-to-design matrix, not a bibliography-only page.
    write_jsonl(PRIVATE/'processed/pages.jsonl',[asdict(p) for p in pages])
    stats={}
    for strategy in ('A','B'):
        chunks=[c for p in pages for c in (fixed_size(p,500,50) if strategy=='A' else by_paragraph(p,1100))]
        if len({c.chunk_id for c in chunks})!=len(chunks) or any(not c.text for c in chunks):
            raise ValueError('Invalid chunks')
        write_jsonl(PRIVATE/f'processed/chunks_{strategy}.jsonl',[asdict(c) for c in chunks])
        lengths=[len(c.text) for c in chunks]
        stats[strategy]={'chunks':len(chunks),'characters':sum(lengths),'min':min(lengths),
            'median':statistics.median(lengths),'max':max(lengths),'unknown_section_chunks':sum(c.metadata['section'] is None for c in chunks)}
    stats['C']={**stats['B'],'reuse':'B exact rows/vectors'}
    manifest={'source_id':'kpi-v2','title':'Private KPI design specification, selected excerpt',
        'source_path_or_url':'.agents/corpus/kpi_ooad_uml_selected_42p_PRIVATE.pdf',
        'license_or_permission':'Local processing and chunk transfer to OpenRouter/Google authorized by user 2026-11-13; redistribution NOT authorized',
        'accessed_at':now(),'sha256':digest(args.pdf.read_bytes()),'physical_pages':len(pages),
        'content_pages':len(pages),'content_original_pages':[p.page for p in pages],
        'page_count_rule':'Inspect real PDF pages; exclude covers/TOC/blank/bibliography. All 42 selected pages contain design/rules/API or source-design trace matrix.',
        'pages':[{'pdf_page':p.metadata['pdf_page'],'original_page':p.page,'characters':len(p.text),
            'classification':'content','warnings':p.metadata['warnings']} for p in pages],
        'characters':sum(len(p.text) for p in pages),'token_count':'Measured by provider usage at embedding time; no local tokenizer asserted',
        'metadata':'section is explicit chapter heading plus propagation across contiguous original pages; split at chapter changes; reset across gaps',
        'public_reproduction':'PENDING_AUTHORIZED_CORPUS_ACCESS; full source, draft gold and text traces local only'}
    write_json(ROOT/'data/manifest.json',manifest)
    stats['prepare_seconds']=time.perf_counter()-start
    write_json(ROOT/'results/chunk_statistics.json',stats)
    write_json(PRIVATE/'config.json',CONFIG)
    # Same ten source positions locked before search; source offsets never chosen from retrieval scores.
    positions=[{'original_page':p.page,'offset':min(200,len(p.text)-1)} for p in pages[:10]]
    write_json(PRIVATE/'coherence_positions.json',positions)
    write_json(PRIVATE/'preparation.json',{'at':now(),'config':CONFIG,'sha256':manifest['sha256'],'source_positions':positions})
    print(json.dumps({'pages':len(pages),'characters':manifest['characters'],'chunk_stats':stats},ensure_ascii=False))


def load_chunks(strategy):
    return [Chunk(**r) for r in read_jsonl(PRIVATE/f'processed/chunks_{strategy}.jsonl')]


def lock(args):
    path=PRIVATE/'benchmark/questions.jsonl'
    questions=read_jsonl(path)
    pages={p.page:p for p in corpus(args)}
    if len(questions)<20 or sum(q['split']=='dev' for q in questions)<15 or sum(q['split']=='test' for q in questions)<5:
        raise ValueError('Need >=20 questions, >=15 dev and >=5 test')
    if len({q['id'] for q in questions})!=len(questions):
        raise ValueError('Duplicate question IDs')
    if sum(bool(q.get('filter')) for q in questions)<3 or not any(q.get('filter') and q['split']=='test' for q in questions):
        raise ValueError('Need three metadata questions including test')
    for q in questions:
        p=pages[q['gold_page']]
        if q['gold_source_id']!='kpi-v2' or compact(q['evidence_quote']) not in compact(p.text):
            raise ValueError('Gold quote mismatch: '+q['id'])
        if q.get('filter'):
            if set(q['filter'])!={'section'} or q['filter']['section'] not in q['question']:
                raise ValueError('Filter must be supplied explicitly in question: '+q['id'])
            if not any(s['section']==q['filter']['section'] and compact(q['evidence_quote']) in compact(p.text[s['start']:s['end']]) for s in p.metadata['section_spans']):
                raise ValueError('Gold evidence contradicts filter: '+q['id'])
    frozen={'at':now(),'benchmark_sha256':digest(path.read_bytes()),'config':CONFIG,
        'chunks_sha256':{s:digest((PRIVATE/f'processed/chunks_{s}.jsonl').read_bytes()) for s in ('A','B')},
        'positions_sha256':digest((PRIVATE/'coherence_positions.json').read_bytes()),
        'selection_criteria':'Max dev complete-quote Evidence Hit@3, then Hit@1, then fewer stored chunks, then strategy alphabetically. Human quality metrics remain PENDING; decision provisional.',
        'gold_status':'PENDING_HUMAN','split_method':'Author fixed dev on early policy/design topics, test on API conventions and operations; same-document topic overlap remains.',
        'questions':len(questions),'dev':sum(q['split']=='dev' for q in questions),'test':sum(q['split']=='test' for q in questions)}
    target=PRIVATE/'benchmark/lock.json'
    if target.exists():
        old=json.loads(target.read_text(encoding='utf-8'))
        if old['benchmark_sha256']!=frozen['benchmark_sha256'] or old['config']!=CONFIG or old['chunks_sha256']!=frozen['chunks_sha256']:
            raise ValueError('Existing experiment lock differs; do not overwrite or retune test')
        print('Existing benchmark lock verified')
        return
    write_json(target,frozen)
    print(f"Locked {len(questions)} questions before retrieval; human gold approval PENDING")


def check_lock():
    frozen=json.loads((PRIVATE/'benchmark/lock.json').read_text(encoding='utf-8'))
    if frozen['benchmark_sha256']!=digest((PRIVATE/'benchmark/questions.jsonl').read_bytes()) or frozen['config']!=CONFIG:
        raise ValueError('Benchmark/config changed after lock')
    for s in ('A','B'):
        if frozen['chunks_sha256'][s]!=digest((PRIVATE/f'processed/chunks_{s}.jsonl').read_bytes()):
            raise ValueError('Corpus chunks changed after lock')
    if frozen['positions_sha256']!=digest((PRIVATE/'coherence_positions.json').read_bytes()):
        raise ValueError('Audit source positions changed after lock')
    return frozen


def provider(args):
    if not args.allow_external:
        raise RuntimeError('BLOCKED:DATA_RIGHTS_API; explicit --allow-external required after authorization')
    return MyEmbedder(os.getenv('EMBEDDING_MODEL',MODEL),PRIVATE/'cache/embeddings')


def store():
    if not os.getenv('DATABASE_URL'):
        raise RuntimeError('BLOCKED:DATABASE_URL')
    return PgVectorStore(os.environ['DATABASE_URL'],768)


def ingest(args):
    check_lock()
    db=store()
    db.create_schema()
    embedder=provider(args)
    measurements={}
    for strategy in ('A','B'):
        start=time.perf_counter()
        chunks=load_chunks(strategy)
        vectors=embedder.embed_documents([c.text for c in chunks])
        embedded=time.perf_counter()
        db.upsert(strategy,chunks,vectors)
        first=db.snapshot(strategy)
        first_finished=time.perf_counter()
        db.upsert(strategy,chunks,vectors)
        second=db.snapshot(strategy)
        if first!=second or len(first)!=len(chunks):
            raise ValueError('Idempotency gate failed')
        measurements[strategy]={'chunks':len(first),'embedding_seconds':embedded-start,
            'first_write_seconds':first_finished-embedded,'ingest_seconds':first_finished-start,
            'second_write_seconds':time.perf_counter()-first_finished,'idempotent':True,
            'ids_sha256':digest(json.dumps(first))}
    measurements['C']={'reuse':'B exact persisted rows and vectors','extra_document_embedding_requests':0}
    measurements['backend']=db.versions()
    measurements['at']=now()
    if not (ROOT/'results/ingest_statistics.json').exists():
        write_json(ROOT/'results/ingest_statistics.json',measurements)
    write_json(ROOT/'results/ingest_latest.json',measurements)
    print(json.dumps(measurements))


def audit(traces):
    rows=[]
    for strategy in ('A','B','C'):
        chunks=load_chunks('B' if strategy=='C' else strategy)
        for i,position in enumerate(json.loads((PRIVATE/'coherence_positions.json').read_text(encoding='utf-8')),1):
            candidates=[c for c in chunks if c.page==position['original_page'] and c.metadata['start']<=position['offset']<c.metadata['end']]
            if not candidates:
                raise ValueError('Audit position has no covering chunk')
            c=sorted(candidates,key=lambda c:c.metadata['start'])[0]
            rows.append({'kind':'coherence','id':f'POS{i:02}','strategy':strategy,'rank':'','page':c.page,
                'chunk_id':c.chunk_id,'text':c.text,'metadata':json.dumps(c.metadata,ensure_ascii=False),
                'score':'PENDING_HUMAN','reason':'PENDING_HUMAN','human_verified':False})
    for t in traces:
        if t['split']!='test':
            continue
        for rank,h in enumerate(t['hits'],1):
            rows.append({'kind':'metadata','id':t['id'],'strategy':t['strategy'],'rank':rank,'page':h['page'],
                'chunk_id':h['chunk_id'],'text':h['text'],'metadata':json.dumps(h['metadata'],ensure_ascii=False),
                'score':'PENDING_HUMAN','reason':'PENDING_HUMAN','human_verified':False})
        rows.append({'kind':'grounding','id':t['id'],'strategy':t['strategy'],'rank':'top3','page':'see trace',
            'chunk_id':'see trace','text':t['question'],'metadata':json.dumps(t['filter_applied'],ensure_ascii=False),
            'score':'PENDING_HUMAN','reason':'PENDING_HUMAN','human_verified':False})
        for rank in range(len(t['hits'])+1,4):
            rows.append({'kind':'retrieval_shortfall','id':t['id'],'strategy':t['strategy'],
                'rank':rank,'page':'NOT_RETURNED','chunk_id':'NOT_RETURNED','text':'NOT_RETURNED',
                'metadata':'{}','score':'NOT_APPLICABLE',
                'reason':'Fewer than three eligible results; no duplicate or invented result added',
                'human_verified':False})
    target=PRIVATE/'review/manual_audit_template.csv'
    if target.exists():
        with target.open(encoding='utf-8',newline='') as f:
            existing=list(csv.DictReader(f))
        if any(r['score'] not in ('PENDING_HUMAN','NOT_APPLICABLE') or r['human_verified'].lower()=='true' for r in existing):
            raise ValueError('Existing human review detected; preserve it rather than overwrite')
    csv_write(target,rows)


def benchmark(args):
    frozen=check_lock()
    if frozen['gold_status']!='VERIFIED_HUMAN' and not args.allow_unverified:
        raise RuntimeError('Gold PENDING_HUMAN: --allow-unverified permits explicitly provisional measurements only')
    embedder,db=provider(args),store()
    all_questions=read_jsonl(PRIVATE/'benchmark/questions.jsonl')
    traces=[]
    for split in ('dev','test'):
        if split=='test':
            dev_metrics=summarize(traces)
            counts={s:len(db.snapshot('B' if s=='C' else s)) for s in ('A','B','C')}
            best=sorted(dev_metrics,key=lambda r:(-r['evidence_hit_at_3'],-r['hit_at_1'],counts[r['strategy']],r['strategy']))[0]['strategy']
            write_json(PRIVATE/'results/selection_before_test.json',{'at':now(),'selected':best,
                'dev_metrics':dev_metrics,'benchmark_sha256':frozen['benchmark_sha256'],'test_retrieval_started':False,'status':'PROVISIONAL_PENDING_HUMAN'})
        for q in [q for q in all_questions if q['split']==split]:
            query_start=time.perf_counter()
            vector=embedder.embed_query(q['question'])
            query_seconds=time.perf_counter()-query_start
            for strategy in ('A','B','C'):
                filters=q.get('filter') if strategy=='C' else None
                start=time.perf_counter()
                hits=db.search(strategy,vector,3,filters)
                trace={'id':q['id'],'split':split,'strategy':strategy,'question':q['question'],
                    'filter_input':q.get('filter'),'filter_applied':filters,'hits':hits,
                    'evaluation':evaluate_query(q,hits),'query_embedding_seconds_shared':query_seconds,
                    'search_seconds':time.perf_counter()-start,'at':now(),
                    'gold_source_id':q['gold_source_id'],'gold_page':q['gold_page'],'evidence_quote':q['evidence_quote']}
                traces.append(trace)
            # Crash-safe per-question progress; entire text stays in private directory.
            write_jsonl(PRIVATE/'results/traces.jsonl',traces)
            print(f"Retrieved {q['id']} ({split}) A/B/C",flush=True)
    rows=summarize(traces)
    csv_write(ROOT/'results/metrics.csv',rows)
    write_json(PRIVATE/'results/failures.json',[t for t in traces if not t['evaluation']['evidence_hit_at_3']])
    audit(traces)
    compliance=[]
    for s in ('A','B','C'):
        filtered=[t for t in traces if t['strategy']==s and t['split']=='test' and t['filter_input']]
        compliance.append({'strategy':s,'test_filter_queries':len(filtered),
            'returned_hits_match_requested_scope':sum(bool(t['hits']) and all(h['metadata']['section']==t['filter_input']['section'] for h in t['hits']) for t in filtered),
            'full_top3_matches_requested_scope':sum(len(t['hits'])==3 and all(h['metadata']['section']==t['filter_input']['section'] for h in t['hits']) for t in filtered),
            'queries_with_three_results':sum(len(t['hits'])==3 for t in filtered),
            'note':'Scope correctness and top-3 completeness reported separately; human metadata accuracy PENDING; A/B do not apply filters'})
    write_json(ROOT/'results/filter_compliance.json',compliance)
    write_json(ROOT/'results/run_environment.json',{'at':now(),'python':platform.python_version(),
        'packages':{p:version(p) for p in ['psycopg','pypdf','python-dotenv','requests','PyMuPDF']},
        'backend':db.versions(),'config':CONFIG,'benchmark_sha256':frozen['benchmark_sha256'],
        'gold_status':'PENDING_HUMAN','manual_audit':'PENDING_HUMAN','private_trace_records':len(traces),
        'top3_records':sum(len(t['hits']) for t in traces)})
    usage=read_jsonl(PRIVATE/'cache/api_usage.jsonl')
    tokens=[u['usage'].get('prompt_tokens') for u in usage if u.get('usage')]
    costs=[u['usage'].get('cost') for u in usage if u.get('usage')]
    write_json(ROOT/'results/api_usage_summary.json',{'successful_batches':len(usage),'inputs':sum(u['inputs'] for u in usage),
        'measured_prompt_tokens':sum(t for t in tokens if t is not None) if len(tokens)==len(usage) and all(t is not None for t in tokens) else None,
        'provider_reported_cost_usd':sum(c for c in costs if c is not None) if len(costs)==len(usage) and all(c is not None for c in costs) else None,
        'estimated_cost_usd':sum(t for t in tokens if t is not None)*0.20/1e6 if len(tokens)==len(usage) and all(t is not None for t in tokens) else None,
        'estimate_rate_usd_per_million':0.20,'pricing_checked_date':'2026-11-13',
        'scope':'successful pipeline document and query requests; excludes separate public smoke test (2 tokens); cache hits not rebilled; uncertain failed request charges unknown'})
    print(json.dumps(rows))


def main():
    load_dotenv(ROOT/'starter/.env')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['prepare','lock','ingest','benchmark','report','all'],nargs='?',default='all')
    parser.add_argument('--pdf',type=Path,default=PRIVATE/'corpus/kpi_ooad_uml_selected_42p_PRIVATE.pdf')
    parser.add_argument('--page-map',type=Path,default=PRIVATE/'corpus/page_map.csv')
    parser.add_argument('--allow-external',action='store_true')
    parser.add_argument('--allow-unverified',action='store_true')
    args=parser.parse_args()
    for stage in (['prepare','lock','ingest','benchmark','report'] if args.stage=='all' else [args.stage]):
        if stage=='report':
            from .reporting import generate
            generate(ROOT)
        else:
            globals()[stage](args)


if __name__=='__main__':
    main()
