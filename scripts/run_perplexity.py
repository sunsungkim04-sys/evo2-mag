#!/usr/bin/env python3
"""Evo 2 sliding window perplexity for chimera detection.

For each bin FASTA, compute per-window perplexity using Evo 2 7B.
Windows with perplexity >2σ above the bin mean are flagged as potential
contamination (chimeric regions).

Usage (on RunPod, after run_embed.py):
    python3 -u /workspace/scripts/run_perplexity.py \
        --data_dir /workspace/data \
        --output_dir /workspace/results

Default: 8kb window / 4kb step, batch_size=1 (OOM-safe on H100 80GB)
50kb/25kb was tried but caused CUDA OOM → 8kb로 축소.
"""
import argparse
import glob
import os
import time

import numpy as np
import torch
from Bio import SeqIO


def compute_perplexity_windows(model, sequence, window_size=8000, step_size=4000, batch_size=1):
    """Compute per-window perplexity using Evo 2 log-likelihoods.

    Args:
        model: Evo2 model instance
        sequence: DNA string (ACGT only)
        window_size: sliding window size in bp (default 8kb, matches embed max_len)
        step_size: step size in bp (default 4kb)

    Returns:
        windows: list of (start, end, perplexity) tuples
    """
    sequence = sequence.upper().replace("N", "A")
    windows = []

    if len(sequence) < window_size:
        ppl = _single_perplexity(model, sequence)
        if ppl is not None:
            windows.append((0, len(sequence), ppl))
        return windows

    # Collect all window subsequences
    spans = []
    for start in range(0, len(sequence) - window_size + 1, step_size):
        end = start + window_size
        spans.append((start, end, sequence[start:end]))

    # Batch forward passes
    ppls = _batch_perplexity(model, [s[2] for s in spans], batch_size=batch_size)
    for (start, end, _), ppl in zip(spans, ppls):
        if ppl is not None:
            windows.append((start, end, ppl))

    return windows


def _batch_perplexity(model, seqs, batch_size=4):
    """Compute perplexity for multiple sequences in batches."""
    results = []
    loss_fn = torch.nn.CrossEntropyLoss()

    for i in range(0, len(seqs), batch_size):
        batch = seqs[i:i + batch_size]
        batch_ppls = []
        with torch.no_grad():
            for seq in batch:
                try:
                    input_ids = torch.tensor(
                        model.tokenizer.tokenize(seq), dtype=torch.long
                    ).unsqueeze(0).to("cuda:0")

                    (logits, _), _ = model(input_ids, return_embeddings=False, layer_names=[])

                    shift_logits = logits[:, :-1, :].contiguous()
                    shift_labels = input_ids[:, 1:].contiguous()

                    loss = loss_fn(
                        shift_logits.view(-1, shift_logits.size(-1)),
                        shift_labels.view(-1),
                    )
                    batch_ppls.append(torch.exp(loss).item())
                    del input_ids, logits, shift_logits, shift_labels, loss
                except Exception as e:
                    print(f"    Warning: perplexity computation failed: {e}")
                    batch_ppls.append(None)

        torch.cuda.empty_cache()
        results.extend(batch_ppls)

    return results


def _single_perplexity(model, seq):
    """Compute perplexity for a single sequence (delegates to _batch_perplexity)."""
    results = _batch_perplexity(model, [seq], batch_size=1)
    return results[0] if results else None


def main():
    parser = argparse.ArgumentParser(description="Evo 2 perplexity chimera detection")
    parser.add_argument("--data_dir", default="/workspace/data",
                        help="Directory with baseline_sample*/results/bins/*.fa")
    parser.add_argument("--output_dir", default="/workspace/results")
    parser.add_argument("--model", default="evo2_7b")
    parser.add_argument("--window_size", type=int, default=8000, help="Window size in bp")
    parser.add_argument("--step_size", type=int, default=4000, help="Step size in bp")
    parser.add_argument("--batch_size", type=int, default=1, help="Batch size for forward passes")
    parser.add_argument("--sigma", type=float, default=2.0, help="Sigma threshold for flagging")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # Load model
    print(f"Loading Evo 2 model: {args.model}")
    t0 = time.time()
    from evo2 import Evo2
    model = Evo2(args.model)
    print(f"Model loaded in {time.time() - t0:.0f}s")

    # Find all bin FASTA files
    pattern = os.path.join(args.data_dir, "baseline_sample*/results/bins/*.fa")
    bin_files = sorted(glob.glob(pattern))
    print(f"Found {len(bin_files)} bin files")

    # Output files
    out_windows = os.path.join(args.output_dir, "perplexity_windows.tsv")
    out_chimeras = os.path.join(args.output_dir, "chimera_candidates.tsv")

    # Resume support: check which bins are already done
    done_bins = set()
    if os.path.exists(out_windows):
        with open(out_windows) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("bin\t"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 5:  # valid line has 5 columns
                    done_bins.add(parts[0])
        print(f"Resuming: {len(done_bins)} bins already processed, skipping")
        append_mode = True
    else:
        append_mode = False

    total_flagged = 0
    total_windows = 0
    t_start = time.time()

    mode = "a" if append_mode else "w"
    with open(out_windows, mode) as fw, open(out_chimeras, mode) as fc:
        if not append_mode:
            fw.write("bin\tcontig\tstart\tend\tperplexity\n")
            fc.write("bin\tcontig\tstart\tend\tperplexity\tmean_ppl\tthreshold\n")

        for i, bin_file in enumerate(bin_files):
            bin_name = os.path.splitext(os.path.basename(bin_file))[0]

            if bin_name in done_bins:
                print(f"[{i+1}/{len(bin_files)}] {bin_name}: skipped (already done)")
                continue

            records = list(SeqIO.parse(bin_file, "fasta"))
            t_bin = time.time()
            print(f"\n[{i+1}/{len(bin_files)}] {bin_name}: {len(records)} contigs")

            bin_all_windows = []

            for rec in records:
                seq = str(rec.seq)
                windows = compute_perplexity_windows(
                    model, seq, args.window_size, args.step_size, args.batch_size
                )
                for start, end, ppl in windows:
                    fw.write(f"{bin_name}\t{rec.id}\t{start}\t{end}\t{ppl:.4f}\n")
                    bin_all_windows.append((rec.id, start, end, ppl))

            # Flush after each bin for crash safety
            fw.flush()

            # Detect chimeras within this bin
            if bin_all_windows:
                ppls = [p for _, _, _, p in bin_all_windows]
                mean_ppl = np.mean(ppls)
                std_ppl = np.std(ppls)
                threshold = mean_ppl + args.sigma * std_ppl
                bin_flagged = 0

                for contig_id, start, end, ppl in bin_all_windows:
                    if len(ppls) >= 3 and ppl > threshold:
                        fc.write(f"{bin_name}\t{contig_id}\t{start}\t{end}\t{ppl:.4f}\t{mean_ppl:.4f}\t{threshold:.4f}\n")
                        total_flagged += 1
                        bin_flagged += 1

                fc.flush()
                total_windows += len(bin_all_windows)
                elapsed = time.time() - t_bin
                total_elapsed = time.time() - t_start
                print(f"  {len(bin_all_windows)} windows, {bin_flagged} flagged "
                      f"(threshold={threshold:.2f}) [{elapsed:.0f}s, total {total_elapsed/3600:.1f}h]")

    print(f"\nDone! {total_windows} total windows, {total_flagged} chimera candidates")
    print(f"Saved: {out_windows}")
    print(f"Saved: {out_chimeras}")


if __name__ == "__main__":
    torch.serialization.add_safe_globals([__import__("codecs").encode])
    main()
