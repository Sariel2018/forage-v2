#!/usr/bin/env python3
"""Generate all figures and tables for the Forage paper."""

import os
import csv
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = "/Users/xiehuaqing/Documents/code_workplace/auto_data_collector"
FA_RESULTS = os.path.join(BASE, "experiments_fa/fa_2011/fa_2011_results.csv")
FA_SUMMARY = os.path.join(BASE, "experiments_fa/fa_2011/fa_2011_run_summary.csv")
FA_EVOLUTION = os.path.join(BASE, "experiments_fa/fa_2011/fa_2011_evolution.csv")
WH_RESULTS = os.path.join(BASE, "experiments_whitehouse/whitehouse_trump2/whitehouse_results.csv")
WH_SUMMARY = os.path.join(BASE, "experiments_whitehouse/whitehouse_trump2/whitehouse_run_summary.csv")

FIG_DIR = os.path.join(BASE, "paper/figures")
TAB_DIR = os.path.join(BASE, "paper/tables")
os.makedirs(FIG_DIR, exist_ok=True)
os.makedirs(TAB_DIR, exist_ok=True)

# Canonical group order
GROUPS = ["SA", "M-no-eval", "M-no-iso", "M-co-eval", "M-exp", "M"]
GROUP_LABELS = ["SA", "M\\textminus no\\textminus eval", "M\\textminus no\\textminus iso",
                "M\\textminus co\\textminus eval", "M\\textminus exp", "M"]
GROUP_DISPLAY = ["SA", "M-no-eval", "M-no-iso", "M-co-eval", "M-exp", "M"]

# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 9,
    "axes.labelsize": 10,
    "axes.titlesize": 11,
    "legend.fontsize": 8,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "axes.grid": True,
    "grid.alpha": 0.3,
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def read_csv(path):
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def safe_float(v, default=None):
    if v is None or v == "" or v == "N/A":
        return default
    try:
        return float(v)
    except ValueError:
        return default


def parse_pct(v):
    """Parse a percentage string like '100.0%' or '~85-90% (text)' to float 0-1."""
    if v is None or v == "" or v == "N/A":
        return None
    v = v.strip()
    if v.endswith("%"):
        try:
            return float(v.rstrip("%")) / 100.0
        except ValueError:
            pass
    # Text like "~85-90% (text)" — return midpoint
    import re
    m = re.search(r"~?(\d+)-(\d+)%", v)
    if m:
        return (float(m.group(1)) + float(m.group(2))) / 200.0
    m = re.search(r"~?(\d+)%", v)
    if m:
        return float(m.group(1)) / 100.0
    return None


def group_stats(rows, group_col, recall_col, prec_col, f1_col, cost_col,
                skip_zero=True):
    """Compute per-group mean/min/max for recall, precision, f1, cost."""
    stats = {}
    for g in GROUPS:
        vals = {"recall": [], "precision": [], "f1": [], "cost": []}
        for r in rows:
            if r[group_col] != g:
                continue
            rec = safe_float(r[recall_col])
            pre = safe_float(r[prec_col])
            f1v = safe_float(r[f1_col])
            cst = safe_float(r[cost_col])
            if skip_zero and rec is not None and rec == 0 and pre == 0:
                continue  # skip incomplete runs
            if rec is not None:
                vals["recall"].append(rec)
            if pre is not None:
                vals["precision"].append(pre)
            if f1v is not None:
                vals["f1"].append(f1v)
            if cst is not None:
                vals["cost"].append(cst)
        s = {}
        for k in ["recall", "precision", "f1", "cost"]:
            arr = vals[k]
            if arr:
                s[k] = {"mean": np.mean(arr), "min": np.min(arr), "max": np.max(arr)}
            else:
                s[k] = {"mean": 0, "min": 0, "max": 0}
        stats[g] = s
    return stats


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
fa_rows = read_csv(FA_RESULTS)
fa_summary = read_csv(FA_SUMMARY)
wh_rows = read_csv(WH_RESULTS)
wh_summary = read_csv(WH_SUMMARY)
fa_evo = read_csv(FA_EVOLUTION)

fa_stats = group_stats(fa_rows, "group", "absolute_recall", "precision", "f1",
                       "cost_usd")
wh_stats = group_stats(wh_rows, "Group", "Recall", "Precision", "F1", "Cost")


