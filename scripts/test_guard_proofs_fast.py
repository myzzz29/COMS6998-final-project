#!/usr/bin/env python3
"""Small executable controls for sparse proofs and exact-cache invalidation."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import subprocess
from benchmark_guard_proofs_fast import signature
from guard_proofs_cached import run

BINARY = os.environ.get('GUARD_PROOFS_FAST', '/tmp/egraph-fast-target/release/guard_proofs_fast')

def payload():
    expressions=['x','x','(and x true)','(not (not x))','y','(and y true)']
    targets=[{'id':i,'compact':e,'event_context':{'clock':'a'}} for i,e in enumerate(expressions)]
    targets += [{'id':6,'compact':'x','event_context':{'clock':'b'}},
                {'id':7,'compact':'(and x true)','event_context':{'clock':'b'}}]
    return json.dumps({'targets':targets,'verified_rules':[]}).encode()

class FastControls(unittest.TestCase):
    def test_duplicate_targets_and_context_boundaries(self):
        data=payload()
        base=json.loads(run(BINARY,data,'baseline')[0])
        sparse=json.loads(run(BINARY,data,'spanning')[0])
        self.assertEqual(signature(base),signature(sparse))
        self.assertEqual(len(sparse['rewrite_explanations']),5)
        ts={t['id']:t for t in json.loads(data)['targets']}
        before={t['id']:t['eclass_before'] for t in sparse['targets']}
        for edge in sparse['rewrite_explanations']:
            a,b=edge['left'],edge['right']
            self.assertEqual(ts[a]['event_context'],ts[b]['event_context'])
            self.assertNotEqual(before[a],before[b])

    def test_no_merge_and_empty_input(self):
        for targets in [[],[{'id':0,'compact':'x'},{'id':1,'compact':'x'}]]:
            out=json.loads(run(BINARY,json.dumps({'targets':targets,'verified_rules':[]}).encode())[0])
            self.assertEqual(out['rewrite_explanations'],[])
            self.assertEqual(len(out['targets']),len(targets))

    def test_cache_keys_and_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=payload(); raw,cold=run(BINARY,data,cache_dir=tmp)
            cached,warm=run(BINARY,data,cache_dir=tmp)
            self.assertEqual(raw,cached); self.assertTrue(warm['cache_hit'])
            for mode,changed in [('baseline',data),('spanning',data+b' '),
                ('spanning',json.dumps({**json.loads(data),'verified_rules':[{'name':'identity-x','left':'x','right':'x','proof_status':'unsat'}]}).encode())]:
                _,r=run(BINARY,changed,mode,tmp)
                self.assertFalse(r['cache_hit']); self.assertNotEqual(r['key'],cold['key'])
            altered=Path(tmp)/'engine'; shutil.copy(BINARY,altered)
            with altered.open('ab') as f: f.write(b'changed-binary-fingerprint')
            _,r=run(altered,data,cache_dir=tmp)
            self.assertFalse(r['cache_hit']); self.assertNotEqual(r['key'],cold['key'])
            (Path(tmp)/(cold['key']+'.json')).write_text('{bad')
            _,r=run(BINARY,data,cache_dir=tmp)
            self.assertFalse(r['cache_hit'])

    def test_limited_results_never_cached(self):
        # Wrapper control only: simulated termination is not a measured engine run.
        with tempfile.TemporaryDirectory() as tmp:
            for reason in ['Some(TimeLimit(5.0))','Some(NodeLimit(20000))','Some(IterationLimit(20))']:
                response=subprocess.CompletedProcess([],0,json.dumps({'stop_reason':reason}).encode(),b'{}')
                with patch('guard_proofs_cached.subprocess.run',return_value=response) as call:
                    run(BINARY,payload(),cache_dir=tmp); run(BINARY,payload(),cache_dir=tmp)
                    self.assertEqual(call.call_count,2)
            self.assertEqual(list(Path(tmp).glob('*.json')),[])

if __name__=='__main__': unittest.main()
