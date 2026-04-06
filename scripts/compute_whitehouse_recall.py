#!/usr/bin/env python3
"""
Compute absolute recall for all Whitehouse Trump2 experiment runs against ground truth.

Ground truth: M/run_001's dataset (1695 unique announcements).
Matching strategy: exact URL match (whitehouse.gov URLs are canonical).

Usage: python scripts/compute_whitehouse_recall.py
"""

import csv
import json
import os
import re
import html
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse

# ── Paths ──────────────────────────────────────────────────────────────
BASE_DIR = Path("/Users/xiehuaqing/Documents/code_workplace/auto_data_collector/experiments_whitehouse/whitehouse_trump2")
GT_RUN_DIR = BASE_DIR / "M" / "run_001" / "whitehouse_trump2" / "workspace" / "dataset"
GT_SIZE = 1695  # unique URLs in M/run_001

GROUP_ORDER = ["SA", "M-no-eval", "M-no-iso", "M-co-eval", "M-exp", "M"]


# ── Normalization helpers ──────────────────────────────────────────────

def normalize_url(url: str) -> str:
    """Normalize a whitehouse.gov URL for matching."""
    if not url:
        return ""
    url = url.strip()
    # Parse and reconstruct
    parsed = urlparse(url)
    path = parsed.path.strip("/").lower()
    # Remove trailing index.html etc
    path = re.sub(r'/index\.html?$', '', path)
    # Remove duplicate slashes
    path = re.sub(r'/+', '/', path)
    return path


def extract_slug(url: str) -> str:
    """Extract the last path component (slug) from a URL."""
    if not url:
        return ""
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    slug = parts[-1] if parts else ""
    return slug.lower()


def normalize_title(title: str) -> str:
    """Normalize a title for matching."""
    if not title:
        return ""
    title = html.unescape(title)
    title = title.lower().strip()
    title = re.sub(r'[^\w\s]', '', title)
    title = re.sub(r'\s+', ' ', title).strip()
    return title


def get_record_url(record: dict) -> str:
    """Extract URL from record, handling different field names."""
    return (record.get("url", "")
            or record.get("original_url", "")
            or record.get("source_url", "")
            or "")


def get_record_title(record: dict) -> str:
    """Extract title from record."""
    return record.get("title", "") or ""


# ── Load ground truth ─────────────────────────────────────────────────

def load_ground_truth():
    """Load GT records from M/run_001 and build lookup structures."""
    records = []
    for f in GT_RUN_DIR.iterdir():
        if f.suffix == ".jsonl":
            with open(f) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

    # Deduplicate by URL
    seen_urls = set()
    gt_records = []
    for r in records:
        url = get_record_url(r)
        norm = normalize_url(url)
        if norm and norm not in seen_urls:
            seen_urls.add(norm)
            gt_records.append(r)

    # Build lookup structures
    gt_urls = {}       # normalized_url -> index
    gt_slugs = {}      # slug -> index
    gt_titles = {}     # normalized_title -> index

    for i, r in enumerate(gt_records):
        url = get_record_url(r)
        title = get_record_title(r)
        norm_url = normalize_url(url)
        slug = extract_slug(url)
        norm_title = normalize_title(title)

        if norm_url:
            gt_urls[norm_url] = i
        if slug:
            gt_slugs[slug] = i
        if norm_title:
            gt_titles[norm_title] = i

    return gt_records, gt_urls, gt_slugs, gt_titles


# ── Load run dataset ──────────────────────────────────────────────────

def find_dataset_files(run_dir: Path) -> list:
    """Find all dataset files in a run directory."""
    dataset_dir = run_dir / "whitehouse_trump2" / "workspace" / "dataset"
    files = []
    skip_names = {"url_index.json", "metrics.json", "summary.json"}
    if dataset_dir.is_dir():
        for f in dataset_dir.iterdir():
            if f.suffix in (".jsonl", ".json") and f.name not in skip_names:
                files.append(f)
    return files


def load_records_from_file(filepath: Path) -> list:
    """Load records from a .jsonl or .json file."""
    records = []
    try:
        if filepath.suffix == ".jsonl":
            with open(filepath) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        elif filepath.suffix == ".json":
            with open(filepath) as f:
                data = json.load(f)
                if isinstance(data, list):
                    records = [item for item in data if isinstance(item, dict)]
                elif isinstance(data, dict):
                    if "title" in data or "url" in data:
                        records = [data]
                    else:
                        for v in data.values():
                            if isinstance(v, dict) and ("title" in v or "url" in v):
                                records.append(v)
    except Exception as e:
        print(f"  Warning: failed to load {filepath}: {e}")
    return records


