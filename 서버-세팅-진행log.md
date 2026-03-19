---
tags:
  - experiment
  - Evo2
  - 서버세팅
  - CAMI2
created: 2026-03-14
updated: 2026-03-19
status: in-progress
related-project: "[[03_Projects/Evo2-mmlong2-MAG-enhancement]]"
---

# 연구실 서버 세팅 & CAMI2 진행 로그

> [!info] 목적
> CAMI2 벤치마크 실행을 위한 연구실 서버 환경 세팅 및 데이터 다운로드 기록

---

## 현재 상태 (2026-03-19 13:00 기준)

> [!success] Phase 2 Baseline A — mmlong2 전체 완료 ✅
> **21개 샘플 전부 mmlong2 파이프라인 (lite + proc) 완료**
>
> ### 결과 요약 (131 MAGs)
> | 지표 | 값 |
> |------|-----|
> | 총 MAG 수 | **131개** |
> | HQ (comp ≥90%, cont <5%) | **52개 (39.7%)** |
> | MQ (comp ≥50%, cont <10%) | **79개 (60.3%)** |
> | LQ | **0개** |
> | 평균 completeness (CheckM2) | **83.7%** |
> | 평균 contamination (CheckM2) | **1.52%** |
> | 평균 genome size | **6.2 Mbp** |
> | 평균 N50 | **1,100 kbp** |
> | 평균 coverage | **22.9x** |
> | GUNC pass | **126/131 (96.2%)** |
>
> ### 샘플별 MAG 수
> | 샘플 | bins | HQ | MQ | 샘플 | bins | HQ | MQ |
> |------|------|-----|-----|------|------|-----|-----|
> | 0 | 4 | 2 | 2 | 11 | 6 | 3 | 3 |
> | 1 | 5 | 3 | 2 | 12 | 6 | 1 | 5 |
> | 2 | 5 | 3 | 2 | 13 | 5 | 4 | 1 |
> | 3 | 6 | 2 | 3 | 14 | 4 | 0 | 3 |
> | 4 | 8 | 4 | 3 | 15 | 8 | 4 | 4 |
> | 5 | 5 | 4 | 1 | 16 | 10 | 3 | 6 |
> | 6 | 4 | 1 | 3 | 17 | 8 | 2 | 6 |
> | 7 | 5 | 2 | 1 | 18 | 8 | 4 | 4 |
> | 8 | 5 | 3 | 2 | 19 | 8 | 3 | 5 |
> | 9 | 7 | 3 | 3 | 20 | 9 | 5 | 4 |
> | 10 | 5 | 4 | 1 | | | | |
>
> ### 실행 중 발생한 이슈 & 해결
> 1. **AMRFinderPlus DB 버전 불일치** → `amrfinder_update --force_update` 실행 후 해결
> 2. **sample 17 입력 파일 손상** (gzip truncated) → `frl.publisso.de`에서 재다운로드 후 처음부터 실행
> 3. **sample 10 BAM 파일 손상** → 수동으로 minimap2+samtools로 BAM 재생성 후 proc 완료

> [!note] 다음 단계
> 1. Phase 3: RunPod 계정 세팅 → H100/A100 80GB 사용 예정 (7B PoC 먼저, 예산 ~$100)
> 2. Phase 2 결과 (assembly + bins) → RunPod 전송
> 3. Evo 2 7B 임베딩 추출 시작

---

## 이전 상태 (2026-03-17 17:00 기준)

> [!warning] 메인 서버 변경: PC102 → PC101 (영구)
> PC101 (755GB RAM, 72코어)으로 전면 이전. PC102는 더 이상 사용 안 함.

