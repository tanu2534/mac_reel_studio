"""Reel Studio UI — bash run.sh  ->  http://127.0.0.1:7860"""
import json, glob, os, time, traceback
import gradio as gr
import pipeline as P

LOG_DIR = os.path.join(P.WS, "logs"); os.makedirs(LOG_DIR, exist_ok=True)

EXAMPLE = json.dumps([
  {"line": "My therapist asked what haunts me. Sir... I am the haunting.", "instruct": "deadpan, dry, fast", "pause": 0.5,
   "image_prompt": "sitting on a therapy couch, arms crossed"},
  {"line": "Follow for more dead-end advice.", "instruct": "cheerful, upbeat, quick", "pause": 0.0,
   "image_prompt": "waving at camera"}], indent=1)

def run(pid, char, spk, spd, script_text, music):
    """Poora pipeline; koi bhi error ho toh FULL traceback Progress box mein + workspace/logs/last_error.txt."""
    try:
        script = json.loads(script_text)
        assert isinstance(script, list) and all("line" in s and "image_prompt" in s for s in script), "har item mein 'line' aur 'image_prompt' chahiye"
    except Exception as e:
        yield f"❌ Script JSON galat hai: {e}", None, None; return
    last = ""
    try:
        for status, img, vid in P.make_reel(pid, char, spk, spd, script, music or None):
            last = status
            yield status, img, vid
    except Exception:
        tb = traceback.format_exc()
        ep = os.path.join(LOG_DIR, "last_error.txt")
        open(ep, "w").write(f"{time.ctime()}\nproject={pid} char={char} voice={spk}\n\n{tb}")
        yield f"{last}\n\n❌ ERROR (saved: {ep})\n\n{tb[-3000:]}", None, None

def build_samples(spd_v):
    lines = []
    def log(m): lines.append(m)
    try:
        for _ in P.build_voice_samples_iter(spd_v):
            yield "\n".join(_), P.voice_samples_html(spd_v)
    except Exception:
        yield "❌ " + traceback.format_exc()[-2000:], P.voice_samples_html(spd_v)

chars = list(P.characters())
with gr.Blocks(title="Reel Studio") as demo:
    gr.Markdown("## 🎬 Reel Studio (Mac) — script paste → character → Run")
    if not chars:
        gr.Markdown("⚠️ `characters/` folder khali hai — Drive se character PNGs copy karo ya `.venv-mflux/bin/python make_characters.py` chalao, phir page refresh.")
    with gr.Row():
        with gr.Column():
            pid = gr.Textbox(label="Project id (filename)", value="reel_001")
            char = gr.Dropdown(chars, value=chars[0] if chars else None, label="Character")
            spk = gr.Dropdown(P.SPEAKERS, value="Ryan", label="Voice")
            spd = gr.Slider(1.0, 1.4, value=1.2, step=0.05, label="Voice speed")
            music = gr.Dropdown([""] + sorted(glob.glob(f"{P.FOLDERS['music']}/*.mp3")), value="", label="Background music (workspace/music/*.mp3)")
            script = gr.Code(value=EXAMPLE, language="json", label="Script JSON (ChatGPT se)", lines=16)
            btn = gr.Button("▶ Run", variant="primary")
        with gr.Column():
            log = gr.Textbox(label="Progress / errors", lines=18, max_lines=40)
            prev = gr.Image(label="Latest image", height=300)
            vid = gr.Video(label="Final video", height=420)

    with gr.Accordion("🔊 Voices — sab samples (9 voices × 3 moods, same line)", open=True):
        gr.Markdown("Pehli baar **Build all samples** dabao (ek baar, ~3 min). Uske baad hamesha ready. Custom line sunni ho toh neeche.")
        with gr.Row():
            build_btn = gr.Button("Build all samples (one time)")
            build_log = gr.Textbox(label="build log", lines=2)
        samples_html = gr.HTML(value=P.voice_samples_html())
        with gr.Row():
            pv_text = gr.Textbox(value=P.PREVIEW_LINE, label="Custom test line")
            pv_inst = gr.Textbox(value="deadpan, dry, fast", label="Instruct")
            pv_btn = gr.Button("▶ Preview selected voice")
        pv_audio = gr.Audio(label="Custom sample", autoplay=True)

    gr.Markdown("### 📁 workspace/videos/")
    lst = gr.Textbox(value=P.list_videos(), lines=8, label="videos")
    rf = gr.Button("🔄 Refresh")

    btn.click(run, [pid, char, spk, spd, script, music], [log, prev, vid]).then(P.list_videos, None, lst)
    rf.click(P.list_videos, None, lst)
    build_btn.click(build_samples, [spd], [build_log, samples_html])
    spd.release(lambda v: P.voice_samples_html(v), [spd], samples_html)
    pv_btn.click(lambda s, i, v, t: P.preview_voice(s, i, v, t), [spk, pv_inst, spd, pv_text], pv_audio)

demo.launch(server_name="127.0.0.1", server_port=7860, inbrowser=True)