# ===================================================================
# Figure 1: Co-evolution case (M/run_002)
# ===================================================================
def fig_co_evolution():
    evo_rows = [r for r in fa_evo
                if r["group"] == "M" and r["run"] == "run_002"
                and r["round_effective"] == "true"]
    rounds = [r["round_id"] for r in evo_rows]
    denoms = [int(r["denominator"]) for r in evo_rows]
    records = [int(r["records_total"]) for r in evo_rows]
    coverages = [float(r["coverage_estimate"]) for r in evo_rows]

    annotations = {
        "R2": "308\n(partial sitemap)",
        "R3": "551\n(incl. capsule reviews)",
        "R4": "296\n(capsule reviews excluded)",
        "R5": "295\n(dup slug fixed) \u2192 STOP",
    }

    fig, ax1 = plt.subplots(figsize=(5.5, 3.2))

    color_denom = "#2c7bb6"
    color_rec = "#d7191c"

    ax1.plot(rounds, denoms, "o-", color=color_denom, linewidth=2,
             markersize=7, label="Denominator", zorder=5)
    ax1.set_xlabel("Round")
    ax1.set_ylabel("Denominator", color=color_denom)
    ax1.tick_params(axis="y", labelcolor=color_denom)
    ax1.set_ylim(0, 650)

    for rd, dv in zip(rounds, denoms):
        ann = annotations.get(rd, "")
        yoff = 30 if dv < 400 else -50
        ax1.annotate(ann, (rd, dv), textcoords="offset points",
                     xytext=(0, yoff), fontsize=7, ha="center",
                     color=color_denom,
                     arrowprops=dict(arrowstyle="-", color=color_denom,
                                     lw=0.5) if abs(yoff) > 35 else None)

    ax2 = ax1.twinx()
    ax2.bar(rounds, records, alpha=0.35, color=color_rec, width=0.4,
            label="Records collected", zorder=2)
    ax2.set_ylabel("Cumulative records", color=color_rec)
    ax2.tick_params(axis="y", labelcolor=color_rec)
    ax2.set_ylim(0, 400)

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left",
               framealpha=0.9, fontsize=7)

    ax1.set_title("Co-Evolution of Denominator in M/run\\_002 (FA 2011)",
                  fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "co_evolution_case.pdf"))
    plt.close(fig)
    print("  -> co_evolution_case.pdf")


# ===================================================================
# Figure 2 & 3: Main results (grouped bars)
# ===================================================================
def fig_main_results(stats, benchmark_name, filename):
    x = np.arange(len(GROUPS))
    width = 0.22

    fig, ax = plt.subplots(figsize=(5.5, 3.0))

    for i, (metric, color) in enumerate([
        ("recall", "#4575b4"), ("precision", "#fc8d59"), ("f1", "#91cf60")
    ]):
        means = [stats[g][metric]["mean"] * 100 for g in GROUPS]
        mins_ = [stats[g][metric]["min"] * 100 for g in GROUPS]
        maxs_ = [stats[g][metric]["max"] * 100 for g in GROUPS]
        yerr_lo = [m - lo for m, lo in zip(means, mins_)]
        yerr_hi = [hi - m for m, hi in zip(means, maxs_)]

        ax.bar(x + (i - 1) * width, means, width, color=color,
               label=metric.capitalize(),
               yerr=[yerr_lo, yerr_hi], capsize=2, error_kw={"lw": 0.8})

    ax.set_xticks(x)
    ax.set_xticklabels(GROUP_DISPLAY, rotation=15, ha="right")
    ax.set_ylabel("Score (%)")
    ax.set_ylim(0, 110)
    ax.legend(fontsize=7, ncol=3, loc="upper left")
    ax.set_title(f"Main Results \u2014 {benchmark_name}")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, filename))
    plt.close(fig)
    print(f"  -> {filename}")


