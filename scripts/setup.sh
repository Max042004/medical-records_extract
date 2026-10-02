#!/bin/bash
# Download everything that is not stored in the repository:
#   - MIMIC-IV Clinical Database Demo v2.2 tables (ODbL, PhysioNet)
#   - llama.cpp build b11321 for macOS arm64
#   - JevK5-9B v0.3.3 Q5_K_M GGUF (6.47 GB), verified against its published SHA256
# Then create the Python environment. Needs curl, python3 and poppler (`brew install poppler`).
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p data/mimic-iv-demo
for f in omr patients admissions; do
  curl -fL -o "data/mimic-iv-demo/$f.csv.gz" "https://physionet.org/files/mimic-iv-demo/2.2/hosp/$f.csv.gz"
done

if [ ! -x bin/llama-b11321/llama-server ]; then
  mkdir -p bin
  curl -fL "https://github.com/ggml-org/llama.cpp/releases/download/b11321/llama-b11321-bin-macos-arm64.tar.gz" | tar -xz -C bin
fi

mkdir -p models
MODEL=jevk5-9b-v0.3.3-Q5_K_M.gguf
curl -fL -C - --retry 5 -o "models/$MODEL" "https://huggingface.co/alibiserikbay/JevK5-GGUF/resolve/main/$MODEL"
(cd models && echo "da4a4becd04c3beabd4cefbd09b546ce2648740d923adc8d14ae1d0cb921486e  $MODEL" | shasum -a 256 -c)

python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