> [!success] PC101 세팅 완료 + mmlong2 실행 중 🔄
> - Miniforge 기설치 확인
> - `conda create -n mmlong2` 설치 완료 ✅
> - `mmlong2 --install_databases` ✅ **전체 완료** (2026-03-17 15:00)
>   - 16S rRNA DB ✅
>   - GUNC DB ✅
>   - Metabuli DB ✅
>   - Bakta DB ✅
>   - GTDB-Tk r226 ✅
> - CAMI2 데이터 전송 ✅ 완료 (21/21 샘플 PC101 도착)
> - mmlong2 config 수정 ✅ (CAMI2용: `map-ont`, identity 80%)
> - **21개 샘플 병렬 실행 중 🔄** (PID 3607034, `~/run_mmlong2_step3.log`)
>   - 6개 동시 × 12코어 (`-p 12`), 72코어 풀 활용
>   - Singularity 컨테이너 다운로드 중 (9.1GB, 1회만 필요)
>   - 컨테이너 완료 후 실제 파이프라인 시작 예정
>   - GTDB-Tk도 파이프라인 내 자동 실행 (755GB RAM으로 pplacer 문제 없음)
>   - **전체 완료 예상: 2026-03-18 오후~저녁**
> - `git config` (sunsungkim04@gmail.com / sunsungkim04-sys) 완료
> - `evo2-mag` repo clone → `~/evo2-mag` ✅
> - GitHub PAT 신규 발급 + remote URL 갱신 (만료: 2026-06-12)
> - Mac `~/.ssh/config`에 `lab101` 단축키 등록 완료
> - Claude Code 설치 완료 ✅ (conda nodejs + npm)

> [!tip] 노트 동기화 (Mac에서)
> ```bash
> rsync -avz "/Users/minseokim/Documents/Obsidian Vault/01_Research/Evo2/" lab101:~/evo2-mag/notes/
> ```

---

## 현재 상태 (2026-03-15 20:00 기준)

> [!success] sample_0 완료 ✅ → 나머지 20개 병렬 실행 중 🔄 + GTDB-Tk PC101 세팅 예정
> **sample_0 결과**: HQ 3개 + MQ 2개 (총 5 bins)
> **나머지 20개**: 4개 동시 병렬 실행 중 (예상 ~2일)
> **GTDB-Tk**: PC102 RAM 부족 → **PC101 (755GB)** 에서 실행 예정
> - PC101: `minseo1101@155.230.164.215:8375` ✅
> - DB는 PC102에서 rsync 전송 (옵션 A)

> [!warning] mmlong2 config 수정 사항 (CAMI2 전용)
> CAMI2 NanoSim 데이터는 2020년 구형 나노포어 시뮬레이션 (에러율 ~10-15%)이라
> mmlong2 기본값 (최신 Q20+ 나노포어용)으로는 coverage 매핑이 안 됨.
> **수정 파일 1**: `~/miniforge3/envs/mmlong2/bin/mmlong2-lite-config.yaml`
> | 항목 | 원래 값 | 변경 값 | 이유 |
> |------|---------|---------|------|
> | `minimap_np` | `lr:hq` | `map-ont` | 구형 nanopore read용 preset |
> | `np_map_ident` | `95` | `80` | 에러율 높은 read의 coverage 포함 |
>
> **수정 파일 2**: `~/miniforge3/envs/mmlong2/bin/mmlong2-lite.smk`
> | 위치 | 원래 값 | 변경 값 | 이유 |
> |------|---------|---------|------|
> | 224행 Flye preset | `--nano-hq` | `--nano-raw` | 구형 nanopore 에러율에 맞는 조립 |
> | 891행 MetaBat2 | `metabat2 ...` | `metabat2 ... \|\| touch {output}` | bin 0개 시 파이프라인 중단 방지 |
>
> ⚠️ **CAMI2 실험 완료 후 반드시 원래 값으로 복원할 것!**

---

## 서버 정보

### PC102 (구 메인 — 현재 미사용)

| 항목 | 내용 |
|------|------|
| IP | 155.230.165.50 |
| Port | 5716 |
| ID | minseo1201 |
| OS | Ubuntu 20.04 |
| 호스트명 | pc102-X399-AORUS-XTREME |
| CPU | AMD Threadripper 2990WX 32코어 (64스레드) |
| RAM | 128GB (DDR4) |
| 스토리지 | 6T(boot) + 14T×2 |
| GPU | 없음 |
| 용도 | ~~메인~~ → PC101로 이전 |

### PC101 (메인 — 전체 파이프라인)

| 항목 | 내용 |
|------|------|
| IP | 155.230.164.215 |
| Port | 8375 |
| ID | minseo1101 |
| CPU | Intel Xeon E5-2695 v4 ×2 (72코어) |
| RAM | **755GB** |
| 스토리지 | 2T(boot) + 28T |
| GPU | 없음 |
| 용도 | **메인 — mmlong2 + GTDB-Tk 전체** |

### SSH 접속
```bash
# PC101 (메인)
ssh minseo1101@155.230.164.215 -p 8375

# PC102 (구 서버, 미사용)
ssh minseo1201@155.230.165.50 -p 5716
```

