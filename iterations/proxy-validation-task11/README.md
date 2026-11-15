# Task 11 lite proxy study

**Final report: feasibility demonstrated in about 30 minutes; representativeness not established. New experiments stopped at the user's request on 15 November 2026.**

Read the **[study report](report.md)** for outcomes, costs, plots, trace diagnostics, preparation errors, related research and the limits of the evidence.

- [Completed observations](runs.csv), including time-limited failures.
- [Cost accounting and cutoff](cost-summary.json).
- [Compact trace summaries](trace-summaries/summary.json).
- [Input coverage and checksums](input-coverage.json).
- [Corrected V4 protocol](protocol-v4.json) and [methodology](methodology.md).
- Earlier development protocols: [V2](protocol.json), [V3](protocol-v3.json), [V3 budget amendment](protocol-v3-budget-amendment.json).

One V3 statistical-background lite run finished in 29m34s, produced four downstream artifacts, scored 0.6342 and used $1.1976 of actor API usage. A metadata-helper error excludes V3 from corrected validation. No completed corrected matched full/lite panel or independent confirmation supports a ranking-preservation claim.

The lite task retains all 85 libraries and 30,146 probes, supplies counts and scores four downstream artifacts. Its score must be compared with the full run's downstream mean, not directly with the five-artifact overall score. Prepared references and packages differ from the original cold setup.

Implementation is under [tools/proxy_study](../../tools/proxy_study/). Raw Inspect bundles remain in the private shared results bucket; no credentials, account balances or answer matrices are published here. The [dashboard](https://bixdash-385251430960.us-central1.run.app/) separates full and lite task scopes. Two runs already active at cutoff are excluded from completed-observation claims; passive finalizers stop their VMs after completion. No further experiments are queued.
