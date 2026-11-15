"""Descriptive input coverage and count-source agreement; no pseudo-replicate CIs."""

import argparse
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("counts", type=Path)
    ap.add_argument("historical", type=Path)
    ap.add_argument("metadata", type=Path)
    ap.add_argument("out", type=Path)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    meta = pd.read_csv(a.metadata, sep="\t")
    table = pd.crosstab(meta.timepoint, meta.treatment_ppm).reindex(
        index=["day7", "day28", "day90"],
        columns=["0ppm", "40ppm", "200ppm", "600ppm", "2000ppm", "6000ppm"],
    )
    table.to_csv(a.out / "cohort-coverage.csv")
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.imshow(table, aspect="auto", cmap="Blues", vmin=0, vmax=5)
    for i in range(3):
        for j in range(6):
            ax.text(
                j,
                i,
                str(table.iloc[i, j]),
                ha="center",
                va="center",
                color="white" if table.iloc[i, j] >= 4 else "black",
            )
    ax.set_xticks(range(6), table.columns)
    ax.set_yticks(range(3), table.index)
    ax.set_title(
        "All 85 biological libraries retained in full and lite\nCells show libraries per timepoint / exposure stratum"
    )
    fig.tight_layout()
    fig.savefig(a.out / "cohort-coverage.png", dpi=180)
    plt.close(fig)
    ref = pd.read_csv(a.counts, index_col=0)
    old = pd.read_csv(a.historical, index_col=0)
    old = old.loc[ref.index, ref.columns]
    x = np.log1p(ref.to_numpy(float)).ravel()
    y = np.log1p(old.to_numpy(float)).ravel()
    fig, axs = plt.subplots(1, 2, figsize=(10, 4))
    h = axs[0].hexbin(x, y, gridsize=75, mincnt=1, bins="log", cmap="viridis")
    fig.colorbar(h, ax=axs[0], label="Cell count (log scale)")
    axs[0].plot([0, x.max()], [0, x.max()], lw=1, color="#bbbbbb")
    axs[0].set(
        xlabel="log(1 + supplied count)",
        ylabel="log(1 + historical full count)",
        title="Count agreement across 2.56M cells",
    )
    ratio = old.sum(axis=0) / ref.sum(axis=0)
    axs[1].scatter(range(85), ratio, s=10, color="#385f91")
    axs[1].axhline(1, lw=1, color="#bbbbbb")
    axs[1].set(
        xlabel="Library (fixed matrix column order)",
        ylabel="Historical / supplied library total",
        title="Small systematic source differences remain",
    )
    fig.tight_layout()
    fig.savefig(a.out / "count-source-agreement.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
