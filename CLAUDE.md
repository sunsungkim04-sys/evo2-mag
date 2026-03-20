# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

mmlong2 (Nanopore long-read metagenome pipeline) + Evo 2 (DNA foundation model, 1M bp context) integration for MAG binning quality improvement, chimera detection, and functional annotation. Quantitative validation on CAMI2 benchmark (21 samples), targeting Bioinformatics/NAR publication.

## Server

- **PC101 (main)**: `ssh lab101` / `ssh minseo1101@155.230.164.215 -p 8375` — 72 cores, 755 GB RAM, no GPU
- Phase 3 GPU inference runs on **RunPod** (A100/H100 80GB)

## Key Paths (PC101)

```
~/cami2_data/simulation_nanosim/         # CAMI2 input data (21 samples)
~/cami2_data/source_genomes/             # AMBER ground truth
~/results/baseline_sample*/              # mmlong2 outputs
~/results/baseline_sampleN/results/bins/ # MAG FASTA files
~/results/baseline_sampleN/results/bins.tsv  # quality stats
~/miniforge3/envs/mmlong2/               # mmlong2 conda env
~/evo2-mag/                              # this repo
```

## Commands

```bash
# Always activate before running anything
conda activate mmlong2

# Single sample mmlong2 run
nohup mmlong2 -np ~/cami2_data/.../anonymous_reads.fq.gz \
    -o ~/results/baseline_sampleN -p 16 > ~/mmlong2_sampleN.log 2>&1 &

# Parallel execution (6 samples at a time, -p 6 each)
nohup bash ~/auto_run_mmlong2.sh > ~/auto_run_mmlong2.log 2>&1 &

# Check progress
tail -f ~/auto_run_mmlong2.log
ls ~/results/baseline_sample*/results/bins.tsv 2>/dev/null | wc -l

# GTDB-Tk taxonomy
gtdbtk classify_wf --genome_dir ~/bins/ --out_dir ~/gtdbtk_out/ --cpus 32

# Python package (editable install)
pip install -e .

# RunPod one-stop setup (runs embed + cluster + scp results back)
bash /workspace/evo2-mag/scripts/runpod_setup.sh
```

## Build & Install

- Build system: setuptools (see `pyproject.toml`)
- Python >=3.9, deps: numpy, pandas, hdbscan, biopython
- On RunPod: `pip install evo2 biopython hdbscan scikit-learn`
- CLI entrypoint defined as `evo2-mag = "evo2_mag.cli:main"` (not yet implemented)

## Code Architecture

**`src/evo2_mag/`** — Library modules (stub files, planned structure):
- `embed.py`, `bin.py`, `chimera.py`, `annotate.py` — empty; the library API is not yet implemented.

**`scripts/`** — Working RunPod pipeline scripts (this is where the real code lives):

1. **`run_embed.py`** — Evo 2 7B embedding extraction. Reads assembly FASTAs, mean-pools hidden states from layer `blocks.28.mlp.l3`, handles long contigs via non-overlapping chunking (max 512k bp). Outputs `contig_embeddings.npz` + `contig_names.txt`.
2. **`run_cluster.py`** — HDBSCAN clustering on z-score normalized embeddings → `evo2_c2b.tsv` (contig-to-bin mapping) + per-bin FASTA files in `evo2_bins/` (Binette input format).
3. **`run_perplexity.py`** — Sliding window (10 kb, 5 kb step) perplexity scoring for chimera detection. Windows >2σ above bin mean flagged as contamination candidates. Outputs `perplexity_windows.tsv` + `chimera_candidates.tsv`.
4. **`runpod_setup.sh`** — One-stop RunPod script: scp data from PC101 → install deps → run_embed → run_cluster → scp results back.

Pipeline order: mmlong2 baseline → `run_embed.py` (GPU) → `run_cluster.py` → Binette/DAS Tool merges MetaBAT2 + SemiBin2 + GraphMB + Evo2 bins. Chimera detection (`run_perplexity.py`) runs independently on bin FASTAs.

## mmlong2 Config Modifications (CAMI2 only)

CAMI2 data uses old NanoSim (error rate ~10-15%), requiring these overrides:

| File | Setting | Default | CAMI2 |
|------|---------|---------|-------|
| `mmlong2-lite-config.yaml` | `minimap_np` | `lr:hq` | `map-ont` |
| same file | `np_map_ident` | `95` | `80` |
| `mmlong2-lite.smk` line 224 | Flye preset | `--nano-hq` | `--nano-raw` |
| same file line 891 | MetaBat2 | `metabat2 ...` | `metabat2 ... \|\| touch {output}` |

Revert after CAMI2 experiments.

## A/B Comparison Design

