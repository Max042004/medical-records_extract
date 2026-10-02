#!/bin/bash
# Serve JevK5-9B locally. Bound to 127.0.0.1 so record text never leaves this Mac.
# -np 1 / -ub 256 / -cms 64: one slot with frequent context checkpoints, so successive
# questions about the same record reuse the cached record prefix (Qwen3.5 hybrid layers
# cannot reuse a prefix without a checkpoint). ~2.8x faster, same answers.
DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$DIR/bin/llama-b11321/llama-server" \
  -m "$DIR/models/jevk5-9b-v0.3.3-Q5_K_M.gguf" \
  -c 8192 -ngl 99 --host 127.0.0.1 --port 8080 \
  -np 1 -ub 256 -cms 64 -ctxcp 64 -cram 1024
