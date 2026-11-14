"""
Reel Studio pipeline — Mac (Apple Silicon) edition.
TTS: Qwen3-TTS (EN, MPS/CPU) | Edge-TTS (HI) | Images: FLUX.2 klein 4B via mflux (MLX/Metal, 4-bit)
Subs: faster-whisper (CPU) | Render: moviepy + ffmpeg
"""
import os, gc, json, glob, time, hashlib, tempfile, subprocess, shutil, platform, asyncio
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
if not hasattr(Image, "ANTIALIAS"): Image.ANTIALIAS = Image.LANCZOS   # moviepy 1.0.3 + Pillow 10+ fix

ROOT = os.path.dirname(os.path.abspath(__file__))
WS = os.path.join(ROOT, "workspace")
FOLDERS = {k: os.path.join(WS, k) for k in ["audio", "images", "subtitles", "videos", "music", "models", "projects", "logs"]}
for p in FOLDERS.values(): os.makedirs(p, exist_ok=True)
CHAR_DIR = os.path.join(ROOT, "characters"); os.makedirs(CHAR_DIR, exist_ok=True)
MFLUX_PY = os.path.join(ROOT, ".venv-mflux", "bin", "python")

# ---------------- presets ----------------
SIZE_PRESETS = {
    "Reels / Shorts / TikTok (9:16, 1080x1920)": (1080, 1920),
    "YouTube video (16:9, 1920x1080)": (1920, 1080),
    "Square post (1:1, 1080x1080)": (1080, 1080),
    "Instagram feed (4:5, 1080x1350)": (1080, 1350),
    "Custom (W x H below)": None,
}
def gen_size_for(w, h):
    """FLUX ke liye 16-multiple size, same aspect, ~0.9MP."""
    import math
    ar = w / h; px = 880_000
    gw = int(math.sqrt(px * ar)); gh = int(gw / ar)
    return (gw // 16) * 16, (gh // 16) * 16

LANGS = {"English": "en", "Hindi (हिन्दी)": "hi"}
SPEAKERS_EN = ["Ryan", "Aiden", "Dylan", "Eric", "Serena", "Vivian", "Uncle_Fu", "Ono_Anna", "Sohee"]
SPEAKERS_HI = {"Madhur (male)": "hi-IN-MadhurNeural", "Swara (female)": "hi-IN-SwaraNeural"}
SPEAKERS = SPEAKERS_EN
def speakers_for(lang): return SPEAKERS_EN if lang == "en" else list(SPEAKERS_HI)

STYLE = ("flat 2D vector illustration, thick clean black outlines, muted dark palette with one accent color, "
         "simple shapes, one single character, all facial features only on the head, exactly two eyes and exactly one mouth, "
         "no text, simple dark background")

def get_hash(s: str) -> str: return hashlib.sha256(s.encode()).hexdigest()[:16]
def characters(): return {os.path.basename(p)[:-4]: p for p in sorted(glob.glob(f"{CHAR_DIR}/*.png")) if not os.path.basename(p).startswith("_")}

# ---------------- device / system info ----------------
_DEV = {"tts": "not loaded yet", "images": "MLX (Metal GPU) via mflux", "whisper": "CPU int8"}
def device_info():
    info = {"chip": platform.processor() or platform.machine(), "macOS": platform.mac_ver()[0]}
    try:
        import torch; info["torch"] = torch.__version__; info["mps_available"] = bool(torch.backends.mps.is_available())
    except Exception as e: info["torch"] = f"? {e}"
    try:
        out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout.strip()
        info["RAM_GB"] = round(int(out) / 1e9, 1)
    except Exception: pass
    info.update({f"device_{k}": v for k, v in _DEV.items()})
    info["mflux_venv"] = os.path.exists(MFLUX_PY)
    return info

# ---------------- models (lazy) ----------------
_M = {"tts": None, "wm": None}

def get_tts():
    if _M["tts"] is None:
        import torch
        from qwen_tts import Qwen3TTSModel
        name = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
        try:
            m = Qwen3TTSModel.from_pretrained(name, device_map="mps", dtype=torch.float32, attn_implementation="sdpa"); _DEV["tts"] = "MPS (Apple GPU)"
        except Exception as e:
            print("[tts] MPS failed -> CPU:", str(e)[:150]); _DEV["tts"] = "CPU (MPS failed)"
            m = Qwen3TTSModel.from_pretrained(name, device_map="cpu", dtype=torch.float32, attn_implementation="sdpa")
        _M["tts"] = m
    return _M["tts"]

def free_tts():
    if _M["tts"] is not None:
        _M["tts"] = None; gc.collect()
        try:
            import torch; torch.mps.empty_cache()
        except Exception: pass

def get_wm():
    if _M["wm"] is None:
        from faster_whisper import WhisperModel
        _M["wm"] = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=6, download_root=os.path.join(FOLDERS["models"], "whisper"))
    return _M["wm"]

