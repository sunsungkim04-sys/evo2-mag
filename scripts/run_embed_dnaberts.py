#!/usr/bin/env python3
"""DNABERT-S embedding extraction for all CAMI2 baseline samples.

Evo2 head-to-head 비교용. 동일 assembly FASTA → 동일 contig_names.txt 순서,
임베딩만 DNABERT-S (768d)로 교체.

PC101 CPU에서 실행 (DNABERT-S ~117M 파라미터, GPU 불필요).

Usage:
    python ~/evo2-mag/scripts/run_embed_dnaberts.py
    python ~/evo2-mag/scripts/run_embed_dnaberts.py \
        --data-dir ~/results \
        --output-dir ~/results/dnaberts \
        --max-tokens 500
"""

import argparse
import glob
import os
import time

import numpy as np
import torch
from Bio import SeqIO
from transformers import AutoTokenizer, AutoModel


def load_model(model_name: str) -> tuple:
    """DNABERT-S 모델 + 토크나이저 로딩."""
    print(f"  Loading tokenizer: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    print(f"  Loading model: {model_name}")
    model = AutoModel.from_pretrained(model_name, trust_remote_code=True)
    model.eval()

    # CPU 모드 (PC101에 GPU 없음)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    print(f"  Device: {device}")
    return model, tokenizer, device


def _embed_single(model, tokenizer, seq: str, device, max_tokens: int) -> np.ndarray:
    """단일 시퀀스 임베딩 (mean-pool of last hidden states).

    DNABERT-S 토크나이저의 max_length에 맞춰 truncation.
    """
    inputs = tokenizer(
        seq,
        return_tensors="pt",
        padding=False,
        truncation=True,
        max_length=max_tokens,
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)

    # last_hidden_state: [1, seq_len, 768]
    hidden = outputs.last_hidden_state
    # attention_mask으로 패딩 토큰 제외한 mean-pool
    mask = inputs["attention_mask"].unsqueeze(-1).float()  # [1, seq_len, 1]
    mean_emb = (hidden * mask).sum(dim=1) / mask.sum(dim=1)  # [1, 768]

    return mean_emb.cpu().numpy()


def _embed_chunked(model, tokenizer, seq: str, device, max_tokens: int, max_bp_per_chunk: int) -> np.ndarray:
    """긴 시퀀스를 청크로 나눠 length-weighted average."""
    chunks = [seq[i:i + max_bp_per_chunk] for i in range(0, len(seq), max_bp_per_chunk)]
    chunk_embs = []
    chunk_lens = []

    for chunk in chunks:
        emb = _embed_single(model, tokenizer, chunk, device, max_tokens)
        chunk_embs.append(emb[0])  # [768]
        chunk_lens.append(len(chunk))

    weights = np.array(chunk_lens, dtype=np.float32)
    weights /= weights.sum()
    weighted_emb = np.average(chunk_embs, axis=0, weights=weights)
    return weighted_emb.reshape(1, -1)


def extract_embeddings(
    model, tokenizer, device,
    fasta_path: str,
    max_tokens: int = 500,
    max_bp_per_chunk: int = 2000,
    batch_log_interval: int = 100,
) -> tuple:
    """FASTA 파일에서 DNABERT-S 임베딩 추출.

    Args:
        max_tokens: 토크나이저 max_length (DNABERT-S는 ~512 토큰 제한)
        max_bp_per_chunk: 청크당 최대 bp 수.
            DNABERT-S BPE 토크나이저는 ~2-4bp/token 압축률이므로
            max_tokens=500 → 약 1000~2000bp. 보수적으로 2000bp.

    Returns:
        (contig_names, embeddings_matrix)
    """
    records = list(SeqIO.parse(fasta_path, "fasta"))
    sample_name = os.path.basename(fasta_path).replace("_assembly.fasta", "")
    print(f"  {sample_name}: {len(records)} contigs")

    contig_names = []
    embeddings = []

    for idx, rec in enumerate(records):
        seq = str(rec.seq).upper()

        # Evo2와 동일: 50% 이상 N인 contig 스킵
        n_frac = seq.count("N") / len(seq) if len(seq) > 0 else 1.0
        if n_frac > 0.5:
            continue

        # N을 A로 치환 (Evo2와 동일 전처리)
        seq = seq.replace("N", "A")

        contig_names.append(rec.id)

        if len(seq) <= max_bp_per_chunk:
            emb = _embed_single(model, tokenizer, seq, device, max_tokens)
        else:
            emb = _embed_chunked(model, tokenizer, seq, device, max_tokens, max_bp_per_chunk)

        embeddings.append(emb)

        if (idx + 1) % batch_log_interval == 0:
            print(f"    {idx + 1}/{len(records)} contigs processed")

    print(f"    {len(embeddings)}/{len(records)} contigs embedded "
          f"(skipped {len(records) - len(embeddings)} high-N)")
    return contig_names, np.vstack(embeddings)


def main():
    parser = argparse.ArgumentParser(description="DNABERT-S embedding extraction")
    parser.add_argument(
        "--data-dir", default=os.path.expanduser("~/results"),
        help="Directory with baseline_sample*/results/*_assembly.fasta"
    )
    parser.add_argument(
        "--output-dir", default=os.path.expanduser("~/results/dnaberts"),
        help="Output directory"
    )
    parser.add_argument(
        "--model-name", default="zhihan1996/DNABERT-S",
        help="HuggingFace model name"
    )
    parser.add_argument(
        "--max-tokens", type=int, default=500,
        help="Max tokens per input (DNABERT-S limit ~512)"
    )
    parser.add_argument(
        "--max-bp-per-chunk", type=int, default=2000,
        help="Max bp per chunk for long contigs (default: 2000)"
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    print("=" * 60)
    print("DNABERT-S Embedding Extraction")
    print("=" * 60)
    print(f"Data dir      : {args.data_dir}")
    print(f"Output dir    : {args.output_dir}")
    print(f"Model         : {args.model_name}")
    print(f"Max tokens    : {args.max_tokens}")
    print(f"Max bp/chunk  : {args.max_bp_per_chunk}")
    print()

    # [1] Load model
    print("[1] Loading DNABERT-S model...")
    t0 = time.time()
    model, tokenizer, device = load_model(args.model_name)
    print(f"  Model loaded in {time.time() - t0:.0f}s")
    print()

    # [2] Find assembly files
    pattern = os.path.join(args.data_dir, "baseline_sample*/results/*_assembly.fasta")
    fasta_files = sorted(glob.glob(pattern))
    print(f"[2] Found {len(fasta_files)} assembly files")

    if not fasta_files:
        print(f"ERROR: No files found matching {pattern}")
        return
    print()

    # [3] Process each sample
    all_names = []
    all_embeddings = []

    for i, fasta in enumerate(fasta_files):
        print(f"[{i + 1}/{len(fasta_files)}] Processing {os.path.basename(fasta)}")
        t1 = time.time()
        names, embs = extract_embeddings(
            model, tokenizer, device, fasta,
            args.max_tokens, args.max_bp_per_chunk,
        )
        elapsed = time.time() - t1
        print(f"  Done in {elapsed:.0f}s ({len(names)} contigs, {embs.shape[1]}d)")
        print()

        all_names.extend(names)
        all_embeddings.append(embs)

    # [4] Save
    all_embeddings = np.vstack(all_embeddings)
    out_npz = os.path.join(args.output_dir, "contig_embeddings.npz")
    out_names = os.path.join(args.output_dir, "contig_names.txt")

    np.savez_compressed(out_npz, embeddings=all_embeddings)
    with open(out_names, "w") as f:
        f.write("\n".join(all_names))

    print(f"All done! {len(all_names)} contigs, shape={all_embeddings.shape}")
    print(f"Saved: {out_npz} ({os.path.getsize(out_npz) / 1e6:.1f} MB)")
    print(f"Saved: {out_names}")


if __name__ == "__main__":
    main()
