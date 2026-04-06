#!/usr/bin/env python3
"""
Compute absolute recall for all FA 2011 experiment runs against ground truth.

Ground truth: M/run_002's dataset (295 unique article-length items).
Matching strategies: exact URL slug, normalized slug, fuzzy title match.

Usage: python scripts/compute_absolute_recall.py
"""

import json
import os
import re
import html
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse

# ── Paths ──────────────────────────────────────────────────────────────
BASE_DIR = Path("/Users/xiehuaqing/Documents/code_workplace/auto_data_collector/experiments_fa/fa_2011")
GT_DATASET = BASE_DIR / "M" / "run_002" / "fa_2011" / "workspace" / "dataset" / "articles_2011.jsonl"
GT_SIZE = 295  # known ground truth count (285 articles + 9 review-essays + 1 interview)

GROUP_ORDER = ["SA", "M-no-eval", "M-no-iso", "M-co-eval", "M-exp", "M"]


# ── Normalization helpers ──────────────────────────────────────────────

def extract_slug(url: str) -> str:
    """Extract the last path component (slug) from a URL."""
    if not url:
        return ""
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    slug = parts[-1] if parts else ""
    return slug.lower()


def normalize_slug(slug: str) -> str:
    """Further normalize a slug for fuzzy matching."""
    slug = slug.lower().strip()
    # Remove trailing numbers that might be dedup suffixes (e.g., "title-2")
    # But be careful not to strip year-like numbers
    # Remove common variations
    slug = re.sub(r'^(the-|a-|an-)', '', slug)
    # Normalize hyphens / underscores
    slug = slug.replace('_', '-')
    # Remove duplicate hyphens
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    return slug


def normalize_title(title: str) -> str:
    """Normalize a title for matching."""
    if not title:
        return ""
    # Decode HTML entities
    title = html.unescape(title)
    title = title.lower().strip()
    # Remove punctuation except spaces
    title = re.sub(r'[^\w\s]', '', title)
    # Collapse whitespace
    title = re.sub(r'\s+', ' ', title).strip()
    return title


def is_capsule_review_url(url: str) -> bool:
    """Check if URL indicates a capsule review."""
    if not url:
        return False
    url_lower = url.lower()
    return "/capsule-review/" in url_lower or "/reviews/capsule-review/" in url_lower


def is_capsule_review_record(record: dict) -> bool:
    """Check if a record is a capsule review by URL or type field."""
    url = get_record_url(record)
    if is_capsule_review_url(url):
        return True
    rec_type = (record.get("type", "") or "").lower()
    if "capsule" in rec_type:
        return True
    # Check article_type field (M/run_001 format)
    art_type = (record.get("article_type", "") or "").lower()
    if "capsule" in art_type:
        return True
    return False


def get_record_url(record: dict) -> str:
    """Extract URL from record, handling different field names."""
    return (record.get("url", "")
            or record.get("original_url", "")
            or record.get("source_url", "")
            or record.get("wayback_url", "")
            or "")


def get_record_title(record: dict) -> str:
    """Extract title from record."""
    return record.get("title", "") or ""


# ── Load ground truth ─────────────────────────────────────────────────

def load_ground_truth():
    """Load GT records and build lookup structures.

    GT = 295 unique article-length items:
    285 articles + 9 review-essays + 1 interview.
    Excludes: capsule reviews, 'other' type (anthologies), duplicates.
    """
    records = []
    with open(GT_DATASET) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))

    # Filter: exclude capsule reviews, 'other' type (anthologies)
    gt_records_raw = [
        r for r in records
        if not is_capsule_review_record(r)
        and r.get("type", "") != "other"
    ]

    # Deduplicate by slug (handles sick-man-asia duplicate)
    seen_slugs = set()
    gt_records = []
    for r in gt_records_raw:
        slug = extract_slug(get_record_url(r))
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        gt_records.append(r)

    # Build lookup structures
    gt_slugs = {}       # slug -> record
    gt_norm_slugs = {}  # normalized_slug -> record
    gt_titles = {}      # normalized_title -> record

    for r in gt_records:
        url = get_record_url(r)
        title = get_record_title(r)
        slug = extract_slug(url)
        norm_slug = normalize_slug(slug)
        norm_title = normalize_title(title)

        if slug:
            gt_slugs[slug] = r
        if norm_slug:
            gt_norm_slugs[norm_slug] = r
        if norm_title:
            gt_titles[norm_title] = r

    return gt_records, gt_slugs, gt_norm_slugs, gt_titles


