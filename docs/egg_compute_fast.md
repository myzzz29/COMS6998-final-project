# Opt-in egg computation efficiency

Adds `guard_proofs_fast` alongside the unchanged historical `guard_proofs` binary.
No rewrite rule, saturation limit, checker, or existing production caller changes.
This branch excludes the later N/U/E, scheduling and incremental-discovery experiments.

Modes (first binary argument):
- `baseline` (default): all eligible pairwise explanations, uncached representatives.
- `representatives`: extract a representative once per final e-class; retain all pairs.
- `spanning`: representative reuse plus a spanning set of proof edges per final
  e-class and event context. Preserves baseline proof connectivity and every target,
  but not every direct pairwise explanation. Consumers requiring direct pair entries
  must use baseline/representatives or explicitly support proof paths.

Detailed timings go to stderr; the historical result schema stays on stdout.
`build_seconds` combines input parsing, rules, insertion and initial rebuild.
Extraction, explanation/pair selection, serialization and total time are separate.

## Build and verify

```bash
CARGO_TARGET_DIR=/tmp/egraph-fast-target cargo build --release --locked --manifest-path egraph/Cargo.toml --bin guard_proofs --bin guard_proofs_fast
GUARD_PROOFS_FAST=/tmp/egraph-fast-target/release/guard_proofs_fast python scripts/test_guard_proofs_fast.py -v
```

Run a fresh-process benchmark against the original binary, with five repetitions
per mode, rotated mode order, and one warmup per mode:

```bash
python scripts/benchmark_guard_proofs_fast.py --binary /tmp/egraph-fast-target/release/guard_proofs_fast --original /tmp/egraph-fast-target/release/guard_proofs --input test2/tasks/axis_length_fifo_v1/qualification/typed-v5/screen/egg-input.json --input results/real_parent_screen_20261104/spi_host_core_v2/screen-v2/egg-input.json --input results/i2c_event_candidate_20261104/egg-input.json --output results/egg_compute_local_reproduction --repeats 5
```

The output directory must not exist. Raw outputs, per-stage timing and summaries
are saved. Each measured result must saturate and match the original target
partition, representative strings and proof-graph connected components.
The test is not independent formal verification of every proof term.

## Exact-input cache

```bash
python scripts/guard_proofs_cached.py --binary /tmp/egraph-fast-target/release/guard_proofs_fast --mode spanning --cache-dir /tmp/guard-proofs-cache < INPUT.json > result.json 2> timing.json
```

Specify the mode explicitly: the wrapper defaults to spanning, while the binary
defaults to baseline. The cache key includes exact input bytes (all supplied rules
and provenance), mode, schema and full binary bytes (compiled rules/dependencies/caps).
Entries are integrity-checked and atomically replaced. Only Some(Saturated) results
are stored/reused. Time/node/iteration-limit results are recomputed.
A cache hit's stdout contains the original computation timings; fresh wrapper
wall time and cache_hit are on stderr. Input must still describe the current RTL:
unchanged stale inputs are not new source certification. Use a trusted local cache.

## Earlier measurements (historical, not new measurements for this push)

On one shared Linux host, five repetitions of three saved inputs gave baseline to
spanning wall medians: controller278.90→147.36ms, SPI108.18→74.87ms,
I2C22.59→29.59ms. Proof edges312→70,305→94,9→9 respectively.
Timings include wrapper key hashing, process launch and output transport, without
whole-result caching. The two proof-heavy inputs improved, I2C did not. Saturation
algorithm is unchanged; no universal or end-to-end LLM/RTL speedup is claimed.
The 45 original measured runs and four controls passed. Full historical data was
saved separately as egraph_compute_fast_v1.zip; this branch publishes the code and
reproduction instructions rather than duplicating those result files.

## Publication verification

Fresh release build and all four control tests passed before publishing this branch.
Python compilation and git diff whitespace checks also passed. The historical
45-run timing study was not rerun just for publication.