# ---------------- TTS ----------------
def tts_line(text, lang, speaker, instruct, out_path):
    """Ek line -> wav. EN: Qwen3 (instruct emotion). HI: Edge-TTS (no instruct; Devanagari text)."""
    if lang == "hi":
        import edge_tts
        voice = SPEAKERS_HI.get(speaker, "hi-IN-MadhurNeural")
        mp3 = out_path.replace(".wav", ".mp3")
        async def _go(): await edge_tts.Communicate(text, voice).save(mp3)
        asyncio.run(_go())
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3, out_path]); os.remove(mp3)
    else:
        import soundfile as sf
        wavs, sr = get_tts().generate_custom_voice(text=text, language="English", speaker=speaker, instruct=instruct or None)
        sf.write(out_path, wavs[0], sr)
    return out_path

def speed_up(path, factor):
    if abs(factor - 1.0) < 0.01: return path
    out = path.replace(".wav", f"_x{factor:.2f}.wav")
    if not os.path.exists(out):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-filter:a", f"atempo={factor}", out])
    return out

# ---------------- images ----------------
def run_flux_jobs(ref, items, quantize=4):
    jf = os.path.join(WS, f"_flux_jobs_{int(time.time())}.json")
    json.dump({"ref": ref, "quantize": quantize, "items": items}, open(jf, "w"))
    r = subprocess.run([MFLUX_PY, os.path.join(ROOT, "flux_worker.py"), jf], capture_output=True, text=True)
    os.remove(jf)
    if r.returncode != 0: raise RuntimeError("mflux worker failed:\n" + (r.stderr or "")[-2500:])

