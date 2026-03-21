#!/usr/bin/env python3
"""Phase 3b v4: Evo2 임베딩 + 커버리지 결합 → 샘플별 UMAP + HDBSCAN.

v2 대비 개선: Evo2 4096d 임베딩에 log-coverage를 결합하여
같은 종의 contig이 비슷한 abundance를 갖는 특성을 활용.

Usage:
    python run_cluster_v2_cov.py \
        --embeddings ~/results/contig_embeddings.npz \
        --names ~/results/contig_names.txt \
        --data_dir ~/results \
        --output_dir ~/results \
        --suffix v4 \
        --cov_weight 0.5
"""
import argparse
import glob
import os
from collections import defaultdict

import hdbscan
import numpy as np
import umap
from Bio import SeqIO
from sklearn.preprocessing import StandardScaler


def load_sample_contigs(data_dir, sample_name):
    """해당 샘플의 assembly FASTA에서 contig 로드."""
    pattern = os.path.join(data_dir, sample_name, "results", f"{sample_name}_assembly.fasta")
    fasta_files = glob.glob(pattern)
    contigs = {}
    for f in fasta_files:
        for rec in SeqIO.parse(f, "fasta"):
            contigs[rec.id] = rec
    return contigs


def load_coverage(data_dir, sample_name):
    """mmlong2 cov.tsv에서 contig별 coverage 로드."""
    cov_path = os.path.join(data_dir, sample_name, "tmp", "binning", "round_1", "cov.tsv")
    coverage = {}
    if os.path.exists(cov_path):
        with open(cov_path) as f:
            header = f.readline()  # skip header
            for line in f:
                parts = line.strip().split("\t")
                contig_name = parts[0]
                avg_depth = float(parts[2])  # totalAvgDepth
                coverage[contig_name] = avg_depth
    return coverage


def cluster_sample(sample_name, indices, embeddings, names, coverage,
                   min_cluster_size, min_samples, umap_neighbors, umap_components,
                   min_contig_len, contig_lengths, min_prob, cov_weight, metric="euclidean"):
    """Evo2 임베딩 + coverage 결합 후 UMAP + HDBSCAN."""
    # 1kb 필터링
    if min_contig_len > 0 and contig_lengths is not None:
        mask = np.array([contig_lengths.get(names[i], 0) >= min_contig_len for i in indices])
        filtered_indices = [idx for idx, m in zip(indices, mask) if m]
        n_filtered = len(indices) - len(filtered_indices)
    else:
        filtered_indices = indices
        n_filtered = 0

    if len(filtered_indices) < min_cluster_size:
        print(f"  {sample_name}: {len(filtered_indices)} contigs — 스킵")
        return {}, n_filtered

    emb = embeddings[filtered_indices]

    # Z-score 정규화
    scaler_emb = StandardScaler()
    emb_norm = scaler_emb.fit_transform(emb)

    # Cosine: L2-normalize → euclidean (수학적으로 cosine distance와 동일)
    if metric == "cosine":
        norms = np.linalg.norm(emb_norm, axis=1, keepdims=True)
        norms[norms == 0] = 1
        emb_norm = emb_norm / norms

    # Coverage 결합
    n_with_cov = 0
    if coverage and cov_weight > 0:
        cov_values = []
        for i in filtered_indices:
            cov = coverage.get(names[i], 0.0)
            # log(1 + depth)로 스케일 압축
            cov_values.append(np.log1p(cov))
        cov_arr = np.array(cov_values).reshape(-1, 1)
        n_with_cov = (cov_arr > 0).sum()

        # Coverage도 z-score 정규화 후 가중치 적용
        scaler_cov = StandardScaler()
        cov_norm = scaler_cov.fit_transform(cov_arr) * cov_weight

        # 임베딩 + 커버리지 결합
        emb_combined = np.hstack([emb_norm, cov_norm])
    else:
        emb_combined = emb_norm

    # UMAP
    n_neighbors = min(umap_neighbors, len(filtered_indices) - 1)
    if n_neighbors < 2:
        print(f"  {sample_name}: contigs 너무 적음, 스킵")
        return {}, n_filtered

    n_comp = min(umap_components, len(filtered_indices) - 1)
    reducer = umap.UMAP(
        n_neighbors=n_neighbors,
        n_components=n_comp,
        min_dist=0.0,
        metric="euclidean",
        random_state=42,
    )
    emb_umap = reducer.fit_transform(emb_combined)

    # HDBSCAN
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="euclidean",
        cluster_selection_method="leaf",
        core_dist_n_jobs=-1,
    )
    labels = clusterer.fit_predict(emb_umap)
    probabilities = clusterer.probabilities_

    # 확률 필터링
    n_before_prob = (labels != -1).sum()
    if min_prob > 0:
        low_prob_mask = (labels != -1) & (probabilities < min_prob)
        labels[low_prob_mask] = -1

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_assigned = (labels != -1).sum()
    n_total = len(labels)
    noise_pct = (labels == -1).sum() / n_total * 100
    n_prob_filtered = n_before_prob - n_assigned

    prob_info = f", {n_prob_filtered} prob<{min_prob}" if min_prob > 0 else ""
    cov_info = f", cov={n_with_cov}/{n_total}" if cov_weight > 0 else ""
    print(f"  {sample_name}: {n_total} contigs → {n_clusters} clusters, "
          f"{n_assigned} assigned ({100 - noise_pct:.1f}%)"
          f"{prob_info}{cov_info}")

    assignments = {}
    for idx, label in zip(filtered_indices, labels):
        if label != -1:
            assignments[names[idx]] = f"{sample_name}_evo2_bin.{label}"

    return assignments, n_filtered


