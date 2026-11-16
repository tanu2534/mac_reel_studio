"""Reel Studio UI — bash run.sh  ->  http://127.0.0.1:7860"""
import json, glob, os, time, traceback, copy
import gradio as gr
import pipeline as P

NO_CHAR, NEW_CHAR, CHAR_DEFAULT = "(no character)", "+ New character", "(character default)"

def blank_scene(prev=None):
    return {"character": (prev or {}).get("character", NO_CHAR) if (prev or {}).get("character") != NEW_CHAR else NO_CHAR,
            "new_name": "", "new_desc": "", "voice": (prev or {}).get("voice", CHAR_DEFAULT),
            "line": "", "instruct": "", "pause": 0.3, "image_prompt": "", "with": []}

def starter_scenes():
    cs = list(P.characters())
    a = cs[0] if cs else NO_CHAR; b = cs[1] if len(cs) > 1 else a
    return [
        {**blank_scene(), "character": NO_CHAR, "line": "It's 3am. The house is too quiet.", "instruct": "slow whisper, creepy",
         "pause": 0.4, "image_prompt": "dark empty hallway at night, one flickering light, moonlight through window"},
        {**blank_scene(), "character": a, "line": "Doc, I think I'm overthinking.", "instruct": "tired, fast",
         "pause": 0.3, "image_prompt": "lying on a therapy couch, staring at the ceiling"},
        {**blank_scene(), "character": b, "line": "You're dead. That's the least of your problems.", "instruct": "nervous, quick",
         "pause": 0.0, "image_prompt": "sitting in a therapist chair with a clipboard and coffee"},
    ]

# ---------- UI scene <-> pipeline scene ----------
def to_pipeline(sc):
    out = []
    for i, s in enumerate(sc):
        d = {"line": s["line"].strip(), "image_prompt": s["image_prompt"].strip(), "instruct": s.get("instruct", ""),
             "pause": float(s.get("pause") or 0), "voice": None if s.get("voice") == CHAR_DEFAULT else s.get("voice"),
             "with": list(s.get("with") or [])}
        c = s.get("character")
        if c == NEW_CHAR:
            d["character"] = s.get("new_name", "").strip(); d["new_character_desc"] = s.get("new_desc", "").strip()
        elif c in (NO_CHAR, None, ""):
            d["character"] = None
        else:
            d["character"] = c
        out.append(d)
    return out

def from_json(text, default_char):
    data = json.loads(text)
    assert isinstance(data, list), "JSON ek list honi chahiye: [ {...}, {...} ]"
    cs = P.characters()
    # pass 1: naye characters ka look (pehli baar jahan diya ho) — baad ke scenes wahi reuse karenge
    new_desc = {}
    for x in data:
        c = x.get("character")
        if c and c not in cs and P.safe_name(c) not in cs and x.get("new_character_desc"):
            new_desc.setdefault(P.safe_name(c), x["new_character_desc"])
    known = set(cs) | set(new_desc)
    sc = []
    for x in data:
        s = blank_scene(); s.update({"line": x.get("line", ""), "image_prompt": x.get("image_prompt", x.get("scene", "")),
                                     "instruct": x.get("instruct", ""), "pause": x.get("pause", 0.3),
                                     "voice": x.get("voice") or CHAR_DEFAULT,
                                     "with": [P.safe_name(w) for w in (x.get("with") or []) if P.safe_name(w) in known]})
        c = x.get("character", default_char)
        if c in (None, "", "none", NO_CHAR): s["character"] = NO_CHAR
        elif c in cs: s["character"] = c
        elif P.safe_name(c) in cs: s["character"] = P.safe_name(c)
        else:
            n = P.safe_name(c)
            s.update({"character": NEW_CHAR, "new_name": n, "new_desc": x.get("new_character_desc") or new_desc.get(n, "")})
        sc.append(s)
    return sc

