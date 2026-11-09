#!/usr/bin/env python3
"""Opt-in exact-input cache. Never reuse resource-limited results as saturated."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

SCHEMA = 'guard-proofs-exact-cache-v1'

def run(binary, payload, mode='spanning', cache_dir=None):
    start = time.perf_counter()
    binary = Path(binary).resolve()
    # Exact bytes preserve ordering and all provenance fields; binary binds rules/caps.
    key = hashlib.sha256(SCHEMA.encode() + b'\0' + binary.read_bytes() + b'\0' + mode.encode() + b'\0' + payload).hexdigest()
    entry = Path(cache_dir) / (key + '.json') if cache_dir else None
    if entry and entry.exists():
        try:
            cached = json.loads(entry.read_text())
            raw = cached['stdout']
            result = json.loads(raw)
            if (cached['key'] == key and result['stop_reason'] == 'Some(Saturated)' and
                    hashlib.sha256(raw.encode()).hexdigest() == cached['sha256']):
                return raw, {'cache_hit': True, 'key': key, 'wall_seconds': time.perf_counter()-start,
                             'engine_timing': None, 'note': 'Output timing fields describe original computation.'}
        except (ValueError, KeyError, TypeError):
            pass
    p = subprocess.run([str(binary), mode], input=payload, capture_output=True, check=True, timeout=60)
    raw = p.stdout.decode()
    result = json.loads(raw)
    timing = json.loads(p.stderr)
    if entry and result['stop_reason'] == 'Some(Saturated)':
        entry.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix='.pending-', dir=entry.parent)
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump({'key': key, 'sha256': hashlib.sha256(raw.encode()).hexdigest(), 'stdout': raw}, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, entry)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    return raw, {'cache_hit': False, 'key': key, 'wall_seconds': time.perf_counter()-start, 'engine_timing': timing}

if __name__ == '__main__':
    import sys
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', required=True)
    parser.add_argument('--mode', choices=['baseline', 'representatives', 'spanning'], default='spanning')
    parser.add_argument('--cache-dir', required=True)
    args = parser.parse_args()
    raw, timing = run(args.binary, sys.stdin.buffer.read(), args.mode, args.cache_dir)
    sys.stdout.write(raw)
    print(json.dumps(timing), file=sys.stderr)
