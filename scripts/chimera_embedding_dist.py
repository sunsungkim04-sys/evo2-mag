#!/usr/bin/env python3
"""
chimera_embedding_dist.py — Embedding 거리 기반 키메라 탐지 개선

아이디어: 키메라 bin의 contig은 자기 bin centroid보다 다른 bin centroid에 더 가까울 것.
outlier_score = d_own / d_nearest_other (>1.0이면 다른 bin이 더 가까움)
cosine distance 사용 (Evo2 임베딩은 방향이 종 정보를 인코딩).

사용법:
    python3 ~/evo2-mag/scripts/chimera_embedding_dist.py
    python3 ~/evo2-mag/scripts/chimera_embedding_dist.py \\
        --embeddings  ~/results/contig_embeddings.npz \\
        --names       ~/results/contig_names.txt \\
        --results-dir ~/results \\
        --detail-tsv  ~/results/chimera_validation_detail.tsv \\
        --output-dir  ~/results
"""

import argparse
import glob
import os
import re
import sys
import warnings
from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_distances


# ──────────────────────────────────────────────────────────────────────
# 1. Embeddings 로딩
# ──────────────────────────────────────────────────────────────────────
def load_embeddings(npz_path: str, names_path: str) -> tuple:
    """
    contig_embeddings.npz + contig_names.txt 로딩.
    Returns: (emb_matrix, names_list, name_to_idx)
      - emb_matrix: np.ndarray shape (N, 4096), float32
      - names_list: list[str], len N
      - name_to_idx: dict {contig_name: row_index}
    """
    print(f"  Embeddings 로딩: {npz_path}")
    data = np.load(npz_path)
    emb_matrix = data["embeddings"]  # (42320, 4096)

    with open(names_path) as f:
        names_list = [line.strip() for line in f if line.strip()]

    if len(names_list) != emb_matrix.shape[0]:
        print(f"ERROR: names ({len(names_list)}) ≠ embeddings rows ({emb_matrix.shape[0]})",
              file=sys.stderr)
        sys.exit(1)

    name_to_idx = {name: i for i, name in enumerate(names_list)}
    print(f"  완료: {len(names_list):,}개 contigs, {emb_matrix.shape[1]}d embeddings")
    return emb_matrix, names_list, name_to_idx


# ──────────────────────────────────────────────────────────────────────
# 2. Gold standard 로딩
# ──────────────────────────────────────────────────────────────────────
def load_gold_standard(detail_tsv: str) -> dict:
    """
    chimera_validation_detail.tsv의 true_chimera 컬럼에서 {bin_name: bool} 반환.
    """
    gold = {}
    with open(detail_tsv) as f:
        header = f.readline().strip().split("\t")
        try:
            bn_idx = header.index("bin_name")
            tc_idx = header.index("true_chimera")
        except ValueError as e:
            print(f"ERROR: 필요한 컬럼 없음: {e}", file=sys.stderr)
            sys.exit(1)
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) > max(bn_idx, tc_idx):
                gold[parts[bn_idx]] = parts[tc_idx].strip().lower() in ("true", "1")
    print(f"Gold standard 로딩 완료: {len(gold)}개 bins (True chimera: {sum(gold.values())}개)")
    return gold


def load_baseline_predictions(detail_tsv: str) -> tuple:
    """
    CheckM2, Evo2 any-flag 기준선 예측값 로딩.
    Returns: (checkm2_pred_dict, evo2_anyflag_dict)
    """
    checkm2 = {}
    evo2_any = {}
    with open(detail_tsv) as f:
        header = f.readline().strip().split("\t")
        try:
            bn_idx    = header.index("bin_name")
            cm2_idx   = header.index("checkm2_predicted")
            ratio_idx = header.index("evo2_flagged_ratio")
        except ValueError:
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
                    evo2_any[bn] = float(parts[ratio_idx]) > 0.0
                except ValueError:
                    evo2_any[bn] = False
    return checkm2, evo2_any


