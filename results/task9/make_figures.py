"""Task 9 figures: our versions (5 runs each, averaged) vs the BixBench3 paper's GPT 5.4 Mini.

usage (from this folder):  uv run --no-project --with matplotlib python make_figures.py
input:  data/runs.jsonl (from update_data.sh), reference numbers below (paper v2, arXiv 2608.25286v2)
output: figures/*.png + figures/*.pdf, figures/summary.md

Reference numbers (never estimated, only read from the paper):
- task 9 pass rate of GPT 5.4 Mini = 10 of 14 artifacts pass (Figure 1B, filled squares).
  The paper does not say which square is which artifact: per-artifact cells stay empty.
- GPT 5.4 Mini failure-mode tags over ALL 20 tasks (Figure 5A, bar heights measured on the
  embedded figure image; total 65 tags = 3.25 per task attempt). Not task 9 specific.
- GPT 5.4 Mini mean cost per task over all 20 tasks: $8.47 (Edison leaderboard). Not task 9 specific.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch

HERE = Path(__file__).parent
OUT = HERE / "figures"
OUT.mkdir(exist_ok=True)

# ---- versions: order, labels (add new conditions here) ---------------------------------
VERSIONS = [  # the story told on the landing page; other branches are listed in README.md, not plotted
    ("t9-baseline", "Baseline"),
    ("t9-env", "+ Env"),
    ("t9-env-reviewer", "+ Env + Reviewer"),
    ("t9-env-subagents-v5", "+ Env + Swarm v5"),
    ("t9-env-subagents-v5-pastdev", "+ Env + Swarm v5 + past.dev"),
]
PAPER_LABEL = "Paper: GPT 5.4 Mini"

ARTIFACTS = [
    ("tagseq_featurecounts_matrix", "Count matrix"),
    ("t98g_c10_vs_control_degs", "T98G C10 DEGs"),
    ("t98g_f7_vs_control_degs", "T98G F7 DEGs"),
    ("t98g_g2_vs_control_degs", "T98G G2 DEGs"),
    ("t98g_slow_shared_degs", "T98G slow shared"),
    ("t98g_slow_upregulated_go", "T98G slow up GO"),
    ("t98g_slow_downregulated_go", "T98G slow down GO"),
    ("hek293_d10_vs_control_degs", "HEK293 D10 DEGs"),
    ("hek293_e6_vs_control_degs", "HEK293 E6 DEGs"),
    ("hek293_shared_degs", "HEK293 shared"),
    ("hek293_upregulated_go", "HEK293 up GO"),
    ("t98g_d4_vs_control_degs", "T98G D4 DEGs"),
    ("t98g_d4_specific_upregulated_genes", "T98G D4 specific up"),
    ("t98g_d4_vs_slow_upregulated_go", "T98G D4 vs slow up GO"),
]
PASS = 0.80  # paper's binary artifact pass threshold

# ---- paper reference (see docstring) ----------------------------------------------------
PAPER_T9_PASS_RATE = 10 / 14
PAPER_TASKS = 20
PAPER_TAGS = {  # GPT 5.4 Mini, all 20 tasks (Figure 5A)
    "inefficient_analysis": 19, "environment_setup_failure": 10, "method_misconfigured": 11,
    "wrong_method_substitution": 14, "premature_termination": 2, "incomplete_data": 3,
    "repetitive_retry_loop": 1, "output_format_violation": 2, "synthetic_or_placeholder_output": 2,
    "input_misinterpretation": 1,
}
PAPER_COST_ALL_TASKS = 8.47

# ---- failure-mode colors: 7 kept + Other (categorical palette, fixed order) --------------
MODES = [
    ("inefficient_analysis", "Inefficient analysis", "#2a78d6"),
    ("environment_setup_failure", "Environment setup failure", "#eb6834"),
    ("method_misconfigured", "Method misconfigured", "#1baf7a"),
    ("wrong_method_substitution", "Wrong method substitution", "#eda100"),
    ("incomplete_data", "Incomplete data", "#e87ba4"),
    ("premature_termination", "Premature termination", "#008300"),
    ("repetitive_retry_loop", "Repetitive retry loop", "#6250d6"),
    ("other", "Other (output format, synthetic output, input misinterpretation)", "#8a8984"),
]
KEPT = {m[0] for m in MODES[:-1]}

INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
    "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
})

T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262}


def mean_ci(values: list[float]) -> tuple[float, float]:
    n = len(values)
    m = sum(values) / n
    if n < 3:  # a CI from 1-2 runs is not informative
        return m, float("nan")
    sd = math.sqrt(sum((v - m) ** 2 for v in values) / (n - 1))
    return m, T95.get(n - 1, 1.96) * sd / math.sqrt(n)


def load() -> dict[str, list[dict]]:
    runs: dict[str, list[dict]] = defaultdict(list)
    for line in (HERE / "data" / "runs.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r.get("sample_error") == "no samples in eval log":  # crashed run (e.g. out of memory) that still wrote a grade
            continue
        scores = [r["artifact_scores"].get(a) or 0.0 for a, _ in ARTIFACTS]
        r["pass_rate"] = sum(s >= PASS for s in scores) / len(scores)
        r["mean_score"] = sum(scores) / len(scores)
        runs[r["condition"]].append(r)
    return runs


def present(runs):
    return [(c, l) for c, l in VERSIONS if runs.get(c)]


def label_n(label, n):
    tag = f"(n={n})" if n >= 5 else f"(n={n} of 5,\npreliminary)"
    return label.replace(" + ", "\n+ ").lstrip("\n") + "\n" + tag


def save(fig, name):
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)


def mode_of(tag: str) -> str:
    return tag if tag in KEPT else "other"


# ---- Figure A/B: failure modes ---------------------------------------------------------
def judged(c, rs):
    """Sub-agent versions: only runs re-judged on the full logs count (the official judge only sees the orchestrator)."""
    return [r for r in rs if "subagents" not in c or r.get("judge_source") == "full_logs"]


def fig_failure_modes(runs):
    runs = {c: judged(c, rs) for c, rs in runs.items()}
    vers = present(runs)
    per_run = {}  # version -> {mode: mean tags per run}
    for c, _ in vers:
        cnt = Counter(mode_of(f["tag"]) for r in runs[c] for f in r.get("failure_modes") or [])
        per_run[c] = {m: cnt[m] / len(runs[c]) for m, _, _ in MODES}
    paper = Counter()
    for tag, k in PAPER_TAGS.items():
        paper[mode_of(tag)] += k
    per_run["paper"] = {m: paper[m] / PAPER_TASKS for m, _, _ in MODES}

    xs = list(range(len(vers))) + [len(vers) + 0.8]  # gap before the paper bar
    keys = [c for c, _ in vers] + ["paper"]
    full = {c for c, _ in vers if any(r.get("judge_source") == "full_logs" for r in runs[c])}
    labels = [label_n(l + (" †" if c in full else ""), len(runs[c])) for c, l in vers] + ["Paper:\nGPT 5.4 Mini\n(all 20 tasks,\n1 run each)"]

    fig, axes = plt.subplots(1, 2, figsize=(max(16, 3.6 * len(xs)), 5.4))
    for ax, normalized in zip(axes, (False, True)):
        for x, k in zip(xs, keys):
            total = sum(per_run[k].values())
            bottom = 0.0
            for m, name, color in MODES:
                v = per_run[k][m]
                if normalized:
                    v = 100 * v / total if total else 0
                if v <= 0:
                    continue
                ax.bar(x, v, bottom=bottom, width=0.62, color=color, edgecolor=SURFACE, linewidth=1.5,
                       hatch="//" if k == "paper" else None)
                bottom += v
            if not normalized:
                ax.text(x, bottom + 0.05, f"{total:.1f}", ha="center", va="bottom", fontsize=9, color=INK)
            elif total == 0:
                ax.text(x, 2, "no tags", ha="center", va="bottom", fontsize=8, color=INK2, rotation=90)
        ax.axvline(len(vers) + 0.4 - 0.5 + 0.5, color=GRID, linewidth=1, linestyle=":")
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, rotation=0, ha="center", fontsize=8)
        ax.yaxis.grid(True, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        if normalized:
            ax.set_ylim(0, 100)
            ax.set_ylabel("Share of failure-mode tags (%)")
            ax.set_title("B  Failure-mode mix", loc="left", fontweight="bold")
        else:
            ax.set_ylabel("Failure-mode tags per run (mean)")
            ax.set_title("A  Failure-mode tags per run", loc="left", fontweight="bold")
    handles = [Patch(facecolor=c, label=n) for _, n, c in MODES]
    handles.append(Patch(facecolor="white", edgecolor=INK2, hatch="//", label="Paper reference (all tasks, not task 9 only)"))
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, fontsize=8.5, bbox_to_anchor=(0.5, -0.16))
    fig.suptitle("Task 9 process-judge failure modes by version (cf. paper Figure 5A-B)", x=0.01, ha="left", fontsize=12)
    fig.text(0.01, -0.22, "Ours: process judge (gpt-5.5, max effort) tags per run, averaged over each version's runs. "
             "Paper: GPT 5.4 Mini, 65 tags over its 20 task attempts (Figure 5A), shown per attempt; "
             "the judge model may differ.", fontsize=7.5, color=INK2)
    if full:
        fig.text(0.01, -0.26, "† Sub-agent versions: the official judge only sees the orchestrator's messages (0 tags in every run). "
                 "These bars come from the same judge re-run on the full logs, including every sub-agent's tool calls.",
                 fontsize=7.5, color=INK2)
    save(fig, "fig_A_B_failure_modes")


# ---- Figure C: artifact x version heatmap ------------------------------------------------
CMAP = LinearSegmentedColormap.from_list("seq_blue", ["#f4f8fd", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])


def fig_heatmap(runs, metric: str):
    vers = present(runs)
    rows, ranges, row_labels = [], [], []
    for c, l in vers:
        rs = runs[c]
        vals, rng = [], []
        for a, _ in ARTIFACTS:
            s = [r["artifact_scores"].get(a) or 0.0 for r in rs]
            vals.append(sum(s) / len(s) if metric == "score" else sum(v >= PASS for v in s) / len(s))
            rng.append((min(s), max(s)))
        for key in ("mean_score", "pass_rate"):
            s = [r[key] for r in rs]
            vals.append(sum(s) / len(s))
            rng.append((min(s), max(s)))
        rows.append(vals)
        ranges.append(rng if metric == "score" else None)
        row_labels.append(f"{l}  (n={len(rs)})")
    paper_row = [None] * len(ARTIFACTS) + [None, PAPER_T9_PASS_RATE]
    cols = [n for _, n in ARTIFACTS] + ["Mean artifact\nscore", "Pass rate\n(task score)"]

    ncol = len(cols)
    fig, ax = plt.subplots(figsize=(1.0 * ncol + 3.5, (0.82 if metric == "score" else 0.62) * (len(rows) + 2) + 2.2))
    gap = 0.6

    def draw_row(y, values, paper=False, rng=None):
        for j, v in enumerate(values):
            x = j + (0.35 if j >= len(ARTIFACTS) else 0)  # small gap before the summary columns
            if v is None:
                ax.add_patch(plt.Rectangle((x, y), 0.94, 0.9, facecolor="#f0efec", edgecolor="none"))
                continue
            ax.add_patch(plt.Rectangle((x, y), 0.94, 0.9, facecolor=CMAP(v), edgecolor="none"))
            ink = "white" if v > 0.55 else INK
            if rng is None:
                ax.text(x + 0.47, y + 0.45, f"{v:.2f}", ha="center", va="center", fontsize=8.5,
                        color=ink, fontweight="bold" if paper else None)
            else:  # mean, with the min-max over runs underneath
                lo, hi = rng[j]
                ax.text(x + 0.47, y + 0.33, f"{v:.2f}", ha="center", va="center", fontsize=8.5, color=ink, fontweight="bold")
                ax.text(x + 0.47, y + 0.66, f"{lo:.2f}–{hi:.2f}", ha="center", va="center", fontsize=7.2, color=ink)

    for i, vals in enumerate(rows):
        draw_row(i, vals, rng=ranges[i])
    py = len(rows) + gap
    draw_row(py, paper_row, paper=True)
    ax.text(len(ARTIFACTS) / 2, py + 0.45, "per-artifact results for task 9 not reported in the paper",
            ha="center", va="center", fontsize=8, color=INK2, style="italic")

    ax.set_xlim(-0.1, ncol + 0.4)
    ax.set_ylim(py + 1.0, -0.15)
    ax.set_yticks([i + 0.45 for i in range(len(rows))] + [py + 0.45])
    ax.set_yticklabels(row_labels + [f"{PAPER_LABEL} (task 9, 1 run)"], fontsize=9)
    ax.set_xticks([j + 0.47 + (0.35 if j >= len(ARTIFACTS) else 0) for j in range(ncol)])
    ax.set_xticklabels(cols, rotation=45, ha="left", fontsize=8.5)
    ax.xaxis.tick_top()
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    what = ("mean artifact score (0-1) over each version's runs, min–max below" if metric == "score"
            else f"share of runs in which the artifact passes (score >= {PASS:.2f})")
    ax.set_title(f"Task 9 per-artifact results by version: {what}", loc="left", fontsize=11, pad=95)
    sm = plt.cm.ScalarMappable(cmap=CMAP, norm=plt.Normalize(0, 1))
    cb = fig.colorbar(sm, ax=ax, fraction=0.02, pad=0.01)
    cb.outline.set_visible(False)
    fig.text(0.01, 0.0, "Pass rate = share of the 14 artifacts with score >= 0.80, the paper's task score. "
             "Paper value: 10 of 14 artifacts passed (Figure 1B).", fontsize=7.5, color=INK2)
    save(fig, f"fig_C_heatmap_{'scores' if metric == 'score' else 'pass_frequency'}")


# ---- Figure D: task score per run + mean and 95% CI ---------------------------------------
def fig_task_scores(runs):
    vers = present(runs)
    fig, axes = plt.subplots(1, 2, figsize=(max(13, 3.1 * len(present(runs))), 5), sharey=True)
    for ax, key, title in ((axes[0], "pass_rate", "Pass rate (paper's task score)"),
                           (axes[1], "mean_score", "Mean artifact score")):
        for i, (c, l) in enumerate(vers):
            vals = [r[key] for r in runs[c]]
            m, h = mean_ci(vals)
            jit = [(-0.12 + 0.24 * k / max(1, len(vals) - 1)) if len(vals) > 1 else 0 for k in range(len(vals))]
            ax.scatter([i + j for j in jit], vals, s=28, color="#86b6ef", edgecolor=SURFACE, linewidth=1, zorder=3)
            if not math.isnan(h):
                ax.errorbar(i + 0.28, m, yerr=h, fmt="none", ecolor=INK, elinewidth=1.5, capsize=4, zorder=4)
            ax.scatter([i + 0.28], [m], s=46, color="#1c5cab", zorder=5)
            ax.text(i + 0.36, m, f"{m:.2f}", va="center", fontsize=8.5, color=INK)
        if key == "pass_rate":
            ax.axhline(PAPER_T9_PASS_RATE, color="#e34948", linewidth=1.5, linestyle="--")
            ax.text(0.0, -0.32, f"Red dashed line: paper, GPT 5.4 Mini, task 9 = {PAPER_T9_PASS_RATE:.2f}",
                    transform=ax.transAxes, ha="left", va="top", fontsize=8.5, color="#a83332")
        ax.set_xticks(range(len(vers)))
        ax.set_xticklabels([label_n(l, len(runs[c])) for c, l in vers], rotation=0, ha="center", fontsize=8)
        ax.set_ylim(0, 1.02)
        ax.yaxis.grid(True, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.set_title(title, loc="left", fontweight="bold")
    axes[0].set_ylabel("Task 9 score")
    fig.suptitle("Task 9 score per run (light dots) with mean and 95% CI (dark; 95% CI shown only for versions with 3+ runs)", x=0.01, ha="left", fontsize=12)
    save(fig, "fig_D_task_scores")


# ---- Figure E: cost and wall time -----------------------------------------------------------
def fig_cost_time(runs):
    vers = present(runs)
    fig, axes = plt.subplots(1, 2, figsize=(max(13, 3.1 * len(present(runs))), 4.8))
    for ax, key, unit, title in ((axes[0], "cost_usd", "$", "OpenAI cost per run (USD)"),
                                 (axes[1], "total_time_s", "h", "Wall time per run (hours)")):
        for i, (c, l) in enumerate(vers):
            vals = [r.get(key) or 0 for r in runs[c]]
            if key == "total_time_s":
                vals = [v / 3600 for v in vals]
            m, h = mean_ci(vals)
            ax.bar(i, m, width=0.6, color="#cde2fb", edgecolor="none")
            ax.scatter([i] * len(vals), vals, s=22, color="#1c5cab", zorder=3)
            if not math.isnan(h):
                ax.errorbar(i, m, yerr=h, fmt="none", ecolor=INK, elinewidth=1.2, capsize=4, zorder=4)
            ax.text(i + 0.33, m, f"{m:.1f}", ha="left", va="center", fontsize=8.5, color=INK)
        if key == "cost_usd":
            ax.axhline(PAPER_COST_ALL_TASKS, color="#e34948", linewidth=1.5, linestyle="--")
            ax.text(0.0, -0.32, f"Red dashed line: paper, GPT 5.4 Mini, mean over all 20 tasks = ${PAPER_COST_ALL_TASKS}",
                    transform=ax.transAxes, ha="left", va="top", fontsize=8.5, color="#a83332")
        ax.set_xticks(range(len(vers)))
        ax.set_xticklabels([label_n(l, len(runs[c])) for c, l in vers], rotation=0, ha="center", fontsize=8)
        ax.yaxis.grid(True, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.set_title(title, loc="left", fontweight="bold")
    fig.suptitle("Task 9 cost and time by version (bars: mean, dots: runs, whiskers: 95% CI)", x=0.01, ha="left", fontsize=12)
    save(fig, "fig_E_cost_time")


# ---- Figure F: score per dollar (efficiency) ------------------------------------------------
def fig_efficiency(runs):
    vers = [(c, l) for c, l in present(runs) if len(runs[c]) >= 5]  # complete versions only
    fig, ax = plt.subplots(figsize=(7.5, 5))
    for c, l in vers:
        xs = [r.get("cost_usd") or 0 for r in runs[c]]
        ys = [r["pass_rate"] for r in runs[c]]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        ax.scatter(xs, ys, s=18, color="#86b6ef", zorder=2)
        ax.scatter([mx], [my], s=60, color="#1c5cab", zorder=3)
        ax.annotate(l, (mx, my), xytext=(6, 4), textcoords="offset points", fontsize=8.5, color=INK)
    ax.axhline(PAPER_T9_PASS_RATE, color="#e34948", linewidth=1.2, linestyle="--")
    ax.text(ax.get_xlim()[1], PAPER_T9_PASS_RATE + 0.01, "Paper, GPT 5.4 Mini, task 9", ha="right", va="bottom",
            fontsize=8, color="#a83332")
    ax.set_xlabel("OpenAI cost per run (USD)")
    ax.set_ylabel("Pass rate (task score)")
    ax.set_ylim(0, 1.02)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_title("Cost vs task 9 score, complete versions (light: runs, dark: version mean)", loc="left", fontsize=11)
    save(fig, "fig_F_cost_vs_score")


def summary(runs):
    lines = ["# Task 9 summary by version", "",
             "| Version | n | Pass rate (task score) mean ± 95% CI | Mean artifact score ± 95% CI | Cost/run $ | Time/run h | Tags/run |",
             "|---|---|---|---|---|---|---|"]
    for c, l in present(runs):
        rs = runs[c]
        pr, prh = mean_ci([r["pass_rate"] for r in rs])
        ms, msh = mean_ci([r["mean_score"] for r in rs])
        cost = sum(r.get("cost_usd") or 0 for r in rs) / len(rs)
        t = sum(r.get("total_time_s") or 0 for r in rs) / len(rs) / 3600
        tags = sum(len(r.get("failure_modes") or []) for r in rs) / len(rs)
        f = lambda m, h: f"{m:.3f}" + ("" if math.isnan(h) else f" ± {h:.3f}")
        lines.append(f"| {l} | {len(rs)} | {f(pr, prh)} | {f(ms, msh)} | {cost:.2f} | {t:.2f} | {tags:.1f} |")
    lines += [f"| *{PAPER_LABEL} (task 9, 1 run)* | 1 | {PAPER_T9_PASS_RATE:.3f} | not reported | {PAPER_COST_ALL_TASKS} (all tasks) | - | 3.25 (all tasks) |", ""]
    (OUT / "summary.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    runs = load()
    fig_failure_modes(runs)
    fig_heatmap(runs, "score")
    fig_heatmap(runs, "pass")
    fig_task_scores(runs)
    fig_cost_time(runs)
    fig_efficiency(runs)
    summary(runs)
    print("figures ->", OUT)
