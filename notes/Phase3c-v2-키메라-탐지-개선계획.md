---
tags:
  - Evo2
  - MAG
  - CAMI2
  - 키메라
  - perplexity
  - 계획
created: 2026-03-23
parent: "[[Phase3c-키메라-탐지-결과]]"
---

# Phase 3c-v2: 키메라 탐지 개선 계획

> [!abstract] 배경
> 현재 sliding window perplexity (any flag) 방식은 Recall 100%이지만 Precision 24.4%.
> 131개 bin 전부에서 최소 1개 window가 flagged되어 **사실상 전부 양성 판정**과 다름없음.
> 리뷰어 지적 예상: "threshold 없이 전부 flag하면 recall 100%는 당연한 거 아니냐"

---

## 근본 문제

```
현재: bin 내 mean + 2σ → threshold
→ 모든 bin은 내부 분산이 있음 → 어디서나 2σ 초과 구간 존재 → 무조건 flag
```

**Precision을 올리려면 "어디서든 높다"가 아니라 "이 contig에서 뭔가 바뀐다"를 탐지해야 함.**

---

## 개선 방향 3가지

### 방향 1: Junction 탐지 (perplexity 불연속점)

**아이디어**: 진짜 키메라는 perplexity가 **갑자기 튀는 지점(junction)**이 존재해야 한다.

```
정상 contig:  낮음 ─────────────────── 낮음
키메라 contig: 낮음 ──────┬─────────── 높음
                         ↑ junction (genome A → genome B 경계)
```

현재는 "어디서든 높으면 flag"인데, **인접 window 간 perplexity의 급격한 불연속**을 탐지해야 함.

**구현**:
```python
# perplexity_windows.tsv에서 contig별로 window 순서대로 정렬
# 인접 window 간 차이 (1차 미분)
delta = perplexity[i+1] - perplexity[i]

# 급격한 step-change가 있는 contig = 키메라 후보
if max(abs(delta)) > threshold:
    → junction 위치 특정 가능
```

> [!success] 장점
> - 추가 GPU 실험 불필요 — `perplexity_windows.tsv` 이미 있음
> - PC101에서 바로 실행 가능
> - junction 위치까지 특정 가능 → 논문에서 시각화 가능

> [!warning] 고려사항
> - threshold 설정 필요 (ROC curve로 최적화)
> - 반복 서열, IS element 등 정상적 불연속도 존재

---

### 방향 2: Bin 간 embedding 거리 비교

**아이디어**: 진짜 키메라 contig은 **자기 bin보다 다른 bin에 더 가까울** 것이다.

```python
# 각 bin의 centroid 계산
bin_centroid[b] = mean(embeddings[contigs in bin b])

# 각 contig에 대해
d_own = cosine_distance(contig_emb, bin_centroid[own_bin])
d_nearest_other = min(cosine_distance(contig_emb, bin_centroid[b]) for b != own_bin)

# 키메라 후보 조건
ratio = d_own / d_nearest_other
if ratio > 1.0:  # 자기 bin보다 다른 bin이 더 가까움
    → 키메라 또는 misassignment 의심
```

> [!success] 장점
> - `contig_embeddings.npz` (4096d) 이미 있음 → 추가 GPU 실험 불필요
> - PC101 CPU만으로 실행 가능
> - 이론적으로 가장 직접적: bin 소속 자체를 의심하는 방식
> - contig 단위 판정 → 어느 contig이 오염인지 특정 가능

> [!warning] 고려사항
> - bin 수가 많으면 (6000+) centroid 계산 비용 있음 (but CPU로 충분)
> - Binette 결과 bins에만 적용 (Evo2 클러스터 bins가 아닌 최종 MAG bins)

**입력 파일**:
```
~/results/contig_embeddings.npz          # 4096d embeddings
~/results/evo2_c2b_v4_1.tsv             # contig-to-bin mapping
~/results/chimera_validation_detail.tsv  # gold standard 비교용
```

---

### 방향 3: Contig 내 청크 간 일관성

**아이디어**: `run_embed.py`가 긴 contig를 청크로 나눠 임베딩했으므로, **청크별 embedding이 얼마나 일관적인지**로 키메라 판정.

```
정상 contig: chunk1 ≈ chunk2 ≈ chunk3  (같은 genome → 비슷한 embedding)
키메라:      chunk1 ↔ chunk2 급격히 다름 (genome A|B 경계 포함)
```

**구현**:
```python
# 같은 contig의 청크들 cosine similarity
sim = cosine_similarity(chunk_embeddings)

# 인접 청크 간 급격한 유사도 하락 = junction
if min(sim[i, i+1]) < threshold:
    → 키메라, junction 위치 = chunk i / i+1 경계
```

> [!success] 장점
> - 가장 이론적으로 강함: embedding 자체가 genome 정체성을 인코딩
> - junction을 bp 단위로 특정 가능

> [!warning] 고려사항
> - `run_embed.py` 코드 확인 결과: `_embed_chunked()`가 청크 평균을 내서 **contig당 벡터 1개만 저장** (`contig_embeddings.npz`)
> - 청크별 개별 embedding이 존재하지 않음 → 방향 3 실행 불가
> - **RunPod 재실행 필요** (~27시간, ~$46): 청크별 저장하도록 `run_embed.py` 수정 후 재추론

---

## 우선순위 및 실행 계획

| 우선순위 | 방향 | 추가 실험 | 예상 효과 |
|---------|------|----------|----------|
| **1순위** | 방향 2: Bin 간 embedding 거리 | ❌ 없음 | Precision 대폭 개선 |
| **2순위** | 방향 1: Junction 탐지 (perplexity 미분) | ❌ 없음 | FP 감소 + junction 위치 특정 |
| **3순위** | 방향 3: 청크 간 일관성 | ❌ RunPod 재실행 필요 (~$46) | 이론적으로 가장 강함 |

> [!todo] 실행 순서
> - [ ] 방향 2: `chimera_embedding_dist.py` 작성 → PC101에서 실행 → Precision/Recall 재계산
> - [ ] 방향 1: `perplexity_windows.tsv` 재분석 → delta 계산 → threshold ROC 최적화
> - [ ] 방향 3: `run_embed.py` 수정 (청크별 저장) → RunPod 재실행 (~$46) → 청크 간 cosine similarity 분석

---

## 목표 지표

| 지표 | 현재 (any flag) | 목표 |
|------|----------------|------|
| Precision | 0.2443 | **> 0.5** |
| Recall | 1.0000 | > 0.8 유지 |
| F1 | 0.3926 | **> 0.55** |

---

## 관련 노트

- [[Phase3c-키메라-탐지-결과]] — 현재 결과 및 문제점
- [[Phase3b-v2-클러스터링-개선]] — 클러스터링 탐색
- [[Evo2-mmlong2-MAG-enhancement]] — 프로젝트 메인
