#!/usr/bin/env python3
"""Phase 3b v2: 샘플별 UMAP + HDBSCAN 클러스터링.

v1 대비 개선사항:
  1. 글로벌 → 샘플별 클러스터링 (서로 다른 커뮤니티 혼합 방지)
  2. PCA → UMAP (지역 구조 보존, HDBSCAN 궁합 좋음)
  3. 공격적 HDBSCAN (min_cluster_size=3, min_samples=1, leaf)
  4. 1kb 미만 contig 필터링 (임베딩 품질 낮음)

Outputs:
  - evo2_c2b_v2.tsv: contig-to-bin mapping
  - evo2_bins_v2/: per-sample bin FASTA directories (Binette input)

Usage:
    python run_cluster_v2.py \
        --embeddings ~/results/contig_embeddings.npz \
        --names ~/results/contig_names.txt \
        --data_dir ~/results \
        --output_dir ~/results
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


def cluster_sample(sample_name, indices, embeddings, names, min_cluster_size, min_samples,
                   umap_neighbors, umap_components, min_contig_len, contig_lengths):
    """단일 샘플에 대해 UMAP + HDBSCAN 클러스터링 수행."""
    # 1kb 필터링
    if min_contig_len > 0 and contig_lengths is not None:
        mask = np.array([contig_lengths.get(names[i], 0) >= min_contig_len for i in indices])
        filtered_indices = [idx for idx, m in zip(indices, mask) if m]
        n_filtered = len(indices) - len(filtered_indices)
    else:
        filtered_indices = indices
        n_filtered = 0

    if len(filtered_indices) < min_cluster_size:
        print(f"  {sample_name}: {len(filtered_indices)} contigs (필터 후) — 클러스터링 불가, 스킵")
        return {}, n_filtered

    emb = embeddings[filtered_indices]

    # Z-score 정규화
    scaler = StandardScaler()
    emb_norm = scaler.fit_transform(emb)

    # UMAP
    n_neighbors = min(umap_neighbors, len(filtered_indices) - 1)
    if n_neighbors < 2:
        print(f"  {sample_name}: contigs 너무 적음 ({len(filtered_indices)}), 스킵")
        return {}, n_filtered

    n_comp = min(umap_components, len(filtered_indices) - 1)
    reducer = umap.UMAP(
        n_neighbors=n_neighbors,
        n_components=n_comp,
        min_dist=0.0,
        metric="euclidean",
        random_state=42,
    )
    emb_umap = reducer.fit_transform(emb_norm)

    # HDBSCAN
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="euclidean",
        cluster_selection_method="leaf",
        core_dist_n_jobs=-1,
    )
    labels = clusterer.fit_predict(emb_umap)

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_assigned = (labels != -1).sum()
    n_total = len(labels)
    noise_pct = (labels == -1).sum() / n_total * 100

    print(f"  {sample_name}: {n_total} contigs → {n_clusters} clusters, "
          f"{n_assigned} assigned ({100 - noise_pct:.1f}%), "
          f"{n_filtered} filtered (<{min_contig_len}bp)")

    # 결과 매핑
    assignments = {}
    for idx, label in zip(filtered_indices, labels):
        if label != -1:
            assignments[names[idx]] = f"{sample_name}_evo2_bin.{label}"

    return assignments, n_filtered


def main():
    parser = argparse.ArgumentParser(description="Phase 3b v2: 샘플별 UMAP + HDBSCAN")
    parser.add_argument("--embeddings", default=os.path.expanduser("~/results/contig_embeddings.npz"))
    parser.add_argument("--names", default=os.path.expanduser("~/results/contig_names.txt"))
    parser.add_argument("--data_dir", default=os.path.expanduser("~/results"),
                        help="baseline_sample*/results/*_assembly.fasta 위치")
    parser.add_argument("--output_dir", default=os.path.expanduser("~/results"))
    parser.add_argument("--min_cluster_size", type=int, default=3)
    parser.add_argument("--min_samples", type=int, default=1)
    parser.add_argument("--umap_neighbors", type=int, default=15)
    parser.add_argument("--umap_components", type=int, default=50)
    parser.add_argument("--min_contig_len", type=int, default=1000, help="최소 contig 길이 (bp)")
    args = parser.parse_args()

    # 임베딩 로드
    print("임베딩 로드 중...")
    data = np.load(args.embeddings)
    embeddings = data["embeddings"]
    with open(args.names) as f:
        names = [line.strip() for line in f]
    print(f"  {len(names)} contigs, {embeddings.shape[1]}d")
    assert len(names) == embeddings.shape[0]

    # 샘플별 contig 인덱스 분류
    sample_indices = defaultdict(list)
    for i, name in enumerate(names):
        parts = name.split("_contig_")
        if len(parts) == 2:
            sample_name = parts[0]  # e.g., "baseline_sample0"
        else:
            sample_name = "unknown"
        sample_indices[sample_name].append(i)

    print(f"\n{len(sample_indices)}개 샘플 발견:")
    for s in sorted(sample_indices.keys()):
        print(f"  {s}: {len(sample_indices[s])} contigs")

    # Assembly에서 contig 길이 로드 (1kb 필터용)
    print("\nContig 길이 로드 중...")
    contig_lengths = {}
    for sample_name in sorted(sample_indices.keys()):
        contigs_db = load_sample_contigs(args.data_dir, sample_name)
        for cid, rec in contigs_db.items():
            contig_lengths[cid] = len(rec.seq)
    print(f"  {len(contig_lengths)} contigs 길이 로드됨")

    # 샘플별 클러스터링
    print(f"\n=== 샘플별 클러스터링 시작 ===")
    print(f"  HDBSCAN: min_cluster_size={args.min_cluster_size}, min_samples={args.min_samples}, leaf")
    print(f"  UMAP: n_neighbors={args.umap_neighbors}, n_components={args.umap_components}, min_dist=0.0")
    print(f"  최소 contig 길이: {args.min_contig_len}bp\n")

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
            min_cluster_size=args.min_cluster_size,
            min_samples=args.min_samples,
            umap_neighbors=args.umap_neighbors,
            umap_components=args.umap_components,
            min_contig_len=args.min_contig_len,
            contig_lengths=contig_lengths,
        )
        all_assignments.update(assignments)
        total_filtered += n_filtered

    # 결과 요약
    total_contigs = len(names)
    total_assigned = len(all_assignments)
    total_bins = len(set(all_assignments.values()))
    print(f"\n=== v2 결과 요약 ===")
    print(f"  전체 contigs: {total_contigs}")
    print(f"  1kb 미만 필터링: {total_filtered}")
    print(f"  할당됨: {total_assigned}/{total_contigs} ({total_assigned/total_contigs*100:.1f}%)")
    print(f"  총 bins: {total_bins}")
    print(f"  (v1 대비: 6398/{total_contigs} = 15.1%, 403 bins)")

    # 1) evo2_c2b_v2.tsv 저장
    tsv_path = os.path.join(args.output_dir, "evo2_c2b_v2.tsv")
    with open(tsv_path, "w") as f:
        for name in names:
            if name in all_assignments:
                f.write(f"{name}\t{all_assignments[name]}\n")
    print(f"\n저장: {tsv_path}")

    # 2) 샘플별 bin FASTA 생성
    print("\nBin FASTA 생성 중...")
    bin_dir_root = os.path.join(args.output_dir, "evo2_bins_v2")
    os.makedirs(bin_dir_root, exist_ok=True)

    # bin별 contig 그룹핑
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

    print(f"  {total_bin_files} bin FASTA 파일 생성 → {bin_dir_root}/")
    print("\n완료!")


if __name__ == "__main__":
    main()