def chatgpt_prompt():
    prof = P.load_profiles()
    roster = "\n".join(f"- {n}: {prof.get(n, {}).get('desc', '(no description)')}" for n in P.characters()) or "- (none yet)"
    return f'''You write scripts for 15–30 second faceless reels (dark comedy / horror).
Topic: [WRITE TOPIC HERE]

Existing characters you can use (use the exact name):
{roster}
You may also use NO character (a pure scene / b-roll shot): set "character": null.

Available voices (put one in EVERY scene as "voice"; keep the same voice for the same character; narrator scenes use one narrator voice):
- Male: Ryan (confident, energetic), Aiden (young, friendly), Dylan (young, casual), Eric (calm, good narrator), Uncle_Fu (older, deep, mellow)
- Female: Vivian (bright, young-sounding), Serena (warm, gentle), Ono_Anna (playful, slight Japanese accent), Sohee (soft, slight Korean accent)
Match voice to the character's gender and age. There is no child voice — use Vivian for young girls and add "childlike" to instruct.
You may invent ONE new character: give it a short snake_case name and add "new_character_desc" (look: shape, eyes, mouth, props, vibe).

Rules:
- 5 to 8 scenes. Scene 1 = hook under 8 words. Every line under 12 words. Last scene = punchline or twist + short CTA.
- Written to be SPOKEN fast. At most ONE slow line per script.
- "instruct" = how to say it (emotion + pace), e.g. "fast, panicked", "slow whisper, creepy", "deadpan, bored".
- "pause" = seconds of silence after the line: 0.3 normal, 0.6–0.9 before a punchline, 0 on the last.
- "image_prompt" = what we SEE: setting/background + pose + props + expression, 8–20 words, no text in image.
  Change backgrounds between scenes to keep it visually moving.
- Optional "with": ["other_character"] if two characters share the frame (use rarely).

Output ONLY valid JSON, nothing else:
[
  {{"character": "name_or_null", "voice": "Eric", "line": "...", "instruct": "...", "pause": 0.3, "image_prompt": "..."}}
]'''

def _size(preset, cw, ch):
    s = P.SIZE_PRESETS.get(preset)
    if s: return s
    w, h = int(cw), int(ch); return (max(256, w - w % 2), max(256, h - h % 2))

def run(pid, sc, lang_label, narrator, spd, preset, cw, ch, music, style):
    lang = P.LANGS[lang_label]
    probs = []
    for i, s in enumerate(sc, 1):
        if not s["line"].strip(): probs.append(f"scene {i}: line khali hai")
        if not s["image_prompt"].strip(): probs.append(f"scene {i}: scene/background khali hai")
        if s["character"] == NEW_CHAR and not (s["new_name"].strip() and s["new_desc"].strip()): probs.append(f"scene {i}: new character ka naam + look dono chahiye")
    if not sc: probs.append("koi scene nahi")
    if probs: yield "❌ " + "\n❌ ".join(probs), None, None; return
    script = to_pipeline(sc); last = ""
    try:
        for status, img, vid in P.make_reel(pid, script, narrator, spd, music or None, lang=lang, size=_size(preset, cw, ch), style=style):
            last = status; yield status, img, vid
    except Exception:
        tb = traceback.format_exc(); ep = os.path.join(P.FOLDERS["logs"], "last_error.txt")
        open(ep, "w").write(f"{time.ctime()}\nproject={pid} lang={lang} style={style}\n\n{json.dumps(script, ensure_ascii=False, indent=1)}\n\n{tb}")
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

CSS = """
.scene-card {border:1px solid #3a3a3a; border-radius:10px; padding:10px !important; margin-bottom:10px}
.scene-head {font-weight:700; font-size:16px}
.tiny button {min-width:38px !important; padding:4px 8px !important}
"""

