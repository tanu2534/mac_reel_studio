"""mflux worker — alag venv (.venv-mflux) mein chalta hai. Ek JSON job file leta hai, saari images bana deta hai.
Usage: .venv-mflux/bin/python flux_worker.py jobs.json
jobs.json = {"ref": "characters/x.png" | null, "quantize": 4, "items": [{"prompt": "...", "out": "path.png", "width": 704, "height": 1248, "seed": 7}, ...]}
"""
import sys, json, os
jobs = json.load(open(sys.argv[1]))
items = [j for j in jobs["items"] if not os.path.exists(j["out"])]
if not items:
    print("all cached"); sys.exit(0)
from mflux.models.common.config import ModelConfig
if jobs.get("ref"):
    from mflux.models.flux2.variants import Flux2KleinEdit as M
else:
    from mflux.models.flux2.variants import Flux2Klein as M
model = M(model_config=ModelConfig.flux2_klein_4b(), quantize=int(jobs.get("quantize", 4)))
for j in items:
    kw = dict(seed=j.get("seed", 7), prompt=j["prompt"], num_inference_steps=j.get("steps", 4), width=j["width"], height=j["height"])
    if jobs.get("ref"): kw["image_paths"] = [jobs["ref"]]
    r = model.generate_image(**kw)
    img = r.image if hasattr(r, "image") else r
    os.makedirs(os.path.dirname(j["out"]), exist_ok=True)
    img.save(j["out"]); print("DONE", j["out"], flush=True)
