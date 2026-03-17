# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

mmlong2 (Nanopore long-read metagenome pipeline) + Evo 2 (DNA foundation model, 1M bp context) integration for MAG binning quality improvement, chimera detection, and functional annotation. Quantitative validation on CAMI2 benchmark, targeting Bioinformatics/NAR publication.

## Server

- **PC101 (main)**: `ssh lab101` / `ssh minseo1101@155.230.164.215 -p 8375` — 72 cores, 755 GB RAM, no GPU
- Phase 3 GPU inference runs on **RunPod** (A100 80GB)

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
```

## Build & Install

- Build system: setuptools (see `pyproject.toml`)
- Python >=3.9, deps: numpy, pandas, hdbscan, biopython
- CLI entrypoint defined as `evo2-mag = "evo2_mag.cli:main"` (not yet implemented)

## Code Architecture

All source lives in `src/evo2_mag/`. The four modules map to the pipeline's Phase 3 steps:

1. **`embed.py`** — Evo 2 embedding extraction: contig → `Evo2('7b').embed()` → mean-pooled vector → `contig_embeddings.npz`
2. **`bin.py`** — HDBSCAN clustering on embeddings → `evo2_c2b.tsv` (contig-to-bin mapping), fed to DAS Tool as 4th binner
3. **`chimera.py`** — Sliding window (10 kb, 5 kb step) perplexity scoring; regions >2σ above mean = contamination candidates
4. **`annotate.py`** — Evo 2 likelihood-based functional annotation for hypothetical proteins

These modules are invoked after mmlong2 baseline completes. DAS Tool then merges MetaBAT2 + SemiBin2 + GraphMB + Evo2 bins.

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

## GitHub

- Repo: https://github.com/sunsungkim04-sys/evo2-mag
- Git config: user.email=sunsungkim04@gmail.com, user.name=sunsungkim04-sys