def fit_to_canvas(img, w, h):
    bg = img.copy(); s = max(w / bg.width, h / bg.height)
    bg = bg.resize((int(bg.width * s) + 1, int(bg.height * s) + 1), Image.LANCZOS)
    l, t = (bg.width - w) // 2, (bg.height - h) // 2
    bg = bg.crop((l, t, l + w, t + h)).filter(ImageFilter.GaussianBlur(40))
    bg = ImageEnhance.Brightness(bg).enhance(0.55)
    if w >= h:   # landscape / square: height-fit, center
        fg = img.resize((int(img.width * h / img.height), h), Image.LANCZOS); bg.paste(fg, ((w - fg.width) // 2, 0))
    else:        # portrait: width-fit, thoda upar (subtitle ke liye jagah)
        fg = img.resize((w, int(img.height * w / img.width)), Image.LANCZOS); bg.paste(fg, (0, int((h - fg.height) * 0.35)))
    return bg

# ---------------- subtitles ----------------
_FONTS = {
    "en": ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc"],
    "hi": ["/System/Library/Fonts/Supplemental/Kohinoor Devanagari.ttc", "/System/Library/Fonts/Supplemental/Devanagari Sangam MN.ttc",
           "/System/Library/Fonts/Kohinoor.ttc", "/Library/Fonts/NotoSansDevanagari-Bold.ttf"],
}
def font_for(lang):
    for p in _FONTS.get(lang, []) + _FONTS["en"]:
        if os.path.exists(p): return p
    return None

def text_overlay(text, w, h, lang="en", highlight=None):
    fontsize = int(w * 0.088) if h > w else int(h * 0.075)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(img); stroke = max(3, fontsize // 16); max_w = int(w * 0.84)
    fp = font_for(lang)
    def font(sz):
        try: return ImageFont.truetype(fp, sz, index=1) if fp and fp.endswith(".ttc") and lang == "hi" else ImageFont.truetype(fp, sz)
        except Exception:
            try: return ImageFont.truetype(fp, sz)
            except Exception: return ImageFont.load_default()
    def wrap(f):
        lines, cur = [], []
        for word in text.split():
            if d.textbbox((0, 0), " ".join(cur + [word]), font=f, stroke_width=stroke)[2] <= max_w or not cur: cur.append(word)
            else: lines.append(cur); cur = [word]
        if cur: lines.append(cur)
        return lines
    f = font(fontsize); lines = wrap(f)
    while len(lines) > 3 and fontsize > 40: fontsize -= 4; f = font(fontsize); lines = wrap(f)
    line_h = int(fontsize * 1.35); y = int(h * (0.72 if h > w else 0.80)) - line_h * len(lines) // 2
    for line in lines:
        widths = [d.textbbox((0, 0), wd, font=f, stroke_width=stroke)[2] for wd in line]; space = d.textbbox((0, 0), " ", font=f)[2]
        x = (w - (sum(widths) + space * (len(line) - 1))) // 2
        for wd, ww in zip(line, widths):
            color = (255, 220, 0) if highlight and wd.strip(".,?!।") == highlight.strip(".,?!।") else "white"
            d.text((x, y), wd, font=f, fill=color, stroke_width=stroke, stroke_fill="black"); x += ww + space
        y += line_h
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False); img.save(tmp.name); return tmp.name

# ---------------- main ----------------
def make_reel(project_id, character, speaker, speed, script, music_file=None, lang="en", size=(1080, 1920), log=print):
    """Yields (status_text, latest_image_path, video_path_or_None). Timings + metadata -> workspace/projects/<id>.json"""
    W, H = int(size[0]), int(size[1]); FPS = 30
    ref_path = characters()[character]
    project_id = (project_id or "").strip() or f"reel_{int(time.time())}"
    def pdir(k): p = os.path.join(FOLDERS[k], project_id); os.makedirs(p, exist_ok=True); return p
    lines, T = [], {}
    def say(m): lines.append(m); log(m); return "\n".join(lines)
    meta_path = os.path.join(FOLDERS["projects"], f"{project_id}.json")
    meta = {"project_id": project_id, "character": character, "voice": speaker, "lang": lang, "speed": speed, "size": [W, H],
            "slides": len(script), "script": script, "created": time.strftime("%Y-%m-%d %H:%M"), "status": "running"}
    json.dump(meta, open(meta_path, "w"), ensure_ascii=False, indent=1)
    t_all = time.time()
    yield say(f"▶ {project_id} | {character} | {speaker} ({lang}) | {speed}x | {W}x{H} | {len(script)} slides"), None, None

    # 1) TTS
    t0 = time.time(); audio = []
    for i, s in enumerate(script):
        inst = s.get("instruct", ""); p = os.path.join(pdir("audio"), f"s{i:02d}_{get_hash(s['line'] + speaker + inst + lang)}.wav")
        if not os.path.exists(p): tts_line(s["line"], lang, speaker, inst, p)
        audio.append(speed_up(p, float(speed)))
        yield say(f"  🎙 voice {i+1}/{len(script)}"), None, None
    if lang == "en": free_tts()
    T["tts_s"] = round(time.time() - t0, 1)

    # 2) Images
    t0 = time.time(); gw, gh = gen_size_for(W, H); images, jobs = [], []
    for i, s in enumerate(script):
        prompt = f"The same character from the reference image, now {s['image_prompt']}. Keep the exact same character design. {STYLE}"
        p = os.path.join(pdir("images"), f"s{i:02d}_{get_hash(prompt + character + f'{gw}x{gh}')}.png")
        images.append(p)
        if not os.path.exists(p): jobs.append({"prompt": prompt, "out": p.replace(".png", "_raw.png"), "width": gw, "height": gh, "seed": 7})
    if jobs:
        yield say(f"  🖼 generating {len(jobs)} images @ {gw}x{gh} (FLUX on Metal; pehli baar model load ~1 min)..."), None, None
        run_flux_jobs(ref_path, jobs)
        for j in jobs: fit_to_canvas(Image.open(j["out"]).convert("RGB"), W, H).save(j["out"].replace("_raw.png", ".png"))
    T["images_s"] = round(time.time() - t0, 1)
    yield say(f"  🖼 images ready {len(images)}/{len(script)}  ({T['images_s']}s)"), images[-1], None

    # 3) word timestamps
    t0 = time.time(); import librosa; words = []
    for i, ap in enumerate(audio):
        jp = os.path.join(pdir("subtitles"), f"s{i:02d}_{get_hash(os.path.basename(ap))}.json")
        if not os.path.exists(jp):
            a, _ = librosa.load(ap, sr=16000)
            segs, _ = get_wm().transcribe(a, language=lang, word_timestamps=True)
            json.dump([{"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)} for sg in segs for w in (sg.words or [])], open(jp, "w"), ensure_ascii=False)
        words.append(json.load(open(jp)))
    T["whisper_s"] = round(time.time() - t0, 1)
    yield say(f"  ⏱ timestamps done ({T['whisper_s']}s)"), images[-1], None

    # 4) render
    t0 = time.time()
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
                layers.append(ImageClip(text_overlay(s["line"], W, H, lang, highlight=wd["word"])).set_start(wd["start"]).set_end(end))
            if words[i][0]["start"] > 0: layers.append(ImageClip(text_overlay(s["line"], W, H, lang)).set_start(0).set_end(words[i][0]["start"]))
        else:
            layers.append(ImageClip(text_overlay(s["line"], W, H, lang)).set_duration(dur))
        clips.append(CompositeVideoClip(layers, size=(W, H)).set_duration(dur).set_audio(ac))
    final = concatenate_videoclips(clips, method="compose")
    if music_file:
        m = AudioFileClip(music_file)
        m = audio_loop(m, duration=final.duration) if m.duration < final.duration else m.subclip(0, final.duration)
        final = final.set_audio(CompositeAudioClip([final.audio, audio_fadeout(volumex(m, 0.12), 1.5)]))
    out = os.path.join(FOLDERS["videos"], f"{project_id}.mp4")
    yield say("  🎬 rendering..."), images[-1], None
    final.write_videofile(out, fps=FPS, codec="libx264", audio_codec="aac", preset="fast", threads=6, logger=None)
    thumb = os.path.join(FOLDERS["projects"], f"{project_id}.jpg")
    Image.fromarray(final.get_frame(min(1.0, final.duration / 2))).resize((W // 4, H // 4)).save(thumb, quality=80)
    T["render_s"] = round(time.time() - t0, 1); T["total_s"] = round(time.time() - t_all, 1)
    meta.update({"status": "done", "video": out, "thumb": thumb, "duration_s": round(final.duration, 1), "timings": T,
                 "size_kb": os.path.getsize(out) // 1024})
    json.dump(meta, open(meta_path, "w"), ensure_ascii=False, indent=1)
    yield say(f"✅ DONE {final.duration:.1f}s video in {T['total_s']}s  (tts {T['tts_s']}s · images {T['images_s']}s · subs {T['whisper_s']}s · render {T['render_s']}s)\n→ {out}"), images[-1], out

# ---------------- library ----------------
def list_projects():
    rows = []
    for jp in sorted(glob.glob(f"{FOLDERS['projects']}/*.json"), key=os.path.getmtime, reverse=True):
        try: rows.append(json.load(open(jp)))
        except Exception: pass
    return rows

def library_table():
    rows = list_projects()
    if not rows: return "<p>(abhi koi project nahi)</p>"
    h = ["<table style='border-collapse:collapse;width:100%;font-size:14px'><tr><th></th><th style='text-align:left'>Project</th><th>Char</th><th>Voice</th><th>Lang</th><th>Size</th><th>Len</th><th>Made in</th><th>tts/img/subs/render</th><th>Date</th><th>Status</th></tr>"]
    import base64
    for r in rows:
        th = ""
        if r.get("thumb") and os.path.exists(r["thumb"]):
            th = f"<img src='data:image/jpeg;base64,{base64.b64encode(open(r['thumb'],'rb').read()).decode()}' style='height:64px;border-radius:4px'>"
        T = r.get("timings", {})
        tm = f"{T.get('tts_s','-')} / {T.get('images_s','-')} / {T.get('whisper_s','-')} / {T.get('render_s','-')}" if T else "-"
        h.append(f"<tr><td>{th}</td><td><b>{r['project_id']}</b></td><td>{r.get('character','')}</td><td>{r.get('voice','')}</td><td>{r.get('lang','en')}</td>"
                 f"<td>{'x'.join(map(str, r.get('size', [])))}</td><td>{r.get('duration_s','-')}s</td><td><b>{T.get('total_s','-')}s</b></td><td style='font-size:12px'>{tm}</td>"
                 f"<td>{r.get('created','')}</td><td>{'✅' if r.get('status')=='done' else '⚠ ' + r.get('status','')}</td></tr>")
    h.append("</table>")
    return "".join(h)

def project_video(project_id):
    p = os.path.join(FOLDERS["videos"], f"{project_id}.mp4")
    return p if os.path.exists(p) else None

def delete_project(project_id):
    """Video + audio + images + subtitles + metadata + thumb — sab hat jaata hai."""
    n = 0
    for k in ["audio", "images", "subtitles"]:
        d = os.path.join(FOLDERS[k], project_id)
        if os.path.isdir(d): shutil.rmtree(d); n += 1
    for p in [os.path.join(FOLDERS["videos"], f"{project_id}.mp4"), os.path.join(FOLDERS["projects"], f"{project_id}.json"), os.path.join(FOLDERS["projects"], f"{project_id}.jpg")]:
        if os.path.exists(p): os.remove(p); n += 1
    return f"🗑 deleted {project_id} ({n} items)"

def workspace_size():
    tot = 0
    for root, _, files in os.walk(WS):
        for f in files: tot += os.path.getsize(os.path.join(root, f))
    return round(tot / 1e9, 2)

# ---------------- voice samples ----------------
PREVIEW_LINE = "I checked my bank balance at 3am. It checked me back."
PREVIEW_LINE_HI = "मैंने रात तीन बजे अपना बैंक बैलेंस देखा। उसने मुझे वापस घूरा।"
MOODS = {"deadpan_fast": "deadpan, dry, fast", "creepy_whisper": "slow whisper, creepy, close", "cheerful_quick": "cheerful, upbeat, quick, sales pitch"}

def sample_path(speaker, mood, speed=1.2):
    d = os.path.join(FOLDERS["audio"], "_previews"); os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"sample_{speaker}_{mood}_x{float(speed):.2f}.wav")

def preview_voice(speaker, instruct="deadpan, dry, fast", speed=1.2, text=None, lang="en"):
    text = (text or "").strip() or (PREVIEW_LINE_HI if lang == "hi" else PREVIEW_LINE)
    d = os.path.join(FOLDERS["audio"], "_previews"); os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{speaker}_{get_hash(text + instruct + lang)}.wav")
    if not os.path.exists(p): tts_line(text, lang, speaker, instruct, p)
    return speed_up(p, float(speed))

def build_voice_samples_iter(speed=1.2):
    lines = []
    todo = [(s, m, "en") for s in SPEAKERS_EN for m in MOODS] + [(s, "hindi", "hi") for s in SPEAKERS_HI]
    todo = [t for t in todo if not os.path.exists(sample_path(t[0], t[1], speed))]
    if not todo: lines.append("✅ saare samples pehle se bane hain"); yield lines; return
    lines.append(f"TTS model load ho raha hai... ({len(todo)} samples)"); yield lines
    for i, (s, m, lg) in enumerate(todo, 1):
        raw = sample_path(s, m, speed).replace(f"_x{float(speed):.2f}.wav", "_raw.wav")
        if not os.path.exists(raw): tts_line(PREVIEW_LINE_HI if lg == "hi" else PREVIEW_LINE, lg, s, MOODS.get(m, ""), raw)
        out = speed_up(raw, speed)
        if out != sample_path(s, m, speed): os.replace(out, sample_path(s, m, speed))
        lines[-1] = f"[{i}/{len(todo)}] {s} / {m}"; yield lines
    free_tts(); lines.append("✅ done"); yield lines

def voice_samples_html(speed=1.2):
    import base64
    def cell(p):
        if not os.path.exists(p): return "<td style='color:#888'>—</td>"
        return f"<td><audio controls src='data:audio/wav;base64,{base64.b64encode(open(p,'rb').read()).decode()}' style='height:30px;width:180px'></audio></td>"
    rows = ["<table style='border-collapse:collapse;width:100%'><tr><th style='text-align:left'>English (Qwen3)</th>" + "".join(f"<th style='text-align:left'>{m}</th>" for m in MOODS) + "</tr>"]
    missing = 0
    for s in SPEAKERS_EN:
        cells = [cell(sample_path(s, m, speed)) for m in MOODS]; missing += sum("—" in c for c in cells)
        rows.append(f"<tr><td><b>{s}</b></td>{''.join(cells)}</tr>")
    rows.append("<tr><th style='text-align:left;padding-top:10px'>Hindi (Edge-TTS)</th><th colspan=3 style='text-align:left'>same line in Hindi</th></tr>")
    for s in SPEAKERS_HI:
        c = cell(sample_path(s, "hindi", speed)); missing += "—" in c
        rows.append(f"<tr><td><b>{s}</b></td>{c}<td></td><td></td></tr>")
    rows.append("</table>")
    if missing: rows.insert(0, f"<p style='color:#e8a33d'>⚠ {missing} samples nahi bane — 'Build all samples' dabao (ek baar, ~3 min)</p>")
    return "".join(rows)

def list_videos():
    vs = sorted(glob.glob(f"{FOLDERS['videos']}/*.mp4"), key=os.path.getmtime, reverse=True)
    return "\n".join(f"{os.path.basename(v)}  ({os.path.getsize(v)//1024} KB, {time.strftime('%d %b %H:%M', time.localtime(os.path.getmtime(v)))})" for v in vs) or "(koi video nahi)"