with gr.Blocks(title="Reel Studio") as demo:
    gr.Markdown("## 🎬 Reel Studio (Mac)")
    scenes = gr.State(starter_scenes())
    rev = gr.Number(0, visible=False)

    with gr.Tab("Create"):
        with gr.Row():
            # ---------------- left: video settings + scenes ----------------
            with gr.Column(scale=3):
                with gr.Group():
                    gr.Markdown("### 1 · Video settings")
                    with gr.Row():
                        pid = gr.Textbox(label="Project name", value=f"reel_{time.strftime('%m%d_%H%M')}", scale=2)
                        style = gr.Dropdown(list(P.STYLE_PRESETS), value=list(P.STYLE_PRESETS)[0], label="Visual style", scale=2)
                        preset = gr.Dropdown(list(P.SIZE_PRESETS), value=list(P.SIZE_PRESETS)[0], label="Size", scale=3)
                    with gr.Row(visible=False) as custom_row:
                        cw = gr.Number(value=1080, label="Width", precision=0); ch = gr.Number(value=1920, label="Height", precision=0)
                    with gr.Row():
                        lang = gr.Dropdown(list(P.LANGS), value="English", label="Language", scale=1)
                        narrator = gr.Dropdown(P.SPEAKERS_EN, value="Ryan", label="Narrator voice (no-character scenes)", scale=1)
                        spd = gr.Slider(1.0, 1.4, value=1.2, step=0.05, label="Voice speed", scale=1)
                        music = gr.Dropdown([""] + sorted(glob.glob(f"{P.FOLDERS['music']}/*.mp3")), value="", label="Background music", scale=1)
                    style_hint = gr.Markdown("")

                gr.Markdown("### 2 · Scenes")

                @gr.render(inputs=[scenes, lang], triggers=[rev.change, demo.load])
                def render_scenes(sc, lang_label):
                    code = P.LANGS[lang_label]
                    cs = list(P.characters())
                    char_opts = [NO_CHAR] + cs + [NEW_CHAR]
                    voice_opts = [CHAR_DEFAULT] + P.speakers_for(code)

                    def set_field(state, val, i, key):
                        state = copy.deepcopy(state); state[i][key] = val; return state

                    for i, s in enumerate(sc):
                        with gr.Column(elem_classes="scene-card"):
                            with gr.Row(equal_height=True):
                                gr.Markdown(f"<span class='scene-head'>Scene {i+1}</span>")
                                with gr.Row(elem_classes="tiny"):
                                    b_up = gr.Button("↑", size="sm"); b_dn = gr.Button("↓", size="sm")
                                    b_dup = gr.Button("⧉", size="sm"); b_rm = gr.Button("🗑", size="sm")
                            with gr.Row():
                                c_dd = gr.Dropdown(char_opts, value=s["character"] if s["character"] in char_opts else NO_CHAR,
                                                   interactive=True, label="Who's in this scene", scale=2)
                                v_dd = gr.Dropdown(voice_opts, value=s["voice"] if s["voice"] in voice_opts else CHAR_DEFAULT,
                                                   interactive=True, label="Voice", scale=2)
                                pz = gr.Number(value=s.get("pause", 0.3), interactive=True, label="Pause after (s)", minimum=0, maximum=3, step=0.1, scale=1)
                            if s["character"] == NEW_CHAR:
                                with gr.Row():
                                    nn = gr.Textbox(value=s["new_name"], interactive=True, label="New character name", placeholder="sad_vampire", scale=1)
                                    nd = gr.Textbox(value=s["new_desc"], interactive=True, label="Look (shape, eyes, mouth, props, vibe)", scale=3,
                                                    placeholder="a tiny vampire with an oversized cape, two sleepy red eyes, one small frown, holding a juice box")
                                nn.change(lambda st, v, i=i: set_field(st, v, i, "new_name"), [scenes, nn], scenes, queue=False)
                                nd.change(lambda st, v, i=i: set_field(st, v, i, "new_desc"), [scenes, nd], scenes, queue=False)
                            ln = gr.Textbox(value=s["line"], interactive=True, label="Line (jo bola jayega — subtitle bhi yahi)", lines=1)
                            with gr.Row():
                                sp = gr.Textbox(value=s["image_prompt"], interactive=True, label="Scene / background (kya dikhega)", lines=2, scale=3,
                                                placeholder="rainy rooftop at night, neon signs, character sitting on the edge looking down")
                                if code == "en":
                                    ins = gr.Textbox(value=s.get("instruct", ""), interactive=True, label="How to say it", placeholder="deadpan, fast", scale=1)
                                    ins.change(lambda st, v, i=i: set_field(st, v, i, "instruct"), [scenes, ins], scenes, queue=False)
                            pending_new = sorted({x["new_name"].strip() for x in sc if x["character"] == NEW_CHAR and x["new_name"].strip()})
                            me = s["new_name"].strip() if s["character"] == NEW_CHAR else s["character"]
                            others = [x for x in cs + [n for n in pending_new if n not in cs] if x != me]
                            if others:
                                wf = gr.Dropdown(others, value=[w for w in s.get("with", []) if w in others], multiselect=True,
                                                 interactive=True, label="Also in frame (optional)")
                                wf.change(lambda st, v, i=i: set_field(st, v, i, "with"), [scenes, wf], scenes, queue=False)

                            def on_char(st, v, r, i=i):
                                old = st[i]["character"]; st = set_field(st, v, i, "character")
                                restructure = (old == NEW_CHAR) != (v == NEW_CHAR) or (old == NO_CHAR) != (v == NO_CHAR)
                                return st, (r + 1 if restructure else r)
                            c_dd.change(on_char, [scenes, c_dd, rev], [scenes, rev], queue=False)
                            v_dd.change(lambda st, v, i=i: set_field(st, v, i, "voice"), [scenes, v_dd], scenes, queue=False)
                            pz.change(lambda st, v, i=i: set_field(st, v, i, "pause"), [scenes, pz], scenes, queue=False)
                            ln.change(lambda st, v, i=i: set_field(st, v, i, "line"), [scenes, ln], scenes, queue=False)
                            sp.change(lambda st, v, i=i: set_field(st, v, i, "image_prompt"), [scenes, sp], scenes, queue=False)

                            def mv(st, r, i=i, d=-1):
                                j = i + d
                                if 0 <= j < len(st): st = copy.deepcopy(st); st[i], st[j] = st[j], st[i]
                                return st, r + 1
                            def dup(st, r, i=i):
                                st = copy.deepcopy(st); st.insert(i + 1, copy.deepcopy(st[i])); return st, r + 1
                            def rm(st, r, i=i):
                                st = copy.deepcopy(st); st.pop(i); return st, r + 1
                            b_up.click(lambda st, r, i=i: mv(st, r, i, -1), [scenes, rev], [scenes, rev], queue=False)
                            b_dn.click(lambda st, r, i=i: mv(st, r, i, +1), [scenes, rev], [scenes, rev], queue=False)
                            b_dup.click(dup, [scenes, rev], [scenes, rev], queue=False)
                            b_rm.click(rm, [scenes, rev], [scenes, rev], queue=False)

                with gr.Row():
                    add_btn = gr.Button("➕ Add scene")
                    clear_btn = gr.Button("Clear all", size="sm")
                add_btn.click(lambda st, r: (st + [blank_scene(st[-1] if st else None)], r + 1), [scenes, rev], [scenes, rev], queue=False)
                clear_btn.click(lambda r: ([blank_scene()], r + 1), [rev], [scenes, rev], queue=False)

                with gr.Accordion("📋 ChatGPT se script laao (JSON import / export)", open=False):
                    gr.Markdown("**1.** Ye prompt copy karke ChatGPT mein do (topic badal ke). **2.** Jo JSON mile, neeche paste karke *Load into scenes*. Phir upar cards mein edit kar sakti ho.")
                    gpt = gr.Code(value=chatgpt_prompt(), language="markdown", label="ChatGPT prompt (copy icon top-right)", lines=12)
                    gr.Markdown("#### ⬇ Import — ChatGPT ka JSON yahan paste karo")
                    js = gr.Code(language="json", label="Paste JSON here", lines=12)
                    with gr.Row():
                        imp_default = gr.Dropdown([NO_CHAR] + list(P.characters()), value=NO_CHAR, label="Lines without 'character' →", scale=1)
                        imp_btn = gr.Button("⬇ Load into scenes", variant="primary", scale=2)
                    imp_msg = gr.Markdown("")
                    gr.Markdown("#### ⬆ Export — current scenes ka JSON (backup / ChatGPT ko wapas dene ke liye)")
                    exp_btn = gr.Button("⬆ Export current scenes", size="sm")
                    js_out = gr.Code(language="json", label="Exported JSON (alag box — import wala text safe rehta hai)", lines=8)
                    def do_import(text, dflt, r):
                        if not (text or "").strip(): return gr.update(), r, "❌ pehle upar wale box mein JSON paste karo"
                        try: sc = from_json(text, dflt); return sc, r + 1, f"✅ {len(sc)} scenes loaded — upar Scenes mein dekho"
                        except Exception as e: return gr.update(), r, f"❌ JSON galat hai: {e}"
                    imp_btn.click(do_import, [js, imp_default, rev], [scenes, rev, imp_msg])
                    exp_btn.click(lambda st: json.dumps(to_pipeline(st), ensure_ascii=False, indent=1), scenes, js_out)

                btn = gr.Button("▶ Make video", variant="primary", size="lg")

            # ---------------- right: progress ----------------
            with gr.Column(scale=2):
                log = gr.Textbox(label="Progress / errors / timings", lines=16, max_lines=40)
                prev = gr.Image(label="Latest image", height=300)
                vid = gr.Video(label="Final video", height=460)

        def on_lang(l, st, r):
            code = P.LANGS[l]; opts = P.speakers_for(code)
            st = copy.deepcopy(st)
            for s in st:
                if s["voice"] not in opts: s["voice"] = CHAR_DEFAULT
            return gr.update(choices=opts, value=opts[0]), st, r + 1
        lang.change(on_lang, [lang, scenes, rev], [narrator, scenes, rev])
        preset.change(lambda p: gr.update(visible=P.SIZE_PRESETS.get(p) is None), preset, custom_row)
        style.change(lambda s: "" if s.startswith("Flat") else
                     f"ℹ️ Pehle se bane characters flat-cartoon style ke hain — **{s}** mein unka look thoda badlega. "
                     f"Is style ke liye best: scene mein *+ New character* (Run pe isi style mein banega) ya *(no character)* scenes.", style, style_hint)
        btn.click(run, [pid, scenes, lang, narrator, spd, preset, cw, ch, music, style], [log, prev, vid])

    with gr.Tab("Characters"):
        gr.Markdown("Apne characters — dekho, naye banao (text se ya image upload), default voice set karo, delete karo.")
        ch_html = gr.HTML(value=P.characters_html())
        with gr.Accordion("➕ New character", open=True):
            with gr.Row():
                nc_name = gr.Textbox(label="Name (e.g. sad_vampire)", scale=1)
                nc_style = gr.Dropdown(list(P.STYLE_PRESETS), value=list(P.STYLE_PRESETS)[0], label="Style", scale=1)
                nc_voice = gr.Dropdown(P.SPEAKERS_EN + list(P.SPEAKERS_HI), value="Ryan", label="Default voice", scale=1)
                nc_seed = gr.Number(value=42, label="Seed (dusra look = badlo)", precision=0, scale=1)
            nc_desc = gr.Textbox(label="Look description (English: shape, eyes, mouth, props, vibe)", lines=2,
                                 placeholder="a tiny vampire with oversized cape, two sleepy red eyes, one small frown, holding a juice box, bored vibe")
            nc_btn = gr.Button("✨ Create (~1–2 min)", variant="primary")
        with gr.Accordion("⬆ Upload existing image as character", open=False):
            with gr.Row():
                up_name = gr.Textbox(label="Name"); up_voice = gr.Dropdown(P.SPEAKERS_EN + list(P.SPEAKERS_HI), value="Ryan", label="Default voice")
            up_img = gr.Image(type="filepath", label="Character image (plain background best)")
            up_btn = gr.Button("Add")
        with gr.Row():
            ed_sel = gr.Dropdown(list(P.characters()), label="Character", scale=2)
            ed_voice = gr.Dropdown(P.SPEAKERS_EN + list(P.SPEAKERS_HI), label="Set default voice", scale=2)
            ed_save = gr.Button("💾 Save voice", scale=1)
            ed_del = gr.Button("🗑 Delete character", variant="stop", scale=1)
        ch_msg = gr.Textbox(label="", lines=2)

        def _ch_refresh(msg, r):
            cs = list(P.characters())
            return msg, P.characters_html(), gr.update(choices=cs, value=None), r + 1, chatgpt_prompt(), gr.update(choices=[NO_CHAR] + cs)
        def do_create(n, d, stl, v, sd, r):
            if not n or not d: return _ch_refresh("❌ naam aur description dono chahiye", r)
            try:
                P.create_character(n, d, sd, v, "hi" if v in P.SPEAKERS_HI else "en", stl)
                return _ch_refresh(f"✅ '{P.safe_name(n)}' ban gaya. Pasand nahi? delete karke seed badal ke dobara.", r)
            except Exception as e: return _ch_refresh(f"❌ {e}"[-1500:], r)
        def do_upload(n, img, v, r):
            if not n or not img: return _ch_refresh("❌ naam aur image dono chahiye", r)
            P.add_character_from_image(n, img, v, "hi" if v in P.SPEAKERS_HI else "en"); return _ch_refresh(f"✅ '{P.safe_name(n)}' added", r)
        def do_save_voice(n, v, r):
            if not n: return _ch_refresh("❌ character select karo", r)
            P.save_profile(n, voice=v, lang="hi" if v in P.SPEAKERS_HI else "en"); return _ch_refresh(f"✅ {n} → {v}", r)
        def do_del(n, r):
            if not n: return _ch_refresh("❌ character select karo", r)
            return _ch_refresh(P.delete_character(n), r)
        outs = [ch_msg, ch_html, ed_sel, rev, gpt, imp_default]
        nc_btn.click(do_create, [nc_name, nc_desc, nc_style, nc_voice, nc_seed, rev], outs)
        up_btn.click(do_upload, [up_name, up_img, up_voice, rev], outs)
        ed_save.click(do_save_voice, [ed_sel, ed_voice, rev], outs)
        ed_del.click(do_del, [ed_sel, rev], outs)

    with gr.Tab("Library"):
        gr.Markdown("Saare projects — timings ke saath. Delete = video + audio + images + subtitles + metadata sab hat jaata hai.")
        lib_html = gr.HTML(value=P.library_table())
        with gr.Row():
            lib_sel = gr.Dropdown(lib_choices(), label="Project", scale=3)
            lib_refresh = gr.Button("🔄 Refresh", scale=1)
            lib_play = gr.Button("▶ Play", scale=1)
            lib_load = gr.Button("✏ Open in editor", scale=1)
            lib_del = gr.Button("🗑 Delete (all artifacts)", variant="stop", scale=1)
        lib_vid = gr.Video(label="Preview", height=420)
        lib_msg = gr.Textbox(label="", lines=1)
        def lib_do_refresh(): return P.library_table(), gr.update(choices=lib_choices())
        def lib_do_delete(p):
            if not p: return "koi project select nahi", P.library_table(), gr.update(choices=lib_choices(), value=None), None
            m = P.delete_project(p); return m, P.library_table(), gr.update(choices=lib_choices(), value=None), None
        def lib_open(p, r):
            if not p: return gr.update(), r, "koi project select nahi", gr.update()
            meta = json.load(open(os.path.join(P.FOLDERS["projects"], f"{p}.json")))
            sc = from_json(json.dumps(meta.get("script", [])), NO_CHAR)
            return sc, r + 1, f"✏ '{p}' Create tab mein khul gaya (naya naam do warna overwrite hoga)", f"{p}_v2"
        lib_refresh.click(lib_do_refresh, None, [lib_html, lib_sel])
        lib_play.click(lambda p: P.project_video(p) if p else None, lib_sel, lib_vid)
        lib_load.click(lib_open, [lib_sel, rev], [scenes, rev, lib_msg, pid])
        lib_del.click(lib_do_delete, lib_sel, [lib_msg, lib_html, lib_sel, lib_vid])

    with gr.Tab("Voices"):
        gr.Markdown("9 English voices × 3 moods (Qwen3-TTS, instruct se emotion) + 2 Hindi voices (Edge-TTS, sirf speed). Pehli baar **Build all samples** (~3 min).")
        with gr.Row():
            build_btn = gr.Button("Build all samples (one time)"); build_log = gr.Textbox(label="build log", lines=2)
        samples_html = gr.HTML(value=P.voice_samples_html())
        with gr.Row():
            pv_voice = gr.Dropdown(P.SPEAKERS_EN + list(P.SPEAKERS_HI), value="Ryan", label="Voice")
            pv_text = gr.Textbox(value=P.PREVIEW_LINE, label="Test line"); pv_inst = gr.Textbox(value="deadpan, dry, fast", label="Instruct (EN only)")
            pv_btn = gr.Button("▶ Preview")
        pv_audio = gr.Audio(label="Custom sample", autoplay=True)
        build_btn.click(build_samples, [spd], [build_log, samples_html])
        pv_btn.click(lambda s, i, v, t: P.preview_voice(s, i, v, t, "hi" if s in P.SPEAKERS_HI else "en"), [pv_voice, pv_inst, spd, pv_text], pv_audio)

    with gr.Tab("System"):
        gr.Markdown("Images = MLX → Apple GPU (Metal). TTS = PyTorch MPS (Apple GPU) ya CPU fallback. Whisper = CPU.")
        sys_box = gr.HTML(value=sys_html()); sys_btn = gr.Button("🔄 Refresh")
        sys_btn.click(sys_html, None, sys_box)

    def _on_load():
        cs = list(P.characters())
        return (P.voice_samples_html(), P.library_table(), gr.update(choices=lib_choices()), sys_html(),
                P.characters_html(), gr.update(choices=cs), chatgpt_prompt(), gr.update(choices=[NO_CHAR] + cs))
    demo.load(_on_load, None, [samples_html, lib_html, lib_sel, sys_box, ch_html, ed_sel, gpt, imp_default])

demo.launch(server_name="127.0.0.1", server_port=7860, inbrowser=True, css=CSS, allowed_paths=[P.WS, P.CHAR_DIR])
