#!/bin/bash
# Reel Studio — Mac setup (Apple Silicon). Ek baar chalao:  bash setup.sh
set -e
cd "$(dirname "$0")"

echo "== 1/4 Homebrew packages (ffmpeg, python 3.12) =="
if ! command -v brew >/dev/null; then
  echo "Homebrew nahi mila. Pehle install karo: https://brew.sh  (phir dobara bash setup.sh)"; exit 1
fi
brew list ffmpeg >/dev/null 2>&1 || brew install ffmpeg
brew list python@3.12 >/dev/null 2>&1 || brew install python@3.12

echo "== 2/4 Python venv =="
PY=$(brew --prefix python@3.12)/bin/python3.12
[ -d .venv ] || "$PY" -m venv .venv
source .venv/bin/activate
pip install -q --upgrade pip

echo "== 3/4 Python packages (5-10 min, ~3GB) =="
pip install -q torch torchaudio
pip install -q "mflux>=0.16" qwen-tts "transformers==4.57.3" faster-whisper "moviepy==1.0.3" gradio librosa soundfile pillow numpy

echo "== 4/4 Folders =="
mkdir -p workspace/{audio,images,subtitles,videos,music,models} characters

echo
echo "✅ Setup done."
echo "   1) Apne 6 character PNGs (Drive: faceless_finance_pipeline/images/character_concepts/*.png) ko  ./characters/  mein copy karo"
echo "      (ya naye banane ke liye:  source .venv/bin/activate && python make_characters.py)"
echo "   2) Chalao:  bash run.sh    -> browser mein http://127.0.0.1:7860"
echo "   Pehli baar models download honge (FLUX ~4.5GB, Qwen-TTS ~3.5GB, whisper ~500MB)."
