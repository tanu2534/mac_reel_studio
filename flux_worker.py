"""mflux worker — alag venv (.venv-mflux) mein chalta hai. Ek JSON job file leta hai, saari images bana deta hai.
Usage: .venv-mflux/bin/python flux_worker.py jobs.json
jobs.json = {"quantize": 4, "items": [{"prompt": "...", "out": "path.png", "width": 704, "height": 1248, "seed": 7, "refs": ["a.png", "b.png"]}, ...]}
refs khali/absent = text-to-image (Flux2Klein); refs diye = reference edit (Flux2KleinEdit, multi-reference ok).
"""
import sys, json, os, gc
jobs = json.load(open(sys.argv[1]))
items = [j for j in jobs["items"] if not os.path.exists(j["out"])]
if not items:
    print("all cached"); sys.exit(0)
from mflux.models.common.config import ModelConfig
q = int(jobs.get("quantize", 4))

def run_group(cls, group):
    model = cls(model_config=ModelConfig.flux2_klein_4b(), quantize=q)
    for j in group:
        kw = dict(seed=j.get("seed", 7), prompt=j["prompt"], num_inference_steps=j.get("steps", 4), width=j["width"], height=j["height"])
        if j.get("refs"): kw["image_paths"] = list(j["refs"])
        r = model.generate_image(**kw)
        img = r.image if hasattr(r, "image") else r
        os.makedirs(os.path.dirname(j["out"]), exist_ok=True)
        img.save(j["out"]); print("DONE", j["out"], flush=True)
    del model; gc.collect()

t2i = [j for j in items if not j.get("refs")]
edit = [j for j in items if j.get("refs")]
if t2i:
    from mflux.models.flux2.variants import Flux2Klein
    run_group(Flux2Klein, t2i)
if edit:
    from mflux.models.flux2.variants import Flux2KleinEdit
    run_group(Flux2KleinEdit, edit)
