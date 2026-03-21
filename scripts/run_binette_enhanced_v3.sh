#!/bin/bash
# Binette 앙상블 v2: 기존 3종(VAMB + MetaBAT2 + SemiBin2) + Evo2 v2 bins = 4종
# v1 대비 변경: evo2_bins → evo2_bins_v3 (샘플별 UMAP+HDBSCAN)
# Usage: bash ~/evo2-mag/scripts/run_binette_enhanced_v3.sh

set -eo pipefail

RESULTS_DIR="$HOME/results"
SING="/home1/minseo1101/miniforge3/envs/mmlong2/bin/sing-mmlong2-lite"
THREADS=12
PARALLEL=6
MIN_COMPL=50
WEIGHT=2

echo "=== [$(date)] Binette Enhanced v3 앙상블 시작 ==="
echo "  4종: VAMB + MetaBAT2 + SemiBin2 + Evo2_v3"
echo "  병렬: ${PARALLEL}개 동시, 샘플당 ${THREADS} threads"
echo ""

run_sample() {
    local i=$1
    local sample="baseline_sample${i}"
    local bindir="${RESULTS_DIR}/${sample}/tmp/binning/round_1"
    local evo2dir="${RESULTS_DIR}/evo2_bins_v3/${sample}"
    local outdir="${bindir}/binette_enhanced_v3"
    local contigs="${bindir}/contigs.fasta"
    local tmpdir="${bindir}/tmp_decompress_v3"

    if [ ! -d "$bindir" ]; then
        echo "  [sample_${i}] round_1 없음, 스킵"
        return
    fi
    if [ ! -f "$contigs" ]; then
        echo "  [sample_${i}] contigs.fasta 없음, 스킵"
        return
    fi
    if [ ! -d "$evo2dir" ] || [ -z "$(ls -A "$evo2dir" 2>/dev/null)" ]; then
        echo "  [sample_${i}] Evo2 v2 bins 없음, 스킵"
        return
    fi

    local vamb_n=$(ls "$bindir/vamb/bins/"*.fna.gz 2>/dev/null | wc -l)
    local mb2_n=$(ls "$bindir/metabat2/"*.fa.gz 2>/dev/null | wc -l)
    local sb2_n=$(ls "$bindir/semibin/output_bins/"*.fa.gz 2>/dev/null | wc -l)
    local evo2_n=$(ls "$evo2dir/"*.fa 2>/dev/null | wc -l)

    if [ "$vamb_n" -eq 0 ] && [ "$mb2_n" -eq 0 ] && [ "$sb2_n" -eq 0 ]; then
        echo "  [sample_${i}] 기존 bins 0개, 스킵"
        return
    fi

    echo "  [$(date +%H:%M:%S)] sample_${i} 시작 (vamb=$vamb_n mb2=$mb2_n sb2=$sb2_n evo2_v3=$evo2_n)"

    mkdir -p "$tmpdir/vamb" "$tmpdir/metabat2" "$tmpdir/semibin"

    if [ "$vamb_n" -gt 0 ]; then
        for f in "$bindir/vamb/bins/"*.fna.gz; do
            gunzip -c "$f" > "$tmpdir/vamb/$(basename "${f%.gz}")"
        done
    fi
    if [ "$mb2_n" -gt 0 ]; then
        for f in "$bindir/metabat2/"*.fa.gz; do
            gunzip -c "$f" > "$tmpdir/metabat2/$(basename "${f%.gz}")"
        done
    fi
    if [ "$sb2_n" -gt 0 ]; then
        for f in "$bindir/semibin/output_bins/"*.fa.gz; do
            gunzip -c "$f" > "$tmpdir/semibin/$(basename "${f%.gz}")"
        done
    fi

    # Evo2 v2 bins 필터링: contigs.fasta에 없는 contig 제거
    local evo2_filtered="${tmpdir}/evo2"
    mkdir -p "$evo2_filtered"
    local valid_contigs="${tmpdir}/valid_contigs.txt"
    grep "^>" "$contigs" | sed 's/^>//' > "$valid_contigs"
    for f in "$evo2dir"/*.fa; do
        local out_fa="${evo2_filtered}/$(basename "$f")"
        python3 -c "
from Bio import SeqIO
valid = set(open('${valid_contigs}').read().strip().split('\n'))
recs = [r for r in SeqIO.parse('${f}', 'fasta') if r.id in valid]
if recs:
    SeqIO.write(recs, '${out_fa}', 'fasta')
" 2>/dev/null
    done
    local evo2_filtered_n=$(ls "$evo2_filtered"/*.fa 2>/dev/null | wc -l)
    echo "    evo2_v3 filtered: $evo2_n → $evo2_filtered_n bins (contigs.fasta 기준)"

    if [ -d "$outdir" ]; then
        rm -rf "$outdir"
    fi

    singularity exec "$SING" bash -c "
        export PATH=/opt/conda/envs/env_8/bin:\$PATH
        binette -d '$tmpdir/vamb' '$tmpdir/metabat2' '$tmpdir/semibin' '$evo2_filtered' \
            -c '$contigs' -o '$outdir' -w $WEIGHT -m $MIN_COMPL -t $THREADS
    "

    rm -rf "$tmpdir"

    local result_n=$(ls "$outdir/final_bins/"*.fa 2>/dev/null | wc -l)
    echo "  [$(date +%H:%M:%S)] sample_${i} 완료 → ${result_n} enhanced_v3 bins"
}

export -f run_sample
export RESULTS_DIR SING THREADS MIN_COMPL WEIGHT

seq 0 20 | xargs -P "$PARALLEL" -I {} bash -c 'run_sample {}'

echo ""
echo "=== [$(date)] 전체 완료! ==="
echo ""

echo "--- Enhanced v3 Binette 결과 요약 ---"
total_baseline=0
total_v1=0
total_v2=0
for i in $(seq 0 20); do
    outdir_v2="${RESULTS_DIR}/baseline_sample${i}/tmp/binning/round_1/binette_enhanced_v3"
    outdir_v1="${RESULTS_DIR}/baseline_sample${i}/tmp/binning/round_1/binette_enhanced"
    outdir_base="${RESULTS_DIR}/baseline_sample${i}/tmp/binning/round_1/binette/final_bins"

    n_v2=0; n_v1=0; n_base=0
    [ -d "$outdir_v2/final_bins" ] && n_v2=$(ls "$outdir_v2/final_bins/"*.fa 2>/dev/null | wc -l)
    [ -d "$outdir_v1/final_bins" ] && n_v1=$(ls "$outdir_v1/final_bins/"*.fa 2>/dev/null | wc -l)
    if [ -d "$outdir_base" ]; then
        n_base=$(( $(ls "$outdir_base"/*.fa 2>/dev/null | wc -l) + $(ls "$outdir_base"/*.fa.gz 2>/dev/null | wc -l) ))
    fi

    total_baseline=$((total_baseline + n_base))
    total_v1=$((total_v1 + n_v1))
    total_v2=$((total_v2 + n_v2))
    echo "  sample_${i}: baseline=${n_base} → v1=${n_v1} → v2=${n_v2}"
done
echo ""
echo "  TOTAL: baseline=${total_baseline} → v1=${total_v1} → v2=${total_v2}"
