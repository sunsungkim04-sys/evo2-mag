#!/bin/bash
# AMBER 평가: Baseline A vs Enhanced B (샘플별)
# Usage: bash ~/evo2-mag/scripts/run_amber.sh

set -eo pipefail

RESULTS_DIR="$HOME/results"
OUTPUT_DIR="$RESULTS_DIR/amber_eval"

echo "=== [$(date)] AMBER 평가 시작 ==="

for i in $(seq 0 20); do
    sample="baseline_sample${i}"
    gold_in="$OUTPUT_DIR/gold_standard_${sample}.tsv"

    if [ ! -f "$gold_in" ]; then
        echo "  [$sample] gold standard 없음, 스킵"
        continue
    fi

    # Gold standard → CAMI biobox format
    gold="$OUTPUT_DIR/gold_${i}.tsv"
    echo "@Version:0.9.1" > "$gold"
    echo "@SampleID:${sample}" >> "$gold"
    echo "@@SEQUENCEID	BINID" >> "$gold"
    grep -v "@@SEQUENCEID" "$gold_in" >> "$gold"

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

    # Enhanced binning
    enhanced="$OUTPUT_DIR/enhanced_${i}.tsv"
    echo "@Version:0.9.1" > "$enhanced"
    echo "@SampleID:${sample}" >> "$enhanced"
    echo "@@SEQUENCEID	BINID" >> "$enhanced"

    bindir_e="$RESULTS_DIR/${sample}/tmp/binning/round_1/binette_enhanced/final_bins"
    if [ -d "$bindir_e" ]; then
        for f in "$bindir_e"/*.fa; do
            [ -f "$f" ] || continue
            bin_name="enh_$(basename "$f" .fa)"
            grep "^>" "$f" | sed "s/^>//" | while read c; do echo -e "${c}\t${bin_name}"; done
        done >> "$enhanced"
    fi
done

# AMBER 실행 (전체 샘플 한 번에)
echo ""
echo "AMBER 실행..."

# Collect all files
gold_files=""
baseline_files=""
enhanced_files=""
for i in $(seq 0 20); do
    [ -f "$OUTPUT_DIR/gold_${i}.tsv" ] && gold_files="$gold_files $OUTPUT_DIR/gold_${i}.tsv"
    [ -f "$OUTPUT_DIR/baseline_${i}.tsv" ] && baseline_files="$baseline_files $OUTPUT_DIR/baseline_${i}.tsv"
    [ -f "$OUTPUT_DIR/enhanced_${i}.tsv" ] && enhanced_files="$enhanced_files $OUTPUT_DIR/enhanced_${i}.tsv"
done

# AMBER needs one gold standard file and multiple binning files
# For multi-sample, concatenate with different SampleIDs
# Actually AMBER supports multiple samples natively - pass all files

# Combine gold standards
GOLD_ALL="$OUTPUT_DIR/gold_combined.tsv"
first=1
for i in $(seq 0 20); do
    f="$OUTPUT_DIR/gold_${i}.tsv"
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

# Combine enhanced
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

amber.py \
    -g "$GOLD_ALL" \
    "$BASE_ALL" "$ENH_ALL" \
    -l "Baseline,Enhanced" \
    -o "$OUTPUT_DIR/amber_output" \
    2>&1

echo ""
echo "=== [$(date)] AMBER 완료 ==="
echo "결과: $OUTPUT_DIR/amber_output/"
