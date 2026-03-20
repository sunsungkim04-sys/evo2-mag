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

## Current Status (2026-03-20 20:00 KST 기준)

### Phase 2 — mmlong2 Baseline ✅ 완료
- 21개 샘플 전부 완료 (3/18 14:13)
- 131 MAGs: HQ 52, MQ 79
- 출력 파일명: `baseline_sampleN_bins.tsv` (not `bins.tsv`)
- 결과 경로: `~/results/baseline_sampleN/results/` (assembly, bins, bins.tsv 등)

### Phase 3a — Evo 2 임베딩 ✅ 완료 (RunPod)
- 42,320 contigs 임베딩 완료 (3/20 08:03 UTC)
- `contig_embeddings.npz` (546MB, 42320×4096d)
- RunPod H100 SXM 80GB, 총 ~27시간, 비용 ~$46

### Phase 3b — HDBSCAN 클러스터링 ✅ 완료
- PCA 4096d → 50d (explained variance: 99.9%) + HDBSCAN
- 403 clusters, 6398/42320 contigs assigned (84.9% noise — 앙상블에서 걸러짐)
- `evo2_c2b.tsv` + `evo2_bins/` (샘플별 bin FASTA)

### Phase 3c — Perplexity 키메라 탐지 ✅ 완료
- 131 bins, 5351 windows 분석, **237개 키메라 후보** flagged
- window 8kb / step 4kb, batch_size 1 (OOM 방지)
- `perplexity_windows.tsv` + `chimera_candidates.tsv`
- 실행 중 발견된 이슈: 50kb window → CUDA OOM → 8kb로 축소, model output unpacking 버그 수정

### Phase 3 결과 (PC101 백업 완료)
```
~/results/contig_embeddings.npz     # 임베딩 (546MB)
~/results/contig_names.txt          # contig 이름 목록
~/results/evo2_c2b.tsv              # 클러스터링 결과
~/results/evo2_bins/                # bin별 FASTA (Binette 입력용)
~/results/perplexity_windows.tsv    # perplexity 전체
~/results/chimera_candidates.tsv    # 키메라 후보 (237개)
```

### Phase 3d — Binette Enhanced 앙상블 ✅ 20/21 완료, sample_10 🔄 진행 중
- 기존 3종(VAMB+MetaBAT2+SemiBin2) + **Evo2 bins** = 4종 앙상블
- Singularity 컨테이너 내 Binette 1.1.2 + CheckM2 사용 (PATH=/opt/conda/envs/env_8/bin)
- Evo2 bins 필터링 적용 (contigs.fasta에 없는 split contig 제거)
- **20개 샘플 완료: 총 163 Enhanced bins** (Baseline 131 → +32)
- sample_10: 원래 np_map_ident=95에서 binning 실패 → 수동으로 np_map_ident=80 재실행 중
  - minimap2 mapping ✅ → coverage + MetaBAT2 + VAMB + SemiBin2 🔄 진행 중
  - 완료 후 Binette enhanced 실행 예정

### 실행 중 발견된 이슈 & 해결
1. BioPython 미설치 → `pip install biopython` (PC101)
2. CheckM2 PATH 문제 → singularity exec 시 `PATH=/opt/conda/envs/env_8/bin` 설정
3. Evo2 bins 필터링 0개 → BioPython 없어서 조용히 실패 → 설치 후 해결
4. sample_10 binning 실패 → np_map_ident=95 (config sed 패턴 불일치로 80 적용 안 됨) → 수동 재실행

### Phase 4 — AMBER 평가 ⏳ 대기
- sample_10 완료 후 전체 21개 샘플로 Baseline A vs Enhanced B 정량 비교

## GitHub

- Repo: https://github.com/sunsungkim04-sys/evo2-mag
- Git config: user.email=sunsungkim04@gmail.com, user.name=sunsungkim04-sys