> [!tip] SSH config 등록 (Mac ~/.ssh/config)
> ```
> Host lab101
>     HostName 155.230.164.215
>     User minseo1101
>     Port 8375
> ```
> 이후 `ssh lab101` 한 줄로 접속 가능

---

> [!warning] 서버 작업 주의사항
> **장시간 작업은 반드시 `nohup`으로 실행할 것**
> ```bash
> nohup [command] > ~/logname.log 2>&1 &
> ```
> - SSH 연결이 끊기거나 터미널을 닫으면 foreground 프로세스는 **즉시 종료**됨
> - `nohup` + `&`로 백그라운드 실행해야 터미널 종료와 무관하게 작업 유지
> - 로그 파일 경로(`~/logname.log`)를 반드시 이 노트에 기록해 둘 것
> - 진행 확인: `tail -f ~/logname.log`

---

## 설치된 환경

| 소프트웨어 | 버전 | 경로 |
|-----------|------|------|
| Miniforge | 최신 | `/media/hdd/14Tb_2/minseo1201/miniforge3` |
| mmlong2 | conda 환경 | `conda activate mmlong2` |
| Singularity | 3.8.6 | mmlong2 환경 내 포함 |

```bash
# 서버 접속 후 항상 이것부터
conda activate mmlong2
```

---

## Phase 1. CAMI2 데이터 ✅ 완료

### 데이터 위치
```
~/cami2_data/
├── simulation_nanosim/
│   ├── 2020.01.23_15.51.11_sample_0/reads/anonymous_reads.fq.gz  ← mmlong2 입력
│   ├── 2020.01.23_15.51.11_sample_1/reads/anonymous_reads.fq.gz
│   ├── ... (총 21개 샘플, sample_0 ~ sample_20)
├── source_genomes/               ← ground truth (AMBER 평가용)
└── rhimgCAMI2_*.tar.gz           ← 원본 압축파일 (보관용)
```

> [!info] 데이터 출처
> CAMI 공식 서버 접속 불가 → `frl.publisso.de` 대안 경로 사용
> `https://frl.publisso.de/data/frl:6425521/plant_associated/`

---

## Phase 2. Baseline A — mmlong2 실행 🔄 진행 중

### 목적
Evo 2 **없이** mmlong2만으로 돌린 결과 = 비교 기준(Baseline A)

### 현재 진행
- [x] sample_0 백그라운드 실행 시작 시도 (PID 2243007)
- [x] 에러 발견: results 경로 없음 + DB 미설치
- [x] `mmlong2 --install_databases` 완료 ✅
  - [x] 16S rRNA DB (Greengenes2) ✅
  - [x] GUNC DB ✅
  - [x] Metabuli DB (~450GB+) ✅
  - [x] Bakta DB (29.7GB) ✅
  - [x] GTDB-Tk r226 (132GB) ✅ — 2026-03-15 17:07 완료
- [x] DB 완료 후 sample_0 실행 → coverage 0 문제 발견 (identity 필터 95% + lr:hq preset)
- [x] config 수정: `map-ont` / identity 80% → sample_0 재실행 (PID 2435208, nohup) 🔄
- [x] sample_0 완료 확인
- [ ] sample_1~20 병렬 실행 스크립트 돌리기
- [ ] 전체 결과 확인 (bins.tsv, general.tsv)

### sample_0 실행 명령 (이미 실행됨)
```bash
conda activate mmlong2
nohup mmlong2 -np ~/cami2_data/simulation_nanosim/2020.01.23_15.51.11_sample_0/reads/anonymous_reads.fq.gz \
    -o ~/results/baseline_sample0 \
    -p 64 > ~/mmlong2_sample0.log 2>&1 &
```

### sample_0 결과 ✅

> [!success] sample_0 비닝 완료 — HQ 3개 + MQ 2개
> 경로: `~/results/baseline_sample0/results/bins/`

| Bin | Completeness | Contamination | 크기 | 등급 |
|-----|-------------|---------------|------|------|
| bin.1.4 | 92.68% | 1.67% | 5.6M | ⭐ HQ |
| bin.1.680 | 98.43% | 4.74% | 6.4M | ⭐ HQ |
| bin.1.16 | 94.38% | 4.99% | 7.8M | ⭐ HQ |
| bin.1.10 | 65.75% | 0.93% | 7.3M | MQ |
| bin.1.1245 | 53.68% | 1.69% | 6.5M | MQ |

