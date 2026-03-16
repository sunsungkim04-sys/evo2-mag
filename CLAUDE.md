# Evo2 × mmlong2 프로젝트 — Claude Code 컨텍스트

## 프로젝트 한 줄 요약
mmlong2(Nanopore long-read 메타게놈 파이프라인)에 Evo 2(DNA foundation model, 1M bp context)를 결합하여 MAG 비닝 품질 개선, 키메라 탐지, 기능 주석을 통합 수행. CAMI2 벤치마크로 정량 검증 후 Bioinformatics/NAR 투고 목표.

## 서버 정보

| 서버 | 접속 | 용도 |
|------|------|------|
| **PC101 (메인)** | `ssh lab101` / `ssh minseo1101@155.230.164.215 -p 8375` | **전체 파이프라인** (72코어, 755GB RAM) |
| PC102 (미사용) | `ssh minseo1201@155.230.165.50 -p 5716` | 더 이상 사용 안 함 |

SSH 단축: `ssh lab101` (Mac ~/.ssh/config 등록됨)

## 현재 상태 (2026-03-17 기준)

- **Phase 1** ✅ CAMI2 데이터 21개 샘플 — PC101로 rsync 전송 중 🔄
- **Phase 2** 🔄 PC101에서 처음부터 재실행
  - mmlong2 conda 환경 설치 완료 ✅
  - mmlong2 DB 설치 중 🔄 (~37%, PID 3522391, `~/mmlong2_db_install.log`)
  - CAMI2 데이터 rsync 중 🔄 (PC102 → PC101, PID 3757420, `~/cami2_rsync.log`)
  - CAMI2 데이터 rsync 전송 중 🔄 (PC102 → PC101)
  - Claude Code 설치 완료 ✅ (conda nodejs + npm)
  - DB + 데이터 완료 후 → config 수정 → 병렬 실행 예정
- **Phase 3** ⏳ Evo 2 추론 — RunPod A100 필요 (GPU 없음)
- **Phase 4** ⏳ AMBER 평가

## 주요 경로 (PC101 서버)

```
~/cami2_data/simulation_nanosim/    # CAMI2 입력 데이터
~/cami2_data/source_genomes/        # AMBER ground truth
~/results/baseline_sample*/         # mmlong2 출력
~/results/baseline_sampleN/results/bins/      # MAG 파일들
~/results/baseline_sampleN/results/bins.tsv   # 품질 통계
~/evo2-mag/                         # GitHub 코드 저장소
~/miniforge3/envs/mmlong2/          # mmlong2 conda 환경
~/mmlong2_db_install.log            # DB 설치 로그
~/cami2_rsync.log                   # 데이터 전송 로그
```

## 중요: mmlong2 config 수정 사항 (CAMI2 전용) — DB 완료 후 적용

CAMI2 데이터가 구형 NanoSim(에러율 ~10-15%)이라 기본값 수정 필요:

| 파일 | 항목 | 원래값 | CAMI2용 |
|------|------|--------|---------|
| `~/miniforge3/envs/mmlong2/bin/mmlong2-lite-config.yaml` | `minimap_np` | `lr:hq` | `map-ont` |
| 위 파일 | `np_map_ident` | `95` | `80` |
| `~/miniforge3/envs/mmlong2/bin/mmlong2-lite.smk` 224행 | Flye preset | `--nano-hq` | `--nano-raw` |
| 위 파일 891행 | MetaBat2 | `metabat2 ...` | `metabat2 ... \|\| touch {output}` |

⚠️ CAMI2 실험 완료 후 원래 값으로 복원할 것!

## 주요 명령어

```bash
# 서버 접속 후 항상
conda activate mmlong2

# mmlong2 실행 (단일 샘플)
nohup mmlong2 -np ~/cami2_data/.../anonymous_reads.fq.gz \
    -o ~/results/baseline_sampleN -p 16 > ~/mmlong2_sampleN.log 2>&1 &

# 병렬 실행
nohup bash ~/run_mmlong2_parallel.sh > ~/mmlong2_parallel.log 2>&1 &

# 진행 확인
tail -f ~/mmlong2_parallel.log
ls ~/results/baseline_sample*/results/bins.tsv 2>/dev/null | wc -l

# GTDB-Tk (PC101에서)
ssh lab101
gtdbtk classify_wf --genome_dir ~/bins/ --out_dir ~/gtdbtk_out/ --cpus 32
```

## 코드 저장소 구조 (~/evo2-mag)

```
src/evo2_mag/
├── embed.py      # Evo 2 임베딩 추출 (contig → vector)
├── bin.py        # HDBSCAN 클러스터링 → evo2_c2b.tsv
├── chimera.py    # perplexity 기반 키메라 탐지
└── annotate.py   # 기능 주석 likelihood
scripts/
└── run_mmlong2_parallel.sh  # 병렬 실행 스크립트
```

## Phase 3 핵심 로직 요약

1. **임베딩 추출** (`embed.py`): 각 contig → Evo2('7b').embed() → 평균 벡터 → contig_embeddings.npz
2. **비닝** (`bin.py`): HDBSCAN(min_cluster_size=5) → evo2_c2b.tsv → DAS Tool 4번째 binner
3. **키메라** (`chimera.py`): 슬라이딩 윈도우(10kb, 5kb step) perplexity → 2σ 이상 구간 = 오염 의심
4. **DAS Tool 재실행**: MetaBAT2 + SemiBin2 + GraphMB + Evo2 = 4개 합의

## A/B 비교 설계

| 태스크 | Baseline A | Enhanced B | 지표 |
|--------|-----------|-----------|------|
| 비닝 | MetaBAT2+SemiBin2+GraphMB | +Evo2 임베딩 (4번째) | HQ/MQ MAG 수, ARI |
| 키메라 탐지 | CheckM2 | CheckM2+Evo2 perplexity | 오염률 |
| 기능 주석 | Prokka/eggNOG | +Evo2 likelihood | hypothetical → 기능 비율 |

## Phase 3 실행 환경 (RunPod)

- 7B 모델: A100 80GB × 1, ~$1.5/hr
- 40B 모델: A100 80GB × 4, ~$6/hr
- 전략: 7B 먼저 개념 증명 → 40B는 핵심 실험만

## GitHub

- URL: https://github.com/sunsungkim04-sys/evo2-mag
- git config: user.email=sunsungkim04@gmail.com, user.name=sunsungkim04-sys

## 관련 옵시디언 노트 (~/evo2-mag/notes/)

- `서버-세팅-진행log.md` — 실험 진행 로그 (현재 상태 확인)
- `Step1-CAMI2-벤치마크-실행가이드.md` — Phase 1~4 상세 가이드
- `Evo2-mmlong2-MAG-enhancement.md` — 프로젝트 전체 설계 (논문 구조, 경쟁 논문 분석)