# ──────────────────────────────────────────────────────────────────────
# 3. Baseline bins 로딩 (validate_chimera.py와 동일 로직)
# ──────────────────────────────────────────────────────────────────────
def load_baseline_bins(results_dir: str, n_samples: int = 21) -> dict:
    """
    각 샘플의 bins/*.fa 파일을 읽어 {bin_name: [contig_names]} 반환.
    FASTA 헤더에서 range suffix (_숫자-숫자) 제거.
    """
    bin_contigs = {}
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
                        raw_name = line[1:].strip().split()[0]
                        clean_name = range_suffix_re.sub("", raw_name)
                        contigs.append(clean_name)
            bin_contigs[bin_name] = contigs

    total_contigs = sum(len(v) for v in bin_contigs.values())
    print(f"Baseline bins 로딩 완료: {len(bin_contigs)}개 bins, {total_contigs:,}개 contigs")
    return bin_contigs


# ──────────────────────────────────────────────────────────────────────
# 4. Bin centroids 계산
# ──────────────────────────────────────────────────────────────────────
def build_bin_centroids(
    bin_contigs: dict,
    emb_matrix: np.ndarray,
    name_to_idx: dict,
) -> tuple:
    """
    각 bin의 centroid (embedded contigs 평균) 계산.

    Returns:
        bin_names:         list[str] — 131개 bin 이름 (정렬된 순서)
        centroids:         np.ndarray shape (131, 4096)
        bin_to_col:        dict {bin_name: column_index_in_centroids}
        bin_emb_indices:   dict {bin_name: [embedding_row_indices]}
        bin_coverage:      dict {bin_name: {"n_total": int, "n_embedded": int}}
    """
    bin_names = sorted(bin_contigs.keys())
    dim = emb_matrix.shape[1]

    centroids_list = []
    bin_emb_indices = {}
    bin_coverage = {}

    n_missing_total = 0
    for bin_name in bin_names:
        contigs = bin_contigs[bin_name]
        embedded_idxs = [name_to_idx[c] for c in contigs if c in name_to_idx]
        n_missing = len(contigs) - len(embedded_idxs)
        n_missing_total += n_missing

        bin_coverage[bin_name] = {
            "n_total":    len(contigs),
            "n_embedded": len(embedded_idxs),
        }

        if len(embedded_idxs) == 0:
            # embedding 없는 bin → zero centroid, metrics에서 제외
            centroids_list.append(np.zeros(dim, dtype=np.float32))
            bin_emb_indices[bin_name] = []
        else:
            bin_embs = emb_matrix[embedded_idxs]  # (k, 4096)
            centroid = bin_embs.mean(axis=0)
            centroids_list.append(centroid)
            bin_emb_indices[bin_name] = embedded_idxs

    centroids = np.vstack(centroids_list)  # (131, 4096)
    bin_to_col = {name: i for i, name in enumerate(bin_names)}

    n_no_emb = sum(1 for bn in bin_names if len(bin_emb_indices[bn]) == 0)
    print(f"Centroids 계산 완료: {len(bin_names)}개 bins, {n_no_emb}개 embedding 없음, "
          f"contig 미매핑 {n_missing_total:,}개")
    return bin_names, centroids, bin_to_col, bin_emb_indices, bin_coverage


