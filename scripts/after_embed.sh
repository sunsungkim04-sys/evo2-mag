#!/bin/bash
# 임베딩 완료 감지 → 클러스터링 → perplexity → PC101 백업
# Usage: nohup bash /workspace/scripts/after_embed.sh &

LAB_SERVER="minseo1101@155.230.164.215"
LAB_PORT=8375
RESULTS=/workspace/results
SCRIPTS=/workspace/scripts

echo "=== [$(date)] embed PID 감시 시작 ==="

# 1) run_embed.py 프로세스가 끝날 때까지 대기
while pgrep -f 'run_embed.py' > /dev/null; do
    sleep 60
done

echo "=== [$(date)] 임베딩 완료 감지! ==="

# 2) 임베딩 파일 존재 확인
if [ ! -f "$RESULTS/contig_embeddings.npz" ]; then
    echo "ERROR: contig_embeddings.npz 없음 — 임베딩이 비정상 종료된 듯"
    exit 1
fi

# 3) HDBSCAN 클러스터링
echo "=== [$(date)] Step 1: HDBSCAN 클러스터링 ==="
python3 -u $SCRIPTS/run_cluster.py \
    --embeddings $RESULTS/contig_embeddings.npz \
    --names $RESULTS/contig_names.txt \
    --data_dir /workspace/data \
    --output_dir $RESULTS
if [ $? -ne 0 ]; then
    echo "ERROR: 클러스터링 실패"
    exit 1
fi
echo "  클러스터링 완료"

# 4) Perplexity 키메라 탐지 (~5-8시간)
echo "=== [$(date)] Step 2: Perplexity 키메라 탐지 ==="
python3 -u $SCRIPTS/run_perplexity.py \
    --data_dir /workspace/data \
    --output_dir $RESULTS \
    --window_size 50000 \
    --step_size 25000 \
    --batch_size 4
if [ $? -ne 0 ]; then
    echo "ERROR: perplexity 실패"
    # perplexity 실패해도 백업은 진행 (resume 지원되므로 재실행 가능)
fi
echo "  perplexity 완료"

# 5) PC101로 전체 백업
echo "=== [$(date)] Step 3: PC101 백업 ==="
scp -P $LAB_PORT $RESULTS/contig_embeddings.npz $LAB_SERVER:~/results/ && echo "  embeddings OK" || echo "  WARNING: embeddings 백업 실패"
scp -P $LAB_PORT $RESULTS/contig_names.txt $LAB_SERVER:~/results/ && echo "  names OK" || echo "  WARNING: names 백업 실패"
scp -P $LAB_PORT $RESULTS/evo2_c2b.tsv $LAB_SERVER:~/results/ && echo "  c2b OK" || echo "  WARNING: c2b 백업 실패"
scp -r -P $LAB_PORT $RESULTS/evo2_bins/ $LAB_SERVER:~/results/ && echo "  bins OK" || echo "  WARNING: bins 백업 실패"
scp -P $LAB_PORT $RESULTS/perplexity_windows.tsv $LAB_SERVER:~/results/ && echo "  perplexity_windows OK" || echo "  WARNING: perplexity_windows 백업 실패"
scp -P $LAB_PORT $RESULTS/chimera_candidates.tsv $LAB_SERVER:~/results/ && echo "  chimera_candidates OK" || echo "  WARNING: chimera_candidates 백업 실패"

echo ""
echo "=== [$(date)] 전체 완료! ==="
echo "  - 임베딩 + 클러스터링 + perplexity + 백업 완료"
echo "  - RunPod 종료해도 됩니다 (PC101 백업 확인 후)"
