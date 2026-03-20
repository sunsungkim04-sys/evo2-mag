#!/bin/bash
# mmlong2 4개 병렬 실행 스크립트
# sample_0은 이미 별도 실행 완료 가정
# 사용법: bash ~/run_mmlong2_parallel.sh

set -e

MAX_JOBS=4
CORES_PER_JOB=16
DATA_DIR=~/cami2_data/simulation_nanosim
RESULTS_DIR=~/results
LOG_DIR=~/mmlong2_logs

mkdir -p $LOG_DIR

echo "============================================"
echo "mmlong2 병렬 실행 시작 (4개 동시, 16코어씩)"
echo "시작 시간: $(date)"
echo "============================================"

running_jobs=0

for i in $(seq 1 20); do
    SAMPLE_DIR="${DATA_DIR}/2020.01.23_15.51.11_sample_${i}/reads/anonymous_reads.fq.gz"
    OUTPUT_DIR="${RESULTS_DIR}/baseline_sample${i}"
    LOG_FILE="${LOG_DIR}/sample_${i}.log"

    # 이미 완료된 샘플은 건너뛰기
    if [ -f "${OUTPUT_DIR}/results/bins.tsv" ]; then
        echo "[SKIP] sample_${i} — 이미 완료됨"
        continue
    fi

    echo "[START] sample_${i} — $(date)"
    mmlong2 -np "$SAMPLE_DIR" -o "$OUTPUT_DIR" -p $CORES_PER_JOB > "$LOG_FILE" 2>&1 &

    running_jobs=$((running_jobs + 1))

    # MAX_JOBS에 도달하면 하나가 끝날 때까지 대기
    if [ $running_jobs -ge $MAX_JOBS ]; then
        wait -n  # 아무 백그라운드 작업 하나가 끝날 때까지 대기
        running_jobs=$((running_jobs - 1))
        echo "[SLOT FREE] — $(date)"
    fi
done

# 남은 작업 모두 완료 대기
wait
echo "============================================"
echo "전체 완료: $(date)"
echo "============================================"