> HQ = completeness ≥90%, contamination <5% / MQ = completeness ≥50%, contamination <10%
> ❌ GTDB-Tk: pplacer RAM 부족 (128GB < 필요 ~150GB+) → **PC101 (755GB)** 에서 별도 실행 예정

### sample_0 완료 후 → 나머지 20개 병렬 실행 (4개 동시)

> [!tip] 병렬 실행 전략
> 64코어 ÷ 4 = 샘플당 16코어. RAM 125GB → 4개 동시 가능 (~30GB/샘플).
> 순차 실행 7일 → **병렬 실행 약 2일**로 단축.

**스크립트 서버로 복사 (Mac에서):**
```bash
scp -P 5716 "/Users/minseokim/Documents/Obsidian Vault/01_Research/Evo2/scripts/run_mmlong2_parallel.sh" minseo1201@155.230.165.50:~/
```

**서버에서 실행:**
```bash
conda activate mmlong2
nohup bash ~/run_mmlong2_parallel.sh > ~/mmlong2_parallel.log 2>&1 &
```

**진행 확인:**
```bash
# 전체 로그
tail -f ~/mmlong2_parallel.log

# 개별 샘플 로그
tail ~/mmlong2_logs/sample_1.log

# 완료된 샘플 수 확인
ls ~/results/baseline_sample*/results/bins.tsv 2>/dev/null | wc -l

# 현재 실행 중인 mmlong2 프로세스 수
ps aux | grep mmlong2 | grep -v grep | wc -l
```

> [!warning] 주의
> - sample_0이 **완전히 끝난 뒤** 실행할 것 (Singularity 컨테이너 다운로드가 sample_0 실행 중에 완료됨)
> - 이미 완료된 샘플(`bins.tsv` 존재)은 자동 스킵
> - 중간에 중단돼도 다시 실행하면 완료된 것은 건너뜀

### mmlong2 출력 구조
```
~/results/baseline_sample0/
└── results/
    ├── bins/          ← ⭐ MAG 파일들 (.fa)
    ├── bakta/         ← 기능 주석
    ├── bins.tsv       ← completeness, contamination 등
    ├── contigs.tsv    ← contig별 정보
    └── general.tsv    ← 전체 통계
```

---

## Phase 3. Enhanced B — Evo 2 추가 🔄 실행 중

> [!warning] RunPod H100 SXM 실행 중 (2026-03-19 14:00~ KST)
> - SSH: `ssh root@64.247.201.49 -p 13118 -i ~/.ssh/id_ed25519`
> - 요금: $1.7/hr
> - Evo 2 7B 임베딩 추출 🔄 (~21시간, ~$36 예상)
> - 처리 속도: ~33 contigs/분, 총 42,320개
> - GPU 메모리: 19GB/80GB 사용 (여유 충분)

### 실행 환경
- **연구실 서버**: GPU 없음 → Evo 2 실행 불가
- **RunPod**: **H100 SXM 80GB** GPU 인스턴스
  - 7B 모델: 1× H100 SXM 80GB, ~$3.5/hr
  - 40B 모델: 4× H100 SXM 80GB, ~$14/hr
  - **전략: 7B 먼저 → 결과 확인 → 필요시 40B**

### 전송 데이터 (연구실 서버에서 준비 완료 ✅)
```
~/cami2_baseline_for_runpod.tar.gz   # 832MB (assembly 21개 + bins 21개)
~/cami2_contig_bin_all.tsv           # contig-to-bin 매핑 (4,615 contigs)
~/evo2-mag/scripts/run_embed.py      # 임베딩 추출 스크립트
~/evo2-mag/scripts/run_cluster.py    # HDBSCAN 클러스터링 스크립트
~/evo2-mag/scripts/runpod_setup.sh   # 원스톱 실행 스크립트
```

### 임베딩 대상 규모
- 총 contig 수: **42,320개**
- 평균 contig 길이: **50kbp** (최대 7Mbp)
- Evo 2 7B 모델 크기: ~14GB (bfloat16)
- 임베딩 레이어: `blocks.28.mlp.l3` (intermediate layer, 경험적으로 최적)

### RunPod 실행 순서 (H100 SXM에서)

> [!warning] 돈 절약 핵심
> 스크립트 미리 완성됨 → GPU 켜놓고 코딩 X → 켜자마자 바로 실행 → 끝나면 즉시 종료