# ===================================================================
# Figure 4: Denominator blindness
# ===================================================================
def fig_denominator_blindness():
    """Paired bars: self-reported vs absolute recall (FA only)."""
    fig, ax = plt.subplots(figsize=(5.5, 3.0))
    x = np.arange(len(GROUPS))
    width = 0.32

    self_rep = []
    abs_recall = []

    for g in GROUPS:
        g_rows = [r for r in fa_rows if r["group"] == g]
        # Absolute recall
        recalls = [safe_float(r["absolute_recall"]) for r in g_rows
                   if safe_float(r["absolute_recall"]) is not None
                   and safe_float(r["absolute_recall"]) > 0]
        abs_recall.append(np.mean(recalls) * 100 if recalls else 0)

        # Self-reported
        srs = []
        for r in g_rows:
            v = parse_pct(r["self_reported_coverage"])
            if v is not None and safe_float(r["absolute_recall"], 0) > 0:
                srs.append(v)
        self_rep.append(np.mean(srs) * 100 if srs else 0)

    c_self = "#fdae61"
    c_abs = "#2c7bb6"

    ax.bar(x - width / 2, self_rep, width, color=c_self,
           label="Self-reported coverage", edgecolor="white", linewidth=0.5)
    ax.bar(x + width / 2, abs_recall, width, color=c_abs,
           label="Absolute recall (ground truth)", edgecolor="white",
           linewidth=0.5)

    ax.set_xticks(x)
    ax.set_xticklabels(GROUP_DISPLAY, rotation=15, ha="right")
    ax.set_ylabel("Coverage / Recall (%)")
    ax.set_ylim(0, 115)
    ax.legend(fontsize=7, loc="upper left")
    ax.set_title("Denominator Blindness (FA 2011)")

    # Add gap annotations
    for i in range(len(GROUPS)):
        gap = self_rep[i] - abs_recall[i]
        if abs(gap) > 2:
            y_top = max(self_rep[i], abs_recall[i]) + 2
            ax.annotate(f"gap={gap:+.0f}pp", (x[i], y_top), fontsize=6,
                        ha="center", color="red" if gap > 0 else "blue")

    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "denominator_blindness.pdf"))
    plt.close(fig)
    print("  -> denominator_blindness.pdf")


# ===================================================================
# Figure 5: Cost comparison
# ===================================================================
def fig_cost_comparison():
    fig, ax = plt.subplots(figsize=(5.5, 3.0))
    x = np.arange(len(GROUPS))
    width = 0.32

    wh_costs = [wh_stats[g]["cost"]["mean"] for g in GROUPS]
    fa_costs = [fa_stats[g]["cost"]["mean"] for g in GROUPS]

    ax.bar(x - width / 2, wh_costs, width, color="#4575b4",
           label="White House", edgecolor="white", linewidth=0.5)
    ax.bar(x + width / 2, fa_costs, width, color="#fc8d59",
           label="Foreign Affairs", edgecolor="white", linewidth=0.5)

    ax.set_xticks(x)
    ax.set_xticklabels(GROUP_DISPLAY, rotation=15, ha="right")
    ax.set_ylabel("Cost (USD)")
    ax.legend(fontsize=7)
    ax.set_title("Average Cost per Group")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "cost_comparison.pdf"))
    plt.close(fig)
    print("  -> cost_comparison.pdf")


# ===================================================================
# Figure 6: Coverage gap heatmap (FA)
# ===================================================================
def fig_coverage_gap_heatmap():
    # Determine max runs across all groups
    max_runs = 4
    run_labels = [f"run_{i+1:03d}" for i in range(max_runs)]

    # Build matrix
    matrix = np.full((len(GROUPS), max_runs), np.nan)

    for gi, g in enumerate(GROUPS):
        g_rows = [r for r in fa_rows if r["group"] == g]
        for r in g_rows:
            run = r["run"]
            ri = int(run.split("_")[1]) - 1
            if ri >= max_runs:
                continue
            recall = safe_float(r["absolute_recall"])
            if recall is None or recall == 0:
                continue
            if g == "SA":
                # SA self-reported ~87.5%
                sr = 0.875
            else:
                sr = parse_pct(r["self_reported_coverage"])
                if sr is None:
                    sr_f = safe_float(r["coverage_gap"])
                    if sr_f is not None:
                        matrix[gi, ri] = sr_f
                        continue
                    continue
            matrix[gi, ri] = sr - recall

    fig, ax = plt.subplots(figsize=(4.5, 3.5))
    vmax = np.nanmax(np.abs(matrix[~np.isnan(matrix)])) if np.any(~np.isnan(matrix)) else 1
    vmax = max(vmax, 0.1)

    cmap = plt.cm.RdBu_r
    norm = mcolors.TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax)

    im = ax.imshow(matrix, cmap=cmap, norm=norm, aspect="auto")

    ax.set_xticks(np.arange(max_runs))
    ax.set_xticklabels([f"Run {i+1}" for i in range(max_runs)])
    ax.set_yticks(np.arange(len(GROUPS)))
    ax.set_yticklabels(GROUP_DISPLAY)

    # Annotate
    for gi in range(len(GROUPS)):
        for ri in range(max_runs):
            v = matrix[gi, ri]
            if np.isnan(v):
                ax.text(ri, gi, "--", ha="center", va="center", fontsize=7,
                        color="gray")
            else:
                color = "white" if abs(v) > vmax * 0.6 else "black"
                ax.text(ri, gi, f"{v:+.2f}", ha="center", va="center",
                        fontsize=7, color=color)

    cbar = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cbar.set_label("Coverage gap\n(self-reported \u2212 recall)", fontsize=8)
    ax.set_title("Coverage Gap Heatmap (FA 2011)", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "coverage_gap_heatmap.pdf"))
    plt.close(fig)
    print("  -> coverage_gap_heatmap.pdf")


