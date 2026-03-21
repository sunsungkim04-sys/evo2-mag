#!/bin/bash
# Bakta 기능 주석: Enhanced Binette bins
# Usage: bash ~/evo2-mag/scripts/run_bakta_enhanced.sh

set -eo pipefail

RESULTS_DIR="$HOME/results"
SING="/home1/minseo1101/miniforge3/envs/mmlong2/bin/sing-mmlong2-proc"
BAKTA_DB="/home1/minseo1101/mmlong2_db_v1.2.1/db_bakta"
OUTPUT_DIR="$RESULTS_DIR/bakta_enhanced"
THREADS=12  # per bin
PARALLEL=6  # concurrent bins (12 threads × 6 = 72 cores)

mkdir -p "$OUTPUT_DIR/tmp"

echo "=== [$(date)] Bakta Enhanced bins 기능 주석 시작 ==="

# Collect all enhanced bins
BINS=()
for i in $(seq 0 20); do
    bindir="$RESULTS_DIR/baseline_sample${i}/tmp/binning/round_1/binette_enhanced/final_bins"
    if [ -d "$bindir" ]; then
        for f in "$bindir"/*.fa; do
            [ -f "$f" ] && BINS+=("$f")
        done
    fi
done
echo "  ${#BINS[@]} enhanced bins 발견"

# Run bakta on each bin
run_bakta() {
    local bin_fa=$1
    local bin_name=$(basename "$bin_fa" .fa)
    local out_dir="$OUTPUT_DIR/$bin_name"

    if [ -f "$out_dir/${bin_name}.tsv" ]; then
        return 0  # already done
    fi

    singularity exec "$SING" bash -c "
        export PATH=/opt/conda/envs/env_12/bin:\$PATH
        export TMPDIR='$OUTPUT_DIR/tmp'
        bakta --db '$BAKTA_DB' --prefix '$bin_name' --output '$out_dir' \
            --keep-contig-headers --tmp-dir '$OUTPUT_DIR/tmp' \
            --threads $THREADS '$bin_fa' --meta --force
    " > /dev/null 2>&1

    if [ -f "$out_dir/${bin_name}.tsv" ]; then
        echo "  ✓ $bin_name"
    else
        echo "  ✗ $bin_name FAILED"
    fi
}
export -f run_bakta
export OUTPUT_DIR SING BAKTA_DB THREADS

printf '%s\n' "${BINS[@]}" | xargs -P "$PARALLEL" -I {} bash -c 'run_bakta "$@"' _ {}

# Summarize results
echo ""
echo "=== [$(date)] Bakta 완료, 요약 생성 ==="
echo "bin,bakta_cds_all,bakta_cds_hyp,bakta_cds_dens" > "$OUTPUT_DIR/bakta_stats.csv"

for d in "$OUTPUT_DIR"/*/; do
    bin_name=$(basename "$d")
    tsv="$d/${bin_name}.tsv"
    [ -f "$tsv" ] || continue

    cds_all=$(grep -v "^#" "$tsv" | awk -F'\t' 'tolower($2)=="cds"' | wc -l)
    cds_hyp=$(grep -v "^#" "$tsv" | awk -F'\t' 'tolower($2)=="cds" && $8=="hypothetical protein"' | wc -l)
    # genome size from fasta
    fa=$(find "$RESULTS_DIR" -path "*/binette_enhanced/final_bins/${bin_name}.fa" 2>/dev/null | head -1)
    if [ -n "$fa" ]; then
        genome_size=$(grep -v "^>" "$fa" | tr -d '\n' | wc -c)
        cds_dens=$(echo "scale=1; $cds_all * 1000 / $genome_size" | bc 2>/dev/null || echo "0")
    else
        cds_dens=0
    fi

    echo "$bin_name,$cds_all,$cds_hyp,$cds_dens"
done >> "$OUTPUT_DIR/bakta_stats.csv"

# Final summary
python3 -c "
import csv
total_cds = total_hyp = 0
count = 0
with open('$OUTPUT_DIR/bakta_stats.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        total_cds += int(row['bakta_cds_all'])
        total_hyp += int(row['bakta_cds_hyp'])
        count += 1

func = total_cds - total_hyp
ratio = func / total_cds * 100 if total_cds > 0 else 0
print(f'')
print(f'--- Enhanced Bakta 결과 요약 ---')
print(f'  Bins annotated: {count}')
print(f'  Total CDS: {total_cds}')
print(f'  Hypothetical: {total_hyp}')
print(f'  Functional: {func}')
print(f'  Functional ratio: {ratio:.1f}%')
print(f'')
print(f'  Baseline: 77.4% functional (131 bins)')
print(f'  Enhanced: {ratio:.1f}% functional ({count} bins)')
"
