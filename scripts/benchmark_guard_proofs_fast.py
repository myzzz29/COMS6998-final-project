#!/usr/bin/env python3
"""Offline engine-only comparison; preserves raw outputs and tests graph connectivity."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import time
from guard_proofs_cached import run

MODES = ['baseline', 'representatives', 'spanning']

def components(result):
    ids = [json.dumps(t['id'], sort_keys=True) for t in result['targets']]
    parent = {i:i for i in ids}
    def root(i):
        while parent[i] != i:
            i = parent[i]
        return i
    for e in result['rewrite_explanations']:
        a,b = (json.dumps(e[k],sort_keys=True) for k in ('left','right'))
        parent[root(a)] = root(b)
    return sorted(sorted(i for i in ids if root(i)==r) for r in set(root(i) for i in ids))

def signature(result):
    # Do not require opaque e-class numbers to remain the same.
    groups = {}
    for t in result['targets']:
        groups.setdefault(t['eclass'], []).append(json.dumps(t['id'], sort_keys=True))
    return (sorted(sorted(g) for g in groups.values()),
            [t['representative'] for t in result['targets']], components(result))

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary', required=True)
    p.add_argument('--original', required=True)
    p.add_argument('--input', action='append', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--repeats', type=int, default=5)
    args=p.parse_args()
    out=Path(args.output); out.mkdir(parents=True,exist_ok=False)
    rows=[]; summaries=[]
    for n, name in enumerate(args.input):
        data=Path(name).read_bytes(); label=f'input-{n}'
        (out/f'{label}.json').write_bytes(data)
        p0=subprocess.run([args.original],input=data,capture_output=True,check=True,timeout=60)
        original=json.loads(p0.stdout)
        (out/f'{label}-original.json').write_bytes(p0.stdout)
        # Warm each mode once; all timed trials still start fresh processes.
        for mode in MODES:
            run(args.binary,data,mode)
        for trial in range(args.repeats):
            order=MODES[trial%3:]+MODES[:trial%3]
            for mode in order:
                start=time.perf_counter()
                raw, timing=run(args.binary,data,mode)
                wall=time.perf_counter()-start
                result=json.loads(raw)
                assert signature(result)==signature(original), (name,mode,'semantic mismatch')
                assert result['stop_reason']==original['stop_reason']=='Some(Saturated)', (name,mode,'not saturated')
                row={'input':name,'label':label,'mode':mode,'trial':trial,'wall_seconds':wall,
                     **timing['engine_timing'], 'explanations':len(result['rewrite_explanations']), 'bytes':len(raw.encode())}
                rows.append(row)
                (out/f'{label}-{mode}-{trial}.json').write_text(raw)
                (out/'trials.json').write_text(json.dumps(rows,indent=2))
        cold,ct=run(args.binary,data,'spanning',out/'cache')
        warm,wt=run(args.binary,data,'spanning',out/'cache')
        assert cold==warm and not ct['cache_hit'] and wt['cache_hit']
        stats={m:{k:statistics.median(r[k] for r in rows if r['label']==label and r['mode']==m)
                  for k in ['wall_seconds','saturation_seconds','extraction_seconds','explanation_seconds','serialization_seconds','explanations','bytes']} for m in MODES}
        summaries.append({'input':name,'sha256':hashlib.sha256(data).hexdigest(),'targets':len(original['targets']),
                          'ground_rules':original['ground_rule_count'],'medians':stats,'cache_cold':ct,'cache_hit':wt})
    (out/'summary.json').write_text(json.dumps({'repeats':args.repeats,'inputs':summaries,
        'binary_sha256':hashlib.sha256(Path(args.binary).read_bytes()).hexdigest(),
        'original_sha256':hashlib.sha256(Path(args.original).read_bytes()).hexdigest()},indent=2))
    print(json.dumps(summaries,indent=2))

if __name__=='__main__': main()
