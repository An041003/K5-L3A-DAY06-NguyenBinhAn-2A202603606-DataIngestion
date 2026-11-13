"""Validate private user-confirmed labels and export only aggregate review results.

Frozen benchmark/trace flags describe the original run. Current human approvals
are a separate overlay; this module never rescales retrieval or edits gold.
"""
import csv
import json
from collections import Counter
from .io_utils import digest, read_jsonl


def _csv(path):
    with path.open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))


def aggregate_human_review(root):
    private = root/'.agents'
    review = private/'review'
    packet = review/'human_approved_labels.json'
    if not packet.exists():
        return None
    labels = json.loads(packet.read_text(encoding='utf-8'))
    questions = {q['id']:q for q in read_jsonl(private/'benchmark/questions.jsonl')}
    gold_rows = _csv(review/'gold_review.csv')
    audit_rows = _csv(review/'manual_audit_template.csv')
    gold = {r['id']:r for r in gold_rows}
    audit = {(r['kind'],r['id'],r['strategy'],r['rank']):r for r in audit_rows}
    if len(gold)!=len(gold_rows) or len(audit)!=len(audit_rows):
        raise ValueError('Duplicate review keys')
    approved_gold = labels['gold_evidence']
    if {r['id'] for r in approved_gold}!=set(questions) or len(approved_gold)!=len(questions):
        raise ValueError('Gold approval IDs must match frozen benchmark')
    for approved in approved_gold:
        r,q = gold[approved['id']],questions[approved['id']]
        if approved['status']!='confirmed' or approved['evidence_supported'] is not True:
            raise ValueError('Gold approval not confirmed')
        if r['human_verified'].lower()!='true' or r['evidence_sufficient']!='YES_USER_CONFIRMED':
            raise ValueError('Gold CSV conflicts with approval packet')
        if any(r[k]!=str(q[qk]) for k,qk in [('split','split'),('question','question'),('expected_answer','expected_answer'),('original_page','gold_page'),('pdf_page','pdf_page'),('evidence_quote','evidence_quote')]):
            raise ValueError('Gold review changed frozen question/evidence')
    summary = {'status':'PARTIAL_HUMAN_REVIEW','confirmation_date':labels['confirmation_date'],
        'label_origin':'USER_CONFIRMED','approval_packet_sha256':digest(packet.read_bytes()),
        'benchmark_sha256':digest((private/'benchmark/questions.jsonl').read_bytes()),
        'gold':{'confirmed':len(approved_gold),'total':len(questions),'alternatives_status':'PENDING_HUMAN'},
        'reason_origin':'Scores/evidence support confirmed by user; AI-proposed explanations are not user-authored or human-confirmed explanations'}
    for kind in ('coherence','grounding'):
        summary[kind] = {}
        approved = labels[kind]
        if any(r['strategy'] not in ('A','B','C') for r in approved):
            raise ValueError('Unknown strategy in human approvals')
        if len({(r['id'],r['strategy']) for r in approved})!=len(approved):
            raise ValueError('Duplicate approval labels')
        for strategy in ('A','B','C'):
            group = [r for r in approved if r['strategy']==strategy]
            expected_ids = {f'POS{i:02}' for i in range(1,11)} if kind=='coherence' else {q['id'] for q in questions.values() if q['split']=='test'}
            if {r['id'] for r in group}!=expected_ids:
                raise ValueError('Incomplete human review sample')
            scores = []
            for approved_row in group:
                rank = '' if kind=='coherence' else 'top3'
                r = audit[(kind,approved_row['id'],strategy,rank)]
                score = approved_row['score']
                if isinstance(score,bool) or score not in (0,1,2) or approved_row['max_score']!=2 or approved_row['status']!='confirmed':
                    raise ValueError('Invalid human score')
                if r['human_verified'].lower()!='true' or int(r['score'])!=score or r['label_origin']!='USER_CONFIRMED':
                    raise ValueError('Audit CSV conflicts with approved score')
                scores.append(score)
            distribution = Counter(scores)
            summary[kind][strategy] = {'n':len(scores),'sum':sum(scores),'mean':sum(scores)/len(scores),
                'max_score':2,'distribution':{str(i):distribution[i] for i in (0,1,2)},'status':'USER_CONFIRMED'}
    metadata = [r for r in audit_rows if r['kind']=='metadata']
    if any(r['human_verified'].lower()=='true' for r in metadata):
        raise ValueError('Metadata approval absent from this packet; do not infer it')
    technical_path = review/'metadata_technical_summary.json'
    technical = json.loads(technical_path.read_text(encoding='utf-8')) if technical_path.exists() else {}
    extraction_path = review/'extraction_technical_summary.json'
    extraction = json.loads(extraction_path.read_text(encoding='utf-8')) if extraction_path.exists() else {}
    summary['metadata'] = {'rows':len(metadata),'human_confirmed':0,'status':'PENDING_HUMAN',
        'technical_source_trace_matches':technical.get('source_trace_checks_pass'),
        'technical_database_matches':technical.get('database_matches')}
    summary['gold_alternatives'] = {'questions_pending':len(questions),'human_confirmed':0,'status':'PENDING_HUMAN'}
    summary['extraction'] = {'warning_pages':extraction.get('warning_pages_checked'),'human_confirmed':0,
        'ai_visual_reviewed_original_pages':extraction.get('ai_visual_reviewed_original_pages',[]),'status':'PENDING_HUMAN'}
    summary['retrieval_policy'] = 'Original exact-quote metrics, traces, benchmark and A/B/C unchanged; no alternate-gold rescoring or embedding calls'
    return summary