**방법 1: 원스톱 스크립트 (권장)**
```bash
# RunPod 터미널에서
git clone https://github.com/sunsungkim04-sys/evo2-mag.git /workspace/evo2-mag
bash /workspace/evo2-mag/scripts/runpod_setup.sh
# → 데이터 수신 → 환경 설치 → 임베딩 추출 → 클러스터링 → 결과 회수 → 전부 자동
```

**방법 2: 단계별 수동 실행**
```bash
# 1) 데이터 수신
scp -P 8375 minseo1101@155.230.164.215:~/cami2_baseline_for_runpod.tar.gz /workspace/
scp -P 8375 minseo1101@155.230.164.215:~/cami2_contig_bin_all.tsv /workspace/results/
mkdir -p /workspace/data && cd /workspace/data && tar xzf /workspace/cami2_baseline_for_runpod.tar.gz

# 2) 환경 설치
pip install evo2 biopython hdbscan scikit-learn

# 3) 임베딩 추출 (~2-3시간, H100 SXM 기준)
python /workspace/evo2-mag/scripts/run_embed.py \
    --data_dir /workspace/data --output_dir /workspace/results

# 4) HDBSCAN 클러스터링 (~5분)
python /workspace/evo2-mag/scripts/run_cluster.py

# 5) 결과 회수
scp -P 8375 /workspace/results/contig_embeddings.npz minseo1101@155.230.164.215:~/results/
scp -P 8375 /workspace/results/evo2_c2b.tsv minseo1101@155.230.164.215:~/results/
```

### 예상 비용 (실측 기반 수정)
| 항목 | 시간 | 비용 ($1.7/hr) |
|------|------|---------|
| 데이터 전송 + 환경 세팅 | ~15분 | ~$0.4 |
| 임베딩 추출 (42k contigs, max_len=8k) | ~21시간 | ~$36 |
| HDBSCAN 클러스터링 | ~5분 | ~$0.1 |
| Perplexity 키메라 탐지 (131 bins) | ~2-3시간 | ~$4-5 |
| **합계** | **~24-25시간** | **~$41-42** |

### 실행 중 발생한 이슈 & 해결
1. `torch.load` weights_only 호환 → `torch.serialization.add_safe_globals` 추가
2. bfloat16 → float32 변환 → `.float().cpu().numpy()` 수정
3. 32bit index overflow (max_len=512k) → **max_len=8192**로 축소
4. stdout 버퍼링으로 로그 안 보임 → `python3 -u` (unbuffered) 모드 사용

### RunPod 작업 완료 후 — PC101에서 할 일
1. **Binette 재실행** — 기존 3종(VAMB+MetaBAT2+SemiBin2) + Evo2 `evo2_bins/` = 4종 앙상블
   - mmlong2는 DAS Tool이 아닌 **Binette**로 bin 앙상블 수행
   - `run_cluster.py`가 Binette 입력 형식(per-bin FASTA 디렉토리)으로 출력
2. **CheckM2** — Enhanced bins 품질 평가
3. Phase 4 AMBER 평가로 이동 (Baseline A vs Enhanced B)

---

## Phase 4. AMBER 평가 ⏳ 대기 중

```bash
# AMBER 설치
pip install cami-amber

# Baseline A 평가
amber.py -g ~/cami2_data/source_genomes/genome_binning.tsv \
         -o ~/results/evaluation/amber_baseline/ \
         ~/results/baseline_sample0/results/bins.tsv

# Enhanced B 평가
amber.py -g ~/cami2_data/source_genomes/genome_binning.tsv \
         -o ~/results/evaluation/amber_enhanced/ \
         ~/results/enhanced/bins.tsv
```

### 비교 지표 (논문 Figure 2-3 뼈대)

| 지표 | 의미 | Baseline A | Enhanced B |
|------|------|-----------|-----------|
| **Precision** | MAG 안에 다른 종이 안 섞인 정도 | ___ % | ___ % |
| **Recall** | 전체 게놈 중 MAG으로 회수된 비율 | ___ % | ___ % |
| **F1** | Precision과 Recall의 조화 평균 | ___ | ___ |
| **HQ MAG 수** | 완전성 ≥90%, 오염 <5% | ___ 개 | ___ 개 |
| **MQ MAG 수** | 완전성 ≥50%, 오염 <10% | ___ 개 | ___ 개 |
| **키메라 탐지** | CheckM2 vs +Evo 2 perplexity | ___ 개 | ___ 개 |
| **기능 주석율** | hypothetical protein → 기능 부여 비율 | ___ % | ___ % |

