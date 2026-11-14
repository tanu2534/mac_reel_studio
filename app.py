"""Reel Studio UI — bash run.sh  ->  http://127.0.0.1:7860"""
import json, glob, os, time, traceback
import gradio as gr
import pipeline as P

EXAMPLE = json.dumps([
  {"line": "My therapist asked what haunts me. Sir... I am the haunting.", "instruct": "deadpan, dry, fast", "pause": 0.5,
   "image_prompt": "sitting on a therapy couch, arms crossed"},
  {"line": "Follow for more dead-end advice.", "instruct": "cheerful, upbeat, quick", "pause": 0.0,
   "image_prompt": "waving at camera"}], indent=1)
EXAMPLE_HI = json.dumps([
  {"line": "थेरेपिस्ट ने पूछा, तुम्हें क्या सताता है? सर... मैं ही सताता हूँ।", "pause": 0.5,
   "image_prompt": "sitting on a therapy couch, arms crossed"},
  {"line": "फॉलो करो, और बेकार सलाह के लिए।", "pause": 0.0, "image_prompt": "waving at camera"}], indent=1, ensure_ascii=False)

def _size(preset, cw, ch):
    s = P.SIZE_PRESETS.get(preset)
    if s: return s
    w, h = int(cw), int(ch)
    return (max(256, w - w % 2), max(256, h - h % 2))

def run(pid, char, lang_label, spk, spd, preset, cw, ch, script_text, music):
    lang = P.LANGS[lang_label]
    try:
        script = json.loads(script_text)
        assert isinstance(script, list) and all("line" in s and "image_prompt" in s for s in script), "har item mein 'line' aur 'image_prompt' chahiye"
    except Exception as e:
        yield f"❌ Script JSON galat hai: {e}", None, None; return
    last = ""
    try:
        for status, img, vid in P.make_reel(pid, char, spk, spd, script, music or None, lang=lang, size=_size(preset, cw, ch)):
            last = status; yield status, img, vid
    except Exception:
        tb = traceback.format_exc(); ep = os.path.join(P.FOLDERS["logs"], "last_error.txt")
        open(ep, "w").write(f"{time.ctime()}\nproject={pid} char={char} voice={spk} lang={lang}\n\n{tb}")
        yield f"{last}\n\n❌ ERROR (saved: {ep})\n\n{tb[-3000:]}", None, None

def build_samples(spd_v):
    try:
        for lines in P.build_voice_samples_iter(spd_v): yield "\n".join(lines[-2:]), P.voice_samples_html(spd_v)
    except Exception:
        yield "❌ " + traceback.format_exc()[-2000:], P.voice_samples_html(spd_v)

def sys_html():
    d = P.device_info()
    rows = "".join(f"<tr><td style='padding:3px 12px 3px 0'><b>{k}</b></td><td>{v}</td></tr>" for k, v in d.items())
    return f"<table>{rows}<tr><td><b>workspace size</b></td><td>{P.workspace_size()} GB</td></tr></table>"

def lib_choices(): return [r["project_id"] for r in P.list_projects()]

