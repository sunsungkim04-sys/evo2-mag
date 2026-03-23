#!/usr/bin/env python3
"""
chimera_junction.py — Perplexity junction 탐지 기반 키메라 탐지 개선

현재 sliding window perplexity의 문제: 모든 bin에서 2σ 초과 구간이 존재 → Precision 24.4%.
개선 아이디어: 진짜 키메라는 perplexity가 갑자기 튀는 junction이 있어야 함.
인접 window 간 delta(1차 미분)의 최댓값으로 step-change를 탐지.

사용법:
    python3 ~/evo2-mag/scripts/chimera_junction.py
    python3 ~/evo2-mag/scripts/chimera_junction.py \\
        --windows-tsv ~/results/perplexity_windows.tsv \\
        --detail-tsv  ~/results/chimera_validation_detail.tsv \\
        --output-dir  ~/results
"""

import argparse
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd


# ──────────────────────────────────────────────────────────────────────
# 1. Gold standard 로딩 (chimera_validation_detail.tsv 재사용)
# ──────────────────────────────────────────────────────────────────────
def load_gold_standard(detail_tsv: str) -> dict:
    """
    chimera_validation_detail.tsv의 true_chimera 컬럼을 읽어
    {bin_name: bool} 딕셔너리를 반환.
    gold standard를 재계산하지 않고 기존 결과를 재사용.
    """
    gold = {}
    with open(detail_tsv) as f:
        header = f.readline().strip().split("\t")
        try:
            bn_idx = header.index("bin_name")
            tc_idx = header.index("true_chimera")
        except ValueError as e:
            print(f"ERROR: chimera_validation_detail.tsv에 필요한 컬럼 없음: {e}", file=sys.stderr)
            sys.exit(1)
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) > max(bn_idx, tc_idx):
                gold[parts[bn_idx]] = parts[tc_idx].strip().lower() in ("true", "1")
    print(f"Gold standard 로딩 완료: {len(gold)}개 bins "
          f"(True chimera: {sum(gold.values())}개)")
    return gold


# ──────────────────────────────────────────────────────────────────────
# 2. Baseline 참조값 로딩 (summary 비교용)
# ──────────────────────────────────────────────────────────────────────
def load_baseline_predictions(detail_tsv: str) -> tuple:
    """
    chimera_validation_detail.tsv에서 CheckM2와 Evo2 any-flag 예측값을 로딩.
    Returns: (checkm2_pred_dict, evo2_anyflag_dict) — {bin_name: bool}
    """
    checkm2 = {}
    evo2_any = {}
    with open(detail_tsv) as f:
        header = f.readline().strip().split("\t")
        try:
            bn_idx   = header.index("bin_name")
            cm2_idx  = header.index("checkm2_predicted")
            ratio_idx = header.index("evo2_flagged_ratio")
        except ValueError as e:
            print(f"[경고] baseline 예측값 컬럼 없음: {e} — 비교 행 생략됨")
            return {}, {}
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) > max(bn_idx, cm2_idx, ratio_idx):
                bn = parts[bn_idx]
                checkm2[bn] = parts[cm2_idx].strip().lower() in ("true", "1")
                try:
                    ratio = float(parts[ratio_idx])
                    evo2_any[bn] = ratio > 0.0
                except ValueError:
                    evo2_any[bn] = False
    return checkm2, evo2_any


# ──────────────────────────────────────────────────────────────────────
# 3. Perplexity windows 로딩
# ──────────────────────────────────────────────────────────────────────
def load_perplexity_windows(windows_tsv: str) -> dict:
    """
    perplexity_windows.tsv를 읽어
    {(bin_name, contig_name): [(start, end, ppl), ...]} 를 반환.
    헤더: bin\tcontig\tstart\tend\tperplexity
    """
    data = defaultdict(list)
    n_rows = 0
    with open(windows_tsv) as f:
        f.readline()  # 헤더 스킵
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 5:
                continue
            bin_name = parts[0]
            contig   = parts[1]
            try:
                start = int(parts[2])
                end   = int(parts[3])
                ppl   = float(parts[4])
            except ValueError:
                continue
            data[(bin_name, contig)].append((start, end, ppl))
            n_rows += 1
    n_bins    = len(set(k[0] for k in data.keys()))
    n_contigs = len(data)
    print(f"Perplexity windows 로딩 완료: {n_rows:,}행, {n_bins}개 bins, {n_contigs:,}개 (bin,contig) 쌍")
    return dict(data)