def main():
    parser = argparse.ArgumentParser(description="Evo2 + coverage 결합 클러스터링")
    parser.add_argument("--embeddings", default=os.path.expanduser("~/results/contig_embeddings.npz"))
    parser.add_argument("--names", default=os.path.expanduser("~/results/contig_names.txt"))
    parser.add_argument("--data_dir", default=os.path.expanduser("~/results"))
    parser.add_argument("--output_dir", default=os.path.expanduser("~/results"))
    parser.add_argument("--min_cluster_size", type=int, default=3)
    parser.add_argument("--min_samples", type=int, default=1)
    parser.add_argument("--umap_neighbors", type=int, default=15)
    parser.add_argument("--umap_components", type=int, default=50)
    parser.add_argument("--min_contig_len", type=int, default=1000)
    parser.add_argument("--min_prob", type=float, default=0.0)
    parser.add_argument("--cov_weight", type=float, default=0.5,
                        help="커버리지 가중치 (0=임베딩만, 0.5=기본, 1.0=강하게)")
    parser.add_argument("--metric", default="euclidean",
                        help="Distance metric: euclidean or cosine (L2-norm + euclidean)")
    parser.add_argument("--suffix", default="v4")
    args = parser.parse_args()

    # 임베딩 로드
    print("임베딩 로드 중...")
    data = np.load(args.embeddings)
    embeddings = data["embeddings"]
    with open(args.names) as f:
        names = [line.strip() for line in f]
    print(f"  {len(names)} contigs, {embeddings.shape[1]}d")
    assert len(names) == embeddings.shape[0]

    # 샘플별 contig 인덱스
    sample_indices = defaultdict(list)
    for i, name in enumerate(names):
        parts = name.split("_contig_")
        sample_name = parts[0] if len(parts) == 2 else "unknown"
        sample_indices[sample_name].append(i)

    print(f"\n{len(sample_indices)}개 샘플 발견")

    # Contig 길이 + coverage 로드
    print("Contig 길이 & 커버리지 로드 중...")
    contig_lengths = {}
    all_coverage = {}
    for sample_name in sorted(sample_indices.keys()):
        if sample_name == "unknown":
            continue
        contigs_db = load_sample_contigs(args.data_dir, sample_name)
        for cid, rec in contigs_db.items():
            contig_lengths[cid] = len(rec.seq)
        cov = load_coverage(args.data_dir, sample_name)
        all_coverage.update(cov)
        print(f"  {sample_name}: {len(contigs_db)} contigs, {len(cov)} coverage entries")

    # 클러스터링
    print(f"\n=== 클러스터링 시작 (cov_weight={args.cov_weight}, metric={args.metric}) ===\n")

    all_assignments = {}
    total_filtered = 0

    for sample_name in sorted(sample_indices.keys()):
        if sample_name == "unknown":
            continue
        assignments, n_filtered = cluster_sample(
            sample_name=sample_name,
            indices=sample_indices[sample_name],
            embeddings=embeddings,
            names=names,
            coverage=all_coverage,
            min_cluster_size=args.min_cluster_size,
            min_samples=args.min_samples,
            umap_neighbors=args.umap_neighbors,
            umap_components=args.umap_components,
            min_contig_len=args.min_contig_len,
            contig_lengths=contig_lengths,
            min_prob=args.min_prob,
            cov_weight=args.cov_weight,
            metric=args.metric,
        )
        all_assignments.update(assignments)
        total_filtered += n_filtered

    # 결과 요약
    total_contigs = len(names)
    total_assigned = len(all_assignments)
    total_bins = len(set(all_assignments.values()))
    print(f"\n=== 결과 요약 (suffix={args.suffix}) ===")
    print(f"  전체: {total_contigs}, 할당: {total_assigned} ({total_assigned/total_contigs*100:.1f}%)")
    print(f"  총 bins: {total_bins}")

    # TSV 저장
    tsv_path = os.path.join(args.output_dir, f"evo2_c2b_{args.suffix}.tsv")
    with open(tsv_path, "w") as f:
        for name in names:
            if name in all_assignments:
                f.write(f"{name}\t{all_assignments[name]}\n")
    print(f"\n저장: {tsv_path}")

    # Bin FASTA 생성
    print("Bin FASTA 생성 중...")
    bin_dir_root = os.path.join(args.output_dir, f"evo2_bins_{args.suffix}")
    os.makedirs(bin_dir_root, exist_ok=True)

    sample_bin_contigs = defaultdict(lambda: defaultdict(list))
    for contig_name, bin_name in all_assignments.items():
        parts = contig_name.split("_contig_")
        sample_name = parts[0] if len(parts) == 2 else "unknown"
        sample_bin_contigs[sample_name][bin_name].append(contig_name)

    total_bin_files = 0
    for sample_name in sorted(sample_bin_contigs.keys()):
        contigs_db = load_sample_contigs(args.data_dir, sample_name)
        sample_dir = os.path.join(bin_dir_root, sample_name)
        os.makedirs(sample_dir, exist_ok=True)
        for bin_name, contig_names_list in sample_bin_contigs[sample_name].items():
            bin_fasta = os.path.join(sample_dir, f"{bin_name}.fa")
            records = [contigs_db[n] for n in contig_names_list if n in contigs_db]
            if records:
                SeqIO.write(records, bin_fasta, "fasta")
                total_bin_files += 1

    print(f"  {total_bin_files} bin FASTA → {bin_dir_root}/")
    print("\n완료!")


if __name__ == "__main__":
    main()