def load_run_result(run_dir: Path) -> dict:
    """Load run_result.json if it exists."""
    for path in [
        run_dir / "run_result.json",
        run_dir / "whitehouse_trump2" / "run_result.json",
    ]:
        if path.exists():
            with open(path) as f:
                return json.load(f)
    return {}


def load_metrics(run_dir: Path) -> dict:
    """Load metrics.json if it exists."""
    for path in [
        run_dir / "whitehouse_trump2" / "metrics.json",
        run_dir / "whitehouse_trump2" / "workspace" / "metrics.json",
    ]:
        if path.exists():
            with open(path) as f:
                return json.load(f)
    return {}


# ── Matching ──────────────────────────────────────────────────────────

def match_records(run_records, gt_urls, gt_slugs, gt_titles, gt_records):
    """
    Match run records against ground truth.
    Returns (matched_gt_indices, match_details).
    """
    matched_gt = set()
    match_details = {
        "by_url": 0,
        "by_slug": 0,
        "by_title_exact": 0,
        "by_title_fuzzy": 0,
    }

    for rec in run_records:
        url = get_record_url(rec)
        title = get_record_title(rec)
        norm_url = normalize_url(url)
        slug = extract_slug(url)
        norm_title = normalize_title(title)

        # Strategy 1: Exact URL path match
        if norm_url and norm_url in gt_urls:
            idx = gt_urls[norm_url]
            if idx not in matched_gt:
                matched_gt.add(idx)
                match_details["by_url"] += 1
            continue

        # Strategy 2: Slug match (for URLs with slightly different paths)
        if slug and slug in gt_slugs:
            idx = gt_slugs[slug]
            if idx not in matched_gt:
                matched_gt.add(idx)
                match_details["by_slug"] += 1
            continue

        # Strategy 3: Exact title match (normalized)
        if norm_title and norm_title in gt_titles:
            idx = gt_titles[norm_title]
            if idx not in matched_gt:
                matched_gt.add(idx)
                match_details["by_title_exact"] += 1
            continue

        # Strategy 4: Fuzzy title match
        if norm_title and len(norm_title) > 10:
            best_ratio = 0
            best_idx = -1
            for gt_title, gt_idx in gt_titles.items():
                if gt_idx in matched_gt:
                    continue
                ratio = SequenceMatcher(None, norm_title, gt_title).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_idx = gt_idx
            if best_ratio > 0.90 and best_idx >= 0:
                matched_gt.add(best_idx)
                match_details["by_title_fuzzy"] += 1

    return matched_gt, match_details


# ── Main ──────────────────────────────────────────────────────────────