# ──────────────────────────────────────────────────────────────────────
# 4. Contig별 junction score 계산
# ──────────────────────────────────────────────────────────────────────
def compute_contig_junction_scores(window_dict: dict, skip_overlapping: bool = True) -> list:
    """
    각 (bin, contig)에 대해 인접 window 간 |delta| 최댓값(junction score)을 계산.

    skip_overlapping=True: every-other window 선택 (비중첩화, 8kb window 4kb step 전제).
      → 인접 delta가 독립적이 되어 단일 junction이 두 번 카운트되지 않음.

    Returns:
        list of dicts with keys:
          bin_name, contig_name, n_windows_orig, n_windows_used,
          max_delta, mean_delta, p95_delta, mean_ppl, note
    """
    rows = []
    for (bin_name, contig), windows in window_dict.items():
        # start 기준 정렬 (TSV 순서 보장 안 됨)
        windows_sorted = sorted(windows, key=lambda x: x[0])
        n_orig = len(windows_sorted)

        if skip_overlapping:
            windows_sorted = windows_sorted[::2]
        n_used = len(windows_sorted)

        ppls = np.array([w[2] for w in windows_sorted], dtype=np.float64)
        mean_ppl = float(ppls.mean())

        if n_used < 2:
            rows.append({
                "bin_name":       bin_name,
                "contig_name":    contig,
                "n_windows_orig": n_orig,
                "n_windows_used": n_used,
                "max_delta":      0.0,
                "mean_delta":     0.0,
                "p95_delta":      0.0,
                "mean_ppl":       mean_ppl,
                "note":           "single_window",
            })
            continue

        deltas = np.abs(np.diff(ppls))
        rows.append({
            "bin_name":       bin_name,
            "contig_name":    contig,
            "n_windows_orig": n_orig,
            "n_windows_used": n_used,
            "max_delta":      float(deltas.max()),
            "mean_delta":     float(deltas.mean()),
            "p95_delta":      float(np.percentile(deltas, 95)),
            "mean_ppl":       mean_ppl,
            "note":           "",
        })
    print(f"Contig junction scores 계산 완료: {len(rows):,}개 contigs")
    return rows


# ──────────────────────────────────────────────────────────────────────
# 5. Bin별 집계
# ──────────────────────────────────────────────────────────────────────
def compute_bin_junction_scores(contig_rows: list, gold: dict) -> list:
    """
    contig별 max_delta를 bin별로 집계.
    집계 지표: max_junction, mean_junction, p75_junction, p90_junction

    single_window contig은 max_delta=0으로 포함 (보수적).
    embedded contig 0개인 bin은 제외.
    """
    bin_scores = defaultdict(list)
    bin_n_contigs = defaultdict(int)
    bin_n_valid   = defaultdict(int)

    for row in contig_rows:
        bn = row["bin_name"]
        bin_scores[bn].append(row["max_delta"])
        bin_n_contigs[bn] += 1
        if row["note"] != "single_window":
            bin_n_valid[bn] += 1

    rows = []
    for bin_name in sorted(bin_scores.keys()):
        scores = bin_scores[bin_name]
        n_contigs = bin_n_contigs[bin_name]
        n_valid   = bin_n_valid[bin_name]

        if not scores:
            continue

        scores_arr = np.array(scores, dtype=np.float64)
        rows.append({
            "bin_name":       bin_name,
            "n_contigs":      n_contigs,
            "n_valid":        n_valid,
            "max_junction":   float(scores_arr.max()),
            "mean_junction":  float(scores_arr.mean()),
            "p75_junction":   float(np.percentile(scores_arr, 75)),
            "p90_junction":   float(np.percentile(scores_arr, 90)),
            "true_chimera":   gold.get(bin_name, None),
        })
    print(f"Bin junction scores 집계 완료: {len(rows)}개 bins")
    return rows


