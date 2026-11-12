"""Naye character concepts banao (FLUX.2 klein 4B, mflux). Output: characters/<name>.png + characters/_sheet.png
Chalao: source .venv/bin/activate && python make_characters.py
Apne concepts CONCEPTS dict mein badlo/jodo."""
import os
from PIL import Image, ImageDraw, ImageFont
from mflux.models.common.config import ModelConfig
from mflux.models.flux2.variants import Flux2Klein

ROOT = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(ROOT, "characters"); os.makedirs(OUT, exist_ok=True)
STYLE = ("flat 2D vector illustration, thick clean black outlines, muted dark palette with one accent color, "
         "simple shapes, one single character, exactly two eyes and exactly one mouth on the head, "
         "no text, plain dark background, character design sheet, front view, full body")
CONCEPTS = {
    "ghost_therapy":  "a small round sheet ghost with big tired round eyes and a tiny flat mouth, holding a small notebook and pen, slightly slumped, sarcastic vibe",
    "reaper_intern":  "a tiny grim reaper with an oversized hood, two glowing white dot eyes, a bored flat mouth, wearing an office lanyard and holding a paper coffee cup",
    "black_cat":      "a small black cat sitting upright, half-closed deadpan yellow eyes, tiny unimpressed mouth, one ear slightly bent",
    "cracked_doll":   "a small vintage porcelain doll with a visible crack through one eye, fixed polite smile, dark hair, simple dress",
    "hooded_shadow":  "a short hooded figure made of shadow, only two large white eyes and a thin white mouth visible inside the hood, long sleeves",
    "anxious_candle": "a small melting candle with a nervous face, wide eyes, wobbly mouth, the flame shaped like a thought bubble above its head",
}

flux = Flux2Klein(model_config=ModelConfig.flux2_klein_4b(), quantize=4)
tiles = []
for name, desc in CONCEPTS.items():
    p = os.path.join(OUT, f"{name}.png")
    if not os.path.exists(p):
        r = flux.generate_image(seed=42, prompt=f"{desc}, {STYLE}", num_inference_steps=4, width=768, height=1024)
        (r.image if hasattr(r, "image") else r).save(p); print("✓", name)
    t = Image.open(p).convert("RGB").resize((384, 512)); d = ImageDraw.Draw(t)
    d.rectangle([0, 0, 384, 44], fill=(0, 0, 0)); d.text((10, 10), name, fill="white"); tiles.append(t)
sheet = Image.new("RGB", (384 * 3, 512 * ((len(tiles) + 2) // 3)))
for i, t in enumerate(tiles): sheet.paste(t, ((i % 3) * 384, (i // 3) * 512))
sheet.save(os.path.join(OUT, "_sheet.png")); print("sheet:", os.path.join(OUT, "_sheet.png"))