# ── Load run dataset ──────────────────────────────────────────────────

def find_dataset_files(run_dir: Path) -> list:
    """Find all dataset files in a run directory."""
    # Only look in dataset/ subdirectory — not workspace/ root
    dataset_dir = run_dir / "fa_2011" / "workspace" / "dataset"
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
                    # Only keep dict items (skip plain strings like URL lists)
                    records = [item for item in data if isinstance(item, dict)]
                elif isinstance(data, dict):
                    # Could be a single record or a dict of records
                    if "title" in data or "url" in data:
                        records = [data]
                    else:
                        # Maybe values are records
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
        run_dir / "fa_2011" / "run_result.json",
    ]:
        if path.exists():
            with open(path) as f:
                return json.load(f)
    return {}


def load_metrics(run_dir: Path) -> dict:
    """Load metrics.json if it exists."""
    for path in [
        run_dir / "fa_2011" / "metrics.json",
        run_dir / "fa_2011" / "workspace" / "metrics.json",
    ]:
        if path.exists():
            with open(path) as f:
                return json.load(f)
    return {}


# ── Matching ──────────────────────────────────────────────────────────

def match_records(run_records, gt_slugs, gt_norm_slugs, gt_titles, gt_records):
    """
    Match run records against ground truth.
    Returns (matched_gt_indices, match_details).
    """
    # Build a set of GT indices for tracking
    gt_by_slug = {}       # slug -> gt_index
    gt_by_norm_slug = {}  # norm_slug -> gt_index
    gt_by_title = {}      # norm_title -> gt_index

    for i, r in enumerate(gt_records):
        url = get_record_url(r)
        title = get_record_title(r)
        slug = extract_slug(url)
        norm_slug = normalize_slug(slug)
        norm_title = normalize_title(title)

        if slug:
            gt_by_slug[slug] = i
        if norm_slug:
            gt_by_norm_slug[norm_slug] = i
        if norm_title:
            gt_by_title[norm_title] = i

    matched_gt = set()
    match_details = {
        "by_slug": 0,
        "by_norm_slug": 0,
        "by_title_exact": 0,
        "by_title_fuzzy": 0,
    }

    for rec in run_records:
        url = get_record_url(rec)
        title = get_record_title(rec)
        slug = extract_slug(url)
        norm_slug = normalize_slug(slug)
        norm_title = normalize_title(title)

        # Strategy 1: Exact slug match
        if slug and slug in gt_by_slug:
            idx = gt_by_slug[slug]
            if idx not in matched_gt:
                matched_gt.add(idx)
                match_details["by_slug"] += 1
            continue

        # Strategy 2: Normalized slug match
        if norm_slug and norm_slug in gt_by_norm_slug:
            idx = gt_by_norm_slug[norm_slug]
            if idx not in matched_gt:
                matched_gt.add(idx)
                match_details["by_norm_slug"] += 1
            continue

        # Strategy 3: Exact title match (normalized)
        if norm_title and norm_title in gt_by_title:
            idx = gt_by_title[norm_title]
            if idx not in matched_gt:
                matched_gt.add(idx)
                match_details["by_title_exact"] += 1
            continue

        # Strategy 4: Fuzzy title match
        if norm_title and len(norm_title) > 5:
            best_ratio = 0
            best_idx = -1
            for gt_title, gt_idx in gt_by_title.items():
                if gt_idx in matched_gt:
                    continue
                ratio = SequenceMatcher(None, norm_title, gt_title).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_idx = gt_idx
            if best_ratio > 0.85 and best_idx >= 0:
                matched_gt.add(best_idx)
                match_details["by_title_fuzzy"] += 1

    return matched_gt, match_details


