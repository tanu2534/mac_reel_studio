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
PY=$(brew --prefix python@3.12)/bin/python3.12

echo "== 2/4 Main venv (TTS + whisper + render + UI) =="
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q torch torchaudio
.venv/bin/pip install -q qwen-tts "transformers==4.57.3" edge-tts faster-whisper "moviepy==1.0.3" gradio librosa soundfile pillow numpy

echo "== 3/4 Image venv (mflux — alag, kyunki ye naya transformers chahta hai) =="
[ -d .venv-mflux ] || "$PY" -m venv .venv-mflux
.venv-mflux/bin/pip install -q --upgrade pip
.venv-mflux/bin/pip install -q "mflux>=0.16" pillow

echo "== 4/4 Folders =="
mkdir -p workspace/{audio,images,subtitles,videos,music,models} characters

echo
echo "✅ Setup done."
echo "   1) Apne character PNGs (Drive: faceless_finance_pipeline/images/character_concepts/*.png) ko  ./characters/  mein copy karo"
echo "      (ya naye banane ke liye:  .venv-mflux/bin/python make_characters.py)"
echo "   2) Chalao:  bash run.sh    -> browser mein http://127.0.0.1:7860"
echo "   Pehli baar models download honge (FLUX ~4.5GB, Qwen-TTS ~3.5GB, whisper ~500MB)."
