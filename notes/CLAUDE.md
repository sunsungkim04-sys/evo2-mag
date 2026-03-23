# Evo2 × mmlong2 프로젝트 — Claude Code 컨텍스트

## 프로젝트 한 줄 요약
mmlong2(Nanopore long-read 메타게놈 파이프라인)에 Evo 2(DNA foundation model, 1M bp context)를 결합하여 MAG 비닝 품질 개선, 키메라 탐지, 기능 주석을 통합 수행. CAMI2 벤치마크로 정량 검증 후 Bioinformatics/NAR 투고 목표.

## 서버 정보

| 서버 | 접속 | 용도 |
|------|------|------|
| **PC101 (메인)** | `ssh lab101` / `ssh minseo1101@155.230.164.215 -p 8375` | **전체 파이프라인** (72코어, 755GB RAM) |
| **RunPod** | RunPod 콘솔 | GPU 추론 (A100/H100 80GB) |

SSH 단축: `ssh lab101` (Mac ~/.ssh/config 등록됨)

## 현재 상태 (2026-03-23 기준)

### 완료된 Phase
- **Phase 1** ✅ CAMI2 21개 샘플 데이터 PC101 전송 완료
- **Phase 2** ✅ mmlong2 Baseline 완료 — HQ 52, MQ 79, Total 131 MAGs
- **Phase 3a** ✅ Evo2 임베딩 완료 — 42,320 contigs × 4096d (`contig_embeddings.npz`)
- **Phase 3b** ✅ 클러스터링 v1~v4_1 전 버전 완료 (→ `Phase3b-v2-클러스터링-개선.md`)
- **Phase 3c** ✅ Perplexity 키메라 탐지 정량 검증 완료 (→ `Phase3c-키메라-탐지-결과.md`)
- **Phase 3d** ✅ Binette 앙상블 전 버전 완료
- **Phase 4** ✅ CheckM2 + AMBER 전 버전 평가 완료
- **Phase 5** ✅ Bakta 기능 주석 완료 (Functional ratio 50.8%)

### 진행 중 / 다음 단계
- **Phase 3c-v2** 🔄 키메라 탐지 개선 — **스크립트 작성 완료, PC101 실행 대기**
  - 현재 문제: any-flag 방식 Precision 24.4% (131개 bin 전부 flagged)
  - 2개 방향 **병렬 실행** (입력 파일이 달라서 독립적):
  - **방향 1: Junction 탐지** (`scripts/chimera_junction.py`)
    - 입력: `perplexity_windows.tsv` (195,266 windows)
    - 방법: 인접 window 간 |perplexity delta| (1차 미분) 최댓값으로 step-change 탐지
    - 진짜 키메라 = genome A→B 경계에서 급격한 불연속. 단순히 "높다"가 아님
    - every-other window 비중첩화 → bin별 max/mean/p90_junction → threshold sweep
  - **방향 2: Bin 간 embedding 거리** (`scripts/chimera_embedding_dist.py`)
    - 입력: `contig_embeddings.npz` (42320×4096d) + baseline bin FASTAs (131 bins)
    - 방법: 각 bin의 centroid 계산 → contig별 cosine distance 비교
    - outlier_score = d_own / d_nearest_other (>1.0 = 다른 bin에 더 가까움)
    - Method A/B/C + threshold sweep
  - [ ] 방향 3: 청크 간 일관성 → RunPod 재실행 필요 (~$46), 보류
  - **실행 명령**: `nohup python ~/evo2-mag/scripts/chimera_junction.py > ~/chimera_junction.log 2>&1 &` / `nohup python ~/evo2-mag/scripts/chimera_embedding_dist.py > ~/chimera_embedding.log 2>&1 &`
  - 목표: Precision >0.5, F1 >0.55
- **Phase 3d (DNABERT-S)** ⏳ 보류 중

## 현재 결과 요약 (베스트 버전)

### 비닝 (클러스터링)
| | Baseline | **v4_1 (추천)** | v4 (MAG 최대화) |
|--|--|--|--|
| HQ | **52** | 47 | 41 |
| MQ | 79 | 85 | **99** |
| Total | 131 | 163 | **179** |
| F1 | 0.2327 | **0.2634** | 0.2696 |
| ARI | **0.7639** | 0.7334 | 0.6896 |

> ⚠️ 비닝에서 Evo2 추가 시 HQ가 Baseline보다 낮아짐. 메인 contribution 삼기 어려움.
> 방법론적으로 올바른 버전(샘플별 클러스터링) = v2, v3, v4, v2_1, v4_1.
> v1/v1-1은 글로벌 클러스터링이라 방법론적으로 부적합 (논문에서 ablation으로만 사용).

