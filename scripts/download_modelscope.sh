#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
MODEL_ROOT="${HISTORY_TTS_MODEL_ROOT:-$HOME/.cache/history-tts/modelscope}"
.venv/bin/modelscope download Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign --local-dir "$MODEL_ROOT/design" --max-workers 3
.venv/bin/python scripts/verify_models.py design "$MODEL_ROOT/design"
.venv/bin/modelscope download Qwen/Qwen3-TTS-12Hz-0.6B-Base --local-dir "$MODEL_ROOT/base" --max-workers 3
.venv/bin/python scripts/verify_models.py base "$MODEL_ROOT/base"
