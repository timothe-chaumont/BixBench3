# Task 11 proxy study: what would count as evidence?

This study tests whether a cheaper, downstream-only version of BixBench3 task 11 preserves decisions between six fixed harness variants. It does **not** assume that a short run is representative merely because its dataset resembles the full dataset.

The preregistered protocol is [protocol.json](protocol.json). It fixes harness commits, evaluation scope, success criteria, budget limits, censoring rules, and the distinction between discovery and confirmation before prospective results.

## The proxy and the target

Both prospective fidelities use GPT-5.4 mini with xhigh reasoning on a dedicated 6-vCPU/32-GiB VM, the same prepared R/Python runtime and frozen public reference resources. The full task starts from all 85 FASTQs and must produce five artifacts. The lite task receives the official integer count matrix, retains all 85 libraries, all 30,146 probes, every dose/time stratum and every downstream output contract, and must produce four artifacts. The count artifact is removed from both its prompt and score.

This explicitly removes the counting stage from the capability being measured. The lite score therefore measures downstream performance conditional on supplied counts; calling it a complete end-to-end benchmark would be incorrect. Preparation also differs from the historical cold baseline: DESeq2/biomaRt patch versions are 1.28.0/2.44.0, and frozen official Ensembl 100 Compara files replace the unavailable live BioMart archive. Historical cold baselines are context, not matched controls.

The prospective process judge is disabled equally in both fidelities. Primary outcomes are the benchmark's deterministic artifact grades; network adjudication remains in place. The original harness is selected by immutable commit. The study wrapper adjusts resource limits and adds explicit model prices needed to enforce cost limits. No downstream answers are exposed to the actor.

## Compare the same estimand

Let C be the count score and D the mean of the four downstream scores. Under the benchmark's equally weighted five-artifact grading, the full score is F = 0.2 C + 0.8 D. Let L be the lite mean over those same four downstream contracts. Primary ranking tests compare L with D, rather than comparing L directly with F.

For a fixed count reference c₀, the predicted full score is F̂ = 0.2 c₀ + 0.8 L, and

|F − F̂| ≤ 0.2 |C − c₀| + 0.8 |D − L|.

This identity explains what must be controlled. A stable count score is helpful but does not bound the downstream mismatch. A pairwise ranking is guaranteed only if defensible error bounds for both candidates sum to less than their predicted gap. Error quantiles estimated on a few observed arms are empirical coverage estimates, not universal guarantees.

## Decision preservation

For each fixed lite budget, pair harnesses by commit and compare their downstream means. Report Spearman rho, Kendall tau-b, exact two-sided permutation p, directional agreement for full-score gaps of at least 0.05, and whether lite retains the full winner in its top two. Report ties explicitly. A constant score vector is uninformative, not perfect agreement. Near ties deserve more full evaluation even when aggregate correlation is high.

Discovery results may choose a useful lite budget. New stochastic repeats then test that choice separately, if the preregistered time and credit limits permit. Repeated outcomes for the same six harnesses validate stability within this panel; they do not establish transfer to unseen harness families, models, tasks, or environments. Thousands of genes, fifteen contrasts, four artifacts, and fifteen pairwise comparisons do not create thousands of independent agent replicates.

Predefined support criteria require rho ≥ 0.8, directional agreement ≥ 0.8, full winner retained in lite top two, permutation p ≤ 0.05, and confirmation. If the campaign cannot meet these requirements, the conclusion is inconclusive or negative, even if one plot looks encouraging.

A small paired panel can support a screening decision, but it cannot establish universal reliability. For one fixed pair with independent repeated outcomes and agreement probability p, observing r agreements out of r has a one-sided exact 95% lower bound p = 0.05^(1/r). Two perfect agreements give a lower bound of only 0.224; at least fourteen perfect agreements are needed before that bound exceeds 0.8. Requiring the same guarantee simultaneously for fifteen fixed pairs with a Bonferroni correction would require at least twenty-six perfect repeats per pair. These calculations assume a stable repeated-run distribution; the fifteen dependent pairs in a single six-arm panel are not fifteen independent repetitions. They explain why this study uses cautious, task-specific language even if its empirical criteria pass.

A fixed downstream program satisfies Y = g(f(X)): replacing raw reads X with exactly the same counts f(X) leaves its output unchanged. An autonomous agent is different. Its post-count state also includes package versions, files, conversation history, and remaining budget. The lite task replaces that state with clean preparation and supplied counts. Numerical agreement of the count matrices does not demonstrate equivalence of those operational states. A checkpoint-based suffix evaluation would preserve more state, but would still only validate downstream changes conditional on that checkpoint.

## Cost, timing and failures

Authoritative model usage comes from completed Inspect samples. Cached input, uncached input, and output are priced separately; reasoning tokens are part of output and are not charged twice. Actor API cost excludes separately billed network-broker adjudication calls. Those calls receive a conservative campaign reserve; they are not silently reported as zero. VM uptime includes setup, actor time, grading, transfer and idle periods. Retail compute estimates are labeled estimates rather than reconciled billing charges.

Time- and cost-censored scientific runs are retained, including runs with no output artifacts. Infrastructure failures are recorded separately and never converted into scientific score-zero observations. The initial pilot is diagnostic and excluded from confirmation because its Python PATH problem motivated a prospective preparation repair.

## Relevant research and its limits

[tinyBenchmarks (Polo et al., 2024)](https://arxiv.org/html/2402.14992v2) shows that curated examples and item-response models can estimate performance on large static benchmarks from small subsets. It relies on response patterns across source models. It does not establish that removing stages from one autonomous scientific workflow preserves harness rankings.

[How Reliable is Language Model Micro-Benchmarking? (Yauney et al., 2025)](https://arxiv.org/html/2510.08730v1) emphasizes pairwise reliability conditional on the full-performance gap. Good aggregate correlation can coexist with poor decisions between close models. This motivates the material-gap agreement metric and explicit near-tie handling here; its quantitative sample-size results do not directly transfer to this single-task study.

[Hyperband (Li et al., 2018)](https://www.jmlr.org/papers/v18/16-558.html) and [BOHB (Falkner et al., 2018)](https://proceedings.mlr.press/v80/falkner18a.html) motivate spending small budgets broadly and increasing budgets for promising candidates. They do not imply that every proposed low fidelity is informative. A practical screening policy should preserve some random full evaluations to detect false eliminations and fidelity drift.

[RNA-seq differential expression studies: more sequence or more replication? (Liu et al., 2014)](https://pmc.ncbi.nlm.nih.gov/articles/PMC3904521/) finds a trade-off between read depth and biological replication in the studied RNA-seq settings. It motivates retaining this task's complete biological design while exploring depth separately. Its depth thresholds are not assumed valid for TempO-Seq or for agent performance.

The secondary replay applies one fixed DESeq2 implementation to binomially thinned counts and to historical versus supplied counts. It isolates a biological sensitivity mechanism. It is neither a raw-read subsampling experiment nor an independent demonstration of agent-ranking preservation. Budget–quality curves from a small grid are empirical curves, not universal scaling laws.
