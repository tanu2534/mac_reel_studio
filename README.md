# Reel Studio — Mac (Apple Silicon)

Colab pipeline ka Mac version. Sab local, sab open-source, koi session limit nahi.

- Voice: Qwen3-TTS 1.7B (MPS / CPU)
- Images: FLUX.2 klein 4B, 4-bit via mflux (MLX) — reference image se consistent character
- Subtitles: faster-whisper (CPU)
- Render: moviepy + ffmpeg

## Setup (ek baar, ~15 min)
```bash
cd mac_reel_studio
bash setup.sh
```
Phir apne character PNGs `characters/` mein daalo (Drive → `faceless_finance_pipeline/images/character_concepts/*.png`),
ya naye banao: `source .venv/bin/activate && python make_characters.py`

## Chalao
```bash
bash run.sh
```
Browser khulega → script paste → character → Run. Videos: `workspace/videos/`.
Pehli baar models download honge (~8GB). Pehla reel slow (models load), uske baad ~2–3 min per 4-slide reel.

## Script format (ChatGPT se)
```json
[{"line": "...", "instruct": "deadpan, fast", "pause": 0.5, "image_prompt": "..."}]
```

## Agar kuch toote
- `qwen-tts` MPS pe fail ho → automatically CPU pe chalega (slow par sahi)
- Memory warning → Terminal mein `export MFLUX_LOW_RAM=1` nahi hai; instead `pipeline.py` mein `quantize=4` already hai. Dusre heavy apps band karo (Chrome tabs!)
- `ffmpeg not found` → `brew install ffmpeg`
