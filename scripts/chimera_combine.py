#!/usr/bin/env python3
"""
chimera_combine.py — Junction + Embedding 두 방법 결합 분석

Union (둘 중 하나라도 chimera) → Recall 극대화
Intersection (둘 다 chimera) → Precision 극대화

사용법:
    python3 ~/evo2-mag/scripts/chimera_combine.py
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    tp = int(np.sum(y_true & y_pred))
    fp = int(np.sum(~y_true & y_pred))
    fn = int(np.sum(y_true & ~y_pred))
    tn = int(np.sum(~y_true & ~y_pred))
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return {"Precision": precision, "Recall": recall, "F1": f1,
            "TP": tp, "FP": fp, "FN": fn, "TN": tn}


def main():
    parser = argparse.ArgumentParser(description="Junction + Embedding 결합 분석")
    parser.add_argument("--junction-bins", default=os.path.expanduser("~/results/chimera_junction_bins.tsv"))
    parser.add_argument("--embedding-bins", default=os.path.expanduser("~/results/chimera_embedding_bins.tsv"))
    parser.add_argument("--detail-tsv", default=os.path.expanduser("~/results/chimera_validation_detail.tsv"))
    parser.add_argument("--output-dir", default=os.path.expanduser("~/results"))
    parser.add_argument("--n-thresholds", type=int, default=200)
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    print("=" * 70)
    print("=== Chimera Combined Analysis (Junction + Embedding) ===")
    print("=" * 70)

    # 1. 데이터 로딩
    junc_df = pd.read_csv(args.junction_bins, sep="\t")
    emb_df  = pd.read_csv(args.embedding_bins, sep="\t")

    # detail.tsv에서 baseline 예측값
    detail_df = pd.read_csv(args.detail_tsv, sep="\t")

    # 공통 bins 기준으로 merge
    bins_all = sorted(set(junc_df["bin_name"]) & set(emb_df["bin_name"]) & set(detail_df["bin_name"]))
    print(f"공통 bins: {len(bins_all)}개")

    # gold standard
    gold = dict(zip(detail_df["bin_name"], detail_df["true_chimera"]))
    checkm2_pred = dict(zip(detail_df["bin_name"], detail_df["checkm2_predicted"]))
    evo2_ratio = dict(zip(detail_df["bin_name"], detail_df["evo2_flagged_ratio"]))

    # junction: max_junction score
    junc_scores = dict(zip(junc_df["bin_name"], junc_df["max_junction"]))
    # embedding: max_outlier_score
    emb_scores = dict(zip(emb_df["bin_name"], emb_df["max_outlier_score"]))

    # 평가용 배열
    y_true = np.array([gold[b] for b in bins_all], dtype=bool)
    y_cm2  = np.array([checkm2_pred[b] for b in bins_all], dtype=bool)
    y_evo2_any = np.array([evo2_ratio[b] > 0.0 for b in bins_all], dtype=bool)

    total = len(bins_all)
    n_pos = int(y_true.sum())

    # 2. 개별 best threshold (각 방법에서 가져온 값)
    # Junction: best threshold sweep
    j_vals = np.array([junc_scores[b] for b in bins_all])
    best_jt, best_jf1 = 0.0, -1.0
    for t in np.linspace(j_vals.min(), j_vals.max(), args.n_thresholds):
        m = compute_metrics(y_true, j_vals > t)
        if m["F1"] > best_jf1:
            best_jf1 = m["F1"]
            best_jt = t

    # Embedding: best threshold sweep
    e_vals = np.array([emb_scores[b] for b in bins_all])
    e_finite = e_vals[np.isfinite(e_vals)]
    best_et, best_ef1 = 0.0, -1.0
    for t in np.linspace(e_finite.min(), e_finite.max(), args.n_thresholds):
        y_pred = (e_vals > t) | np.isinf(e_vals)
        m = compute_metrics(y_true, y_pred)
        if m["F1"] > best_ef1:
            best_ef1 = m["F1"]
            best_et = t

    y_junc = j_vals > best_jt
    y_emb  = (e_vals > best_et) | np.isinf(e_vals)

    # 3. 결합 방식
    y_union = y_junc | y_emb
    y_inter = y_junc & y_emb

    m_cm2     = compute_metrics(y_true, y_cm2)
    m_evo2any = compute_metrics(y_true, y_evo2_any)
    m_junc    = compute_metrics(y_true, y_junc)
    m_emb     = compute_metrics(y_true, y_emb)
    m_union   = compute_metrics(y_true, y_union)
    m_inter   = compute_metrics(y_true, y_inter)

    # 4. 2D threshold sweep (junction × embedding)
    print("\n2D threshold sweep 실행 중...")
    best_2d = {"F1": -1.0, "jt": 0.0, "et": 0.0, "mode": "", "metrics": None}

    j_range = np.linspace(j_vals.min(), j_vals.max(), 50)
    e_range = np.linspace(e_finite.min(), e_finite.max(), 50)

    for jt in j_range:
        yj = j_vals > jt
        for et in e_range:
            ye = (e_vals > et) | np.isinf(e_vals)
            for mode, yc in [("union", yj | ye), ("inter", yj & ye)]:
                m = compute_metrics(y_true, yc)
                if m["F1"] > best_2d["F1"]:
                    best_2d = {"F1": m["F1"], "jt": jt, "et": et, "mode": mode, "metrics": m}

    m_best2d = best_2d["metrics"]

    # 5. 리포트
    lines = []
    lines.append("=" * 80)
    lines.append("=== Chimera Combined Analysis — Validation Report ===")
    lines.append("=" * 80)
    lines.append(f"Total bins: {total}  |  True chimeras: {n_pos}/{total} ({100*n_pos/total:.1f}%)")
    lines.append(f"Junction best threshold: {best_jt:.2f}  |  Embedding best threshold: {best_et:.2f}")
    lines.append("")

    hdr = f"{'Method':<35s} {'Prec':>7s} {'Recall':>7s} {'F1':>7s}   {'TP':>4s} {'FP':>4s} {'FN':>4s} {'TN':>4s}"
    lines.append(hdr)
    lines.append("-" * len(hdr))

    for label, m in [
        ("CheckM2 (>5%)", m_cm2),
        ("Evo2 perplexity (any flag)", m_evo2any),
        ("Junction (max_delta)", m_junc),
        ("Embedding (max_outlier, C)", m_emb),
        ("Union (J ∪ E)", m_union),
        ("Intersection (J ∩ E)", m_inter),
        (f"Best 2D ({best_2d['mode']}, jt={best_2d['jt']:.2f}, et={best_2d['et']:.2f})", m_best2d),
    ]:
        lines.append(
            f"{label:<35s} {m['Precision']:>7.4f} {m['Recall']:>7.4f} {m['F1']:>7.4f}   "
            f"{m['TP']:>4d} {m['FP']:>4d} {m['FN']:>4d} {m['TN']:>4d}"
        )

    lines.append("")

    # 놓친 chimera 분석
    lines.append("=== 각 방법별 놓친 True chimera ===")
    for label, y_pred in [("Junction", y_junc), ("Embedding", y_emb),
                           ("Union", y_union), ("Intersection", y_inter)]:
        missed = [bins_all[i] for i in range(total) if y_true[i] and not y_pred[i]]
        lines.append(f"  {label}: {len(missed)}개 놓침 — {', '.join(missed) if missed else '(없음)'}")
    lines.append("")

    # FP 분석
    lines.append("=== FP 비교 ===")
    fp_junc = set(bins_all[i] for i in range(total) if not y_true[i] and y_junc[i])
    fp_emb  = set(bins_all[i] for i in range(total) if not y_true[i] and y_emb[i])
    fp_both = fp_junc & fp_emb
    fp_junc_only = fp_junc - fp_emb
    fp_emb_only  = fp_emb - fp_junc
    lines.append(f"  Junction FP: {len(fp_junc)}개  |  Embedding FP: {len(fp_emb)}개")
    lines.append(f"  둘 다 FP: {len(fp_both)}개  |  Junction만: {len(fp_junc_only)}개  |  Embedding만: {len(fp_emb_only)}개")
    lines.append(f"  Union FP: {len(fp_junc | fp_emb)}개  |  Intersection FP: {len(fp_both)}개")
    lines.append("")

    report = "\n".join(lines)
    print(report)

    out_path = os.path.join(args.output_dir, "chimera_combined_summary.txt")
    with open(out_path, "w") as f:
        f.write(report)
    print(f"Saved: {out_path}")

    # 상세 테이블
    rows = []
    for i, b in enumerate(bins_all):
        rows.append({
            "bin_name": b,
            "true_chimera": bool(y_true[i]),
            "checkm2_pred": bool(y_cm2[i]),
            "junction_score": junc_scores[b],
            "junction_pred": bool(y_junc[i]),
            "embedding_score": emb_scores[b],
            "embedding_pred": bool(y_emb[i]),
            "union_pred": bool(y_union[i]),
            "intersection_pred": bool(y_inter[i]),
        })
    out_detail = os.path.join(args.output_dir, "chimera_combined_detail.tsv")
    pd.DataFrame(rows).to_csv(out_detail, sep="\t", index=False)
    print(f"Saved: {out_detail}")
    print("\n완료!")


if __name__ == "__main__":
    main()