# ===================================================================
# Table 1: Main results
# ===================================================================
def tab_main_results():
    lines = []
    lines.append(r"\begin{table*}[t]")
    lines.append(r"\centering")
    lines.append(r"\caption{Main results across both benchmarks. "
                 r"Values are averaged across runs; best per column in \textbf{bold}.}")
    lines.append(r"\label{tab:main-results}")
    lines.append(r"\small")
    lines.append(r"\begin{tabular}{l|cccc|cccc}")
    lines.append(r"\toprule")
    lines.append(r" & \multicolumn{4}{c|}{\textbf{White House}} "
                 r"& \multicolumn{4}{c}{\textbf{Foreign Affairs}} \\")
    lines.append(r"\textbf{Group} & Recall & Prec. & F1 & Cost "
                 r"& Recall & Prec. & F1 & Cost \\")
    lines.append(r"\midrule")

    # Find best per column
    all_vals = {col: [] for col in ["wh_r", "wh_p", "wh_f", "wh_c",
                                     "fa_r", "fa_p", "fa_f", "fa_c"]}
    for g in GROUPS:
        all_vals["wh_r"].append(wh_stats[g]["recall"]["mean"])
        all_vals["wh_p"].append(wh_stats[g]["precision"]["mean"])
        all_vals["wh_f"].append(wh_stats[g]["f1"]["mean"])
        all_vals["wh_c"].append(wh_stats[g]["cost"]["mean"])
        all_vals["fa_r"].append(fa_stats[g]["recall"]["mean"])
        all_vals["fa_p"].append(fa_stats[g]["precision"]["mean"])
        all_vals["fa_f"].append(fa_stats[g]["f1"]["mean"])
        all_vals["fa_c"].append(fa_stats[g]["cost"]["mean"])

    # For metrics: higher is better. For cost: lower is better.
    best = {}
    for col in ["wh_r", "wh_p", "wh_f", "fa_r", "fa_p", "fa_f"]:
        best[col] = max(all_vals[col])
    for col in ["wh_c", "fa_c"]:
        # Exclude SA cost = 0 edge case
        nonzero = [v for v in all_vals[col] if v > 0]
        best[col] = min(nonzero) if nonzero else 0

    def fmt_pct(v, best_v, higher=True):
        s = f"{v*100:.1f}"
        is_best = (abs(v - best_v) < 1e-6)
        return r"\textbf{" + s + "}" if is_best else s

    def fmt_cost(v, best_v):
        s = f"\\${v:.2f}"
        is_best = (abs(v - best_v) < 0.005) and v > 0
        return r"\textbf{" + s + "}" if is_best else s

    for i, g in enumerate(GROUPS):
        label = g.replace("-", "\\textminus ")
        row_vals = [
            fmt_pct(wh_stats[g]["recall"]["mean"], best["wh_r"]),
            fmt_pct(wh_stats[g]["precision"]["mean"], best["wh_p"]),
            fmt_pct(wh_stats[g]["f1"]["mean"], best["wh_f"]),
            fmt_cost(wh_stats[g]["cost"]["mean"], best["wh_c"]),
            fmt_pct(fa_stats[g]["recall"]["mean"], best["fa_r"]),
            fmt_pct(fa_stats[g]["precision"]["mean"], best["fa_p"]),
            fmt_pct(fa_stats[g]["f1"]["mean"], best["fa_f"]),
            fmt_cost(fa_stats[g]["cost"]["mean"], best["fa_c"]),
        ]
        lines.append(f"{label} & " + " & ".join(row_vals) + r" \\")

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table*}")

    path = os.path.join(TAB_DIR, "main_results.tex")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("  -> main_results.tex")