### 키메라 탐지 (현재)
| | CheckM2 단독 | Evo2 perplexity (any flag) |
|--|--|--|
| Precision | 0.3333 | 0.2443 |
| Recall | 0.0625 | **1.0000** |
| F1 | 0.1053 | **0.3926** |

> ⚠️ Recall 100%이지만 131개 bin 전부 flagged → 사실상 무차별 판정.
> Precision 개선이 핵심 과제 → `Phase3c-v2-키메라-탐지-개선계획.md` 참고.

## 주요 파일 경로 (PC101)

```
~/results/contig_embeddings.npz              # Evo2 임베딩 (546MB, 42320×4096d)
~/results/contig_names.txt                   # contig 이름
~/results/evo2_c2b_v4_1.tsv                 # 최종 클러스터링 (v4_1)
~/results/evo2_bins_v4_1/                    # bin FASTAs
~/results/perplexity_windows.tsv             # perplexity 전체 (195,266 windows)
~/results/chimera_candidates.tsv             # flagged windows (10,407개)
~/results/chimera_validation_detail.tsv      # gold standard 비교 상세
~/results/amber_eval_v4_1/                   # AMBER 평가 결과
~/results/checkm2_enhanced_v4_1/             # CheckM2 결과
~/results/bakta_enhanced/                    # Bakta 기능 주석
~/cami2_data/source_genomes/                 # AMBER ground truth
```

## 스크립트 (~/evo2-mag/scripts/)

| 스크립트 | 용도 | 실행 환경 |
|---------|------|----------|
| `run_embed.py` | Evo2 7B 임베딩 추출 | RunPod GPU |
| `run_cluster_v2.py` | 샘플별 UMAP+HDBSCAN | PC101 CPU |
| `run_cluster_v2_cov.py` | v4: 임베딩+커버리지 결합 | PC101 CPU |
| `run_perplexity.py` | Sliding window perplexity | RunPod GPU |
| `validate_chimera.py` | Gold standard 정량 검증 | PC101 CPU |
| `chimera_junction.py` | Junction 탐지 (perplexity delta) | PC101 CPU |
| `chimera_embedding_dist.py` | Embedding 거리 기반 outlier 탐지 | PC101 CPU |
| `run_binette_enhanced_v2.sh` | Binette 앙상블 실행 | PC101 |
| `run_checkm2_enhanced_v2.sh` | CheckM2 평가 | PC101 |
| `run_amber_v2.sh` | AMBER 3-way 비교 | PC101 |

## 주요 명령어

```bash
# 항상 먼저
conda activate mmlong2

# Binette (Singularity)
PATH=/opt/conda/envs/env_8/bin singularity exec ...

# CheckM2 진행 확인
tail -f ~/binette_v2.log

# AMBER 결과 확인
cat ~/results/amber_eval_v4_1/amber_output/results.tsv
```

## mmlong2 Config 수정 사항 (CAMI2 전용)

| 파일 | 항목 | 원래값 | CAMI2용 |
|------|------|--------|---------|
| `mmlong2-lite-config.yaml` | `minimap_np` | `lr:hq` | `map-ont` |
| 위 파일 | `np_map_ident` | `95` | `80` |
| `mmlong2-lite.smk` 224행 | Flye preset | `--nano-hq` | `--nano-raw` |
| 위 파일 891행 | MetaBat2 | `metabat2 ...` | `metabat2 ... \|\| touch {output}` |

## GitHub

- URL: https://github.com/sunsungkim04-sys/evo2-mag
- git config: user.email=sunsungkim04@gmail.com, user.name=sunsungkim04-sys

## 관련 노트

| 노트 | 내용 |
|------|------|
| `Phase3b-v2-클러스터링-개선.md` | 클러스터링 v1~v4_1 전 결과 및 해석 |
| `Phase3c-키메라-탐지-결과.md` | 현재 키메라 탐지 결과 (Recall 100%, Precision 24.4%) |
| `Phase3c-v2-키메라-탐지-개선계획.md` | **키메라 탐지 개선 3가지 방향 (다음 실험)** |
| `Phase4-CheckM2-AMBER-결과.md` | 전 버전 CheckM2/AMBER 결과 비교 |
| `Step1-CAMI2-벤치마크-실행가이드.md` | Phase 1~4 상세 실행 가이드 |
| `서버-세팅-진행log.md` | 서버 세팅 및 실험 진행 로그 |
