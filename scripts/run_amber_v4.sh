#!/bin/bash
# AMBER 평가: Baseline vs Enhanced v1 vs v2 vs v3
set -eo pipefail

RESULTS_DIR="$HOME/results"
OUTPUT_DIR="$RESULTS_DIR/amber_eval_v4"
mkdir -p "$OUTPUT_DIR"

echo "=== [$(date)] AMBER v3 평가 시작 ==="

for i in $(seq 0 20); do
    sample="baseline_sample${i}"
    
    # Gold standard (v1에서 재사용)
    gold_v1="$RESULTS_DIR/amber_eval/gold_${i}.tsv"
    [ ! -f "$gold_v1" ] && continue
    cp "$gold_v1" "$OUTPUT_DIR/gold_${i}.tsv"

    # Baseline
    baseline="$OUTPUT_DIR/baseline_${i}.tsv"
    echo -e "@Version:0.9.1\n@SampleID:${sample}\n@@SEQUENCEID\tBINID" > "$baseline"
    bindir="$RESULTS_DIR/${sample}/tmp/binning/round_1/binette/final_bins"
    [ ! -d "$bindir" ] && bindir="$RESULTS_DIR/${sample}/results/bins"
    if [ -d "$bindir" ]; then
        for f in "$bindir"/*.fa "$bindir"/*.fa.gz; do
            [ -f "$f" ] || continue
            bn=$(basename "$f" | sed 's/\.fa\.gz$//' | sed 's/\.fa$//')
            if [[ "$f" == *.gz ]]; then
                zcat "$f" 2>/dev/null | grep "^>" | sed "s/^>//" | while read c; do echo -e "${c}\t${bn}"; done
            else
                grep "^>" "$f" | sed "s/^>//" | while read c; do echo -e "${c}\t${bn}"; done
            fi
        done >> "$baseline"
    fi

    # Enhanced v3
    enhanced="$OUTPUT_DIR/enhanced_v4_${i}.tsv"
    echo -e "@Version:0.9.1\n@SampleID:${sample}\n@@SEQUENCEID\tBINID" > "$enhanced"
    bindir_v3="$RESULTS_DIR/${sample}/tmp/binning/round_1/binette_enhanced_v4/final_bins"
    if [ -d "$bindir_v3" ]; then
        for f in "$bindir_v3"/*.fa; do
            [ -f "$f" ] || continue
            bn="enh4_$(basename "$f" .fa)"
            grep "^>" "$f" | sed "s/^>//" | while read c; do echo -e "${c}\t${bn}"; done
        done >> "$enhanced"
    fi
done

# Combine
for prefix in gold baseline enhanced_v4; do
    combined="$OUTPUT_DIR/${prefix}_combined.tsv"
    first=1
    for i in $(seq 0 20); do
        f="$OUTPUT_DIR/${prefix}_${i}.tsv"
        [ -f "$f" ] || continue
        if [ $first -eq 1 ]; then cat "$f" > "$combined"; first=0
        else echo "" >> "$combined"; cat "$f" >> "$combined"; fi
    done
done

~/miniforge3/bin/amber.py \
    -g "$OUTPUT_DIR/gold_combined.tsv" \
    "$OUTPUT_DIR/baseline_combined.tsv" \
    "$OUTPUT_DIR/enhanced_v4_combined.tsv" \
    -l "Baseline,Enhanced_v4" \
    -o "$OUTPUT_DIR/amber_output" \
    2>&1

echo "=== [$(date)] AMBER v3 완료 ==="
