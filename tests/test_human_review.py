"""Review-overlay consistency on real, privately supplied approvals; no API calls."""
import csv
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'starter'))
from src.human_review import aggregate_human_review
from src.io_utils import digest


@unittest.skipUnless((ROOT/'.agents/review/human_approved_labels.json').exists(),'Authorized private human approvals required')
class HumanReviewTests(unittest.TestCase):
    def test_complete_primary_gold_and_confirmed_sample_sizes(self):
        summary=aggregate_human_review(ROOT)
        self.assertEqual(summary['gold']['confirmed'],20)
        for s in ('A','B','C'):
            self.assertEqual(summary['coherence'][s]['n'],10)
            self.assertEqual(summary['grounding'][s]['n'],5)
            self.assertEqual(summary['coherence'][s]['mean'],1.0 if s=='A' else 1.5)
            self.assertEqual(summary['grounding'][s]['mean'],1.8)
            self.assertEqual(summary['grounding'][s]['distribution'],{'0':0,'1':1,'2':4})

    def test_unconfirmed_scopes_remain_pending(self):
        summary=aggregate_human_review(ROOT)
        for kind in ('metadata','gold_alternatives','extraction'):
            self.assertEqual(summary[kind]['human_confirmed'],0)
            self.assertEqual(summary[kind]['status'],'PENDING_HUMAN')
        self.assertEqual(summary['metadata']['rows'],44)
        self.assertEqual(summary['metadata']['technical_source_trace_matches'],44)
        self.assertEqual(summary['metadata']['technical_database_matches'],44)

    def test_original_benchmark_metrics_trace_and_config_bytes_unchanged(self):
        receipt=json.loads((ROOT/'.agents/review/merge_receipt.json').read_text(encoding='utf-8'))
        for name,expected in receipt['protected_sha256'].items():
            with self.subTest(path=name):
                self.assertEqual(digest((ROOT/name).read_bytes()),expected)

    def test_csv_has_45_confirmed_labels_and_44_pending_metadata(self):
        with (ROOT/'.agents/review/manual_audit_template.csv').open(encoding='utf-8-sig',newline='') as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),90)
        self.assertEqual(sum(r['human_verified'].lower()=='true' for r in rows),45)
        self.assertEqual(sum(r['kind']=='metadata' and r['human_verified'].lower()=='false' and r['score']=='PENDING_HUMAN' for r in rows),44)
        shortfall=[r for r in rows if r['kind']=='retrieval_shortfall']
        self.assertEqual(len(shortfall),1)
        self.assertEqual(shortfall[0]['score'],'NOT_APPLICABLE')
        self.assertTrue(all(r['reason_origin']=='AI_PROPOSED_NOT_HUMAN_CONFIRMED' for r in rows if r['human_verified'].lower()=='true'))

    def test_missing_approval_packet_never_creates_scores(self):
        self.assertIsNone(aggregate_human_review(ROOT/'.agents/nonexistent_review_root'))

    def test_merge_preserves_review_text_mapping_and_shortfall_payload(self):
        receipt=json.loads((ROOT/'.agents/review/merge_receipt.json').read_text(encoding='utf-8'))
        backup=ROOT/receipt['backup_path']
        for filename,key,fields in (
            ('gold_review.csv',lambda r:r['id'],('id','split','question','expected_answer','original_page','pdf_page','evidence_quote','alternative_gold')),
            ('manual_audit_template.csv',lambda r:(r['kind'],r['id'],r['strategy'],r['rank']),('kind','id','strategy','rank','page','chunk_id','text','metadata'))):
            with (backup/filename).open(encoding='utf-8-sig',newline='') as f:
                old={key(r):r for r in csv.DictReader(f)}
            with (ROOT/'.agents/review'/filename).open(encoding='utf-8-sig',newline='') as f:
                new={key(r):r for r in csv.DictReader(f)}
            self.assertEqual(set(old),set(new))
            for k in old:
                self.assertEqual({f:old[k][f] for f in fields},{f:new[k][f] for f in fields})


if __name__=='__main__':
    unittest.main()
