# Results: `v2f` (enrichment validator), task 11

One run on GCP: GPT-5.4 Mini at xhigh, team profile (n2-custom-6-32768, 6 vCPU / 32 GB), launched with `--harness-overlay` from this branch. Run `20261115T040328592491Z`, completed, judge ok.

| Official score | Filtered counts | DESeq2 DEGs | PIANO GSEA | Hypergeometric enrichment | DNA-damage enrichment |
|---|---|---|---|---|---|
| **0.582** | 0.99 | 0.91 | 0.26 | 0.18 | 0.57 |

For comparison, same task and profile: the GCP 6-vCPU baseline scored 0.679 in one run, and the Sherlock baseline 0.630 ± 0.069 over 4 runs. This is a single stochastic run, so it cannot show whether the change helps. See [results/task11 on main](https://github.com/timothe-chaumont/BixBench3/tree/main/results/task11).