---

## 전체 체크리스트

### Phase 1 ✅
- [x] 데이터 다운로드 (21개 샘플 + ground truth)
- [x] 압축 해제 확인

### Phase 2 ✅ 완료 (2026-03-19)
- [x] mmlong2 --install_databases 완료 ✅ (2026-03-15 17:07)
  - [x] Greengenes2 DB ✅
  - [x] GUNC DB ✅
  - [x] Metabuli DB ✅
  - [x] Bakta DB ✅
  - [x] GTDB-Tk r226 ✅
- [x] sample_0 첫 실행 → coverage 0 문제 (config 미스매치)
- [x] config 수정 (`map-ont`, identity 80%) + sample_0 재실행
- [x] sample_0 완료 확인
- [x] **PC101 전면 이전 확정** — PC102 버림, PC101이 메인
  - [x] PC101 접속 + 계정 확인 ✅ (minseo1101 / 8375)
  - [x] `conda create -n mmlong2` 설치 완료
  - [x] `mmlong2 --install_databases` ✅ 완료 (2026-03-17 15:00)
  - [x] git config + evo2-mag clone + PAT 세팅
  - [x] Mac `~/.ssh/config` → `lab101` 단축키 등록
  - [x] Claude Code 설치 완료 ✅
  - [x] CAMI2 데이터 PC101로 전송 ✅ (21/21 샘플 완료)
  - [x] mmlong2 config 수정 ✅ (`map-ont` / identity 80%)
- [x] 21개 샘플 병렬 실행 (6개×12코어) ✅
- [x] AMRFinderPlus DB 업데이트 (`amrfinder_update --force_update`) ✅
- [x] sample 17 입력파일 재다운로드 (`frl.publisso.de`) + 재실행 ✅
- [x] sample 10 BAM 수동 복구 + proc 재실행 ✅
- [x] **전체 21개 샘플 완료 확인** ✅ (131 MAGs: HQ 52, MQ 79)

