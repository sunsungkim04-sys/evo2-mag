#!/bin/bash
# Binette 앙상블: 기존 3종(VAMB + MetaBAT2 + SemiBin2) + Evo2 bins = 4종
# mmlong2의 Singularity 컨테이너 내 Binette 사용
#
# 사전 조건:
#   - ~/results/evo2_bins/baseline_sampleN/ 에 Evo2 bin FASTA 존재
#   - ~/results/baseline_sampleN/tmp/binning/round_1/ 에 기존 3종 bins 존재
#
# Usage: bash ~/evo2-mag/scripts/run_binette_enhanced.sh

set -eo pipefail

RESULTS_DIR="$HOME/results"
SING="/home1/minseo1101/miniforge3/envs/mmlong2/bin/sing-mmlong2-lite"
BINETTE="/opt/conda/envs/env_8/bin/binette"
THREADS=12  # 샘플당 스레드 (6개 병렬 × 12 = 72 cores)
PARALLEL=6
MIN_COMPL=50
WEIGHT=2

echo "=== [$(date)] Binette Enhanced 앙상블 시작 ==="
echo "  4종: VAMB + MetaBAT2 + SemiBin2 + Evo2"
echo "  병렬: ${PARALLEL}개 동시, 샘플당 ${THREADS} threads"
echo ""

run_sample() {
    local i=$1
    local sample="baseline_sample${i}"
    local bindir="${RESULTS_DIR}/${sample}/tmp/binning/round_1"
    local evo2dir="${RESULTS_DIR}/evo2_bins/${sample}"
    local outdir="${bindir}/binette_enhanced"
    local contigs="${bindir}/contigs.fasta"
    local tmpdir="${bindir}/tmp_decompress"

    # 기본 체크
    if [ ! -d "$bindir" ]; then
        echo "  [sample_${i}] round_1 없음, 스킵"
        return
    fi
    if [ ! -f "$contigs" ]; then
        echo "  [sample_${i}] contigs.fasta 없음, 스킵"
        return
    fi
    if [ ! -d "$evo2dir" ] || [ -z "$(ls -A "$evo2dir" 2>/dev/null)" ]; then
        echo "  [sample_${i}] Evo2 bins 없음, 스킵"
        return
    fi

    # 기존 3종 bins 수 체크
    local vamb_n=$(ls "$bindir/vamb/bins/"*.fna.gz 2>/dev/null | wc -l)
    local mb2_n=$(ls "$bindir/metabat2/"*.fa.gz 2>/dev/null | wc -l)
    local sb2_n=$(ls "$bindir/semibin/output_bins/"*.fa.gz 2>/dev/null | wc -l)
    local evo2_n=$(ls "$evo2dir/"*.fa 2>/dev/null | wc -l)

    if [ "$vamb_n" -eq 0 ] && [ "$mb2_n" -eq 0 ] && [ "$sb2_n" -eq 0 ]; then
        echo "  [sample_${i}] 기존 bins 0개, 스킵"
        return
    fi

    echo "  [$(date +%H:%M:%S)] sample_${i} 시작 (vamb=$vamb_n mb2=$mb2_n sb2=$sb2_n evo2=$evo2_n)"

    # 기존 bins 압축 해제 (임시 디렉토리)
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

    # Evo2 bins 필터링: contigs.fasta에 없는 contig 제거
    # (assembly에서 split된 짧은 조각이 mmlong2 filtering에서 제거되어 불일치 발생)
    local evo2_filtered="${tmpdir}/evo2"
    mkdir -p "$evo2_filtered"
    local valid_contigs="${tmpdir}/valid_contigs.txt"
    grep "^>" "$contigs" | sed 's/^>//' > "$valid_contigs"
    for f in "$evo2dir"/*.fa; do
        local out_fa="${evo2_filtered}/$(basename "$f")"
        python3 -c "
from Bio import SeqIO
import sys
valid = set(open('${valid_contigs}').read().strip().split('\n'))
recs = [r for r in SeqIO.parse('${f}', 'fasta') if r.id in valid]
if recs:
    SeqIO.write(recs, '${out_fa}', 'fasta')
" 2>/dev/null
    done
    local evo2_filtered_n=$(ls "$evo2_filtered"/*.fa 2>/dev/null | wc -l)
    echo "    evo2 filtered: $evo2_n → $evo2_filtered_n bins (contigs.fasta 기준)"

    # 이전 결과 있으면 삭제
    if [ -d "$outdir" ]; then
        rm -rf "$outdir"
    fi

    # Binette 4종 앙상블 실행
    singularity exec "$SING" "$BINETTE" \
        -d "$tmpdir/vamb" "$tmpdir/metabat2" "$tmpdir/semibin" "$evo2_filtered" \
        -c "$contigs" \
        -o "$outdir" \
        -w "$WEIGHT" \
        -m "$MIN_COMPL" \
        -t "$THREADS"

    # 임시 파일 정리
    rm -rf "$tmpdir"

    local result_n=$(ls "$outdir/final_bins/"*.fa 2>/dev/null | wc -l)
    echo "  [$(date +%H:%M:%S)] sample_${i} 완료 → ${result_n} enhanced bins"
}

export -f run_sample
export RESULTS_DIR SING BINETTE THREADS MIN_COMPL WEIGHT

# 병렬 실행
seq 0 20 | xargs -P "$PARALLEL" -I {} bash -c 'run_sample {}'

echo ""
echo "=== [$(date)] 전체 완료! ==="
echo ""

# 결과 요약
echo "--- Enhanced Binette 결과 요약 ---"
for i in $(seq 0 20); do
    outdir="${RESULTS_DIR}/baseline_sample${i}/tmp/binning/round_1/binette_enhanced"
    if [ -d "$outdir/final_bins" ]; then
        n=$(ls "$outdir/final_bins/"*.fa 2>/dev/null | wc -l)
        orig_n=$(ls "${RESULTS_DIR}/baseline_sample${i}/tmp/binning/round_1/binette/final_bins/"*.fa 2>/dev/null | wc -l)
        orig_gz=$(ls "${RESULTS_DIR}/baseline_sample${i}/tmp/binning/round_1/binette/final_bins/"*.fa.gz 2>/dev/null | wc -l)
        orig_total=$((orig_n + orig_gz))
        echo "  sample_${i}: baseline=${orig_total} → enhanced=${n}"
    else
        echo "  sample_${i}: 결과 없음"
    fi
done
