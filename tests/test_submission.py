"""Integration: validate the actual restricted-source submission without any API work."""
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'starter'))
from src.io_utils import digest
from src.submission import validate


@unittest.skipUnless((ROOT/'.agents/review/final_review_decisions.json').exists(),'Private final decisions and corpus required')
class SubmissionTests(unittest.TestCase):
    def test_final_submission_validation_does_not_mutate_experiment(self):
        receipt=json.loads((ROOT/'.agents/review/finalization_receipt.json').read_text(encoding='utf-8'))
        before={name:digest((ROOT/name).read_bytes()) for name in receipt['protected_sha256']}
        result=validate(ROOT)
        self.assertEqual(result['status'],'READY')
        self.assertEqual(result['blockers'],[])
        self.assertEqual(result['new_embedding_calls'],0)
        self.assertFalse(result['retroactive_rescoring'])
        self.assertEqual(before,{name:digest((ROOT/name).read_bytes()) for name in before})

    def test_ready_does_not_authorize_public_source_or_push(self):
        result=json.loads((ROOT/'results/submission_readiness.json').read_text(encoding='utf-8'))
        self.assertFalse(result['source_gold_trace_publication_authorized'])
        self.assertFalse(result['push_authorized'])
        self.assertFalse(result['checks']['metadata_independently_human_scored'])
        self.assertEqual(result['checks']['metadata_user_accepted_technical'],44)
        self.assertEqual(result['checks']['extraction_warning_pages_retained'],29)


if __name__=='__main__':
    unittest.main()
