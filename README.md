# Reel Studio — Mac (Apple Silicon)

Faceless reel/short/video factory. Sab local, sab open-source, koi session limit nahi.

| Part | Model | Runs on |
|---|---|---|
| Voice (English) | Qwen3-TTS 1.7B — `instruct` se emotion | Apple GPU (MPS), CPU fallback |
| Voice (Hindi) | Edge-TTS Madhur / Swara | Microsoft online (free), speed only |
| Images | FLUX.2 klein 4B, 4-bit (mflux) — reference image = consistent character | Apple GPU (MLX / Metal) |
| Subtitles | faster-whisper small | CPU |
| Render | moviepy + ffmpeg | CPU |

## Setup (ek baar)
```bash
bash setup.sh
.venv/bin/python make_characters.py   # 6 default characters (ya Characters tab se apne)
bash run.sh                           # http://127.0.0.1:7860
```
Do venv: `.venv` (TTS/whisper/render/UI) + `.venv-mflux` (images) — mflux aur qwen-tts alag transformers chahte hain.

## Create tab (no JSON needed)
1. **Video settings** — project name, visual style (flat cartoon / anime / 3D / realistic / horror / webtoon / watercolor / pixel), size, language, narrator voice, speed, music.
2. **Scenes** — har scene ek card: *Who's in this scene* (`(no character)` = sirf background/b-roll, existing character, ya `+ New character` → naam + look, Run pe isi style mein ban jayega), voice, line, scene/background, how to say it, pause, also-in-frame. ↑ ↓ ⧉ 🗑 se order/duplicate/delete.
3. **ChatGPT se** — accordion mein ready prompt (tumhare characters ke naam ke saath) + JSON import/export.
Library → *Open in editor* se purana video dobara edit karke naya version.

## Tabs
- **Create** — character, language, voice, speed, size preset (Reels 9:16 / YouTube 16:9 / Square / 4:5 / custom), music, script → Run. Progress mein har phase ka time.
- **Characters** — gallery, naya character (description se ya image upload), default voice set, delete.
- **Library** — saare videos, thumbnail, length, kitne second mein bana (tts/images/subs/render), Play, Delete (video + audio + images + subs + metadata sab).
- **Voices** — 9 EN voices × 3 moods + 2 Hindi, pre-built samples (ek baar Build).
- **System** — MPS available? TTS kis device pe chal raha hai, RAM, workspace size.

## Script format
```json
[
  {"line": "...", "instruct": "deadpan, fast", "pause": 0.5, "image_prompt": "..."}
]
```
Multi-character — har line mein optional:
- `"character": "reaper_intern"` — kaun bol raha hai (frame mein woh dikhega)
- `"voice": "Eric"` — is line ki voice (na do toh character ki default voice)
- `"with": ["ghost_therapy"]` — dusra character bhi same frame mein

Hindi: Language = Hindi, `line` Devanagari mein likho (Hinglish roman nahi). `instruct` Hindi mein kaam nahi karta.

## Errors
Progress box mein full traceback + `workspace/logs/last_error.txt`.
