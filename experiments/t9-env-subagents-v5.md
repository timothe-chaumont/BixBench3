# t9-env-subagents-v5 (Sherlock)

- **Task:** 9, `10_1186_s12915_024_01879_0_v1`, official v1.0.0 prompt; preinstalled task 9 environment (same SIF as `exp/t9-env`)
- **Base:** `exp/t9-env-subagents` (v4 orchestrator, night batch 2026-11-15); compare with t9-baseline, t9-env, t9-env-subagents
- **Changes vs v4** (from the cost analysis of the v4 night runs: ~$9/run vs ~$2 for t9-env, 3h55-5h vs ~1h45):
  1. Sub-agents wait for long jobs with one blocking call (`wait PID` / `sleep 300`), never poll more often than every 5 min
     (v4: one sub-agent spent $3.18 on 268 status checks).
  2. Never re-run an artifact that passes verification; rebuild only on failure (v4 rebuilt 2 valid artifacts).
  3. `run_subagents(jobs)`: one dependency level runs in parallel (up to 6 at once); levels stay sequential.
  4. Sub-agents run at reasoning effort `medium`; the orchestrator keeps the run's `xhigh`
     (all other generation settings are copied from the run's configuration).
  5. Sub-agents inspect tables with head/wc/grep and run shared scripts instead of reading them.
  6. Parallel only within a level (artifacts of one level never depend on each other), sequential between levels.
  7. No planner by default: the orchestrator writes plan.json itself; it delegates planning to a "planner" sub-agent only
     if the plan exceeds ~30 artifacts or the task text is too long to analyze.
  8. Shared reference files under /data (raw data, genome, GTF/annotation, metadata) are always allowed; FORBIDDEN covers
     outputs of same-level artifacts and of lower-level artifacts the artifact does not depend on.
- **Files:** `src/bixbench3/inspect_harness/tools/subagent.py`, `condition_note.py`, `solvers.py`, `tools/__init__.py`.
- **No change** to data, outputs, grading, judge, run script or upload. Counters as in v4, plus `max_parallel_seen` and
  `subagent_effort` in `broker_logs/subagents_summary.json`.
- **Tested** with Inspect's mock model: run_subagents runs 2 sub-agents concurrently (max_parallel_seen 2), reports return
  in order, orchestrator calls at xhigh and sub-agent calls at medium with max_retries inherited.

## Fix after the first smoke test (job 52428638)

The level-1 sub-agent ran `hisat2-build` in the foreground of its shell; its warnings flooded the
output, Inspect kept only the last 10 MiB of the tool-support reply, and the truncated JSON
(`ValidationError: JSONRPCResponse`) ended the sub-agent after 20 minutes. Two changes:

- sub-agent `bash_session` and `python` are wrapped (`_robust`): an unreadable reply becomes a
  `ToolError` with recovery advice instead of ending the sub-agent;
- one instruction line: run long or verbose programs with output redirected to a log file and
  read it with `tail` / `grep`.