| Task | Baseline A | Enhanced B | Metrics |
|------|-----------|-----------|---------|
| Binning | MetaBAT2+SemiBin2+GraphMB | +Evo2 embedding (4th binner) | HQ/MQ MAG count, ARI |
| Chimera detection | CheckM2 | CheckM2+Evo2 perplexity | contamination rate |
| Functional annotation | Prokka/eggNOG | +Evo2 likelihood | hypothetical→functional ratio |

## Current Status (2026-03-20 09:50 KST 기준)

### Phase 2 — mmlong2 Baseline ✅ 완료
- 21개 샘플 전부 완료 (3/18 14:13)
- 131 MAGs: HQ 52, MQ 79
- 출력 파일명: `baseline_sampleN_bins.tsv` (not `bins.tsv`)
- 결과 경로: `~/results/baseline_sampleN/results/` (assembly, bins, bins.tsv 등)

### Phase 3a — Evo 2 임베딩 🔄 진행 중 (RunPod)

**RunPod 접속**: `ssh root@64.247.201.49 -p 13118 -i ~/.ssh/id_ed25519` (H100 80GB, $1.7/hr)

**현재 실행 중**: `run_embed.py --max_len 8192` (PID 3130)
- 3/19 05:23 시작, 15/21 샘플 완료 (3/20 09:50 기준)
- 샘플당 ~64~98분 (contig 수에 비례), contig당 ~2.2초
- **남은 6개 샘플 → 약 6-8시간 후 완료 예상**
- 누적 비용: ~$66 (예상 총 ~$82)
- **마지막에 한꺼번에 저장**하는 구조 — 크래시 시 전체 유실 위험
- 진행 확인: `tail -f /workspace/embed.log` 또는 `grep -c 'Done in' /workspace/embed.log`

**after_embed.sh 자동 실행 중** (PID 26281):
- 임베딩 PID 종료 감시 → 클러스터링 → PC101 백업 자동 수행
- perplexity는 **제외** (별도 최적화 후 실행 예정)
- 로그: `tail -f /workspace/after_embed.log`

**RunPod → PC101 SSH 설정 완료**: RunPod에서 `ssh -p 8375 minseo1101@155.230.164.215` 가능 (ed25519 키 등록됨)

### Phase 3b — Perplexity 키메라 탐지 ⏳ 최적화 필요

**문제**: 현재 `run_perplexity.py`는 10kb window / 5kb step → ~162,000 forward passes → **~90시간, ~$153**
**해결 방향**:
- window 50kb / step 25kb로 확대 → ~18시간, ~$31
- 배치 처리 추가 시 → ~5-8시간, ~$10-14
- 키메라 경계는 보통 수십kb 단위라 50kb window로 충분
- **임베딩+클러스터링 완료 후 RunPod 일단 종료 → 스크립트 최적화 → 다시 실행**

### Phase 3 자동 파이프라인 (임베딩 완료 후 자동 실행)
1. ✅ HDBSCAN 클러스터링 (`run_cluster.py`) → `evo2_c2b.tsv` + `evo2_bins/`
2. ✅ 결과 PC101 백업 (scp, 실패해도 RunPod에 파일 남음)
3. ❌ perplexity → 별도 최적화 후 실행

### Phase 3 RunPod 경로
```
/workspace/data/baseline_sample*/results/*_assembly.fasta  # 입력 (21개 샘플)
/workspace/results/contig_embeddings.npz                   # 임베딩 출력 (완료 후 생성)
/workspace/results/contig_names.txt                        # contig 이름 목록
/workspace/results/evo2_c2b.tsv                            # 클러스터링 결과 (완료 후)
/workspace/results/evo2_bins/                              # bin별 FASTA (Binette 입력용)
/workspace/embed.log                                       # 임베딩 진행 로그
/workspace/after_embed.log                                 # 자동 파이프라인 로그
/workspace/scripts/run_embed.py                            # 현재 실행 중인 버전
/workspace/scripts/run_embed_v2.py                         # 중간저장 버전 (재시작용)
/workspace/scripts/run_cluster.py                          # HDBSCAN 클러스터링
/workspace/scripts/run_perplexity.py                       # perplexity (최적화 필요)
/workspace/scripts/after_embed.sh                          # 임베딩 후 자동 파이프라인 (perplexity 제외)
```

### Phase 4 — AMBER 평가 ⏳ 대기
- 임베딩+클러스터링 끝난 후 PC101에서 실행 (perplexity 완료 안 기다려도 됨)

## GitHub

- Repo: https://github.com/sunsungkim04-sys/evo2-mag
- Git config: user.email=sunsungkim04@gmail.com, user.name=sunsungkim04-sys