# ──────────────────────────────────────────────────────────────────────
# 5. Outlier score 계산 (벡터화)
# ──────────────────────────────────────────────────────────────────────
def compute_outlier_scores(
    bin_names: list,
    centroids: np.ndarray,
    bin_to_col: dict,
    bin_emb_indices: dict,
    bin_coverage: dict,
    emb_matrix: np.ndarray,
    names_list: list,
) -> list:
    """
    각 contig에 대해 outlier_score = d_own / d_nearest_other 계산.
    sklearn.metrics.pairwise.cosine_distances 벡터화 연산 사용.

    Returns: list of dicts (per-contig rows)
    """
    # embedding이 있는 contig indices만 수집
    all_emb_idx = []
    for bn in bin_names:
        all_emb_idx.extend(bin_emb_indices[bn])
    unique_idx = sorted(set(all_emb_idx))

    if not unique_idx:
        print("ERROR: 어떤 bin에도 embedding이 없습니다.", file=sys.stderr)
        sys.exit(1)

    # 서브행렬 추출 + 전체 cosine distance 행렬 한 번에 계산
    print(f"  cosine_distances 계산: ({len(unique_idx)}, {emb_matrix.shape[1]}) × "
          f"({len(bin_names)}, {emb_matrix.shape[1]})")
    contig_sub = emb_matrix[unique_idx]          # (M, 4096)
    dist_mat   = cosine_distances(contig_sub, centroids)  # (M, 131)
    idx_to_row = {orig: row for row, orig in enumerate(unique_idx)}

    # other bin indices lookup (bin_to_col에서 자기 자신 제외)
    n_bins = len(bin_names)
    other_cols_cache = {}  # bin_col → list of other column indices
    for col in range(n_bins):
        other_cols_cache[col] = [i for i in range(n_bins) if i != col]

    rows = []
    n_inf = 0
    for bin_name in bin_names:
        own_col = bin_to_col[bin_name]
        other_cols = other_cols_cache[own_col]

        for emb_idx in bin_emb_indices[bin_name]:
            row_in_sub = idx_to_row[emb_idx]
            d_own = float(dist_mat[row_in_sub, own_col])

            other_dists      = dist_mat[row_in_sub, other_cols]
            nearest_other_pos = int(other_dists.argmin())
            d_nearest_other  = float(other_dists[nearest_other_pos])
            nearest_other_bin = bin_names[other_cols[nearest_other_pos]]

            if d_nearest_other < 1e-10:
                # 두 bin centroid가 동일 — edge case
                warnings.warn(f"d_nearest_other ≈ 0 for contig {names_list[emb_idx]} "
                               f"(bin={bin_name}). outlier_score=inf.")
                outlier_score = float("inf")
                n_inf += 1
            else:
                outlier_score = d_own / d_nearest_other

            rows.append({
                "bin_name":          bin_name,
                "contig_name":       names_list[emb_idx],
                "d_own":             d_own,
                "d_nearest_other":   d_nearest_other,
                "nearest_other_bin": nearest_other_bin,
                "outlier_score":     outlier_score,
                "is_outlier":        outlier_score > 1.0,
            })

    if n_inf > 0:
        print(f"  [경고] outlier_score=inf인 contig: {n_inf}개 (중복 centroid)")
    print(f"Outlier scores 계산 완료: {len(rows):,}개 contigs")
    return rows


# ──────────────────────────────────────────────────────────────────────
# 6. Bin별 집계
# ──────────────────────────────────────────────────────────────────────
def compute_bin_predictions(
    contig_rows: list,
    bin_coverage: dict,
    gold: dict,
) -> list:
    """
    contig별 outlier_score를 bin별로 집계.
    """
    bin_scores       = defaultdict(list)
    bin_outlier_cnt  = defaultdict(int)

    for row in contig_rows:
        bn = row["bin_name"]
        bin_scores[bn].append(row["outlier_score"])
        if row["is_outlier"]:
            bin_outlier_cnt[bn] += 1

    rows = []
    for bin_name in sorted(bin_scores.keys()):
        scores = [s for s in bin_scores[bin_name] if not np.isinf(s)]
        n_embedded = len(bin_scores[bin_name])
        n_outlier  = bin_outlier_cnt[bin_name]
        cov = bin_coverage.get(bin_name, {"n_total": 0, "n_embedded": 0})

        rows.append({
            "bin_name":           bin_name,
            "n_total_contigs":    cov["n_total"],
            "n_embedded_contigs": cov["n_embedded"],
            "embedding_coverage": cov["n_embedded"] / cov["n_total"] if cov["n_total"] > 0 else 0.0,
            "n_outlier_contigs":  n_outlier,
            "outlier_fraction":   n_outlier / n_embedded if n_embedded > 0 else 0.0,
            "max_outlier_score":  float(max(scores)) if scores else np.nan,
            "mean_outlier_score": float(np.mean(scores)) if scores else np.nan,
            "true_chimera":       gold.get(bin_name, None),
        })
    print(f"Bin predictions 집계 완료: {len(rows)}개 bins")
    return rows


