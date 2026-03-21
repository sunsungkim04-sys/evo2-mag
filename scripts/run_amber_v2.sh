#!/bin/bash
# AMBER 평가: Baseline A vs Enhanced v1 B vs Enhanced v2 C
# Usage: bash ~/evo2-mag/scripts/run_amber_v2.sh

set -eo pipefail

RESULTS_DIR="$HOME/results"
OUTPUT_DIR="$RESULTS_DIR/amber_eval_v2"
mkdir -p "$OUTPUT_DIR"

echo "=== [$(date)] AMBER v2 평가 시작 ==="
echo "  3-way 비교: Baseline vs Enhanced_v1 vs Enhanced_v2"

for i in $(seq 0 20); do
    sample="baseline_sample${i}"

    # Gold standard (기존 것 재사용)
    gold_orig="$RESULTS_DIR/amber_eval/gold_standard_${sample}.tsv"
    if [ ! -f "$gold_orig" ]; then
        echo "  [$sample] gold standard 없음, 스킵"
        continue
    fi

    # 기존 v1 AMBER에서 사용한 gold (LENGTH 포함) 재사용
    gold_v1="$RESULTS_DIR/amber_eval/gold_${i}.tsv"
    gold="$OUTPUT_DIR/gold_${i}.tsv"
    if [ -f "$gold_v1" ]; then
        cp "$gold_v1" "$gold"
    else
        echo "@Version:0.9.1" > "$gold"
        echo "@SampleID:${sample}" >> "$gold"
        echo "@@SEQUENCEID	BINID" >> "$gold"
        grep -v "@@SEQUENCEID" "$gold_orig" >> "$gold"
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

    # Enhanced v1 binning
    enhanced_v1="$OUTPUT_DIR/enhanced_v1_${i}.tsv"
    echo "@Version:0.9.1" > "$enhanced_v1"
    echo "@SampleID:${sample}" >> "$enhanced_v1"
    echo "@@SEQUENCEID	BINID" >> "$enhanced_v1"

    bindir_v1="$RESULTS_DIR/${sample}/tmp/binning/round_1/binette_enhanced/final_bins"
    if [ -d "$bindir_v1" ]; then
        for f in "$bindir_v1"/*.fa; do
            [ -f "$f" ] || continue
            bin_name="enh1_$(basename "$f" .fa)"
            grep "^>" "$f" | sed "s/^>//" | while read c; do echo -e "${c}\t${bin_name}"; done
        done >> "$enhanced_v1"
    fi

    # Enhanced v2 binning
    enhanced_v2="$OUTPUT_DIR/enhanced_v2_${i}.tsv"
    echo "@Version:0.9.1" > "$enhanced_v2"
    echo "@SampleID:${sample}" >> "$enhanced_v2"
    echo "@@SEQUENCEID	BINID" >> "$enhanced_v2"

    bindir_v2="$RESULTS_DIR/${sample}/tmp/binning/round_1/binette_enhanced_v2/final_bins"
    if [ -d "$bindir_v2" ]; then
        for f in "$bindir_v2"/*.fa; do
            [ -f "$f" ] || continue
            bin_name="enh2_$(basename "$f" .fa)"
            grep "^>" "$f" | sed "s/^>//" | while read c; do echo -e "${c}\t${bin_name}"; done
        done >> "$enhanced_v2"
    fi
done

# Combine files
for prefix in gold baseline enhanced_v1 enhanced_v2; do
    combined="$OUTPUT_DIR/${prefix}_combined.tsv"
    first=1
    for i in $(seq 0 20); do
        f="$OUTPUT_DIR/${prefix}_${i}.tsv"
        [ -f "$f" ] || continue
        if [ $first -eq 1 ]; then
            cat "$f" > "$combined"
            first=0
        else
            echo "" >> "$combined"
            cat "$f" >> "$combined"
        fi
    done
done

echo ""
echo "AMBER 실행 (3-way 비교)..."

~/miniforge3/bin/amber.py \
    -g "$OUTPUT_DIR/gold_combined.tsv" \
    "$OUTPUT_DIR/baseline_combined.tsv" \
    "$OUTPUT_DIR/enhanced_v1_combined.tsv" \
    "$OUTPUT_DIR/enhanced_v2_combined.tsv" \
    -l "Baseline,Enhanced_v1,Enhanced_v2" \
    -o "$OUTPUT_DIR/amber_output" \
    2>&1

echo ""
echo "=== [$(date)] AMBER 완료 ==="
echo "결과: $OUTPUT_DIR/amber_output/"