chars = list(P.characters())
with gr.Blocks(title="Reel Studio") as demo:
    gr.Markdown("## 🎬 Reel Studio (Mac)")
    if not chars:
        gr.Markdown("⚠️ `characters/` folder khali hai — Drive se character PNGs copy karo ya `.venv-mflux/bin/python make_characters.py`, phir page refresh.")

    with gr.Tab("Create"):
        with gr.Row():
            with gr.Column():
                pid = gr.Textbox(label="Project id (filename)", value=f"reel_{time.strftime('%m%d_%H%M')}")
                char = gr.Dropdown(chars, value=chars[0] if chars else None, label="Character")
                with gr.Row():
                    lang = gr.Dropdown(list(P.LANGS), value="English", label="Language")
                    spk = gr.Dropdown(P.SPEAKERS_EN, value="Ryan", label="Voice")
                spd = gr.Slider(1.0, 1.4, value=1.2, step=0.05, label="Voice speed")
                with gr.Row():
                    preset = gr.Dropdown(list(P.SIZE_PRESETS), value=list(P.SIZE_PRESETS)[0], label="Size preset")
                    cw = gr.Number(value=1080, label="Custom W", precision=0); ch = gr.Number(value=1920, label="Custom H", precision=0)
                music = gr.Dropdown([""] + sorted(glob.glob(f"{P.FOLDERS['music']}/*.mp3")), value="", label="Background music (workspace/music/*.mp3)")
                script = gr.Code(value=EXAMPLE, language="json", label="Script JSON (ChatGPT se)", lines=16)
                btn = gr.Button("▶ Run", variant="primary")
            with gr.Column():
                log = gr.Textbox(label="Progress / errors / timings", lines=18, max_lines=40)
                prev = gr.Image(label="Latest image", height=300)
                vid = gr.Video(label="Final video", height=420)

        def on_lang(l):
            code = P.LANGS[l]; opts = P.speakers_for(code)
            return gr.update(choices=opts, value=opts[0]), gr.update(value=EXAMPLE_HI if code == "hi" else EXAMPLE)
        lang.change(on_lang, lang, [spk, script])
        btn.click(run, [pid, char, lang, spk, spd, preset, cw, ch, script, music], [log, prev, vid])

    with gr.Tab("Library"):
        gr.Markdown("Saare projects — timings ke saath. Delete = video + audio + images + subtitles + metadata sab hat jaata hai.")
        lib_html = gr.HTML(value=P.library_table())
        with gr.Row():
            lib_sel = gr.Dropdown(lib_choices(), label="Project", scale=3)
            lib_refresh = gr.Button("🔄 Refresh", scale=1)
            lib_play = gr.Button("▶ Play", scale=1)
            lib_del = gr.Button("🗑 Delete (all artifacts)", variant="stop", scale=1)
        lib_vid = gr.Video(label="Preview", height=420)
        lib_msg = gr.Textbox(label="", lines=1)
        def lib_do_refresh(): return P.library_table(), gr.update(choices=lib_choices())
        def lib_do_delete(p):
            if not p: return "koi project select nahi", P.library_table(), gr.update(choices=lib_choices(), value=None), None
            m = P.delete_project(p); return m, P.library_table(), gr.update(choices=lib_choices(), value=None), None
        lib_refresh.click(lib_do_refresh, None, [lib_html, lib_sel])
        lib_play.click(lambda p: P.project_video(p) if p else None, lib_sel, lib_vid)
        lib_del.click(lib_do_delete, lib_sel, [lib_msg, lib_html, lib_sel, lib_vid])

    with gr.Tab("Voices"):
        gr.Markdown("9 English voices × 3 moods (Qwen3-TTS, instruct se emotion) + 2 Hindi voices (Edge-TTS, emotion control nahi, sirf speed). Pehli baar **Build all samples** (ek baar, ~3 min).")
        with gr.Row():
            build_btn = gr.Button("Build all samples (one time)"); build_log = gr.Textbox(label="build log", lines=2)
        samples_html = gr.HTML(value=P.voice_samples_html())
        gr.Markdown("**Custom line** — selected language/voice (Create tab se) + apna instruct:")
        with gr.Row():
            pv_text = gr.Textbox(value=P.PREVIEW_LINE, label="Test line"); pv_inst = gr.Textbox(value="deadpan, dry, fast", label="Instruct (EN only)")
            pv_btn = gr.Button("▶ Preview")
        pv_audio = gr.Audio(label="Custom sample", autoplay=True)
        build_btn.click(build_samples, [spd], [build_log, samples_html])
        spd.release(lambda v: P.voice_samples_html(v), [spd], samples_html)
        pv_btn.click(lambda s, i, v, t, l: P.preview_voice(s, i, v, t, P.LANGS[l]), [spk, pv_inst, spd, pv_text, lang], pv_audio)

    with gr.Tab("System"):
        gr.Markdown("Kaunsa hissa kahan chal raha hai. Images = MLX seedha Apple GPU (Metal). TTS = PyTorch MPS (Apple GPU) ya CPU fallback. Whisper = CPU.")
        sys_box = gr.HTML(value=sys_html()); sys_btn = gr.Button("🔄 Refresh")
        sys_btn.click(sys_html, None, sys_box)

    # page load/refresh pe sab dobara scan (pehle static tha — isi liye table '—' dikhati thi)
    demo.load(lambda: (P.voice_samples_html(), P.library_table(), gr.update(choices=lib_choices()), sys_html()), None, [samples_html, lib_html, lib_sel, sys_box])

demo.launch(server_name="127.0.0.1", server_port=7860, inbrowser=True)
