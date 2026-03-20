#!/bin/bash
# AMBER gold standard 생성: reads_mapping + BAM → contig-to-genome 매핑
# 방법: read→genome (reads_mapping.tsv) + read→contig (BAM) → contig→genome (majority vote)
# Output: CAMI biobox format (@@SEQUENCEID\tBINID)
# Usage: bash ~/evo2-mag/scripts/make_gold_standard.sh

set -eo pipefail

SING="/home1/minseo1101/miniforge3/envs/mmlong2/bin/sing-mmlong2-lite"
CAMI_DIR="/home1/minseo1101/cami2_data/simulation_nanosim"
RESULTS_DIR="/home1/minseo1101/results"
OUTPUT_DIR="$RESULTS_DIR/amber_eval"

mkdir -p "$OUTPUT_DIR"

echo "=== [$(date)] Gold standard 생성 시작 ==="

for i in $(seq 0 20); do
    sample="baseline_sample${i}"
    reads_map="$CAMI_DIR/2020.01.23_15.51.11_sample_${i}/reads/reads_mapping.tsv.gz"
    bam="$RESULTS_DIR/${sample}/tmp/binning/mapping/1-NP.bam"
    gold_out="$OUTPUT_DIR/gold_standard_${sample}.tsv"

    if [ ! -f "$reads_map" ]; then
        echo "  [$sample] reads_mapping 없음, 스킵"
        continue
    fi
    if [ ! -f "$bam" ]; then
        echo "  [$sample] BAM 없음, 스킵"
        continue
    fi
    if [ -f "$gold_out" ]; then
        echo "  [$sample] 이미 존재, 스킵"
        continue
    fi

    echo -n "  [$sample] "

    # Extract read→contig from BAM, combine with read→genome
    singularity exec "$SING" bash -c "
        export PATH=/opt/conda/envs/env_1/bin:\$PATH
        samtools view '$bam' | awk '{print \$1, \$3}' OFS='\t'
    " > "$OUTPUT_DIR/tmp_read_contig_${i}.tsv"

    python3 -c "
import gzip
from collections import defaultdict, Counter

# 1) read → genome (from reads_mapping.tsv.gz)
read2genome = {}
with gzip.open('$reads_map', 'rt') as f:
    for line in f:
        if line.startswith('#'):
            continue
        parts = line.strip().split('\t')
        read2genome[parts[0]] = parts[1]  # anonymous_read_id → genome_id

# 2) read → contig (from BAM)
contig_genomes = defaultdict(list)
with open('$OUTPUT_DIR/tmp_read_contig_${i}.tsv') as f:
    for line in f:
        read_id, contig = line.strip().split('\t')
        if contig != '*' and read_id in read2genome:
            contig_genomes[contig].append(read2genome[read_id])

# 3) contig → genome (majority vote)
with open('$gold_out', 'w') as out:
    out.write('@@SEQUENCEID\tBINID\n')
    for contig in sorted(contig_genomes):
        genome = Counter(contig_genomes[contig]).most_common(1)[0][0]
        out.write(f'{contig}\t{genome}\n')

print(f'{len(contig_genomes)} contigs → {len(set(g for gs in contig_genomes.values() for g in gs))} genomes')
"

    rm -f "$OUTPUT_DIR/tmp_read_contig_${i}.tsv"
done

# 전체 합치기
echo ""
echo "전체 gold standard 합치기..."
echo "@@SEQUENCEID	BINID" > "$OUTPUT_DIR/gold_standard_all.tsv"
for i in $(seq 0 20); do
    f="$OUTPUT_DIR/gold_standard_baseline_sample${i}.tsv"
    if [ -f "$f" ]; then
        grep -v "@@SEQUENCEID" "$f" >> "$OUTPUT_DIR/gold_standard_all.tsv"
    fi
done
total=$(grep -v "@@SEQUENCEID" "$OUTPUT_DIR/gold_standard_all.tsv" | wc -l)
echo "  Total: $total contigs mapped"

echo "=== [$(date)] Gold standard 생성 완료 ==="
