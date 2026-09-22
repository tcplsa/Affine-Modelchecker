# CNF Presentation Random Replay v2

This supplement does not rerun the 7,020-task live PDR phase. It retraces the
selected 30-model mechanism design with a corrected SAT API trace and replays
the resulting frame/lift workloads under deterministic and random mappings.

## What changed

- Trace protocol v2 records a `val` or `failed` observation when it first
  introduces an external variable into the canonical mapping.
- Recorded replay must exactly reproduce SAT results, conflicts, decisions,
  propagations, restarts, and the recorded mapping observations.
- `first` is an explicit alias for first-encounter mapping.
- Eight fixed random permutations estimate the mapping noise floor.
- Empty trace files are ignored.

## One extra server

Run all three causal shards on one server:

```bash
cd /home/wudl
tmux new -s cnf-random-v2
CNF_V2_ROLE=all \
CNF_V2_TRACE_WORKERS=12 \
CNF_V2_REPLAY_WORKERS=60 \
test_tools/compare/run_cnf_random_replay_v2.sh
```

Detach with `Ctrl-b d` and return with:

```bash
tmux attach -t cnf-random-v2
```

Expected runtime is roughly 30 to 60 minutes on a 128-core server. Trace data
may occupy 9 to 12 GiB. The script is resumable and writes no per-process log.

## Split across servers

Use distinct roles if multiple servers share `/home/wudl`:

```bash
CNF_V2_ROLE=server-a test_tools/compare/run_cnf_random_replay_v2.sh
CNF_V2_ROLE=server-b test_tools/compare/run_cnf_random_replay_v2.sh
CNF_V2_ROLE=server-c test_tools/compare/run_cnf_random_replay_v2.sh
```

After all roles finish, rerunning any one command regenerates the combined
report from every available shard.

## Outputs

- `results/cnf_presentation_random_replay_v2/server-*/trace_summary.tsv`
- `results/cnf_presentation_random_replay_v2/server-*/replay_results.tsv`
- `results/cnf_presentation_random_replay_v2/random_replay_report.md`

The primary mechanism metric is conflicts. Wall time is secondary. The report
also gives the full cross-origin 2x2 conflict decomposition and the percentile
of the deterministic candidate within the eight-random-seed distribution.
