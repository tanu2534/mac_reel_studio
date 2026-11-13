"""Reel Studio UI — bash run.sh  ->  http://127.0.0.1:7860"""
import json, glob, os
import gradio as gr
import pipeline as P

EXAMPLE = json.dumps([
  {"line": "My therapist asked what haunts me. Sir... I am the haunting.", "instruct": "deadpan, dry, fast", "pause": 0.5,
   "image_prompt": "sitting on a therapy couch, arms crossed"},
  {"line": "Follow for more dead-end advice.", "instruct": "cheerful, upbeat, quick", "pause": 0.0,
   "image_prompt": "waving at camera"}], indent=1)

def run(pid, char, spk, spd, script_text, music):
    try:
        script = json.loads(script_text)
        assert isinstance(script, list) and all("line" in s and "image_prompt" in s for s in script)
    except Exception as e:
        yield f"❌ Script JSON galat hai: {e}", None, None; return
    yield from P.make_reel(pid, char, spk, spd, script, music or None)

chars = list(P.characters())
with gr.Blocks(title="Reel Studio") as demo:
    gr.Markdown("## 🎬 Reel Studio (Mac) — script paste → character → Run")
    if not chars:
        gr.Markdown("⚠️ `characters/` folder khali hai — Drive se character PNGs copy karo ya `python make_characters.py` chalao, phir page refresh.")
    with gr.Row():
        with gr.Column():
            pid = gr.Textbox(label="Project id (filename)", value="reel_001")
            char = gr.Dropdown(chars, value=chars[0] if chars else None, label="Character")
            spk = gr.Dropdown(P.SPEAKERS, value="Ryan", label="Voice")
            spd = gr.Slider(1.0, 1.4, value=1.2, step=0.05, label="Voice speed")
            with gr.Accordion("🔊 Voice preview", open=True):
                pv_text = gr.Textbox(value=P.PREVIEW_LINE, label="Test line")
                pv_inst = gr.Textbox(value="deadpan, dry, fast", label="Instruct (emotion + pace)")
                with gr.Row():
                    pv_btn = gr.Button("▶ Preview this voice")
                    pv_all = gr.Button("Preview all 9 voices")
                pv_audio = gr.Audio(label="Sample", autoplay=True)
                pv_gallery = gr.HTML()
            music = gr.Dropdown([""] + sorted(glob.glob(f"{P.FOLDERS['music']}/*.mp3")), value="", label="Background music (workspace/music/*.mp3)")
            script = gr.Code(value=EXAMPLE, language="json", label="Script JSON (ChatGPT se)", lines=16)
            btn = gr.Button("▶ Run", variant="primary")
        with gr.Column():
            log = gr.Textbox(label="Progress", lines=14)
            prev = gr.Image(label="Latest image", height=300)
            vid = gr.Video(label="Final video", height=420)
    gr.Markdown("### 📁 workspace/videos/")
    lst = gr.Textbox(value=P.list_videos(), lines=8, label="videos")
    rf = gr.Button("🔄 Refresh")
    btn.click(run, [pid, char, spk, spd, script, music], [log, prev, vid]).then(P.list_videos, None, lst)
    rf.click(P.list_videos, None, lst)

    def preview_one(speaker, inst, spd_v, text):
        return P.preview_voice(speaker, inst, spd_v, text)

    def preview_all(inst, spd_v, text):
        import base64
        rows = []
        for s in P.SPEAKERS:
            p = P.preview_voice(s, inst, spd_v, text)
            b64 = base64.b64encode(open(p, "rb").read()).decode()
            rows.append(f'<div style="margin:6px 0"><b style="display:inline-block;width:90px">{s}</b>'
                        f'<audio controls src="data:audio/wav;base64,{b64}" style="height:32px;vertical-align:middle"></audio></div>')
        return "".join(rows)

    pv_btn.click(preview_one, [spk, pv_inst, spd, pv_text], pv_audio)
    pv_all.click(preview_all, [pv_inst, spd, pv_text], pv_gallery)

demo.launch(server_name="127.0.0.1", server_port=7860, inbrowser=True)
