# Results: `t11-baseline` (task 11 baseline on Sherlock)

Task 11 (`10.1016_j.crtox.2021.01.003_v1`), GPT-5.4 Mini at xhigh, upstream harness unchanged, 6 CPU / 32 GB on Sherlock (AMD EPYC 7502), 4 repeats (v2 relaunch with the parity fixes; see [`experiments/t11-baseline.md`](experiments/t11-baseline.md)).

| Run (id suffix) | Official score (mean of 5 artifacts) |
|---|---|
| `492db17cc5` | 0.654 |
| `8824416a81` | 0.567 |
| `0ab40a951a` | 0.661 |
| `b7954650db` | 0.636 |
| **Mean ± 95% CI** | **0.630 ± 0.069** |

The GCP 6-vCPU reference run of the same code scored 0.679 ([`iterations/baseline-task11-6vcpu`](https://github.com/timothe-chaumont/BixBench3/tree/main/iterations/baseline-task11-6vcpu)). That is inside the Sherlock interval, so the Sherlock runner reproduces the GCP setup. The v1 attempt (3 CPU / 16 GB, broken apt) was cancelled and is not counted.

Overview of all results: [results/task11 on main](https://github.com/timothe-chaumont/BixBench3/tree/main/results/task11).
