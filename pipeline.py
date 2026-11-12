"""
Reel pipeline — Mac (Apple Silicon) edition.
TTS: Qwen3-TTS (MPS, CPU fallback) | Images: FLUX.2 klein 4B via mflux (MLX, 4-bit) | Subs: faster-whisper (CPU) | Render: moviepy
"""
import os, gc, json, glob, time, hashlib, tempfile, subprocess
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

ROOT = os.path.dirname(os.path.abspath(__file__))
WS = os.path.join(ROOT, "workspace")
FOLDERS = {k: os.path.join(WS, k) for k in ["audio", "images", "subtitles", "videos", "music", "models"]}
for p in FOLDERS.values(): os.makedirs(p, exist_ok=True)
CHAR_DIR = os.path.join(ROOT, "characters"); os.makedirs(CHAR_DIR, exist_ok=True)

W, H, FPS = 1080, 1920, 30
SPEAKERS = ["Ryan", "Aiden", "Dylan", "Eric", "Serena", "Vivian", "Uncle_Fu", "Ono_Anna", "Sohee"]
STYLE = ("flat 2D vector illustration, thick clean black outlines, muted dark palette with one accent color, "
         "simple shapes, one single character, all facial features only on the head, exactly two eyes and exactly one mouth, "
         "no text, simple dark background")

def get_hash(s: str) -> str: return hashlib.sha256(s.encode()).hexdigest()[:16]
def characters(): return {os.path.basename(p)[:-4]: p for p in sorted(glob.glob(f"{CHAR_DIR}/*.png")) if not os.path.basename(p).startswith("_")}

# ---------------- models (lazy, cached) ----------------
_M = {"tts": None, "wm": None}

def get_tts():
    if _M["tts"] is None:
        import torch
        from qwen_tts import Qwen3TTSModel
        name = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
        try:
            m = Qwen3TTSModel.from_pretrained(name, device_map="mps", dtype=torch.float32, attn_implementation="sdpa")
            print("[tts] MPS")
        except Exception as e:
            print("[tts] MPS failed, CPU fallback:", str(e)[:120])
            m = Qwen3TTSModel.from_pretrained(name, device_map="cpu", dtype=torch.float32, attn_implementation="sdpa")
        _M["tts"] = m
    return _M["tts"]

def free_tts():
    if _M["tts"] is not None:
        _M["tts"] = None; gc.collect()
        try:
            import torch; torch.mps.empty_cache()
        except Exception: pass

MFLUX_PY = os.path.join(ROOT, ".venv-mflux", "bin", "python")
def run_flux_jobs(ref, items, quantize=4):
    """Images alag venv (.venv-mflux) mein banti hain — worker ko ek JSON job do, woh sab bana deta hai."""
    jf = os.path.join(WS, f"_flux_jobs_{int(time.time())}.json")
    json.dump({"ref": ref, "quantize": quantize, "items": items}, open(jf, "w"))
    r = subprocess.run([MFLUX_PY, os.path.join(ROOT, "flux_worker.py"), jf], capture_output=True, text=True)
    os.remove(jf)
    if r.returncode != 0:
        raise RuntimeError("mflux worker failed:\n" + (r.stderr or "")[-2000:])

def get_wm():
    if _M["wm"] is None:
        from faster_whisper import WhisperModel
        _M["wm"] = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=6, download_root=os.path.join(FOLDERS["models"], "whisper"))
    return _M["wm"]

# ---------------- helpers ----------------
def speed_up(path, factor):
    if abs(factor - 1.0) < 0.01: return path
    out = path.replace(".wav", f"_x{factor:.2f}.wav")
    if not os.path.exists(out):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-filter:a", f"atempo={factor}", out])
    return out

def fit_to_canvas(img, w, h):
    bg = img.copy(); s = max(w / bg.width, h / bg.height)
    bg = bg.resize((int(bg.width * s) + 1, int(bg.height * s) + 1), Image.LANCZOS)
    l, t = (bg.width - w) // 2, (bg.height - h) // 2
    bg = bg.crop((l, t, l + w, t + h)).filter(ImageFilter.GaussianBlur(40))
    bg = ImageEnhance.Brightness(bg).enhance(0.55)
    fg = img.resize((w, int(img.height * w / img.width)), Image.LANCZOS)
    bg.paste(fg, (0, int((h - fg.height) * 0.35))); return bg

_FONTS = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc",
          "/Library/Fonts/Arial Bold.ttf", "/System/Library/Fonts/SFCompact.ttf"]
FONT_PATH = next((p for p in _FONTS if os.path.exists(p)), None)

def text_overlay(text, w, h, fontsize=95, highlight=None):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(img); stroke = 6; max_w = int(w * 0.84)
    def font(sz):
        try: return ImageFont.truetype(FONT_PATH, sz)
        except Exception: return ImageFont.load_default()
    def wrap(f):
        lines, cur = [], []
        for word in text.split():
            if d.textbbox((0, 0), " ".join(cur + [word]), font=f, stroke_width=stroke)[2] <= max_w or not cur: cur.append(word)
            else: lines.append(cur); cur = [word]
        if cur: lines.append(cur)
        return lines
    f = font(fontsize); lines = wrap(f)
    while len(lines) > 3 and fontsize > 50: fontsize -= 5; f = font(fontsize); lines = wrap(f)
    line_h = int(fontsize * 1.3); y = int(h * 0.72) - line_h * len(lines) // 2
    for line in lines:
        widths = [d.textbbox((0, 0), wd, font=f, stroke_width=stroke)[2] for wd in line]; space = d.textbbox((0, 0), " ", font=f)[2]
        x = (w - (sum(widths) + space * (len(line) - 1))) // 2
        for wd, ww in zip(line, widths):
            color = (255, 220, 0) if highlight and wd.strip(".,?!") == highlight.strip(".,?!") else "white"
            d.text((x, y), wd, font=f, fill=color, stroke_width=stroke, stroke_fill="black"); x += ww + space
        y += line_h
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False); img.save(tmp.name); return tmp.name

