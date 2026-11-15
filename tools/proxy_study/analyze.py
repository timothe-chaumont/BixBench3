"""Rebuild compact, public study metrics and figures from downloaded job bundles."""

import argparse
import itertools
import json
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
from scipy.stats import kendalltau, spearmanr

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def compare(full, lite):
    arms = sorted(set(full) & set(lite))
    x = np.array([full[a] for a in arms])
    y = np.array([lite[a] for a in arms])
    out = {"arms": arms, "n_arms": len(arms), "full": x.tolist(), "lite": y.tolist()}
    if len(arms) < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return {
            **out,
            "conclusion": "unidentifiable: fewer than three arms or a constant score vector",
            "spearman_rho": None,
        }
    rho = float(spearmanr(x, y).statistic)
    tau = float(kendalltau(x, y).statistic)
    permutations = [float(spearmanr(x, np.array(p)).statistic) for p in itertools.permutations(y)]
    pairs = [(i, j) for i in range(len(arms)) for j in range(i) if abs(x[i] - x[j]) >= 0.05]
    agreements = [np.sign(x[i] - x[j]) == np.sign(y[i] - y[j]) for i, j in pairs]
    top2 = set(arms[i] for i in np.flatnonzero(y >= np.sort(y)[-2]))
    winners = set(arms[i] for i in np.flatnonzero(x == x.max()))
    out.update(
        spearman_rho=rho,
        kendall_tau_b=tau,
        exact_permutation_p_two_sided=sum(abs(r) >= abs(rho) - 1e-12 for r in permutations)
        / len(permutations),
        material_pairs=len(pairs),
        pairwise_directional_agreement=float(np.mean(agreements)) if pairs else None,
        full_winner_in_lite_top2=any(sum(y >= y[i]) <= 2 for i in np.flatnonzero(x == x.max())),
        lite_top2_including_ties=sorted(top2),
        full_winners=sorted(winners),
    )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jobs", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--profile", default="v3")
    ap.add_argument("--target-full-budget", type=int, default=10800)
    ap.add_argument("--target-lite-budget", type=int, default=1800)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for p in sorted(a.jobs.glob("*/study_metrics.json")):
        if not (p.parent / "job.json").exists():
            continue
        j = json.loads((p.parent / "job.json").read_text())
        m = json.loads(p.read_text())
        j.setdefault("profile", "v2")
        rows.append(
            {
                **j,
                **{k: v for k, v in m.items() if not isinstance(v, (dict, list))},
                "limit_type": (m.get("limit") or {}).get("type"),
                "error": json.dumps(m.get("sample_error")),
                "artifact_scores": json.dumps(m.get("artifact_scores", {})),
            }
        )
    if not rows:
        raise SystemExit("No completed scientific jobs yet")
    df = pd.DataFrame(rows)
    df.to_csv(a.out / "runs.csv", index=False)
    results = {}
    valid = df[df.scientifically_valid.astype(bool)]
    valid = valid[
        (valid.profile == a.profile)
        & (
            ((valid["mode"] == "full") & (valid.budget == a.target_full_budget))
            | ((valid["mode"] == "lite") & (valid.budget == a.target_lite_budget))
        )
    ]
    valid.to_csv(a.out / "matched-panel.csv", index=False)
    for stage in sorted(valid.stage.unique()):
        sub = valid[valid.stage == stage]
        full = sub[sub["mode"] == "full"].groupby("variant").downstream_score.mean().to_dict()
        for b in sorted(sub[sub["mode"] == "lite"].budget.unique()):
            lite = (
                sub[(sub["mode"] == "lite") & (sub.budget == b)]
                .groupby("variant")
                .downstream_score.mean()
                .to_dict()
            )
            results[f"stage{stage}_lite{b}"] = compare(full, lite)
    (a.out / "ranking-tests.json").write_text(json.dumps(results, indent=2, allow_nan=False) + "\n")
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    colors = {"full": "#385f91", "lite": "#de823e"}
    fig, ax = plt.subplots(figsize=(8, 5))
    for mode, sub in valid.groupby("mode"):
        ax.scatter(
            sub.elapsed_s / 60,
            sub.downstream_score,
            label=mode,
            color=colors[mode],
            s=35,
            alpha=0.8,
        )
        for _, r in sub.iterrows():
            ax.annotate(
                r.variant,
                (r.elapsed_s / 60, r.downstream_score),
                xytext=(3, 3),
                textcoords="offset points",
                fontsize=7,
            )
    ax.set(
        xlabel="Actor wall time (minutes)",
        ylabel="Common downstream score (4 artifacts)",
        ylim=(-0.03, 1.03),
        title=f"Task 11 {a.profile}: matched budget / quality observations",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(a.out / "score-vs-time.png", dpi=180)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 5))
    for mode, sub in valid.groupby("mode"):
        ax.scatter(
            sub.cost_usd, sub.downstream_score, label=mode, color=colors[mode], s=35, alpha=0.8
        )
    ax.set(
        xlabel="Actor API cost (USD; broker calls excluded)",
        ylabel="Common downstream score",
        ylim=(-0.03, 1.03),
        title=f"Task 11 {a.profile}: matched cost / quality observations",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(a.out / "score-vs-cost.png", dpi=180)
    plt.close(fig)
    # Each plot compares within the same prospective stage; historical cold runs are excluded.
    for key, r in results.items():
        if r["n_arms"] == 0:
            continue
        fig, ax = plt.subplots(figsize=(6, 5))
        ax.plot([0, 1], [0, 1], color="#bbbbbb", lw=1)
        ax.scatter(r["full"], r["lite"], s=40, color=colors["lite"])
        for name, x, y in zip(r["arms"], r["full"], r["lite"], strict=True):
            ax.annotate(name, (x, y), xytext=(4, 4), textcoords="offset points", fontsize=8)
        ax.set(
            xlabel="Prepared full: 4-artifact downstream score",
            ylabel="Lite: same 4-artifact score",
            xlim=(-0.05, 1.05),
            ylim=(-0.05, 1.05),
            title=key + " (paired harness means)",
        )
        fig.tight_layout()
        fig.savefig(a.out / (key + "-paired.png"), dpi=180)
        plt.close(fig)
    print(
        json.dumps(
            {"n_runs": len(df), "actor_usd": df.cost_usd.sum(), "ranking_tests": results}, indent=2
        )
    )


if __name__ == "__main__":
    main()
