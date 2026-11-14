"""Default 6 character concepts banao (ek baar). UI ke 'Characters' tab se bhi naye bana sakti ho.
Chalao: .venv/bin/python make_characters.py   (images andar se .venv-mflux worker mein banti hain)"""
import pipeline as P

CONCEPTS = {
    "ghost_therapy":  ("a small round sheet ghost with big tired round eyes and a tiny flat mouth, holding a small notebook and pen, slightly slumped, sarcastic vibe", "Ryan"),
    "reaper_intern":  ("a tiny grim reaper with an oversized hood, two glowing white dot eyes, a bored flat mouth, wearing an office lanyard and holding a paper coffee cup", "Aiden"),
    "black_cat":      ("a small black cat sitting upright, half-closed deadpan yellow eyes, tiny unimpressed mouth, one ear slightly bent", "Serena"),
    "cracked_doll":   ("a small vintage porcelain doll with a visible crack through one eye, fixed polite smile, dark hair, simple dress", "Vivian"),
    "hooded_shadow":  ("a short hooded figure made of shadow, only two large white eyes and a thin white mouth visible inside the hood, long sleeves", "Uncle_Fu"),
    "anxious_candle": ("a small melting candle with a nervous face, wide eyes, wobbly mouth, the flame shaped like a thought bubble above its head", "Dylan"),
}
have = P.characters()
for name, (desc, voice) in CONCEPTS.items():
    if name in have:
        P.save_profile(name, voice=voice, lang="en", desc=desc); print("✓", name, "(exists, profile updated)")
    else:
        P.create_character(name, desc, seed=42, voice=voice); print("✓", name)
print("done ->", P.CHAR_DIR)
