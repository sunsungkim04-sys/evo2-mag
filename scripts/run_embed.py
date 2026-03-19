#!/usr/bin/env python3
"""Evo 2 7B embedding extraction for all CAMI2 baseline samples.

Usage (on RunPod):
    python /workspace/evo2-mag/scripts/run_embed.py \
        --data_dir /workspace/data \
        --output_dir /workspace/results \
        --layer blocks.28.mlp.l3
"""
import argparse
import glob
import os
import time

import numpy as np
import torch
from Bio import SeqIO


def extract_embeddings(model, fasta_path, layer, max_len=524288, batch_log_interval=100):
    """Extract mean-pooled Evo 2 embeddings from a FASTA file.

    For contigs longer than max_len, use non-overlapping chunks and
    average the chunk embeddings (length-weighted).
    """
    records = list(SeqIO.parse(fasta_path, "fasta"))
    sample_name = os.path.basename(fasta_path).replace("_assembly.fasta", "")
    print(f"  {sample_name}: {len(records)} contigs")

    contig_names = []
    embeddings = []

    for idx, rec in enumerate(records):
        seq = str(rec.seq).upper()
        # Skip contigs with too many ambiguous bases
        n_frac = seq.count("N") / len(seq) if len(seq) > 0 else 1.0
        if n_frac > 0.5:
            continue

        # Replace N with A (Evo 2 expects ACGT only)
        seq = seq.replace("N", "A")

        contig_names.append(rec.id)

        if len(seq) <= max_len:
            emb = _embed_single(model, seq, layer)
        else:
            # Chunk long contigs
            emb = _embed_chunked(model, seq, layer, max_len)

        embeddings.append(emb)

        if (idx + 1) % batch_log_interval == 0:
            print(f"    {idx + 1}/{len(records)} contigs processed")

        # Free GPU memory
        torch.cuda.empty_cache()

    print(f"    {len(embeddings)}/{len(records)} contigs embedded (skipped {len(records) - len(embeddings)} high-N)")
    return contig_names, np.vstack(embeddings)


def _embed_single(model, seq, layer):
    """Embed a single sequence."""
    with torch.no_grad():
        input_ids = torch.tensor(
            model.tokenizer.tokenize(seq), dtype=torch.int
        ).unsqueeze(0).to("cuda:0")

        _, emb_dict = model(input_ids, return_embeddings=True, layer_names=[layer])
        token_emb = emb_dict[layer]  # [1, seq_len, hidden_dim]
        mean_emb = torch.mean(token_emb, dim=1)  # [1, hidden_dim]

    return mean_emb.cpu().numpy()


def _embed_chunked(model, seq, layer, max_len):
    """Embed a long sequence by chunking and length-weighted averaging."""
    chunks = [seq[i : i + max_len] for i in range(0, len(seq), max_len)]
    chunk_embs = []
    chunk_lens = []

    for chunk in chunks:
        emb = _embed_single(model, chunk, layer)
        chunk_embs.append(emb[0])  # [hidden_dim]
        chunk_lens.append(len(chunk))

    # Length-weighted average
    weights = np.array(chunk_lens, dtype=np.float32)
    weights /= weights.sum()
    weighted_emb = np.average(chunk_embs, axis=0, weights=weights)
    return weighted_emb.reshape(1, -1)


def main():
    parser = argparse.ArgumentParser(description="Evo 2 embedding extraction")
    parser.add_argument("--data_dir", default="/workspace/data",
                        help="Directory with baseline_sample*/results/*_assembly.fasta")
    parser.add_argument("--output_dir", default="/workspace/results",
                        help="Output directory for embeddings")
    parser.add_argument("--model", default="evo2_7b", help="Evo 2 model name")
    parser.add_argument("--layer", default="blocks.28.mlp.l3",
                        help="Layer to extract embeddings from")
    parser.add_argument("--max_len", type=int, default=524288,
                        help="Max sequence length per chunk (default 512k)")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # Load model
    print(f"Loading Evo 2 model: {args.model}")
    t0 = time.time()
    model = Evo2(args.model)
    print(f"Model loaded in {time.time() - t0:.0f}s")

    # Find all assembly files
    pattern = os.path.join(args.data_dir, "baseline_sample*/results/*_assembly.fasta")
    fasta_files = sorted(glob.glob(pattern))
    print(f"Found {len(fasta_files)} assembly files")

    if not fasta_files:
        print(f"ERROR: No files found matching {pattern}")
        return

    # Process each sample
    all_names = []
    all_embeddings = []

    for i, fasta in enumerate(fasta_files):
        print(f"\n[{i + 1}/{len(fasta_files)}] Processing {os.path.basename(fasta)}")
        t1 = time.time()
        names, embs = extract_embeddings(model, fasta, args.layer, args.max_len)
        elapsed = time.time() - t1
        print(f"  Done in {elapsed:.0f}s ({len(names)} contigs, {embs.shape[1]}d)")

        all_names.extend(names)
        all_embeddings.append(embs)

    # Save
    all_embeddings = np.vstack(all_embeddings)
    out_npz = os.path.join(args.output_dir, "contig_embeddings.npz")
    out_names = os.path.join(args.output_dir, "contig_names.txt")

    np.savez_compressed(out_npz, embeddings=all_embeddings)
    with open(out_names, "w") as f:
        f.write("\n".join(all_names))

    print(f"\nAll done! {len(all_names)} contigs, shape={all_embeddings.shape}")
    print(f"Saved: {out_npz} ({os.path.getsize(out_npz) / 1e6:.1f} MB)")
    print(f"Saved: {out_names}")


if __name__ == "__main__":
    from evo2 import Evo2
    main()