# ──────────────────────────────────────────────────────────────────────
# 7. 지표 계산
# ──────────────────────────────────────────────────────────────────────
def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Binary classification 지표."""
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
# 8. Threshold sweep 및 리포트
# ──────────────────────────────────────────────────────────────────────
def sweep_and_report(
    bin_df: pd.DataFrame,
    checkm2_pred: dict,
    evo2_any_pred: dict,
    n_thresholds: int = 200,
) -> tuple:
    """
    세 가지 방법으로 threshold sweep.
    Returns: (report_str, bin_df_with_predictions)
    """
    eval_df = bin_df[bin_df["true_chimera"].notna()].copy()
    if eval_df.empty:
        return "No bins with gold standard — nothing to evaluate.\n", bin_df

    y_true = eval_df["true_chimera"].values.astype(bool)
    total  = len(eval_df)
    n_pos  = int(y_true.sum())

    # 기준선
    y_cm2     = np.array([checkm2_pred.get(b, False) for b in eval_df["bin_name"]], dtype=bool)
    y_evo2any = np.array([evo2_any_pred.get(b, False) for b in eval_df["bin_name"]], dtype=bool)
    m_cm2     = compute_metrics(y_true, y_cm2)
    m_evo2any = compute_metrics(y_true, y_evo2any)

    # Method A: any outlier (threshold 없음)
    y_methodA = eval_df["n_outlier_contigs"].values > 0
    m_A = compute_metrics(y_true, y_methodA.astype(bool))

    # Method B: outlier_fraction > threshold sweep
    frac_scores = eval_df["outlier_fraction"].values.astype(np.float64)
    best_B = {"F1": -1.0, "threshold": 0.0, "metrics": None}
    for t in np.linspace(0.0, min(frac_scores.max(), 1.0), n_thresholds):
        m = compute_metrics(y_true, frac_scores > t)
        if m["F1"] > best_B["F1"]:
            best_B = {"F1": m["F1"], "threshold": t, "metrics": m}

    # Method C: max_outlier_score > threshold sweep
    max_scores = eval_df["max_outlier_score"].values.astype(np.float64)
    # inf 처리: 유효한 max 값 기준으로 sweep
    valid_max = max_scores[np.isfinite(max_scores)]
    if len(valid_max) == 0:
        best_C = {"F1": 0.0, "threshold": 1.0, "metrics": compute_metrics(y_true, np.zeros(total, dtype=bool))}
    else:
        best_C = {"F1": -1.0, "threshold": 1.0, "metrics": None}
        for t in np.linspace(0.0, valid_max.max(), n_thresholds):
            y_pred = (max_scores > t) | np.isinf(max_scores)
            m = compute_metrics(y_true, y_pred.astype(bool))
            if m["F1"] > best_C["F1"]:
                best_C = {"F1": m["F1"], "threshold": t, "metrics": m}

    # predicted 컬럼 추가
    bin_df["predicted_methodA"] = bin_df["n_outlier_contigs"] > 0
    bin_df["predicted_methodB"] = bin_df["outlier_fraction"] > best_B["threshold"]
    bin_df["predicted_methodC"] = (bin_df["max_outlier_score"] > best_C["threshold"]) | \
                                   bin_df["max_outlier_score"].apply(lambda x: np.isinf(x) if not np.isnan(x) else False)

    # 리포트
    lines = []
    lines.append("=" * 80)
    lines.append("=== Chimera Embedding Distance Detection — Validation Report ===")
    lines.append("=" * 80)
    lines.append(f"Total bins evaluated: {total}  |  True chimeras: {n_pos}/{total} ({100*n_pos/total:.1f}%)")
    lines.append(f"Metric: cosine distance, outlier_score = d_own / d_nearest_other")
    lines.append("")

    hdr = f"{'Method':<30s} {'Precision':>9s} {'Recall':>9s} {'F1':>9s}   {'TP':>4s} {'FP':>4s} {'FN':>4s} {'TN':>4s}  {'Best threshold':>16s}"
    lines.append("=== Metrics: Embedding outlier methods ===")
    lines.append("(bin predicted chimera if score > threshold)")
    lines.append("")
    lines.append(hdr)
    lines.append("-" * len(hdr))

    lines.append(
        f"{'Method A (any outlier)':<30s} {m_A['Precision']:>9.4f} {m_A['Recall']:>9.4f} {m_A['F1']:>9.4f}   "
        f"{m_A['TP']:>4d} {m_A['FP']:>4d} {m_A['FN']:>4d} {m_A['TN']:>4d}  {'(binary)':>16s}"
    )
    m_B = best_B["metrics"]
    lines.append(
        f"{'Method B (frac>best_t)':<30s} {m_B['Precision']:>9.4f} {m_B['Recall']:>9.4f} {m_B['F1']:>9.4f}   "
        f"{m_B['TP']:>4d} {m_B['FP']:>4d} {m_B['FN']:>4d} {m_B['TN']:>4d}  {best_B['threshold']:>16.4f}"
    )
    m_C = best_C["metrics"]
    lines.append(
        f"{'Method C (max>best_t)':<30s} {m_C['Precision']:>9.4f} {m_C['Recall']:>9.4f} {m_C['F1']:>9.4f}   "
        f"{m_C['TP']:>4d} {m_C['FP']:>4d} {m_C['FN']:>4d} {m_C['TN']:>4d}  {best_C['threshold']:>16.4f}"
    )
    lines.append("-" * len(hdr))
    lines.append("=== Baseline (from chimera_validation_detail.tsv) ===")
    lines.append(
        f"{'CheckM2 (>5%)':<30s} {m_cm2['Precision']:>9.4f} {m_cm2['Recall']:>9.4f} {m_cm2['F1']:>9.4f}   "
        f"{m_cm2['TP']:>4d} {m_cm2['FP']:>4d} {m_cm2['FN']:>4d} {m_cm2['TN']:>4d}  {'(N/A)':>16s}"
    )
    lines.append(
        f"{'Evo2 perplexity (any)':<30s} {m_evo2any['Precision']:>9.4f} {m_evo2any['Recall']:>9.4f} {m_evo2any['F1']:>9.4f}   "
        f"{m_evo2any['TP']:>4d} {m_evo2any['FP']:>4d} {m_evo2any['FN']:>4d} {m_evo2any['TN']:>4d}  {'(N/A)':>16s}"
    )
    lines.append("")

    # 가장 좋은 method 기준으로 상세 분석
    methods_results = [("A", y_methodA.astype(bool), m_A),
                       ("B", frac_scores > best_B["threshold"], m_B),
                       ("C", (max_scores > best_C["threshold"]) | np.isinf(max_scores), m_C)]
    best_letter, y_best, _ = max(methods_results, key=lambda x: x[2]["F1"])

    caught_only = eval_df[y_best & ~y_cm2 & y_true]
    lines.append(f"=== Embedding-only caught (best: Method {best_letter}): {len(caught_only)}개 ===")
    for _, row in caught_only.iterrows():
        lines.append(f"  {row['bin_name']}  outlier_frac={row['outlier_fraction']:.3f}  "
                     f"max_outlier={row['max_outlier_score']:.3f}  "
                     f"n_emb={int(row['n_embedded_contigs'])}/{int(row['n_total_contigs'])}")
    lines.append("")

    missed = eval_df[~y_best & y_true]
    lines.append(f"=== 놓친 True chimera (best method): {len(missed)}개 ===")
    for _, row in missed.iterrows():
        lines.append(f"  {row['bin_name']}  outlier_frac={row['outlier_fraction']:.3f}  "
                     f"max_outlier={row['max_outlier_score']:.3f}  "
                     f"emb_coverage={row['embedding_coverage']:.2f}")
    lines.append("")

    # Embedding coverage 통계
    cov_vals = eval_df["embedding_coverage"].values
    lines.append("=== Embedding coverage 통계 ===")
    lines.append(f"평균: {cov_vals.mean():.3f}  중앙값: {np.median(cov_vals):.3f}  "
                 f"최솟값: {cov_vals.min():.3f}  최댓값: {cov_vals.max():.3f}")
    n_low_cov = int((cov_vals < 0.5).sum())
    lines.append(f"Embedding coverage < 50%인 bins: {n_low_cov}개 (결과 신뢰도 낮음)")
    lines.append("")

    return "\n".join(lines), bin_df


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Embedding 거리 기반 키메라 탐지 개선"
    )
    parser.add_argument(
        "--embeddings", default=os.path.expanduser("~/results/contig_embeddings.npz"),
        help="contig_embeddings.npz 경로"
    )
    parser.add_argument(
        "--names", default=os.path.expanduser("~/results/contig_names.txt"),
        help="contig_names.txt 경로"
    )
    parser.add_argument(
        "--results-dir", default=os.path.expanduser("~/results"),
        help="baseline bin FASTA 루트 디렉토리"
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
        "--n-samples", type=int, default=21,
        help="CAMI2 샘플 수 (기본: 21)"
    )
    parser.add_argument(
        "--n-thresholds", type=int, default=200,
        help="threshold sweep 단계 수 (기본: 200)"
    )
    args = parser.parse_args()

    output_dir = os.path.expanduser(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print("Chimera Embedding Distance Detection")
    print("=" * 60)
    print(f"Embeddings : {args.embeddings}")
    print(f"Names      : {args.names}")
    print(f"Results dir: {args.results_dir}")
    print(f"Detail TSV : {args.detail_tsv}")
    print(f"Output dir : {output_dir}")
    print()

    # [1/5] Gold standard
    print("[1/5] Gold standard 로딩...")
    gold = load_gold_standard(args.detail_tsv)
    checkm2_pred, evo2_any_pred = load_baseline_predictions(args.detail_tsv)
    print()

    # [2/5] Embeddings
    print("[2/5] Embeddings 로딩...")
    emb_matrix, names_list, name_to_idx = load_embeddings(args.embeddings, args.names)
    print()

    # [3/5] Baseline bins
    print("[3/5] Baseline bin FASTA 파싱...")
    bin_contigs = load_baseline_bins(args.results_dir, args.n_samples)
    if not bin_contigs:
        print("ERROR: Baseline bin을 로딩할 수 없습니다.", file=sys.stderr)
        sys.exit(1)
    print()

    # [4/5] Centroids + outlier scores
    print("[4/5] Centroids 계산 및 outlier scores 계산...")
    bin_names, centroids, bin_to_col, bin_emb_indices, bin_coverage = build_bin_centroids(
        bin_contigs, emb_matrix, name_to_idx
    )
    contig_rows = compute_outlier_scores(
        bin_names, centroids, bin_to_col, bin_emb_indices, bin_coverage,
        emb_matrix, names_list
    )
    bin_rows = compute_bin_predictions(contig_rows, bin_coverage, gold)
    print()

    # [5/5] Threshold sweep 및 리포트
    print("[5/5] Threshold sweep 및 리포트 생성...")
    contig_df = pd.DataFrame(contig_rows)
    bin_df    = pd.DataFrame(bin_rows)

    report, bin_df = sweep_and_report(bin_df, checkm2_pred, evo2_any_pred, args.n_thresholds)
    print()
    print(report)

    # 파일 저장
    out_contigs = os.path.join(output_dir, "chimera_embedding_contigs.tsv")
    out_bins    = os.path.join(output_dir, "chimera_embedding_bins.tsv")
    out_summary = os.path.join(output_dir, "chimera_embedding_summary.txt")

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