# ===================================================================
# Table 2: Ablation design
# ===================================================================
def tab_ablation_design():
    lines = []
    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(r"\caption{Ablation study design. Each row removes or freezes "
                 r"one component from the full Forage system (M).}")
    lines.append(r"\label{tab:ablation}")
    lines.append(r"\small")
    lines.append(r"\begin{tabular}{l|ccccc|l}")
    lines.append(r"\toprule")
    lines.append(r"\textbf{Group} & \rotatebox{70}{Rounds} "
                 r"& \rotatebox{70}{Separation} & \rotatebox{70}{Isolation} "
                 r"& \rotatebox{70}{Co-evolution} & \rotatebox{70}{Knowledge} "
                 r"& \textbf{Tests} \\")
    lines.append(r"\midrule")

    configs = [
        ("SA",         ["-", "-", "-", "-", "-"], "Baseline"),
        ("M\\textminus no\\textminus eval",
                       [r"\cmark", "-", "-", r"\cmark", r"\cmark"],
                       "Planner self-evaluates"),
        ("M\\textminus no\\textminus iso",
                       [r"\cmark", r"\cmark", "-", r"\cmark", r"\cmark"],
                       "No method isolation"),
        ("M\\textminus co\\textminus eval",
                       [r"\cmark", r"\cmark", r"\cmark", "frozen", r"\cmark"],
                       "Frozen denominator"),
        ("M\\textminus exp",
                       [r"\cmark", r"\cmark", r"\cmark", r"\cmark", "-"],
                       "No experience KB"),
        ("M",          [r"\cmark", r"\cmark", r"\cmark", r"\cmark", r"\cmark"],
                       "Full Forage"),
    ]

    for name, flags, tests in configs:
        row = f"{name} & " + " & ".join(flags) + f" & {tests}" + r" \\"
        lines.append(row)

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")

    path = os.path.join(TAB_DIR, "ablation_design.tex")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("  -> ablation_design.tex")


# ===================================================================
# Table 3: Denominator evolution
# ===================================================================
def tab_denominator_evolution():
    lines = []
    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(r"\caption{Denominator evolution paths for selected FA 2011 runs. "
                 r"Ground truth = 295.}")
    lines.append(r"\label{tab:denom-evolution}")
    lines.append(r"\small")
    lines.append(r"\begin{tabular}{ll|l|c}")
    lines.append(r"\toprule")
    lines.append(r"\textbf{Group} & \textbf{Run} & "
                 r"\textbf{Denominator path} & \textbf{Final acc.} \\")
    lines.append(r"\midrule")

    # Get paths from summary
    summary_map = {}
    for r in fa_summary:
        key = (r["group"], r["run"])
        summary_map[key] = r

    selected = [
        ("M", "run_002", "Perfect convergence"),
        ("M", "run_004", "Expanding (incl. capsule)"),
        ("M-co-eval", "run_001", "Frozen"),
        ("M-no-eval", "run_001", "Self-serving"),
        ("M-no-iso", "run_002", "Gradual expansion"),
    ]

    for g, run, note in selected:
        r = summary_map.get((g, run))
        if r is None:
            continue
        path = r["denominator_evolution_path"].replace("->", r"\to ")
        final_d = safe_float(r["final_denominator"], 0)
        acc = final_d / 295.0 if final_d > 0 else 0
        g_label = g.replace("-", "\\textminus ")
        run_label = run.replace("_", "\\_")
        lines.append(f"{g_label} & {run_label} & "
                     f"${path}$ & {acc:.2f} \\\\")

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")

    path_out = os.path.join(TAB_DIR, "denominator_evolution.tex")
    with open(path_out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("  -> denominator_evolution.tex")


# ===================================================================
# Main
# ===================================================================
if __name__ == "__main__":
    print("Generating figures...")
    fig_co_evolution()
    fig_main_results(fa_stats, "Foreign Affairs 2011", "main_results_fa.pdf")
    fig_main_results(wh_stats, "White House Announcements", "main_results_whitehouse.pdf")
    fig_denominator_blindness()
    fig_cost_comparison()
    fig_coverage_gap_heatmap()

    print("\nGenerating tables...")
    tab_main_results()
    tab_ablation_design()
    tab_denominator_evolution()

    print("\nDone. All outputs saved to:")
    print(f"  Figures: {FIG_DIR}/")
    print(f"  Tables:  {TAB_DIR}/")