# ──────────────────────────────────────────────────────────────────────
# 6. 지표 계산
# ──────────────────────────────────────────────────────────────────────
def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Binary classification 지표를 딕셔너리로 반환."""
    tp = int(np.sum(y_true & y_pred))
    fp = int(np.sum(~y_true & y_pred))
    fn = int(np.sum(y_true & ~y_pred))
    tn = int(np.sum(~y_true & ~y_pred))
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return {"Precision": precision, "Recall": recall, "F1": f1,
            "TP": tp, "FP": fp, "FN": fn, "TN": tn}


# ──────────────────────────────────────────────────────────────────────
# 7. Threshold sweep 및 리포트 생성
# ──────────────────────────────────────────────────────────────────────
def sweep_and_report(
    bin_df: pd.DataFrame,
    checkm2_pred: dict,
    evo2_any_pred: dict,
    n_thresholds: int = 200,
) -> tuple:
    """
    각 junction score 지표에 대해 threshold sweep으로 F1 최대화.
    Returns: (report_str, bin_df_with_predictions)
    """
    # gold standard가 있는 bin만 평가
    eval_df = bin_df[bin_df["true_chimera"].notna()].copy()
    if eval_df.empty:
        return "No bins with gold standard — nothing to evaluate.\n", bin_df

    y_true = eval_df["true_chimera"].values.astype(bool)
    total  = len(eval_df)
    n_pos  = int(y_true.sum())

    # 기준선 비교용: CheckM2와 Evo2 any-flag
    y_cm2     = np.array([checkm2_pred.get(b, False) for b in eval_df["bin_name"]], dtype=bool)
    y_evo2any = np.array([evo2_any_pred.get(b, False) for b in eval_df["bin_name"]], dtype=bool)
    m_cm2     = compute_metrics(y_true, y_cm2)
    m_evo2any = compute_metrics(y_true, y_evo2any)

    methods = [
        ("max_junction",  "Max junction score"),
        ("mean_junction", "Mean junction score"),
        ("p75_junction",  "P75 junction score"),
        ("p90_junction",  "P90 junction score"),
    ]

    best_results = {}
    for col, _ in methods:
        scores = eval_df[col].values.astype(np.float64)
        if scores.max() == scores.min():
            # 모든 score가 동일 — threshold sweep 의미 없음
            best_results[col] = {
                "threshold": scores.max(),
                "metrics": compute_metrics(y_true, scores > scores.max()),
            }
            continue
        thresholds = np.linspace(scores.min(), scores.max(), n_thresholds)
        best_f1 = -1.0
        best_t  = thresholds[0]
        best_m  = None
        for t in thresholds:
            y_pred = scores > t
            m = compute_metrics(y_true, y_pred)
            if m["F1"] > best_f1:
                best_f1 = m["F1"]
                best_t  = t
                best_m  = m
        best_results[col] = {"threshold": best_t, "metrics": best_m}

    # predicted 컬럼 추가
    for col, _ in methods:
        t = best_results[col]["threshold"]
        bin_df[f"predicted_{col}"] = bin_df[col] > t

    # 리포트 생성
    lines = []
    lines.append("=" * 75)
    lines.append("=== Chimera Junction Detection — Validation Report ===")
    lines.append("=" * 75)
    lines.append(f"Total bins evaluated: {total}  |  True chimeras: {n_pos}/{total} ({100*n_pos/total:.1f}%)")
    lines.append(f"Skip-overlapping: True (every-other window, non-overlapping delta)")
    lines.append("")

    hdr = f"{'Method':<28s} {'Precision':>9s} {'Recall':>9s} {'F1':>9s}   {'TP':>4s} {'FP':>4s} {'FN':>4s} {'TN':>4s}  {'Best threshold':>16s}"
    lines.append("=== Metrics: Junction score methods (best F1 threshold) ===")
    lines.append("(bin predicted chimera if score > threshold)")
    lines.append("")
    lines.append(hdr)
    lines.append("-" * len(hdr))

    for col, label in methods:
        t = best_results[col]["threshold"]
        m = best_results[col]["metrics"]
        lines.append(
            f"{label:<28s} {m['Precision']:>9.4f} {m['Recall']:>9.4f} {m['F1']:>9.4f}   "
            f"{m['TP']:>4d} {m['FP']:>4d} {m['FN']:>4d} {m['TN']:>4d}  {t:>16.2f}"
        )

    lines.append("-" * len(hdr))
    lines.append("=== Baseline (from chimera_validation_detail.tsv) ===")
    lines.append(
        f"{'CheckM2 (>5%)':<28s} {m_cm2['Precision']:>9.4f} {m_cm2['Recall']:>9.4f} {m_cm2['F1']:>9.4f}   "
        f"{m_cm2['TP']:>4d} {m_cm2['FP']:>4d} {m_cm2['FN']:>4d} {m_cm2['TN']:>4d}  {'(N/A)':>16s}"
    )
    lines.append(
        f"{'Evo2 perplexity (any)':<28s} {m_evo2any['Precision']:>9.4f} {m_evo2any['Recall']:>9.4f} {m_evo2any['F1']:>9.4f}   "
        f"{m_evo2any['TP']:>4d} {m_evo2any['FP']:>4d} {m_evo2any['FN']:>4d} {m_evo2any['TN']:>4d}  {'(N/A)':>16s}"
    )
    lines.append("")

    # 가장 좋은 method 기준으로 Evo2가 잡고 CheckM2가 놓친 bins
    best_col = max(methods, key=lambda x: best_results[x[0]]["metrics"]["F1"])[0]
    best_t   = best_results[best_col]["threshold"]
    y_best   = eval_df[best_col].values > best_t

    caught_only = eval_df[y_best & ~y_cm2 & y_true]
    lines.append(f"=== Junction-only caught (best method: {best_col}, t={best_t:.2f}): {len(caught_only)}개 ===")
    for _, row in caught_only.iterrows():
        lines.append(f"  {row['bin_name']}  max_junction={row['max_junction']:.2f}  "
                     f"mean_junction={row['mean_junction']:.2f}  n_contigs={int(row['n_contigs'])}")
    lines.append("")

    missed = eval_df[~y_best & y_true]
    lines.append(f"=== 놓친 True chimera (best method): {len(missed)}개 ===")
    for _, row in missed.iterrows():
        lines.append(f"  {row['bin_name']}  max_junction={row['max_junction']:.2f}  "
                     f"mean_junction={row['mean_junction']:.2f}")
    lines.append("")

    return "\n".join(lines), bin_df


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Perplexity junction 탐지 기반 키메라 탐지 개선"
    )
    parser.add_argument(
        "--windows-tsv", default=os.path.expanduser("~/results/perplexity_windows.tsv"),
        help="perplexity_windows.tsv 경로"
    )
    parser.add_argument(
        "--detail-tsv", default=os.path.expanduser("~/results/chimera_validation_detail.tsv"),
        help="chimera_validation_detail.tsv 경로 (gold standard 소스)"
    )
    parser.add_argument(
        "--output-dir", default=os.path.expanduser("~/results"),
        help="출력 디렉토리"
    )
    parser.add_argument(
        "--no-skip-overlapping", dest="skip_overlapping", action="store_false",
        help="중첩 window 비중첩화 비활성화 (기본: 활성화)"
    )
    parser.set_defaults(skip_overlapping=True)
    parser.add_argument(
        "--n-thresholds", type=int, default=200,
        help="threshold sweep 단계 수 (기본: 200)"
    )
    args = parser.parse_args()

    output_dir = os.path.expanduser(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print("Chimera Junction Detection")
    print("=" * 60)
    print(f"Windows TSV : {args.windows_tsv}")
    print(f"Detail TSV  : {args.detail_tsv}")
    print(f"Output dir  : {output_dir}")
    print(f"Skip overlapping: {args.skip_overlapping}")
    print()

    # [1/4] Gold standard
    print("[1/4] Gold standard 로딩...")
    gold = load_gold_standard(args.detail_tsv)
    checkm2_pred, evo2_any_pred = load_baseline_predictions(args.detail_tsv)
    print()

    # [2/4] Perplexity windows
    print("[2/4] Perplexity windows 로딩...")
    window_dict = load_perplexity_windows(args.windows_tsv)
    print()

    # [3/4] Junction scores 계산
    print("[3/4] Junction scores 계산...")
    contig_rows = compute_contig_junction_scores(window_dict, args.skip_overlapping)
    bin_rows    = compute_bin_junction_scores(contig_rows, gold)
    print()

    # [4/4] Threshold sweep 및 리포트
    print("[4/4] Threshold sweep 및 리포트 생성...")
    contig_df = pd.DataFrame(contig_rows)
    bin_df    = pd.DataFrame(bin_rows)

    report, bin_df = sweep_and_report(bin_df, checkm2_pred, evo2_any_pred, args.n_thresholds)
    print()
    print(report)

    # 파일 저장
    out_contigs = os.path.join(output_dir, "chimera_junction_contigs.tsv")
    out_bins    = os.path.join(output_dir, "chimera_junction_bins.tsv")
    out_summary = os.path.join(output_dir, "chimera_junction_summary.txt")

    contig_df.to_csv(out_contigs, sep="\t", index=False)
    bin_df.to_csv(out_bins, sep="\t", index=False)
    with open(out_summary, "w") as f:
        f.write(report)

    print(f"Saved: {out_contigs}")
    print(f"Saved: {out_bins}")
    print(f"Saved: {out_summary}")
    print("\n완료!")


if __name__ == "__main__":
    main()