# ---------------- main generator ----------------
def make_reel(project_id, character, speaker, speed, script, music_file=None, log=print):
    """Yields (status_text, latest_image_path, video_path_or_None)."""
    chars = characters()
    ref_path = chars[character]
    project_id = (project_id or "").strip() or f"reel_{int(time.time())}"
    def pdir(k): p = os.path.join(FOLDERS[k], project_id); os.makedirs(p, exist_ok=True); return p
    lines = []
    def say(m): lines.append(m); log(m); return "\n".join(lines)
    yield say(f"▶ {project_id} | {character} | {speaker} | {speed}x | {len(script)} slides"), None, None

    # 1) TTS
    import soundfile as sf
    audio = []
    for i, s in enumerate(script):
        inst = s.get("instruct", ""); p = os.path.join(pdir("audio"), f"s{i:02d}_{get_hash(s['line'] + speaker + inst)}.wav")
        if not os.path.exists(p):
            wavs, sr = get_tts().generate_custom_voice(text=s["line"], language="English", speaker=speaker, instruct=inst or None)
            sf.write(p, wavs[0], sr)
        audio.append(speed_up(p, float(speed)))
        yield say(f"  🎙 voice {i+1}/{len(script)}"), None, None
    free_tts()

    # 2) Images (mflux worker in .venv-mflux, reference = character png)
    images, jobs = [], []
    for i, s in enumerate(script):
        prompt = f"The same character from the reference image, now {s['image_prompt']}. Keep the exact same character design. {STYLE}"
        p = os.path.join(pdir("images"), f"s{i:02d}_{get_hash(prompt + character)}.png")
        images.append(p)
        if not os.path.exists(p):
            jobs.append({"prompt": prompt, "out": p.replace(".png", "_raw.png"), "width": 704, "height": 1248, "seed": 7})
    if jobs:
        yield say(f"  🖼 generating {len(jobs)} images (FLUX, pehli baar model load ~1 min)..."), None, None
        run_flux_jobs(ref_path, jobs)
        for j in jobs:
            fit_to_canvas(Image.open(j["out"]).convert("RGB"), W, H).save(j["out"].replace("_raw.png", ".png"))
    yield say(f"  🖼 images ready {len(images)}/{len(script)}"), images[-1], None

    # 3) word timestamps
    import librosa
    words = []
    for i, ap in enumerate(audio):
        jp = os.path.join(pdir("subtitles"), f"s{i:02d}_{get_hash(os.path.basename(ap))}.json")
        if not os.path.exists(jp):
            a, _ = librosa.load(ap, sr=16000)
            segs, _ = get_wm().transcribe(a, language="en", word_timestamps=True)
            json.dump([{"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)} for sg in segs for w in (sg.words or [])], open(jp, "w"))
        words.append(json.load(open(jp)))
    yield say("  ⏱ timestamps done"), images[-1], None

    # 4) render
    from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, CompositeAudioClip, concatenate_videoclips
    from moviepy.audio.fx.all import audio_loop, audio_fadeout, volumex
    clips = []
    for i, s in enumerate(script):
        ac = AudioFileClip(audio[i]); dur = ac.duration + float(s.get("pause", 0))
        base = ImageClip(images[i]).set_duration(dur).resize((W, H)).resize(lambda t, d=dur: 1 + 0.04 * t / d).set_position("center")
        layers = [base]
        if words[i]:
            for k, wd in enumerate(words[i]):
                end = words[i][k + 1]["start"] if k + 1 < len(words[i]) else dur
                layers.append(ImageClip(text_overlay(s["line"], W, H, highlight=wd["word"])).set_start(wd["start"]).set_end(end))
            if words[i][0]["start"] > 0: layers.append(ImageClip(text_overlay(s["line"], W, H)).set_start(0).set_end(words[i][0]["start"]))
        else:
            layers.append(ImageClip(text_overlay(s["line"], W, H)).set_duration(dur))
        clips.append(CompositeVideoClip(layers, size=(W, H)).set_duration(dur).set_audio(ac))
    final = concatenate_videoclips(clips, method="compose")
    if music_file:
        m = AudioFileClip(music_file)
        m = audio_loop(m, duration=final.duration) if m.duration < final.duration else m.subclip(0, final.duration)
        final = final.set_audio(CompositeAudioClip([final.audio, audio_fadeout(volumex(m, 0.12), 1.5)]))
    out = os.path.join(FOLDERS["videos"], f"{project_id}.mp4")
    yield say("  🎬 rendering..."), images[-1], None
    final.write_videofile(out, fps=FPS, codec="libx264", audio_codec="aac", preset="fast", threads=6, logger=None)
    yield say(f"✅ DONE {final.duration:.1f}s → {out}"), images[-1], out

def list_videos():
    vs = sorted(glob.glob(f"{FOLDERS['videos']}/*.mp4"), key=os.path.getmtime, reverse=True)
    return "\n".join(f"{os.path.basename(v)}  ({os.path.getsize(v)//1024} KB, {time.strftime('%d %b %H:%M', time.localtime(os.path.getmtime(v)))})" for v in vs) or "(koi video nahi)"
