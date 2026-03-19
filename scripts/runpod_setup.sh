#!/bin/bash
# RunPod H100 SXM 인스턴스 켜자마자 실행할 원스톱 스크립트
# 사용법: bash /workspace/evo2-mag/scripts/runpod_setup.sh
set -e

LAB_SERVER="minseo1101@155.230.164.215"
LAB_PORT=8375
WORKSPACE="/workspace"

echo "=== [$(date)] Step 1: 데이터 수신 (연구실 서버 → RunPod) ==="
mkdir -p $WORKSPACE/data $WORKSPACE/results

# 데이터 + 스크립트 전송 (이미 전송했으면 스킵)
if [ ! -f "$WORKSPACE/data/baseline_sample0/results/baseline_sample0_assembly.fasta" ]; then
    echo "  데이터 전송 중..."
    scp -P $LAB_PORT $LAB_SERVER:~/cami2_baseline_for_runpod.tar.gz $WORKSPACE/
    scp -P $LAB_PORT $LAB_SERVER:~/cami2_contig_bin_all.tsv $WORKSPACE/results/
    cd $WORKSPACE/data && tar xzf $WORKSPACE/cami2_baseline_for_runpod.tar.gz
    echo "  데이터 전송 완료"
else
    echo "  데이터 이미 존재, 스킵"
fi

echo ""
echo "=== [$(date)] Step 2: 환경 설치 ==="
pip install evo2 biopython hdbscan scikit-learn 2>&1 | tail -5

echo ""
echo "=== [$(date)] Step 3: Evo 2 임베딩 추출 ==="
python $WORKSPACE/evo2-mag/scripts/run_embed.py \
    --data_dir $WORKSPACE/data \
    --output_dir $WORKSPACE/results \
    --model evo2_7b \
    --layer blocks.28.mlp.l3

echo ""
echo "=== [$(date)] Step 4: HDBSCAN 클러스터링 ==="
python $WORKSPACE/evo2-mag/scripts/run_cluster.py \
    --embeddings $WORKSPACE/results/contig_embeddings.npz \
    --names $WORKSPACE/results/contig_names.txt \
    --output $WORKSPACE/results/evo2_c2b.tsv

echo ""
echo "=== [$(date)] Step 5: 결과 회수 (RunPod → 연구실 서버) ==="
scp -P $LAB_PORT $WORKSPACE/results/contig_embeddings.npz $LAB_SERVER:~/results/
scp -P $LAB_PORT $WORKSPACE/results/contig_names.txt $LAB_SERVER:~/results/
scp -P $LAB_PORT $WORKSPACE/results/evo2_c2b.tsv $LAB_SERVER:~/results/

echo ""
echo "=== [$(date)] 전체 완료! ==="
echo "결과 파일:"
ls -lh $WORKSPACE/results/contig_embeddings.npz
ls -lh $WORKSPACE/results/evo2_c2b.tsv
echo ""
echo ">>> 이제 RunPod 인스턴스를 종료하세요! <<<"
