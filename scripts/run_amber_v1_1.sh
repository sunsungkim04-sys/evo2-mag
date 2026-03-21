#!/bin/bash
# AMBER 평가: Baseline A vs Enhanced v1_1 (cosine) (샘플별)
# Usage: bash ~/evo2-mag/scripts/run_amber_v1_1.sh

set -eo pipefail

RESULTS_DIR="$HOME/results"
# 기존 amber_eval의 gold standard 재사용
GOLD_DIR="$RESULTS_DIR/amber_eval"
OUTPUT_DIR="$RESULTS_DIR/amber_eval_v1_1"
mkdir -p "$OUTPUT_DIR"

echo "=== [$(date)] AMBER v1_1 (cosine) 평가 시작 ==="

for i in $(seq 0 20); do
    sample="baseline_sample${i}"
    gold_in="$GOLD_DIR/gold_standard_${sample}.tsv"

    if [ ! -f "$gold_in" ]; then
        echo "  [$sample] gold standard 없음, 스킵"
        continue
    fi

    # Gold standard: 기존 amber_eval의 gold 파일 재사용 (_LENGTH 포함)
    gold="$GOLD_DIR/gold_${i}.tsv"
    if [ ! -f "$gold" ]; then
        echo "  [$sample] gold_${i}.tsv 없음, 스킵"
        continue
    fi

    # Baseline binning
    baseline="$OUTPUT_DIR/baseline_${i}.tsv"
    echo "@Version:0.9.1" > "$baseline"
    echo "@SampleID:${sample}" >> "$baseline"
    echo "@@SEQUENCEID	BINID" >> "$baseline"

    bindir="$RESULTS_DIR/${sample}/tmp/binning/round_1/binette/final_bins"
    if [ ! -d "$bindir" ]; then
        bindir="$RESULTS_DIR/${sample}/results/bins"
    fi
    if [ -d "$bindir" ]; then
        for f in "$bindir"/*.fa "$bindir"/*.fa.gz; do
            [ -f "$f" ] || continue
            bin_name=$(basename "$f" | sed 's/\.fa\.gz$//' | sed 's/\.fa$//')
            if [[ "$f" == *.gz ]]; then
                zcat "$f" 2>/dev/null | grep "^>" | sed "s/^>//" | while read c; do echo -e "${c}\t${bin_name}"; done
            else
                grep "^>" "$f" | sed "s/^>//" | while read c; do echo -e "${c}\t${bin_name}"; done
            fi
        done >> "$baseline"
    fi

    # Enhanced v1_1 binning
    enhanced="$OUTPUT_DIR/enhanced_${i}.tsv"
    echo "@Version:0.9.1" > "$enhanced"
    echo "@SampleID:${sample}" >> "$enhanced"
    echo "@@SEQUENCEID	BINID" >> "$enhanced"

    bindir_e="$RESULTS_DIR/${sample}/tmp/binning/round_1/binette_enhanced_v1_1/final_bins"
    if [ -d "$bindir_e" ]; then
        for f in "$bindir_e"/*.fa; do
            [ -f "$f" ] || continue
            bin_name="enh_$(basename "$f" .fa)"
            grep "^>" "$f" | sed "s/^>//" | while read c; do echo -e "${c}\t${bin_name}"; done
        done >> "$enhanced"
    fi
done

# Combine gold standards (기존 amber_eval에서 재사용)
GOLD_ALL="$OUTPUT_DIR/gold_combined.tsv"
first=1
for i in $(seq 0 20); do
    f="$GOLD_DIR/gold_${i}.tsv"
    [ -f "$f" ] || continue
    if [ $first -eq 1 ]; then
        cat "$f" > "$GOLD_ALL"
        first=0
    else
        echo "" >> "$GOLD_ALL"
        cat "$f" >> "$GOLD_ALL"
    fi
done

# Combine baseline
BASE_ALL="$OUTPUT_DIR/baseline_combined.tsv"
first=1
for i in $(seq 0 20); do
    f="$OUTPUT_DIR/baseline_${i}.tsv"
    [ -f "$f" ] || continue
    if [ $first -eq 1 ]; then
        cat "$f" > "$BASE_ALL"
        first=0
    else
        echo "" >> "$BASE_ALL"
        cat "$f" >> "$BASE_ALL"
    fi
done

# Combine enhanced v1_1
ENH_ALL="$OUTPUT_DIR/enhanced_combined.tsv"
first=1
for i in $(seq 0 20); do
    f="$OUTPUT_DIR/enhanced_${i}.tsv"
    [ -f "$f" ] || continue
    if [ $first -eq 1 ]; then
        cat "$f" > "$ENH_ALL"
        first=0
    else
        echo "" >> "$ENH_ALL"
        cat "$f" >> "$ENH_ALL"
    fi
done

~/miniforge3/bin/amber.py \
    -g "$GOLD_ALL" \
    "$BASE_ALL" "$ENH_ALL" \
    -l "Baseline,Enhanced_v1_1" \
    -o "$OUTPUT_DIR/amber_output" \
    2>&1

echo ""
echo "=== [$(date)] AMBER v1_1 완료 ==="
echo "결과: $OUTPUT_DIR/amber_output/"