### GitHub Repo ✅
- [x] `git init evo2-mag` (서버에서 생성)
- [x] GitHub repo 생성 (https://github.com/sunsungkim04-sys/evo2-mag)
- [x] remote 연결 + initial push
- [x] 프로젝트 구조 생성 (src/evo2_mag, tests, docs, scripts)
- [x] pyproject.toml 작성 (pip install 준비)

### Phase 3 🔄 준비 완료 (RunPod 실행 대기)
- [x] 전송 데이터 패킹 ✅ (`~/cami2_baseline_for_runpod.tar.gz`, 832MB)
- [x] contig-to-bin 통합 매핑 생성 ✅ (`~/cami2_contig_bin_all.tsv`, 4,615 contigs)
- [x] 임베딩 추출 스크립트 작성 ✅ (`scripts/run_embed.py`)
- [x] HDBSCAN 클러스터링 스크립트 작성 ✅ (`scripts/run_cluster.py`)
- [x] RunPod 원스톱 실행 스크립트 작성 ✅ (`scripts/runpod_setup.sh`)
- [x] RunPod 계정 세팅 ✅ (H100 SXM 80GB × 1)
- [x] RunPod 인스턴스 실행 ✅ (`ssh root@64.247.201.49 -p 13118`)
- [x] 데이터 전송 (PC101 → RunPod) ✅ scp로 832MB 전송 완료
- [x] 환경 설치 ✅ (evo2, flash-attn, biopython, hdbscan)
- [ ] Evo 2 7B 임베딩 추출 🔄 (42,320 contigs, max_len=8192)
  - torch.load weights_only 호환 수정
  - bfloat16 → float32 변환 추가
  - 32bit index overflow → max_len 축소 (512k → 8k)
- [ ] HDBSCAN 클러스터링 → `evo2_c2b.tsv`
- [ ] 결과 회수 (RunPod → 연구실 서버 PC101)
- [ ] DAS Tool 4-binner 재실행 (연구실 서버, GPU 불필요)
- [ ] Perplexity 키메라 탐지 (추가 GPU 필요할 수 있음)

### Phase 4 ⏳
- [ ] AMBER Baseline A 평가
- [ ] AMBER Enhanced B 평가
- [ ] 비교 테이블 완성

---

## GitHub Repository 세팅 ✅ 완료

### 목적
Phase 3 실험 코드를 처음부터 GitHub에 관리 → 나중에 NAR 제출용 도구 패키징 기반

### Repo 정보
| 항목     | 내용                                                     |
| ------ | ------------------------------------------------------ |
| URL    | https://github.com/sunsungkim04-sys/evo2-mag           |
| 서버 경로  | `~/evo2-mag` (`/media/hdd/14Tb_2/minseo1201/evo2-mag`) |
| Branch | main                                                   |

### Repo 구조
```
evo2-mag/
├── src/evo2_mag/
│   ├── __init__.py
│   ├── embed.py      ← Evo 2 임베딩 추출
│   ├── bin.py        ← HDBSCAN 클러스터링 → evo2_c2b.tsv
│   ├── chimera.py    ← perplexity 키메라 탐지
│   └── annotate.py   ← 기능 주석 likelihood
├── tests/
├── docs/
├── scripts/          ← 병렬 실행 스크립트 등
├── pyproject.toml    ← pip install 준비 (evo2-mag)
└── README.md
```

### Git 설정 (서버)
```bash
git config --global user.email "sunsungkim04@gmail.com"
git config --global user.name "sunsungkim04-sys"
git config --global --add safe.directory /media/hdd/14Tb_2/minseo1201/evo2-mag
```

> [!warning] Personal Access Token
> - HTTPS 인증에 GitHub PAT 필요 (비밀번호 인증 불가)
> - 토큰은 URL에 내장됨: `git remote set-url origin https://USER:TOKEN@github.com/...`
> - 토큰 만료 90일 → **만료 전 갱신 필요**
> - Settings → Developer settings → Personal access tokens → Tokens (classic)

### 도구화 전략 (Phase 3 이후)
```
Phase 3 스크립트 작성 → repo에 커밋
    ↓
결과 논문 → Bioinformatics 제출
    ↓ 리뷰 기간 (2~3달) 동안 도구 패키징
CLI 인터페이스 (argparse) → pyproject.toml → pip install evo2-mag
    ↓
NAR 도전 가능
```

---

## 경쟁 논문 & 차별점

### 주요 선행 연구

| 논문              | 모델                  | 내용                       | 연도   | 저널                            |
| --------------- | ------------------- | ------------------------ | ---- | ----------------------------- |
| **DNABERT-S**   | DNABERT-2 기반        | DNA LM 임베딩으로 종 구분 + 비닝   | 2025 | *Bioinformatics* (ISMB)       |
| **Deepurify**   | Multi-modal LM      | MAG 오염 제거                | 2024 | *Nature Machine Intelligence* |
| **GenomeOcean** | 4B (JGI)            | 메타게놈 contig으로 훈련, BGC 발견 | 2025 | bioRxiv                       |
| **Bacformer**   | Protein transformer | 1.3M MAG으로 훈련            | 2025 | bioRxiv                       |

> [!success] Evo 2 + 메타게노믹스 조합 논문은 아직 없음 (2026-03 기준)

### 우리 연구의 차별점 (vs DNABERT-S)

| | DNABERT-S | 우리 연구 |
|--|---|---|
| 모델 | DNABERT-2 (fine-tuned) | **Evo 2 (7B/40B, pretrained)** |
| 컨텍스트 | ~512bp | **1M bp** → long contig 통째 처리 |
| 훈련 데이터 | 참조 게놈 | **9.3조 nt (메타게놈 포함)** |
| 비닝 통합 | 독립 도구 | **mmlong2 파이프라인 통합** |
| 평가 | 자체 28개 데이터셋 | **CAMI2 표준 벤치마크** |
| 시퀀싱 | short+long | **Nanopore long-read 특화** |

> [!tip] 논문 프레이밍
> "DNABERT-S가 DNA LM 비닝의 가능성을 보였지만, short context + 파이프라인 미통합이 한계.
> 우리는 Evo 2의 1M bp 컨텍스트를 활용해 Nanopore long-read 파이프라인(mmlong2)에 통합하고,
> CAMI2 ground truth로 정량 비교했다."

---

## 관련 노트

- [[01_Research/Evo2/Step1-CAMI2-벤치마크-실행가이드]]
- [[03_Projects/Evo2-mmlong2-MAG-enhancement]]
