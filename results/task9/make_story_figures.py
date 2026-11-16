"""Figures for the README story (same order as the presentation in docs/presentation/).

usage (from this folder):  uv run --no-project --with matplotlib python make_story_figures.py
input: data/runs.jsonl via make_figures.load(); only versions with 5 completed runs are drawn.
output: figures/story_1_failures.png, story_2_scores.png, story_3_cost_time.png (+ .pdf)

Score = mean artifact score (grade.json `score`, the metric used in the presentation).
"""

from __future__ import annotations

from collections import Counter

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

import make_figures as mf

NAMES = {
    "t9-baseline": "Baseline",
    "t9-env": "+ Env",
    "t9-env-reviewer": "+ Env\n+ Reviewer",
    "t9-env-subagents": "+ Env\n+ Swarm",
    "t9-env-subagents-v5-pastdev": "+ Env\n+ Swarm v5 + past.dev",
}
GREY, BLUE, GREEN, ORANGE = "#8a8984", "#2a78d6", "#1baf7a", "#eb6834"
COLOR = {"t9-baseline": GREY, "t9-env": BLUE, "t9-env-reviewer": GREEN, "t9-env-subagents": ORANGE,
         "t9-env-subagents-v5-pastdev": "#c03b8a"}


def complete(runs):
    return [c for c in NAMES if len(runs.get(c, [])) >= 5]


def fig_failures(runs):
    vers = ["t9-baseline", "t9-env"]
    fig, ax = plt.subplots(figsize=(6.2, 4.4))
    for x, c in enumerate(vers):
        cnt = Counter(mf.mode_of(f["tag"]) for r in runs[c] for f in r.get("failure_modes") or [])
        bottom = 0.0
        for m, _, color in mf.MODES:
            v = cnt[m] / len(runs[c])
            if v:
                ax.bar(x, v, bottom=bottom, width=0.55, color=color, edgecolor=mf.SURFACE, linewidth=2)
                bottom += v
        ax.text(x, bottom + 0.05, f"{bottom:.1f}", ha="center", fontsize=12, fontweight="bold", color=mf.INK)
    ax.set_xticks(range(len(vers)))
    ax.set_xticklabels([f"{NAMES[c]} (n=5)" for c in vers], fontsize=10)
    ax.set_ylabel("Failure-mode tags per run (mean)")
    ax.set_ylim(0, 2.9)
    ax.yaxis.grid(True, color=mf.GRID, lw=0.8)
    ax.set_axisbelow(True)
    used = {mf.mode_of(f["tag"]) for c in vers for r in runs[c] for f in r.get("failure_modes") or []}
    ax.legend(handles=[Patch(facecolor=col, label=n) for m, n, col in mf.MODES if m in used],
              loc="upper right", frameon=False, fontsize=8.5)
    ax.set_title("Process-judge failure modes, task 9", loc="left", fontweight="bold", fontsize=11)
    fig.tight_layout()
    mf.save(fig, "story_1_failures")


def fig_scores(runs):
    vers = complete(runs)
    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    for y, c in enumerate(reversed(vers)):
        vals = [r["mean_score"] for r in runs[c]]
        m = sum(vals) / len(vals)
        ax.plot([min(vals), max(vals)], [y, y], color=COLOR[c], lw=2, solid_capstyle="round", zorder=2)
        ax.scatter(vals, [y] * len(vals), s=30, color=COLOR[c], alpha=0.45, edgecolor="none", zorder=3)
        ax.scatter([m], [y], s=110, color=COLOR[c], edgecolor=mf.SURFACE, linewidth=1.5, zorder=4)
        ax.text(m, y + 0.24, f"{m:.3f}", ha="center", fontsize=10.5, fontweight="bold", color=mf.INK)
        cost = sum(r["cost_usd"] for r in runs[c]) / len(runs[c])
        ax.text(1.03, y, f"${cost:.2f}", va="center", fontsize=10, color=mf.INK2, transform=ax.get_yaxis_transform())
    ax.text(1.03, len(vers) - 0.35, "cost / run", fontsize=8.5, color=mf.INK2, transform=ax.get_yaxis_transform())
    ax.set_yticks(range(len(vers)))
    ax.set_yticklabels([NAMES[c].replace("\n", " ") for c in reversed(vers)], fontsize=10)
    ax.set_xlim(0, 1)
    ax.set_xlabel("Task 9 score (mean artifact score, 0-1)")
    ax.xaxis.grid(True, color=mf.GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.set_ylim(-0.6, len(vers) - 0.3)
    ax.set_title("Score per run (small dots), mean (large dot) and min-max range, 5 runs each",
                 loc="left", fontweight="bold", fontsize=11)
    fig.tight_layout()
    mf.save(fig, "story_2_scores")


def fig_cost_time(runs):
    vers = complete(runs)
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4), sharey=True)
    for ax, key, scale, xlabel in ((axes[0], "cost_usd", 1, "OpenAI cost per run (USD)"),
                                   (axes[1], "total_time_s", 1 / 3600, "Wall-clock time per run (hours)")):
        for c in vers:
            xs = [r[key] * scale for r in runs[c]]
            ys = [r["mean_score"] for r in runs[c]]
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            ax.scatter(xs, ys, s=26, color=COLOR[c], alpha=0.4, edgecolor="none", zorder=2)
            ax.scatter([mx], [my], s=120, color=COLOR[c], edgecolor=mf.SURFACE, linewidth=1.5, zorder=3)
            two_line = c == "t9-env-subagents-v5-pastdev"  # one line would run into the "+ Env + Swarm" label
            label = "+ Env + Swarm v5\n+ past.dev" if two_line else NAMES[c].replace("\n", " ")
            ax.annotate(label, (mx, my), xytext=(8, 6), textcoords="offset points",
                        fontsize=9.5, color=mf.INK, linespacing=1.1)
        ax.set_xlabel(xlabel)
        ax.set_xlim(left=0)
        ax.grid(True, color=mf.GRID, lw=0.8)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("Task 9 score (mean artifact score)")
    axes[0].set_ylim(0, 1.02)
    axes[0].set_title("Score vs cost", loc="left", fontweight="bold", fontsize=11)
    axes[1].set_title("Score vs time", loc="left", fontweight="bold", fontsize=11)
    fig.text(0.01, -0.03, "Large dots: mean of 5 completed runs; small dots: individual runs. "
             "Top-left is best: high score, low cost, short runs.", fontsize=8.5, color=mf.INK2)
    fig.tight_layout()
    mf.save(fig, "story_3_cost_time")


if __name__ == "__main__":
    r = mf.load()
    fig_failures(r)
    fig_scores(r)
    fig_cost_time(r)
