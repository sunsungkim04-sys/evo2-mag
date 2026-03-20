#!/bin/bash
# CheckM2 품질 평가: Enhanced Binette bins
# Usage: bash ~/evo2-mag/scripts/run_checkm2_enhanced.sh

set -eo pipefail

RESULTS_DIR="$HOME/results"
SING="/home1/minseo1101/miniforge3/envs/mmlong2/bin/sing-mmlong2-lite"
CHECKM2="/opt/conda/envs/env_8/bin/checkm2"
THREADS=72
OUTPUT="$RESULTS_DIR/checkm2_enhanced"

echo "=== [$(date)] CheckM2 Enhanced bins 품질 평가 시작 ==="

# 1) 모든 enhanced bins를 한 디렉토리에 모으기
ALLBINS="$OUTPUT/all_bins"
mkdir -p "$ALLBINS"

total=0
for i in $(seq 0 20); do
    bindir="$RESULTS_DIR/baseline_sample${i}/tmp/binning/round_1/binette_enhanced/final_bins"
    if [ -d "$bindir" ]; then
        for f in "$bindir"/*.fa; do
            # 파일명에 샘플 prefix 추가 (충돌 방지)
            cp "$f" "$ALLBINS/sample${i}_$(basename "$f")"
            total=$((total + 1))
        done
    fi
done
echo "  $total enhanced bins 수집 완료"

# 2) CheckM2 실행
echo "=== [$(date)] CheckM2 predict 실행 ==="
mkdir -p "$OUTPUT/checkm2_out"

singularity exec "$SING" bash -c "
    export PATH=/opt/conda/envs/env_8/bin:\$PATH
    checkm2 predict \
        --input '$ALLBINS' \
        --output-directory '$OUTPUT/checkm2_out' \
        --threads $THREADS \
        -x fa \
        --force
"

echo "=== [$(date)] CheckM2 완료 ==="

# 3) 결과 요약
REPORT="$OUTPUT/checkm2_out/quality_report.tsv"
if [ -f "$REPORT" ]; then
    total=$(tail -n +2 "$REPORT" | wc -l)
    hq=$(awk -F'\t' 'NR>1 && $2>=90 && $3<5' "$REPORT" | wc -l)
    mq=$(awk -F'\t' 'NR>1 && $2>=50 && $3<10 && !($2>=90 && $3<5)' "$REPORT" | wc -l)
    lq=$(awk -F'\t' 'NR>1 && !($2>=50 && $3<10)' "$REPORT" | wc -l)
    echo ""
    echo "--- Enhanced CheckM2 결과 요약 ---"
    echo "  Total bins: $total"
    echo "  High-Quality (>=90% comp, <5% cont): $hq"
    echo "  Medium-Quality (>=50% comp, <10% cont): $mq"
    echo "  Low-Quality: $lq"
    echo ""
    echo "  Baseline 비교: HQ 52, MQ 79 (total 131)"
    echo "  Enhanced:      HQ $hq, MQ $mq (total $total)"
    echo ""
    echo "  상세: $REPORT"
fi
