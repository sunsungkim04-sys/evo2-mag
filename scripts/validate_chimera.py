#!/usr/bin/env python3
"""
validate_chimera.py — Evo2 perplexity 기반 키메라 탐지 정량 검증 스크립트

CAMI2 gold standard 대비 Evo2 perplexity 예측과 CheckM2 contamination 예측을
비교하여 Precision/Recall/F1 지표를 산출한다.

사용법:
    python3 ~/evo2-mag/scripts/validate_chimera.py
    python3 ~/evo2-mag/scripts/validate_chimera.py --results-dir ~/results --checkm2-threshold 5.0
"""

import argparse
import glob
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd


# ──────────────────────────────────────────────────────────────────────
# 1. Gold standard 로딩: contig → genome 매핑
# ──────────────────────────────────────────────────────────────────────
def load_gold_standards(results_dir: str, n_samples: int = 21) -> dict:
    """
    gold_standard_baseline_sampleN.tsv 파일들을 읽어서
    {contig_name: genome_id} 딕셔너리를 반환한다.
    """
    contig_to_genome = {}
    loaded = 0
    for n in range(n_samples):
        path = os.path.join(results_dir, "amber_eval", f"gold_standard_baseline_sample{n}.tsv")
        if not os.path.isfile(path):
            print(f"  [경고] gold standard 파일 없음: {path}")
            continue
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("@@"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 2:
                    contig_to_genome[parts[0]] = parts[1]
        loaded += 1
    print(f"Gold standard 로딩 완료: {loaded}개 샘플, {len(contig_to_genome):,}개 contig-genome 매핑")
    return contig_to_genome


# ──────────────────────────────────────────────────────────────────────
# 2. Baseline bin FASTA 파싱: bin_name → [contig_list]
# ──────────────────────────────────────────────────────────────────────
def load_baseline_bins(results_dir: str, n_samples: int = 21) -> dict:
    """
    각 샘플의 bins/*.fa 파일을 읽어
    {bin_name: [contig1, contig2, ...]} 딕셔너리를 반환한다.
    FASTA 헤더에서 range suffix (_43645-276993 등)를 제거한다.
    """
    bin_contigs = {}
    # contig 이름에서 range suffix 제거 패턴: _숫자-숫자$ (끝 부분)
    range_suffix_re = re.compile(r"_\d+-\d+$")

    for n in range(n_samples):
        bin_dir = os.path.join(results_dir, f"baseline_sample{n}", "results", "bins")
        if not os.path.isdir(bin_dir):
            continue
        fa_files = glob.glob(os.path.join(bin_dir, "*.fa"))
        for fa_path in fa_files:
            bin_name = os.path.basename(fa_path).replace(".fa", "")
            contigs = []
            with open(fa_path) as f:
                for line in f:
                    if line.startswith(">"):
                        raw_name = line[1:].strip().split()[0]  # 첫 번째 필드만
                        # range suffix 제거
                        clean_name = range_suffix_re.sub("", raw_name)
                        contigs.append(clean_name)
            bin_contigs[bin_name] = contigs

    total_contigs = sum(len(v) for v in bin_contigs.values())
    print(f"Baseline bins 로딩 완료: {len(bin_contigs):,}개 bins, {total_contigs:,}개 contigs")
    return bin_contigs


# ──────────────────────────────────────────────────────────────────────
# 3. Evo2 chimera candidates 로딩
# ──────────────────────────────────────────────────────────────────────
def load_evo2_predictions(chimera_path: str, windows_path: str) -> dict:
    """
    chimera_candidates.tsv + perplexity_windows.tsv를 읽어서
    bin별 (total_windows, flagged_windows, flagged_ratio)를 반환한다.

    Returns:
        {bin_name: {"total": int, "flagged": int, "ratio": float}}
    """
    # 1) 전체 windows 수 (perplexity_windows.tsv)
    total_per_bin = defaultdict(int)
    if os.path.isfile(windows_path):
        with open(windows_path) as f:
            f.readline()  # 헤더 스킵
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 1:
                    total_per_bin[parts[0]] += 1
    else:
        print(f"  [경고] perplexity_windows 파일 없음: {windows_path}")

    # 2) flagged windows 수 (chimera_candidates.tsv)
    flagged_per_bin = defaultdict(int)
    if os.path.isfile(chimera_path):
        with open(chimera_path) as f:
            f.readline()  # 헤더 스킵
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 1:
                    flagged_per_bin[parts[0]] += 1
    else:
        print(f"  [경고] chimera_candidates 파일 없음: {chimera_path}")

    # 3) bin별 정보 합치기
    result = {}
    all_bins = set(total_per_bin.keys()) | set(flagged_per_bin.keys())
    for bin_name in all_bins:
        total = total_per_bin.get(bin_name, 0)
        flagged = flagged_per_bin.get(bin_name, 0)
        ratio = flagged / total if total > 0 else 0.0
        result[bin_name] = {"total": total, "flagged": flagged, "ratio": ratio}

    print(f"Evo2 perplexity 로딩 완료: {len(result)}개 bins, "
          f"총 {sum(v['total'] for v in result.values()):,} windows, "
          f"{sum(v['flagged'] for v in result.values()):,} flagged")
    return result


# ──────────────────────────────────────────────────────────────────────
# 4. CheckM2 contamination 로딩
# ──────────────────────────────────────────────────────────────────────
def load_checkm2_contamination(results_dir: str, n_samples: int = 21) -> dict:
    """
    baseline_sampleN_bins.tsv에서 {bin_name: contamination_checkm2} 딕셔너리를 반환.
    Column 0 = bin name, Column 5 = contamination_checkm2.
    """
    contamination = {}
    for n in range(n_samples):
        path = os.path.join(results_dir, f"baseline_sample{n}", "results",
                            f"baseline_sample{n}_bins.tsv")
        if not os.path.isfile(path):
            continue
        with open(path) as f:
            header = f.readline()
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) > 5:
                    bin_name = parts[0]
                    try:
                        cont = float(parts[5])
                    except (ValueError, IndexError):
                        cont = 0.0
                    contamination[bin_name] = cont
    print(f"CheckM2 contamination 로딩 완료: {len(contamination)}개 bins")
    return contamination