# ── Main ──────────────────────────────────────────────────────────────

def main():
    print("Loading ground truth from M/run_002...")
    gt_records, gt_slugs, gt_norm_slugs, gt_titles = load_ground_truth()
    print(f"  Ground truth: {len(gt_records)} records, {len(gt_slugs)} slugs, "
          f"{len(gt_titles)} titles")
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

        run_dirs = sorted(group_dir.glob("run_*"))
        if not run_dirs:
            print(f"Skipping {group}: no runs found")
            continue

        for run_dir in run_dirs:
            run_name = run_dir.name
            print(f"Processing {group}/{run_name}...")

            # Load run result
            run_result = load_run_result(run_dir)
            metrics = load_metrics(run_dir)

            # Self-reported coverage
            self_coverage = run_result.get("final_coverage", None)
            if isinstance(self_coverage, str):
                # SA group has text description
                self_coverage_str = "~85-90% (text)"
                self_coverage_num = None
            elif self_coverage is not None:
                self_coverage_str = f"{self_coverage*100:.1f}%"
                self_coverage_num = self_coverage
            else:
                self_coverage_str = "N/A"
                self_coverage_num = None

            # System denominator
            sys_denom = metrics.get("denominator", run_result.get("total_records", "N/A"))

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
                    "capsule_reviews": 0,
                    "articles_raw": 0,
                    "articles_deduped": 0,
                    "matched": 0,
                    "absolute_recall": 0.0,
                    "precision": 0.0,
                    "f1": 0.0,
                    "denom_accuracy": None,
                    "coverage_gap": None,
                    "match_details": {},
                    "missed_gt": [{"title": get_record_title(gt_records[i]),
                                    "url": get_record_url(gt_records[i]),
                                    "slug": extract_slug(get_record_url(gt_records[i]))}
                                   for i in range(len(gt_records))],
                })
                continue

            # Separate capsule reviews
            capsule_records = [r for r in all_records if is_capsule_review_record(r)]
            article_records = [r for r in all_records if not is_capsule_review_record(r)]

            # Skip backup files (M-no-eval/run_003 has backup)
            # Already handled by loading all .jsonl - dedup by URL
            seen_slugs = set()
            deduped_articles = []
            for r in article_records:
                url = get_record_url(r)
                slug = extract_slug(url)
                title = normalize_title(get_record_title(r))
                key = slug if slug else title
                if key and key not in seen_slugs:
                    seen_slugs.add(key)
                    deduped_articles.append(r)
                elif not key:
                    deduped_articles.append(r)  # keep records without identifiers

            print(f"  Total: {len(all_records)}, Capsule: {len(capsule_records)}, "
                  f"Articles: {len(article_records)}, Deduped: {len(deduped_articles)}")

            # Match against ground truth
            matched_gt, match_details = match_records(
                deduped_articles, gt_slugs, gt_norm_slugs, gt_titles, gt_records
            )

            absolute_recall = len(matched_gt) / GT_SIZE
            coverage_gap = None
            if self_coverage_num is not None:
                coverage_gap = self_coverage_num - absolute_recall

            print(f"  Matched: {len(matched_gt)}/{GT_SIZE} = {absolute_recall*100:.1f}%")
            print(f"  Match breakdown: {match_details}")

            # Get missed GT articles
            missed_indices = sorted(set(range(len(gt_records))) - matched_gt)
            missed_articles = []
            for i in missed_indices:
                r = gt_records[i]
                missed_articles.append({
                    "title": get_record_title(r),
                    "url": get_record_url(r),
                    "slug": extract_slug(get_record_url(r)),
                })

            # Precision: of all collected records, how many matched GT articles?
            # Use total_records (including capsule reviews and duplicates) as denominator
            precision = len(matched_gt) / len(all_records) if all_records else 0.0
            # F1 = harmonic mean of precision and recall
            f1 = (2 * precision * absolute_recall / (precision + absolute_recall)
                   if (precision + absolute_recall) > 0 else 0.0)
            # Denominator accuracy: how close is the system's denominator to GT?
            # 1.0 = perfect, <1 = underestimated, >1 = overestimated
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
                "capsule_reviews": len(capsule_records),
                "articles_raw": len(article_records),
                "articles_deduped": len(deduped_articles),
                "matched": len(matched_gt),
                "absolute_recall": absolute_recall,
                "precision": precision,
                "f1": f1,
                "denom_accuracy": denom_accuracy,
                "coverage_gap": coverage_gap,
                "match_details": match_details,
                "missed_count": len(missed_articles),
                "missed_gt": missed_articles,
            })

            print()

    # ── Output table ──────────────────────────────────────────────────

    print("\n" + "=" * 140)
    print("ABSOLUTE RECALL RESULTS (Ground Truth = M/run_002, N = 295)")
    print("=" * 140)

    header = (
        f"{'Group':<12} {'Run':<8} {'Self-Cov':>10} {'Denom':>7} {'DenomAcc':>9} "
        f"{'Total':>7} {'Capsule':>8} "
        f"{'Matched':>8} {'Recall':>8} {'Precision':>10} {'F1':>8} {'Gap':>8}"
    )
    print(header)
    print("-" * 130)

    group_results = defaultdict(list)

    for r in all_results:
        gap_str = f"{r['coverage_gap']*100:+.1f}pp" if r['coverage_gap'] is not None else "N/A"
        da = r.get('denom_accuracy')
        da_str = f"{da:.2f}x" if da is not None else "N/A"

        print(
            f"{r['group']:<12} {r['run']:<8} {r['self_coverage']:>10} "
            f"{str(r['sys_denominator']):>7} {da_str:>9} "
            f"{r['total_records']:>7} {r['capsule_reviews']:>8} "
            f"{r['matched']:>8} {r['absolute_recall']*100:>7.1f}% "
            f"{r['precision']*100:>9.1f}% {r['f1']*100:>7.1f}% {gap_str:>8}"
        )
        group_results[r['group']].append(r)

    # Group averages
    print("-" * 140)
    print("\nGROUP AVERAGES:")
    print(f"{'Group':<12} {'Avg Recall':>10} {'Avg Prec':>10} {'Avg F1':>8} "
          f"{'Avg DenAcc':>11} {'Min Recall':>10} {'Max Recall':>10} {'Avg Self-Cov':>12} {'Avg Gap':>10} {'Runs':>5}")
    print("-" * 115)

    group_summaries = {}
    for group in GROUP_ORDER:
        runs = group_results.get(group, [])
        if not runs:
            continue
        recalls = [r['absolute_recall'] for r in runs]
        precisions = [r['precision'] for r in runs]
        f1s = [r['f1'] for r in runs]
        denom_accs = [r['denom_accuracy'] for r in runs if r.get('denom_accuracy') is not None]
        avg_recall = sum(recalls) / len(recalls)
        avg_precision = sum(precisions) / len(precisions)
        avg_f1 = sum(f1s) / len(f1s)
        avg_denom_acc = sum(denom_accs) / len(denom_accs) if denom_accs else None
        min_recall = min(recalls)
        max_recall = max(recalls)

        self_covs = [r['self_coverage_num'] for r in runs if r['self_coverage_num'] is not None]
        avg_self = sum(self_covs) / len(self_covs) if self_covs else None
        avg_gap = avg_self - avg_recall if avg_self is not None else None

        avg_self_str = f"{avg_self*100:.1f}%" if avg_self is not None else "N/A"
        avg_gap_str = f"{avg_gap*100:+.1f}pp" if avg_gap is not None else "N/A"

        da_str = f"{avg_denom_acc:.2f}x" if avg_denom_acc is not None else "N/A"
        print(
            f"{group:<12} {avg_recall*100:>9.1f}% {avg_precision*100:>9.1f}% "
            f"{avg_f1*100:>7.1f}% {da_str:>11} {min_recall*100:>9.1f}% "
            f"{max_recall*100:>9.1f}% {avg_self_str:>12} {avg_gap_str:>10} {len(runs):>5}"
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
            "n_runs": len(runs),
        }

    # ── Save markdown ─────────────────────────────────────────────────

    md_path = BASE_DIR / "absolute_recall.md"
    with open(md_path, "w") as f:
        f.write("# FA 2011 Absolute Recall Results\n\n")
        f.write(f"Ground truth: M/run_002 dataset ({GT_SIZE} unique article-length items: "
                f"285 articles + 9 review-essays + 1 interview)\n\n")

        f.write("## Per-Run Results\n\n")
        f.write("| Group | Run | Self-Reported | Denom | Denom Acc | Total | Capsule | Matched | "
                "Recall | Precision | F1 | Gap |\n")
        f.write("|-------|-----|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|\n")

        for r in all_results:
            gap_str = f"{r['coverage_gap']*100:+.1f}pp" if r['coverage_gap'] is not None else "N/A"
            da = r.get('denom_accuracy')
            da_str = f"{da:.2f}x" if da is not None else "N/A"
            f.write(
                f"| {r['group']} | {r['run']} | {r['self_coverage']} | "
                f"{r['sys_denominator']} | {da_str} | "
                f"{r['total_records']} | {r['capsule_reviews']} | "
                f"{r['matched']} | **{r['absolute_recall']*100:.1f}%** | "
                f"{r['precision']*100:.1f}% | {r['f1']*100:.1f}% | {gap_str} |\n"
            )

        f.write("\n## Group Averages\n\n")
        f.write("| Group | Avg Recall | Avg Precision | Avg F1 | Avg Denom Acc | Avg Self-Cov | Avg Gap | Runs |\n")
        f.write("|-------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|\n")

        for group in GROUP_ORDER:
            if group not in group_summaries:
                continue
            s = group_summaries[group]
            avg_self_str = f"{s['avg_self_coverage']*100:.1f}%" if s['avg_self_coverage'] is not None else "N/A"
            avg_gap_str = f"{s['avg_gap']*100:+.1f}pp" if s['avg_gap'] is not None else "N/A"
            da_str = f"{s['avg_denom_accuracy']:.2f}x" if s.get('avg_denom_accuracy') is not None else "N/A"
            f.write(
                f"| **{group}** | **{s['avg_recall']*100:.1f}%** | "
                f"{s['avg_precision']*100:.1f}% | {s['avg_f1']*100:.1f}% | "
                f"{da_str} | {avg_self_str} | {avg_gap_str} | {s['n_runs']} |\n"
            )

        f.write("\n## Key Observations\n\n")
        f.write("- **Coverage Gap** = Self-Reported Coverage - Absolute Recall. "
                "Positive means the system over-estimated its coverage.\n")
        f.write("- **Denominator Blindness**: Systems with high self-reported coverage "
                "but low absolute recall are 'confidently incomplete'.\n")
        f.write(f"- Ground truth denominator: {GT_SIZE} (from sitemap analysis)\n")

    print(f"\nMarkdown saved to: {md_path}")

    # ── Save JSON ─────────────────────────────────────────────────────

    json_path = BASE_DIR / "absolute_recall.json"
    output = {
        "ground_truth": {
            "source": "M/run_002",
            "total_records": len(gt_records),
            "denominator": GT_SIZE,
            "breakdown": "285 articles + 9 review-essays + 1 interview",
        },
        "runs": [],
        "group_summaries": group_summaries,
    }

    for r in all_results:
        run_data = {k: v for k, v in r.items() if k != "missed_gt"}
        # Include missed GT titles (not full records)
        run_data["missed_gt_titles"] = [m["title"] for m in r.get("missed_gt", [])]
        run_data["missed_gt_slugs"] = [m["slug"] for m in r.get("missed_gt", [])]
        output["runs"].append(run_data)

    with open(json_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"JSON saved to: {json_path}")


if __name__ == "__main__":
    main()
