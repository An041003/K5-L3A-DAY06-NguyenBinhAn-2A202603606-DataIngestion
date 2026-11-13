"""Complete-quote technical proxy, explicitly distinct from human labels."""
from collections import defaultdict
from .ingestion import normalize_text


def compact(text):
    return ' '.join(normalize_text(text).split())


def evaluate_query(question,hits):
    golds=question.get('golds') or [{'source_id':question['gold_source_id'],'page':question['gold_page'],'evidence_quote':question['evidence_quote']}]
    labels=[any(hit['document_id']==g['source_id'] and hit['page']==g['page'] and compact(g['evidence_quote']) in compact(hit['text']) for g in golds) for hit in hits]
    return {'hit_at_1':bool(labels and labels[0]),'evidence_hit_at_3':any(labels[:3]),
            'technical_quote_hits':labels,'label_status':'PROVISIONAL_EXACT_QUOTE_PROXY','human_verified':False}


def summarize(traces):
    groups=defaultdict(list)
    for trace in traces:
        groups[(trace['strategy'],trace['split'])].append(trace)
    result=[]
    for (strategy,split),group in sorted(groups.items()):
        n=len(group)
        one=sum(t['evaluation']['hit_at_1'] for t in group)
        three=sum(t['evaluation']['evidence_hit_at_3'] for t in group)
        result.append({'strategy':strategy,'split':split,'n':n,'hit_at_1_n':one,'hit_at_1':one/n,
            'evidence_hit_at_3_n':three,'evidence_hit_at_3':three/n,'status':'PROVISIONAL_PENDING_HUMAN_GOLD'})
    return result