def main():
    print("Loading ground truth from M/run_001...")
    gt_records, gt_urls, gt_slugs, gt_titles = load_ground_truth()
    print(f"  Ground truth: {len(gt_records)} records, {len(gt_urls)} URLs, "
          f"{len(gt_slugs)} slugs, {len(gt_titles)} titles")
    assert len(gt_records) == GT_SIZE, (
        f"Expected {GT_SIZE} GT records after filtering, got {len(gt_records)}"
    )
    print()

    # Collect results
    all_results = []

    for group in GROUP_ORDER:
        group_dir = BASE_DIR / group
        if not group_dir.is_dir():
            print(f"Skipping {group}: directory not found")
            continue

        # Only include standard run directories (run_001, run_002, run_003)
        run_dirs = sorted([d for d in group_dir.glob("run_*")
                          if re.match(r'^run_\d{3}$', d.name)])
        if not run_dirs:
            print(f"Skipping {group}: no runs found")
            continue

        for run_dir in run_dirs:
            run_name = run_dir.name
            print(f"Processing {group}/{run_name}...")

            # Load run result (top-level has cost/duration/coverage)
            run_result = load_run_result(run_dir)
            metrics = load_metrics(run_dir)

            # Self-reported coverage
            self_coverage = run_result.get("final_coverage", None)
            if isinstance(self_coverage, str):
                # SA group has text description - extract percentage
                pct_match = re.search(r'~?(\d+)(?:-(\d+))?%', self_coverage)
                if pct_match:
                    if pct_match.group(2):
                        # Range like "85-90%", take midpoint
                        lo = int(pct_match.group(1))
                        hi = int(pct_match.group(2))
                        self_coverage_str = f"~{lo}-{hi}% (text)"
                        self_coverage_num = (lo + hi) / 200  # midpoint as fraction
                    else:
                        val = int(pct_match.group(1))
                        self_coverage_str = f"~{val}% (text)"
                        self_coverage_num = val / 100
                else:
                    self_coverage_str = "text"
                    self_coverage_num = None
            elif self_coverage is not None:
                self_coverage_str = f"{self_coverage*100:.1f}%"
                self_coverage_num = self_coverage
            else:
                self_coverage_str = "N/A"
                self_coverage_num = None

            # System denominator
            sys_denom = metrics.get("denominator", metrics.get("total_expected", None))
            if sys_denom is None:
                sys_denom = run_result.get("total_records", "N/A")

            # Cost and duration
            cost = run_result.get("total_cost_usd", None)
            duration = run_result.get("duration_seconds", None)

            # Load dataset
            dataset_files = find_dataset_files(run_dir)
            all_records = []
            for f in dataset_files:
                recs = load_records_from_file(f)
                all_records.extend(recs)
                print(f"  Loaded {len(recs)} records from {f.name}")

            if not all_records:
                print(f"  WARNING: No records found!")
                all_results.append({
                    "group": group,
                    "run": run_name,
                    "self_coverage": self_coverage_str,
                    "self_coverage_num": self_coverage_num,
                    "sys_denominator": sys_denom,
                    "total_records": 0,
                    "unique_records": 0,
                    "matched": 0,
                    "absolute_recall": 0.0,
                    "precision": 0.0,
                    "f1": 0.0,
                    "denom_accuracy": None,
                    "coverage_gap": None,
                    "match_details": {},
                    "cost": cost,
                    "duration": duration,
                })
                continue

            # Deduplicate by URL
            seen_urls = set()
            deduped_records = []
            for r in all_records:
                url = get_record_url(r)
                norm = normalize_url(url)
                title = normalize_title(get_record_title(r))
                key = norm if norm else title
                if key and key not in seen_urls:
                    seen_urls.add(key)
                    deduped_records.append(r)
                elif not key:
                    deduped_records.append(r)  # keep records without identifiers

            print(f"  Total: {len(all_records)}, Deduped: {len(deduped_records)}")

            # Match against ground truth
            matched_gt, match_details = match_records(
                deduped_records, gt_urls, gt_slugs, gt_titles, gt_records
            )

            absolute_recall = len(matched_gt) / GT_SIZE
            coverage_gap = None
            if self_coverage_num is not None:
                coverage_gap = self_coverage_num - absolute_recall

            print(f"  Matched: {len(matched_gt)}/{GT_SIZE} = {absolute_recall*100:.1f}%")
            print(f"  Match breakdown: {match_details}")

            # Precision: of all unique collected records, how many matched GT?
            precision = len(matched_gt) / len(deduped_records) if deduped_records else 0.0
            # F1 = harmonic mean of precision and recall
            f1 = (2 * precision * absolute_recall / (precision + absolute_recall)
                   if (precision + absolute_recall) > 0 else 0.0)
            # Denominator accuracy
            denom_accuracy = None
            if isinstance(sys_denom, (int, float)) and sys_denom > 0:
                denom_accuracy = sys_denom / GT_SIZE

            all_results.append({
                "group": group,
                "run": run_name,
                "self_coverage": self_coverage_str,
                "self_coverage_num": self_coverage_num,
                "sys_denominator": sys_denom,
                "total_records": len(all_records),
                "unique_records": len(deduped_records),
                "matched": len(matched_gt),
                "absolute_recall": absolute_recall,
                "precision": precision,
                "f1": f1,
                "denom_accuracy": denom_accuracy,
                "coverage_gap": coverage_gap,
                "match_details": match_details,
                "cost": cost,
                "duration": duration,
            })

            print()

    # ── Output table ──────────────────────────────────────────────────

    print("\n" + "=" * 160)
    print(f"ABSOLUTE RECALL RESULTS (Ground Truth = M/run_001, N = {GT_SIZE})")
    print("=" * 160)

    header = (
        f"{'Group':<12} {'Run':<8} {'Self-Cov':>12} {'Denom':>7} {'DenomAcc':>9} "
        f"{'Total':>7} {'Unique':>7} "
        f"{'Matched':>8} {'Recall':>8} {'Precision':>10} {'F1':>8} {'Gap':>10} "
        f"{'Cost':>8} {'Duration':>10}"
    )
    print(header)
    print("-" * 160)

    group_results = defaultdict(list)

    for r in all_results:
        gap_str = f"{r['coverage_gap']*100:+.1f}pp" if r['coverage_gap'] is not None else "N/A"
        da = r.get('denom_accuracy')
        da_str = f"{da:.2f}x" if da is not None else "N/A"
        cost_str = f"${r['cost']:.2f}" if r['cost'] is not None else "N/A"
        dur_str = f"{r['duration']/60:.1f}m" if r['duration'] is not None else "N/A"

        print(
            f"{r['group']:<12} {r['run']:<8} {r['self_coverage']:>12} "
            f"{str(r['sys_denominator']):>7} {da_str:>9} "
            f"{r['total_records']:>7} {r['unique_records']:>7} "
            f"{r['matched']:>8} {r['absolute_recall']*100:>7.1f}% "
            f"{r['precision']*100:>9.1f}% {r['f1']*100:>7.1f}% {gap_str:>10} "
            f"{cost_str:>8} {dur_str:>10}"
        )
        group_results[r['group']].append(r)

    # Group averages
    print("-" * 160)
    print("\nGROUP AVERAGES:")
    print(f"{'Group':<12} {'Avg Recall':>10} {'Avg Prec':>10} {'Avg F1':>8} "
          f"{'Avg DenAcc':>11} {'Min Recall':>10} {'Max Recall':>10} "
          f"{'Avg Self-Cov':>12} {'Avg Gap':>10} {'Avg Cost':>10} {'Runs':>5}")
    print("-" * 130)

    group_summaries = {}
    for group in GROUP_ORDER:
        runs = group_results.get(group, [])
        if not runs:
            continue
        recalls = [r['absolute_recall'] for r in runs]
        precisions = [r['precision'] for r in runs]
        f1s = [r['f1'] for r in runs]
        denom_accs = [r['denom_accuracy'] for r in runs if r.get('denom_accuracy') is not None]
        costs = [r['cost'] for r in runs if r.get('cost') is not None]
        durations = [r['duration'] for r in runs if r.get('duration') is not None]
        avg_recall = sum(recalls) / len(recalls)
        avg_precision = sum(precisions) / len(precisions)
        avg_f1 = sum(f1s) / len(f1s)
        avg_denom_acc = sum(denom_accs) / len(denom_accs) if denom_accs else None
        avg_cost = sum(costs) / len(costs) if costs else None
        avg_duration = sum(durations) / len(durations) if durations else None
        min_recall = min(recalls)
        max_recall = max(recalls)

        self_covs = [r['self_coverage_num'] for r in runs if r['self_coverage_num'] is not None]
        avg_self = sum(self_covs) / len(self_covs) if self_covs else None
        avg_gap = avg_self - avg_recall if avg_self is not None else None

        avg_self_str = f"{avg_self*100:.1f}%" if avg_self is not None else "N/A"
        avg_gap_str = f"{avg_gap*100:+.1f}pp" if avg_gap is not None else "N/A"
        da_str = f"{avg_denom_acc:.2f}x" if avg_denom_acc is not None else "N/A"
        cost_str = f"${avg_cost:.2f}" if avg_cost is not None else "N/A"

        print(
            f"{group:<12} {avg_recall*100:>9.1f}% {avg_precision*100:>9.1f}% "
            f"{avg_f1*100:>7.1f}% {da_str:>11} {min_recall*100:>9.1f}% "
            f"{max_recall*100:>9.1f}% {avg_self_str:>12} {avg_gap_str:>10} "
            f"{cost_str:>10} {len(runs):>5}"
        )

        group_summaries[group] = {
            "avg_recall": avg_recall,
            "avg_precision": avg_precision,
            "avg_f1": avg_f1,
            "avg_denom_accuracy": avg_denom_acc,
            "min_recall": min_recall,
            "max_recall": max_recall,
            "avg_self_coverage": avg_self,
            "avg_gap": avg_gap,
            "avg_cost": avg_cost,
            "avg_duration": avg_duration,
            "n_runs": len(runs),
        }

    # ── Save markdown ─────────────────────────────────────────────────

    md_path = BASE_DIR / "absolute_recall.md"
    with open(md_path, "w") as f:
        f.write("# Whitehouse Trump2 Absolute Recall Results\n\n")
        f.write(f"Ground truth: M/run_001 dataset ({GT_SIZE} unique announcements from whitehouse.gov)\n\n")

        f.write("## Per-Run Results\n\n")
        f.write("| Group | Run | Self-Reported | Denom | DenomAcc | Total | Unique | "
                "Matched | Recall | Precision | F1 | Gap | Cost | Duration |\n")
        f.write("|-------|-----|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|\n")

        for r in all_results:
            gap_str = f"{r['coverage_gap']*100:+.1f}pp" if r['coverage_gap'] is not None else "N/A"
            da = r.get('denom_accuracy')
            da_str = f"{da:.2f}x" if da is not None else "N/A"
            cost_str = f"${r['cost']:.2f}" if r['cost'] is not None else "N/A"
            dur_str = f"{r['duration']/60:.1f}m" if r['duration'] is not None else "N/A"
            f.write(
                f"| {r['group']} | {r['run']} | {r['self_coverage']} | "
                f"{r['sys_denominator']} | {da_str} | "
                f"{r['total_records']} | {r['unique_records']} | "
                f"{r['matched']} | **{r['absolute_recall']*100:.1f}%** | "
                f"{r['precision']*100:.1f}% | {r['f1']*100:.1f}% | {gap_str} | "
                f"{cost_str} | {dur_str} |\n"
            )

        f.write("\n## Group Averages\n\n")
        f.write("| Group | Avg Recall | Avg Precision | Avg F1 | Avg DenomAcc | "
                "Min Recall | Max Recall | Avg Self-Cov | Avg Gap | Avg Cost | Runs |\n")
        f.write("|-------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|\n")

        for group in GROUP_ORDER:
            if group not in group_summaries:
                continue
            s = group_summaries[group]
            avg_self_str = f"{s['avg_self_coverage']*100:.1f}%" if s['avg_self_coverage'] is not None else "N/A"
            avg_gap_str = f"{s['avg_gap']*100:+.1f}pp" if s['avg_gap'] is not None else "N/A"
            da_str = f"{s['avg_denom_accuracy']:.2f}x" if s.get('avg_denom_accuracy') is not None else "N/A"
            cost_str = f"${s['avg_cost']:.2f}" if s.get('avg_cost') is not None else "N/A"
            f.write(
                f"| **{group}** | **{s['avg_recall']*100:.1f}%** | "
                f"{s['avg_precision']*100:.1f}% | {s['avg_f1']*100:.1f}% | "
                f"{da_str} | {s['min_recall']*100:.1f}% | {s['max_recall']*100:.1f}% | "
                f"{avg_self_str} | {avg_gap_str} | {cost_str} | {s['n_runs']} |\n"
            )

        f.write("\n## Key Observations\n\n")
        f.write("- **Coverage Gap** = Self-Reported Coverage - Absolute Recall. "
                "Positive means the system over-estimated its coverage.\n")
        f.write("- **Denominator Blindness**: Systems with high self-reported coverage "
                "but low absolute recall are 'confidently incomplete'.\n")
        f.write(f"- Ground truth denominator: {GT_SIZE} (from M/run_001, "
                f"union of all 3 M runs = 1696)\n")
        f.write("- **Precision** = matched GT / unique collected records. "
                "Values above 100% are impossible; values below indicate non-GT records collected.\n")
        f.write("- **DenomAcc** = system's denominator estimate / GT denominator. "
                "1.00x = perfect estimate.\n")

    print(f"\nMarkdown saved to: {md_path}")

    # ── Save JSON ─────────────────────────────────────────────────────

    json_path = BASE_DIR / "absolute_recall.json"
    output = {
        "ground_truth": {
            "source": "M/run_001",
            "total_records": len(gt_records),
            "denominator": GT_SIZE,
            "description": f"{GT_SIZE} unique whitehouse.gov announcements (Jan 2025 - Apr 2026)",
        },
        "runs": [],
        "group_summaries": group_summaries,
    }

    for r in all_results:
        output["runs"].append(r)

    with open(json_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    print(f"JSON saved to: {json_path}")

    # ── Save CSV ──────────────────────────────────────────────────────

    csv_path = BASE_DIR / "whitehouse_results.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Group", "Run", "Self-Reported", "Denom", "DenomAcc",
            "Total Records", "Unique Records", "Matched", "Recall",
            "Precision", "F1", "Gap", "Cost", "Duration_sec"
        ])
        for r in all_results:
            da = r.get('denom_accuracy')
            writer.writerow([
                r['group'],
                r['run'],
                r['self_coverage'],
                r['sys_denominator'],
                f"{da:.4f}" if da is not None else "",
                r['total_records'],
                r['unique_records'],
                r['matched'],
                f"{r['absolute_recall']:.4f}",
                f"{r['precision']:.4f}",
                f"{r['f1']:.4f}",
                f"{r['coverage_gap']:.4f}" if r['coverage_gap'] is not None else "",
                f"{r['cost']:.2f}" if r['cost'] is not None else "",
                f"{r['duration']:.1f}" if r['duration'] is not None else "",
            ])

    print(f"CSV saved to: {csv_path}")


if __name__ == "__main__":
    main()