# ──────────────────────────────────────────────────────────────────────
# 5. 진짜 키메라 판별 및 per-bin 테이블 구축
# ──────────────────────────────────────────────────────────────────────
def build_validation_table(
    bin_contigs: dict,
    contig_to_genome: dict,
    evo2_stats: dict,
    checkm2_contamination: dict,
    checkm2_threshold: float = 5.0,
) -> pd.DataFrame:
    """
    모든 bin에 대해 true chimera 여부, 예측 여부 등을 담은 DataFrame을 반환.
    evo2_stats: {bin_name: {"total": int, "flagged": int, "ratio": float}}
    """
    sample_re = re.compile(r"baseline_sample(\d+)")
    rows = []

    for bin_name, contigs in bin_contigs.items():
        # 샘플 번호 추출
        m = sample_re.search(bin_name)
        sample = int(m.group(1)) if m else -1

        # contig → genome 매핑
        genomes = set()
        n_mapped = 0
        for c in contigs:
            g = contig_to_genome.get(c)
            if g is not None:
                genomes.add(g)
                n_mapped += 1

        true_chimera = len(genomes) >= 2

        # Evo2 perplexity 통계
        evo2_info = evo2_stats.get(bin_name, {"total": 0, "flagged": 0, "ratio": 0.0})
        evo2_total_windows = evo2_info["total"]
        evo2_flagged_windows = evo2_info["flagged"]
        evo2_flagged_ratio = evo2_info["ratio"]

        checkm2_cont = checkm2_contamination.get(bin_name, np.nan)
        checkm2_pred = (checkm2_cont > checkm2_threshold) if not np.isnan(checkm2_cont) else False

        rows.append({
            "bin_name": bin_name,
            "sample": sample,
            "n_contigs": len(contigs),
            "n_mapped_contigs": n_mapped,
            "n_genomes": len(genomes),
            "true_chimera": true_chimera,
            "evo2_total_windows": evo2_total_windows,
            "evo2_flagged_windows": evo2_flagged_windows,
            "evo2_flagged_ratio": evo2_flagged_ratio,
            "checkm2_predicted": bool(checkm2_pred),
            "checkm2_contamination": checkm2_cont,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["sample", "bin_name"]).reset_index(drop=True)
    return df


# ──────────────────────────────────────────────────────────────────────
# 6. Precision / Recall / F1 계산
# ──────────────────────────────────────────────────────────────────────
def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Binary classification 지표를 딕셔너리로 반환."""
    tp = int(np.sum(y_true & y_pred))
    fp = int(np.sum(~y_true & y_pred))
    fn = int(np.sum(y_true & ~y_pred))
    tn = int(np.sum(~y_true & ~y_pred))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "Precision": precision,
        "Recall": recall,
        "F1": f1,
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "TN": tn,
    }


# ──────────────────────────────────────────────────────────────────────
# 7. 리포트 생성
# ──────────────────────────────────────────────────────────────────────
def generate_report(df: pd.DataFrame, checkm2_threshold: float) -> str:
    """사람이 읽기 좋은 요약 리포트 문자열 생성 (다중 flagged ratio threshold)."""
    total = len(df)
    if total == 0:
        return "No bins found — nothing to report.\n"

    true_chimeras = int(df["true_chimera"].sum())
    checkm2_predicted = int(df["checkm2_predicted"].sum())

    y_true = df["true_chimera"].values.astype(bool)
    y_cm2 = df["checkm2_predicted"].values.astype(bool)
    m_cm2 = compute_metrics(y_true, y_cm2)

    lines = []
    lines.append("=" * 70)
    lines.append("=== Chimera Detection Validation ===")
    lines.append("=" * 70)
    lines.append(f"Total baseline bins: {total}")
    lines.append(f"True chimeras (>=2 genomes): {true_chimeras}/{total} ({100*true_chimeras/total:.1f}%)")
    lines.append(f"CheckM2 predicted chimeras (>{checkm2_threshold}% cont): {checkm2_predicted}/{total} bins")
    lines.append(f"Evo2 perplexity: {int(df['evo2_total_windows'].sum()):,} total windows, "
                 f"{int(df['evo2_flagged_windows'].sum()):,} flagged")
    lines.append("")

    # 다중 threshold로 Evo2 메트릭 계산
    # flagged_ratio > threshold이면 키메라 예측
    ratio_thresholds = [0.0, 0.03, 0.05, 0.07, 0.10, 0.15, 0.20]

    lines.append("=== Metrics: Evo2 flagged ratio thresholds ===")
    lines.append("(bin is predicted chimera if flagged_windows/total_windows > threshold)")
    lines.append("")
    header = f"{'Method':<25s} {'Precision':>9s} {'Recall':>9s} {'F1':>9s}   {'TP':>4s} {'FP':>4s} {'FN':>4s} {'TN':>4s}"
    lines.append(header)
    lines.append("-" * len(header))

    # CheckM2 baseline
    lines.append(
        f"{f'CheckM2 (>{checkm2_threshold}%)':<25s} {m_cm2['Precision']:>9.4f} {m_cm2['Recall']:>9.4f} {m_cm2['F1']:>9.4f}   "
        f"{m_cm2['TP']:>4d} {m_cm2['FP']:>4d} {m_cm2['FN']:>4d} {m_cm2['TN']:>4d}"
    )

    # Evo2 at various ratio thresholds
    best_f1 = 0.0
    best_threshold = 0.0
    best_metrics = None
    for thresh in ratio_thresholds:
        y_evo2 = (df["evo2_flagged_ratio"].values > thresh)
        m = compute_metrics(y_true, y_evo2)
        label = f"Evo2 ratio>{thresh:.0%}" if thresh > 0 else "Evo2 (any flag)"
        lines.append(
            f"{label:<25s} {m['Precision']:>9.4f} {m['Recall']:>9.4f} {m['F1']:>9.4f}   "
            f"{m['TP']:>4d} {m['FP']:>4d} {m['FN']:>4d} {m['TN']:>4d}"
        )
        if m["F1"] > best_f1:
            best_f1 = m["F1"]
            best_threshold = thresh
            best_metrics = m

    # Union at best threshold
    y_evo2_best = (df["evo2_flagged_ratio"].values > best_threshold)
    y_union = y_evo2_best | y_cm2
    m_union = compute_metrics(y_true, y_union)
    lines.append(
        f"{'CheckM2+Evo2 (best)':<25s} {m_union['Precision']:>9.4f} {m_union['Recall']:>9.4f} {m_union['F1']:>9.4f}   "
        f"{m_union['TP']:>4d} {m_union['FP']:>4d} {m_union['FN']:>4d} {m_union['TN']:>4d}"
    )
    lines.append("")
    lines.append(f"Best Evo2 threshold: flagged_ratio > {best_threshold:.0%} (F1={best_f1:.4f})")
    lines.append("")

    # Best threshold 기준으로 Evo2가 잡았지만 CheckM2가 놓친 키메라
    evo2_only = df[y_evo2_best & ~y_cm2 & y_true]
    lines.append(f"=== Evo2 caught but CheckM2 missed @ best threshold ({len(evo2_only)} bins) ===")
    if len(evo2_only) > 0:
        for _, row in evo2_only.iterrows():
            cont_str = f"{row['checkm2_contamination']:.2f}" if not np.isnan(row["checkm2_contamination"]) else "N/A"
            lines.append(
                f"  {row['bin_name']}  genomes={int(row['n_genomes'])}  "
                f"contigs={int(row['n_contigs'])}  flagged_ratio={row['evo2_flagged_ratio']:.1%}  "
                f"checkm2_cont={cont_str}%"
            )
    else:
        lines.append("  (none)")
    lines.append("")

    # CheckM2가 잡았지만 Evo2가 놓친 키메라
    cm2_only = df[y_cm2 & ~y_evo2_best & y_true]
    lines.append(f"=== CheckM2 caught but Evo2 missed @ best threshold ({len(cm2_only)} bins) ===")
    if len(cm2_only) > 0:
        for _, row in cm2_only.iterrows():
            cont_str = f"{row['checkm2_contamination']:.2f}" if not np.isnan(row["checkm2_contamination"]) else "N/A"
            lines.append(
                f"  {row['bin_name']}  genomes={int(row['n_genomes'])}  "
                f"contigs={int(row['n_contigs'])}  flagged_ratio={row['evo2_flagged_ratio']:.1%}  "
                f"checkm2_cont={cont_str}%"
            )
    else:
        lines.append("  (none)")
    lines.append("")

    # Unmapped contig 통계
    total_contigs = int(df["n_contigs"].sum())
    total_mapped = int(df["n_mapped_contigs"].sum())
    unmapped = total_contigs - total_mapped
    lines.append(f"=== Contig mapping 통계 ===")
    lines.append(f"전체 contigs: {total_contigs:,}  매핑됨: {total_mapped:,}  미매핑: {unmapped:,} ({100*unmapped/total_contigs:.1f}%)")
    lines.append("")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Evo2 perplexity 키메라 탐지 검증: CAMI2 gold standard 대비 Precision/Recall/F1"
    )
    parser.add_argument(
        "--results-dir", default=os.path.expanduser("~/results"),
        help="결과 디렉토리 (기본: ~/results)"
    )
    parser.add_argument(
        "--chimera-tsv", default=None,
        help="Evo2 chimera_candidates.tsv 경로 (기본: <results-dir>/chimera_candidates.tsv)"
    )
    parser.add_argument(
        "--windows-tsv", default=None,
        help="Evo2 perplexity_windows.tsv 경로 (기본: <results-dir>/perplexity_windows.tsv)"
    )
    parser.add_argument(
        "--checkm2-threshold", type=float, default=5.0,
        help="CheckM2 contamination 키메라 판별 임계값 (기본: 5.0%%)"
    )
    parser.add_argument(
        "--n-samples", type=int, default=21,
        help="CAMI2 샘플 수 (기본: 21)"
    )
    parser.add_argument(
        "--output-summary", default=None,
        help="요약 리포트 출력 경로 (기본: <results-dir>/chimera_validation_summary.txt)"
    )
    parser.add_argument(
        "--output-detail", default=None,
        help="상세 테이블 출력 경로 (기본: <results-dir>/chimera_validation_detail.tsv)"
    )
    args = parser.parse_args()

    results_dir = args.results_dir
    chimera_tsv = args.chimera_tsv or os.path.join(results_dir, "chimera_candidates.tsv")
    windows_tsv = args.windows_tsv or os.path.join(results_dir, "perplexity_windows.tsv")
    output_summary = args.output_summary or os.path.join(results_dir, "chimera_validation_summary.txt")
    output_detail = args.output_detail or os.path.join(results_dir, "chimera_validation_detail.tsv")

    print("=" * 60)
    print("Chimera Detection Validation")
    print("=" * 60)
    print(f"Results dir  : {results_dir}")
    print(f"Chimera TSV  : {chimera_tsv}")
    print(f"Windows TSV  : {windows_tsv}")
    print(f"CheckM2 임계값: {args.checkm2_threshold}%")
    print(f"샘플 수       : {args.n_samples}")
    print()

    # Step 1: Gold standard
    print("[1/5] Gold standard 로딩...")
    contig_to_genome = load_gold_standards(results_dir, args.n_samples)
    if not contig_to_genome:
        print("ERROR: Gold standard를 로딩할 수 없습니다. 종료합니다.", file=sys.stderr)
        sys.exit(1)
    print()

    # Step 2: Baseline bins
    print("[2/5] Baseline bin FASTA 파싱...")
    bin_contigs = load_baseline_bins(results_dir, args.n_samples)
    if not bin_contigs:
        print("ERROR: Baseline bin을 로딩할 수 없습니다. 종료합니다.", file=sys.stderr)
        sys.exit(1)
    print()

    # Step 3: Evo2 predictions (windows + candidates → per-bin stats)
    print("[3/5] Evo2 perplexity 통계 로딩...")
    evo2_stats = load_evo2_predictions(chimera_tsv, windows_tsv)
    print()

    # Step 4: CheckM2 contamination
    print("[4/5] CheckM2 contamination 로딩...")
    checkm2_contamination = load_checkm2_contamination(results_dir, args.n_samples)
    print()

    # Step 5: 검증 테이블 구축 및 리포트 생성
    print("[5/5] 검증 테이블 구축 및 지표 계산...")
    df = build_validation_table(
        bin_contigs, contig_to_genome, evo2_stats,
        checkm2_contamination, args.checkm2_threshold,
    )

    if df.empty:
        print("ERROR: 검증 테이블이 비어있습니다. 종료합니다.", file=sys.stderr)
        sys.exit(1)

    report = generate_report(df, args.checkm2_threshold)

    # 화면 출력
    print()
    print(report)

    # 파일 저장
    os.makedirs(os.path.dirname(output_summary) or ".", exist_ok=True)
    with open(output_summary, "w") as f:
        f.write(report)
    print(f"Saved: {output_summary}")

    os.makedirs(os.path.dirname(output_detail) or ".", exist_ok=True)
    df.to_csv(output_detail, sep="\t", index=False)
    print(f"Saved: {output_detail}")

    print("\n완료!")


if __name__ == "__main__":
    main()
