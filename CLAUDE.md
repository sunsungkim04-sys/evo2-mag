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

## A/B/C Comparison Design

| Task | Baseline A (mmlong2) | +Evo 2 (B) | +DNABERT-S (C) | Metrics |
|------|---------------------|------------|----------------|---------|
| Binning (ensemble) | MetaBAT2+SemiBin2+GraphMB → Binette | +Evo2 embedding (5th binner) → Binette | +DNABERT-S embedding (5th binner) → Binette | HQ/MQ MAG count, ARI |
| Embedding-only binning | — | Evo2 → HDBSCAN | DNABERT-S → HDBSCAN | ARI, precision, recall |
| Chimera detection | CheckM2 | CheckM2+Evo2 perplexity | — | contamination rate |
| Functional annotation | Prokka/eggNOG | +Evo2 likelihood | — | hypothetical→functional ratio |

### Phase 3d — DNABERT-S 직접 비교 (Evo 2 결과 확인 후 실행)
- **목적**: 같은 CAMI2 데이터, 같은 파이프라인(HDBSCAN → Binette → AMBER)에서 임베딩만 교체하여 head-to-head 비교
- **서버**: PC101 (CPU only) — DNABERT-S는 ~117M 파라미터(BERT 크기)라 GPU 불필요
- **순서**: DNABERT-S 임베딩 추출 (CPU, ~수시간~하루) → 동일 HDBSCAN → `dnaberts_c2b.tsv` → Binette 5-binner → AMBER
- **참고**: DNABERT-S 공식 CAMI2 ARI ~54 — 우리 재현 결과와 교차 검증

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

### Phase 3b — HDBSCAN 클러스터링

**v1** (글로벌 PCA+HDBSCAN) ✅ 완료:
- PCA 4096d → 50d + HDBSCAN (min_cluster_size=5, min_samples=3, eom)
- 403 clusters, 6398/42320 assigned (15.1%) — 84.9% noise
- `evo2_c2b.tsv` + `evo2_bins/`

**v2** (샘플별 UMAP+HDBSCAN) ✅ 완료 (3/21):
- 샘플별 클러스터링 + UMAP 50d + HDBSCAN (min_cluster_size=3, min_samples=1, leaf)
- 6439 bins, 31030/42320 assigned (**73.3%**) — noise 대폭 감소
- `evo2_c2b_v2.tsv` + `evo2_bins_v2/`

**v3** (v2 + 확률 필터링 prob≥0.5) ✅ 완료 (3/21):
- v2와 동일 클러스터링 + low-confidence 할당 제거 (1706개)
- 6439 bins, 29324/42320 assigned (69.3%)
- `evo2_c2b_v3.tsv` + `evo2_bins_v3/`

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

### Phase 3d — Binette Enhanced 앙상블
- 기존 3종(VAMB+MetaBAT2+SemiBin2) + **Evo2 bins** = 4종 앙상블
- Singularity 컨테이너 내 Binette 1.1.2 + CheckM2 (PATH=/opt/conda/envs/env_8/bin)
- Evo2 bins 필터링 적용 (contigs.fasta에 없는 split contig 제거)

| 버전 | Evo2 bins 소스 | 결과 (total bins) |
|------|---------------|------------------|
| v1 | `evo2_bins/` (글로벌) | 169 bins (21 samples) |
| v2 | `evo2_bins_v2/` (샘플별 UMAP) | 168 bins |
| v3 | `evo2_bins_v3/` (v2+prob≥0.5) | 164 bins |

### 실행 중 발견된 이슈 & 해결
1. BioPython 미설치 → `pip install biopython` (PC101)
2. CheckM2 PATH 문제 → singularity exec 시 `PATH=/opt/conda/envs/env_8/bin` 설정
3. Evo2 bins 필터링 0개 → BioPython 없어서 조용히 실패 → 설치 후 해결
4. sample_10 binning 실패 → np_map_ident=95 (config sed 패턴 불일치로 80 적용 안 됨) → 수동 재실행

### Phase 4 — CheckM2 + AMBER 평가 ✅ 완료

**CheckM2 결과 비교**:
| | Baseline | Enhanced v1 | Enhanced v2 | Enhanced v3 |
|---|---|---|---|---|
| Total bins | 131 | 169 | 165 | 164 |
| HQ (≥90% comp, <5% cont) | 52 | 45 | 45 | 45 |
| MQ (≥50% comp, <10% cont) | 79 | 88 | **94** | 90 |
| LQ | 0 | 36 | 26 | 29 |

**AMBER 결과** (21 samples 평균, ground truth 비교):
| Metric | Baseline | v1 | v2 | v3 |
|--------|----------|-----|------|------|
| Precision (bp) | 0.8062 | 0.7923 | 0.7762 | 0.7868 |
| Recall (bp) | 0.5702 | 0.5795 | 0.5746 | 0.5689 |
| F1 (bp) | 0.2327 | **0.2658** | 0.2636 | 0.2570 |
| ARI (bp) | **0.7639** | 0.7495 | 0.7189 | 0.7371 |
| Assigned (bp) | 0.5822 | **0.5922** | 0.5892 | 0.5828 |

**분석**:
- v1: F1, Recall, Assigned 최고 — 전반적으로 가장 균형 잡힌 결과
- v2: MQ 최대 (94) — 더 많은 MAG 발견, 하지만 ARI 하락
- v3: v2 대비 Precision/ARI 회복, MQ 감소 — 확률 필터링 효과 있으나 trade-off
- Gold standard: reads_mapping.tsv (read→genome) + BAM (read→contig) → majority vote
- 결과 경로: `~/results/amber_eval/`, `~/results/amber_eval_v2/`, `~/results/amber_eval_v3/`

## GitHub

- Repo: https://github.com/sunsungkim04-sys/evo2-mag
- Git config: user.email=sunsungkim04@gmail.com, user.name=sunsungkim04-sys
