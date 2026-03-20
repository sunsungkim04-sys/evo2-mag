#!/usr/bin/env python3
"""HDBSCAN clustering on Evo 2 embeddings → evo2_c2b.tsv + bin FASTA files.

Outputs:
  - evo2_c2b.tsv: contig-to-bin mapping (contig_name\tbin_name)
  - evo2_bins/: directory of per-bin FASTA files (for Binette input)

Usage (on RunPod, after run_embed.py):
    python /workspace/evo2-mag/scripts/run_cluster.py \
        --embeddings /workspace/results/contig_embeddings.npz \
        --names /workspace/results/contig_names.txt \
        --data_dir /workspace/data \
        --output_dir /workspace/results
"""
import argparse
import glob
import os
from collections import defaultdict

import hdbscan
import numpy as np
from Bio import SeqIO
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler


def load_all_contigs(data_dir):
    """Load all contigs from assembly FASTA files into a dict {contig_id: SeqRecord}."""
    pattern = os.path.join(data_dir, "baseline_sample*/results/*_assembly.fasta")
    fasta_files = sorted(glob.glob(pattern))
    contigs = {}
    for f in fasta_files:
        for rec in SeqIO.parse(f, "fasta"):
            contigs[rec.id] = rec
    print(f"  Loaded {len(contigs)} contigs from {len(fasta_files)} assemblies")
    return contigs


def main():
    parser = argparse.ArgumentParser(description="HDBSCAN clustering on Evo 2 embeddings")
    parser.add_argument("--embeddings", default="/workspace/results/contig_embeddings.npz")
    parser.add_argument("--names", default="/workspace/results/contig_names.txt")
    parser.add_argument("--data_dir", default="/workspace/data",
                        help="Directory with baseline_sample*/results/*_assembly.fasta")
    parser.add_argument("--output_dir", default="/workspace/results")
    parser.add_argument("--min_cluster_size", type=int, default=5)
    parser.add_argument("--min_samples", type=int, default=3)
    parser.add_argument("--pca_dim", type=int, default=50, help="PCA dimensions (0=skip)")
    args = parser.parse_args()

    # Load embeddings
    print("Loading embeddings...")
    data = np.load(args.embeddings)
    embeddings = data["embeddings"]
    with open(args.names) as f:
        names = [line.strip() for line in f]

    print(f"  {len(names)} contigs, {embeddings.shape[1]}d embeddings")
    assert len(names) == embeddings.shape[0]

    # Normalize (z-score) — recommended for Evo 2 embeddings
    print("Normalizing embeddings (z-score)...")
    scaler = StandardScaler()
    embeddings_norm = scaler.fit_transform(embeddings)

    # PCA dimensionality reduction
    if args.pca_dim > 0:
        print(f"PCA: {embeddings_norm.shape[1]}d → {args.pca_dim}d ...")
        pca = PCA(n_components=args.pca_dim)
        embeddings_norm = pca.fit_transform(embeddings_norm)
        explained = pca.explained_variance_ratio_.sum() * 100
        print(f"  Explained variance: {explained:.1f}%")

    # HDBSCAN
    print(f"Running HDBSCAN (min_cluster_size={args.min_cluster_size}, min_samples={args.min_samples})...")
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=args.min_cluster_size,
        min_samples=args.min_samples,
        metric="euclidean",
        cluster_selection_method="eom",
        core_dist_n_jobs=-1,
    )
    labels = clusterer.fit_predict(embeddings_norm)

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = (labels == -1).sum()
    print(f"  {n_clusters} clusters found, {n_noise} noise points ({n_noise / len(labels) * 100:.1f}%)")

    # 1) Write contig-to-bin TSV
    tsv_path = os.path.join(args.output_dir, "evo2_c2b.tsv")
    os.makedirs(args.output_dir, exist_ok=True)
    with open(tsv_path, "w") as f:
        for name, label in zip(names, labels):
            if label == -1:
                continue
            f.write(f"{name}\tevo2_bin.{label}\n")

    assigned = (labels != -1).sum()
    print(f"  {assigned}/{len(labels)} contigs assigned to bins")
    print(f"Saved: {tsv_path}")

    # 2) Write per-bin FASTA files (Binette input format)
    print("\nGenerating bin FASTA files for Binette...")
    contigs_db = load_all_contigs(args.data_dir)

    # Group contigs by sample and bin
    # contig names follow pattern: baseline_sampleN_contig_XXX
    sample_bins = defaultdict(lambda: defaultdict(list))
    for name, label in zip(names, labels):
        if label == -1:
            continue
        # Extract sample name from contig name
        parts = name.split("_contig_")
        if len(parts) == 2:
            sample_name = parts[0]  # e.g., "baseline_sample0"
        else:
            sample_name = "unknown"
        bin_name = f"evo2_bin.{label}"
        sample_bins[sample_name][bin_name].append(name)

    # Write per-sample bin directories
    total_bins = 0
    for sample_name, bins in sorted(sample_bins.items()):
        bin_dir = os.path.join(args.output_dir, "evo2_bins", sample_name)
        os.makedirs(bin_dir, exist_ok=True)
        for bin_name, contig_names in bins.items():
            bin_fasta = os.path.join(bin_dir, f"{bin_name}.fa")
            records = [contigs_db[n] for n in contig_names if n in contigs_db]
            if records:
                SeqIO.write(records, bin_fasta, "fasta")
                total_bins += 1

    print(f"  {total_bins} bin FASTA files written across {len(sample_bins)} samples")
    print(f"  Output: {os.path.join(args.output_dir, 'evo2_bins/')}")


if __name__ == "__main__":
    main()
