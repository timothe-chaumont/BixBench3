"""Headline figure for the repository README: task 9 pass rate and cost per run, by version.

usage (from this folder):  uv run --no-project --with matplotlib python make_headline.py
input / conventions: same as make_figures.py (data/runs.jsonl, pass = artifact score >= 0.80)
output: figures/headline.png + .pdf
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import make_figures as mf

BLUE, BLUE_LIGHT, RED = "#1f5fae", "#8db7ea", "#c8322f"


def main():
    runs = mf.load()
    vers = [(c, l) for c, l in mf.VERSIONS if len(runs.get(c, [])) >= 5]  # headline: complete versions only
    short = {
        "t9-baseline": "Baseline",
        "t9-env": "+ Preinstalled\nenv",
        "t9-env-reviewer": "+ Env\n+ Reviewer",
        "t9-env-subagents-v5": "+ Env\n+ Swarm v5",
        "t9-env-subagents-v5-pastdev": "+ Env + Swarm v5\n+ past.dev",
    }
    labels = [f"{short.get(c, l)}\n(n={len(runs[c])})" for c, l in vers]
    xs = range(len(vers))

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.6), gridspec_kw={"width_ratios": [1.35, 1]})

    # A: pass rate (paper's task score)
    for x, (c, _) in zip(xs, vers):
        vals = sorted(r["pass_rate"] for r in runs[c])
        offs = [(i - (len(vals) - 1) / 2) * 0.07 for i in range(len(vals))]
        a1.scatter([x + o for o in offs], vals, s=34, color=BLUE_LIGHT, edgecolor=mf.SURFACE, linewidth=1, zorder=3)
        m, h = mf.mean_ci(vals)
        a1.errorbar(x + 0.3, m, yerr=h, fmt="o", color=BLUE, ms=8, capsize=4, lw=1.6, zorder=4)
        a1.text(x + 0.42, m, f"{m:.2f}", va="center", fontsize=10.5, fontweight="bold", color=mf.INK)
    a1.axhline(mf.PAPER_T9_PASS_RATE, color=RED, ls="--", lw=1.4)
    a1.text(len(vers) - 0.35, mf.PAPER_T9_PASS_RATE - 0.02, "BixBench3 paper,\nGPT-5.4 Mini, task 9: 0.71",
            color=RED, fontsize=9, ha="right", va="top",
            bbox=dict(facecolor=mf.SURFACE, edgecolor="none", pad=1.5))
    a1.set_ylim(0, 1.05)
    a1.set_xlim(-0.5, len(vers) - 0.3)
    a1.set_xticks(list(xs))
    a1.set_xticklabels(labels, fontsize=9)
    a1.set_ylabel("Task score (share of 14 artifacts passing)")
    a1.yaxis.grid(True, color=mf.GRID, lw=0.8)
    a1.set_axisbelow(True)
    a1.set_title("A  Task 9 score per run (dots), mean and 95% CI", loc="left", fontweight="bold", fontsize=11)

    # B: cost per run
    for x, (c, _) in zip(xs, vers):
        vals = [r["cost_usd"] for r in runs[c]]
        m, _ = mf.mean_ci(vals)
        a2.bar(x, m, width=0.6, color="#cfe0f6", edgecolor=mf.SURFACE, zorder=2)
        offs = [(i - (len(vals) - 1) / 2) * 0.07 for i in range(len(vals))]
        a2.scatter([x + o for o in offs], sorted(vals), s=22, color=BLUE, zorder=3)
        a2.text(x, m + 0.35, f"${m:.2f}", ha="center", fontsize=10, fontweight="bold", color=mf.INK)
    a2.set_xticks(list(xs))
    a2.set_xticklabels(labels, fontsize=9)
    a2.set_ylabel("OpenAI API cost per run (USD)")
    a2.yaxis.grid(True, color=mf.GRID, lw=0.8)
    a2.set_axisbelow(True)
    a2.set_title("B  Cost per run (bar: mean, dots: runs)", loc="left", fontweight="bold", fontsize=11)

    fig.text(0.01, -0.04, "GPT-5.4 Mini (xhigh), 6 CPU / 32 GB per run, 5 independent runs per version. "
             "An artifact passes when its grader score is >= 0.80 (the paper's criterion).",
             fontsize=8, color=mf.INK2)
    fig.tight_layout()
    mf.save(fig, "headline")


if __name__ == "__main__":
    main()
