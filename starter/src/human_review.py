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
    final_path = review/'final_review_decisions.json'
    if final_path.exists():
        final = json.loads(final_path.read_text(encoding='utf-8'))
        accepted_status = 'USER_ACCEPTED_TECHNICAL_VERIFICATION'
        if final['metadata']['status']!=accepted_status or final['metadata']['independent_human_scoring'] is not False:
            raise ValueError('Final metadata decision must preserve technical-verification provenance')
        full_metadata = _csv(review/'metadata_review_44.csv')
        traces = read_jsonl(private/'results/traces.jsonl')
        expected = {(t['id'],t['strategy'],str(rank)):h for t in traces if t['split']=='test' for rank,h in enumerate(t['hits'],1)}
        if len(full_metadata)!=44 or len(expected)!=44 or len(metadata)!=44:
            raise ValueError('Final metadata population differs from frozen test hits')
        if len({(r['id'],r['strategy'],r['rank']) for r in full_metadata})!=44:
            raise ValueError('Duplicate metadata acceptance keys')
        for r in full_metadata:
            hit = expected[(r['id'],r['strategy'],r['rank'])]
            checks = {'document_id':hit['document_id'],'source':hit['source'],'page':str(hit['page']),
                'pdf_page':str(hit['metadata']['pdf_page']),'original_page':str(hit['metadata']['original_page']),
                'section':hit['metadata']['section'],'text':hit['text']}
            if any(r[k]!=v for k,v in checks.items()):
                raise ValueError('Accepted metadata differs from frozen trace')
            if r['verification_status']!=accepted_status or r['human_verified'].lower()!='false':
                raise ValueError('Technical acceptance must not become independent human scoring')
        by_strategy = {s:{'accepted':sum(r['strategy']==s for r in full_metadata),
                          'total':sum(r['strategy']==s for r in full_metadata)} for s in ('A','B','C')}
        if by_strategy!=final['metadata']['by_strategy'] or final['metadata']['accepted']!=44:
            raise ValueError('Final metadata counts disagree with accepted population')
        if technical.get('source_trace_checks_pass')!=44 or technical.get('database_matches')!=44:
            raise ValueError('Accepted technical check evidence incomplete')
        source_manifest = json.loads((root/'data/manifest.json').read_text(encoding='utf-8'))
        warning_rows = [p for p in source_manifest['pages'] if p['warnings']]
        table_pages = [p['original_page'] for p in warning_rows if 'TABLE_READING_ORDER_REQUIRES_REVIEW' in p['warnings']]
        fallback_pages = [p['original_page'] for p in warning_rows if any('FALLBACK' in w for w in p['warnings'])]
        extraction_rows = _csv(review/'extraction_review.csv')
        if len(warning_rows)!=29 or len(table_pages)!=28 or fallback_pages!=[12,13,93]:
            raise ValueError('Source warnings changed after acceptance')
        if len(extraction_rows)!=29 or any(r['human_verified'].lower()=='true' for r in extraction_rows):
            raise ValueError('Do not clear or human-verify unreviewed extraction pages')
        if final['extraction']['status']!='USER_ACCEPTED_WITH_DISCLOSED_LIMITATIONS' or final['extraction']['all_pages_human_verified'] is not False:
            raise ValueError('Extraction acceptance must preserve disclosed limits')
        if final['alternative_gold']['official_additions']!=0 or final['alternative_gold']['D10_page106_status'] not in ('PENDING','USER_CONFIRMED_EQUIVALENT_EVIDENCE'):
            raise ValueError('Unconfirmed alternate evidence cannot become official gold')
        summary['status'] = 'FINAL_REVIEW_ACCEPTED_WITH_LIMITATIONS'
        summary['final_decision_sha256'] = digest(final_path.read_bytes())
        summary['metadata'].update(status=accepted_status,user_accepted_technical=44,
            by_strategy=by_strategy,independent_human_scoring=False,
            fields=final['metadata']['fields'],rubric_method_limit='Accepted technical verification; not independent manual per-chunk audit')
        summary['extraction'].update(status='USER_ACCEPTED_WITH_DISCLOSED_LIMITATIONS',
            table_reading_order_warning_pages=28,parser_fallback_original_pages=fallback_pages,
            warning_pages_retained=29,all_pages_human_verified=False,error_free_claim=False)
        summary['gold_alternatives'].update(status='QUALITATIVE_ONLY_NO_RETROSPECTIVE_RESCORING',
            candidate_chunks=78,official_additions=0,D10_page106_status=final['alternative_gold']['D10_page106_status'],submission_blocker=False)
        if final['alternative_gold']['D10_page106_status']=='USER_CONFIRMED_EQUIVALENT_EVIDENCE':
            summary['gold_alternatives'].pop('questions_pending',None)
            summary['gold_alternatives'].update(human_confirmed=1,human_confirmed_source_passages=1,
                confirmation_scope='D10 source passage original_page106/pdf_page37; not blanket approval of truncated retrieved chunks',
                other_candidates='QUALITATIVE_ONLY_UNCONFIRMED',metrics_rescored=False)
        summary['gold']['alternatives_status'] = summary['gold_alternatives']['status']
        summary['permissions'] = final['permissions']
    return summary
