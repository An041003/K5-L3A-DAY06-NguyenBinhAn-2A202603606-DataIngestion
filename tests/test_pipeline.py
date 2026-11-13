"""Technical invariants on the authorized real corpus/cache; no mock embeddings.

Run from repo root: starter/.venv/Scripts/python -m unittest discover -s tests -v
Private source is intentionally not distributed. Missing local evidence skips tests.
"""
import json
import math
import sys
import unittest
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'starter'))
from src.chunking import by_paragraph, fixed_size
from src.embeddings import validate_vector
from src.evaluation import evaluate_query, summarize, compact
from src.ingestion import load_pdf, normalize_text
from src.io_utils import read_jsonl, digest

PRIVATE = ROOT/'.agents'


@unittest.skipUnless((PRIVATE/'processed/pages.jsonl').exists(), 'Authorized private corpus required')
class CorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = load_pdf(PRIVATE/'corpus/kpi_ooad_uml_selected_42p_PRIVATE.pdf',
                             'kpi-v2','kpi-private',PRIVATE/'corpus/page_map.csv')
        cls.chunks = {s:read_jsonl(PRIVATE/f'processed/chunks_{s}.jsonl') for s in ('A','B')}

    def test_original_page_mapping(self):
        self.assertEqual([p.page for p in self.pages], list(range(7,18))+list(range(81,112)))
        self.assertEqual(self.pages[11].metadata['pdf_page'],12)

    def test_parser_fallback_and_no_control_characters(self):
        for p in self.pages:
            self.assertFalse(any(ord(c)<32 and c not in '\n\t\r' for c in p.text))
        self.assertTrue(any('FALLBACK' in w for p in self.pages for w in p.metadata['warnings']))

    def test_normalization_idempotent(self):
        for page in self.pages:
            self.assertEqual(normalize_text(page.text),page.text)

    def test_deterministic_stable_chunks(self):
        for s in ('A','B'):
            actual = [asdict(c) for p in self.pages for c in (fixed_size(p,500,50) if s=='A' else by_paragraph(p,1100))]
            self.assertEqual(actual,self.chunks[s])
            self.assertEqual(len({c['chunk_id'] for c in actual}),len(actual))

    def test_every_chunk_exact_source_and_single_chapter(self):
        pages={p.page:p for p in self.pages}
        for s,rows in self.chunks.items():
            for c in rows:
                p=pages[c['page']]
                m=c['metadata']
                self.assertEqual(c['text'],p.text[m['start']:m['end']])
                self.assertLessEqual(len(c['text']),500 if s=='A' else 1100)
                self.assertTrue(any(span['start']<=m['start']<m['end']<=span['end'] and m['section']==span['section'] for span in p.metadata['section_spans']))

    def test_paragraph_packing_retains_every_nonspace_character(self):
        for p in self.pages:
            actual=''.join(c['text'] for c in self.chunks['B'] if c['page']==p.page)
            self.assertEqual(''.join(actual.split()),''.join(p.text.split()))

    def test_invalid_chunk_parameters(self):
        with self.assertRaises(ValueError):
            fixed_size(self.pages[0],500,500)
        with self.assertRaises(ValueError):
            by_paragraph(self.pages[0],0)

    def test_benchmark_lock_and_full_quotes(self):
        frozen=json.loads((PRIVATE/'benchmark/lock.json').read_text(encoding='utf-8'))
        self.assertEqual(frozen['benchmark_sha256'],digest((PRIVATE/'benchmark/questions.jsonl').read_bytes()))
        pages={p.page:p for p in self.pages}
        for q in read_jsonl(PRIVATE/'benchmark/questions.jsonl'):
            self.assertIn(compact(q['evidence_quote']),compact(pages[q['gold_page']].text))
            self.assertFalse(q['human_verified'])

    def test_full_quote_proxy_does_not_claim_human_labels(self):
        q=read_jsonl(PRIVATE/'benchmark/questions.jsonl')[0]
        hits=[c for c in self.chunks['B'] if c['page']==q['gold_page'] and compact(q['evidence_quote']) in compact(c['text'])]
        self.assertTrue(hits)
        result=evaluate_query(q,hits[:3])
        self.assertTrue(result['hit_at_1'])
        self.assertFalse(result['human_verified'])
        self.assertFalse(evaluate_query(q,[])['evidence_hit_at_3'])

    def test_metrics_denominators_use_actual_split(self):
        path=PRIVATE/'results/traces.jsonl'
        if not path.exists():
            self.skipTest('Benchmark not yet run')
        rows=summarize(read_jsonl(path))
        self.assertEqual(len(rows),6)
        for r in rows:
            self.assertEqual(r['n'],15 if r['split']=='dev' else 5)
            self.assertLessEqual(r['hit_at_1_n'],r['evidence_hit_at_3_n'])

    def test_real_cached_vectors_have_768_finite_values(self):
        paths=list((PRIVATE/'cache/embeddings').glob('*.json'))
        if not paths:
            self.skipTest('No real provider cache yet')
        for path in paths:
            vector=json.loads(path.read_text(encoding='utf-8'))
            validate_vector(vector)
            self.assertTrue(all(math.isfinite(v) for v in vector))
        with self.assertRaises(ValueError):
            validate_vector(vector[:-1])

    def test_c_reuses_b_unfiltered_ranking_exactly(self):
        path=PRIVATE/'results/traces.jsonl'
        if not path.exists():
            self.skipTest('Benchmark not yet run')
        traces={(t['id'],t['strategy']):t for t in read_jsonl(path)}
        for q in read_jsonl(PRIVATE/'benchmark/questions.jsonl'):
            if not q['filter']:
                self.assertEqual(traces[(q['id'],'B')]['hits'],traces[(q['id'],'C')]['hits'])

    def test_c_filters_scope_and_preserves_real_shortfalls(self):
        path=PRIVATE/'results/traces.jsonl'
        if not path.exists():
            self.skipTest('Benchmark not yet run')
        for trace in read_jsonl(path):
            if trace['strategy']=='C' and trace['filter_applied']:
                scope=trace['filter_applied']['section']
                self.assertTrue(all(h['metadata']['section']==scope for h in trace['hits']))
                eligible=sum(c['metadata']['section']==scope for c in self.chunks['B'])
                self.assertEqual(len(trace['hits']),min(3,eligible))

    def test_partial_quote_on_right_page_does_not_count_as_full_hit(self):
        path=PRIVATE/'results/traces.jsonl'
        if not path.exists():
            self.skipTest('Benchmark not yet run')
        traces=read_jsonl(path)
        questions={q['id']:q for q in read_jsonl(PRIVATE/'benchmark/questions.jsonl')}
        checked=False
        for trace in traces:
            q=questions[trace['id']]
            for hit in trace['hits']:
                if hit['page']==q['gold_page'] and compact(q['evidence_quote']) not in compact(hit['text']):
                    self.assertFalse(evaluate_query(q,[hit])['evidence_hit_at_3'])
                    checked=True
        self.assertTrue(checked)


if __name__=='__main__':
    unittest.main()
