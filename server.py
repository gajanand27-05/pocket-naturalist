"""Pocket Naturalist: an offline field guide powered by Gemma running locally via Ollama.

Run:  python server.py
Then open the printed URL on your phone (same Wi-Fi or phone hotspot; no internet needed).
Snap finds live, or take photos in the garden and add them from your gallery later.
"""
import base64
import datetime
import html
import json
import os
import re
import socket
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
WALKS = ROOT / "walks"
OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("MODEL", "gemma4:12b")
PORT = int(os.environ.get("PORT", "8000"))

IDENTIFY_PROMPT = """You are a careful field naturalist helping someone on a walk outdoors.
Identify the main living thing (plant, bird, insect, fungus, animal) in this photo.
Work like a field guide: first list up to 4 short visible identifying features (a few words each),
then your top 3 candidate species, then pick the best one.
Rules:
- Be honest. Lower the confidence when the candidates look alike. Never invent certainty.
- NEVER say whether anything is safe to eat, touch, or handle.
- If the photo is mainly a person, a poster, artwork, a screen, text, or a man-made object, with no
  plant/animal as the clear subject, set kind to "not_nature". Never identify or describe people.
- Candidate names are plain English common names only. No Latin, no brackets.
- look_closer: one short tip pointing at a detail VISIBLE in this photo that helps tell this species
  apart (e.g. "notice the grey crown and pale cheek"). Describe only what the photo shows; no trivia.
- next_quest: one small, concrete thing to go find OUTSIDE next, inspired by this find
  (e.g. "find a leaf with jagged edges"). Keep it doable within a few minutes of walking.
- how_to_tell: one thing the walker can LOOK FOR on the real organism (flowers, pods, bark, markings,
  call) that separates your top candidates, e.g. "Blue flowers mean A; frilly purple flowers mean B."
  Looking only - never suggest touching, picking, or tasting.
{context}"""

IDENTIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "visible_features": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
        "candidates": {"type": "array", "maxItems": 3, "items": {
            "type": "object",
            "properties": {"common_name": {"type": "string"}},
            "required": ["common_name"]}},
        "best_index": {"type": "integer"},
        "kind": {"type": "string", "enum": ["plant", "bird", "insect", "fungus", "animal", "other", "not_nature"]},
        "confidence": {"type": "number"},
        "look_closer": {"type": "string"},
        "next_quest": {"type": "string"},
        "how_to_tell": {"type": "string"},
    },
    "required": ["visible_features", "candidates", "best_index", "kind", "confidence",
                 "look_closer", "next_quest", "how_to_tell"],
}

SURE = 0.8  # below this, take a second, slower look; still below it -> a "mystery find"

DESCRIBE_PROMPT = """Describe the main living thing in this photo like a field biologist, in 5 short
bullet points. Do NOT name it.
- Plants: leaf type (simple or compound - look closely at whether several leaflets share one stalk),
  leaf/leaflet shape and edges, leaf arrangement, stem, growth habit (vine/climber, shrub, herb, tree),
  flowers or fruit if any.
- Animals: size cues, body shape, colours and markings, beak/bill, legs, wings, posture."""

NAME_PROMPT = """A walker photographed a living thing described by a field biologist as:
{description}
Name the 3 most likely species (plain English common names, no Latin), best first. Base this ONLY on
the described features, and give an honest confidence (0-1) for the best one.
- how_to_tell: one thing the walker can LOOK FOR on the real organism (flowers, pods, bark, markings,
  call) that separates your top candidates, e.g. "Blue flowers mean A; frilly purple flowers mean B."
  Looking only - never suggest touching, picking, or tasting."""

NAME_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": IDENTIFY_SCHEMA["properties"]["candidates"],
        "best_index": {"type": "integer"},
        "confidence": {"type": "number"},
        "how_to_tell": {"type": "string"},
    },
    "required": ["candidates", "best_index", "confidence", "how_to_tell"],
}

JOURNAL_PROMPT = """Write a short nature journal entry about this walk, in second person ("you"):
ONE paragraph of 100-160 words, then one short closing line. No headings, lists, or bullet points.

Make it read like a story, not a log:
- Open with the most striking detail the walker actually noticed (from look_closer / visible_features).
- Connect the finds through those noticed details and the quests, e.g. when a find answered its quest
  (e.g. a spotted leaf turning up right after a quest to find spots), make that a small moment.
  Only claim a quest was answered when that find's own features clearly match it; otherwise just
  say what was found next.
- Mention the same species found twice only once. Vary sentence openings; never write "then you found".
- "mystery": true means it's still unsolved: call it a mystery find, name the guesses, and mention
  the how_to_tell check as something to look for next time.
- "gemma_guessed_wrongly_as" set means Gemma's guess was wrong and the walker named it themselves;
  credit the walker (e.g. "you knew it was a butterfly pea, even though Gemma guessed creeping charlie").
- End with one short line inviting the walker back outside.

Use ONLY the facts in the data below. Do not invent weather, time of day, air, light, paths, trails,
ground, scenery, sounds, smells, feelings, or extra finds. Plain English names only.

Walk started: {started}
Finds (JSON): {finds}"""


def ollama_chat(messages, fmt=None, temperature=0.1):
    body = {"model": MODEL, "stream": False, "think": False, "messages": messages,
            "options": {"temperature": temperature}}
    if fmt:
        body["format"] = fmt
    req = urllib.request.Request(f"{OLLAMA}/api/chat", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)["message"]["content"]


def load_finds(walk_dir):
    f = walk_dir / "finds.json"
    return json.loads(f.read_text("utf-8")) if f.exists() else []


def walk_path(walk_id):
    p = (WALKS / walk_id).resolve()
    if p.parent != WALKS.resolve() or not p.is_dir():
        raise ValueError("unknown walk")
    return p


def start_walk(_):
    walk_id = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    (WALKS / walk_id).mkdir(parents=True)
    return {"walk": walk_id}


def identify(data):
    walk_dir = walk_path(data["walk"])
    if (walk_dir / "journal.html").exists():
        raise ValueError("walk ended")  # the phone starts a fresh walk and retries
    finds = load_finds(walk_dir)
    img = data["image"].split(",", 1)[-1]  # strip data: URL prefix
    photo = f"{len(finds) + 1:02d}.jpg"
    (walk_dir / photo).write_bytes(base64.b64decode(img))

    context = ""
    if data.get("quest"):
        context += f"\nThe walker was on this quest: \"{data['quest']}\". Say nothing about it unless relevant."
    if finds:
        context += "\nAlready found on this walk: " + ", ".join(f["common_name"] for f in finds) + \
                   ". Make the next quest lead somewhere new."
    find = json.loads(ollama_chat(
        [{"role": "user", "content": IDENTIFY_PROMPT.format(context=context), "images": [img]}],
        IDENTIFY_SCHEMA))
    if find.get("kind") == "not_nature":  # posters, screenshots, people: not part of the walk
        (walk_dir / photo).unlink()
        return {"skipped": True,
                "message": "That doesn't look like a plant, bird or bug - skipped it. Try a nature photo!"}
    pick_best(find)
    if find["confidence"] < SURE:
        second_look(find, img)
    # gallery uploads send the time the photo was taken; live snaps use now
    find.update(photo=photo, quest=data.get("quest"), mystery=find["confidence"] < SURE,
                time=data.get("taken") or datetime.datetime.now().strftime("%H:%M"))
    finds.append(find)
    (walk_dir / "finds.json").write_text(json.dumps(finds, indent=2, ensure_ascii=False), "utf-8")
    return find


def pick_best(result):
    """Turn candidates + best_index into common_name / also_could_be, in place."""
    result["confidence"] = max(0.0, min(1.0, float(result.get("confidence", 0))))
    cands = result.pop("candidates") or [{"common_name": "Unknown"}]
    for c in cands:  # the model sometimes adds "(Latin name)" or "'Cultivar'" despite the prompt
        c["common_name"] = re.sub(r"\s*\(.*?\)|\s*'.*?'", "", c["common_name"]).strip() or c["common_name"]
    best = result.pop("best_index", 0)
    best = best if 0 <= best < len(cands) else 0
    result["common_name"] = cands[best]["common_name"]
    result["also_could_be"] = [c["common_name"] for i, c in enumerate(cands) if i != best]


def second_look(find, img):
    """Unsure? Describe the subject's structure first, then name it from that description."""
    description = ollama_chat([{"role": "user", "content": DESCRIBE_PROMPT, "images": [img]}])
    second = json.loads(ollama_chat(
        [{"role": "user", "content": NAME_PROMPT.format(description=description)}], NAME_SCHEMA))
    pick_best(second)
    first_guess = find["common_name"]
    alts = second["also_could_be"] + [first_guess]
    find.update(common_name=second["common_name"], confidence=second["confidence"],
                how_to_tell=second["how_to_tell"],
                also_could_be=[a for a in dict.fromkeys(alts) if a != second["common_name"]],
                first_guess=first_guess, description=description)


def correct(data):
    """The walker knows better: replace the name, keep Gemma's guess for the record."""
    walk_dir = walk_path(data["walk"])
    finds = load_finds(walk_dir)
    name = data["name"].strip()[:80]
    for f in finds:
        if f["photo"] == data["photo"] and name:
            f.setdefault("corrected_from", f["common_name"])
            f.update(common_name=name, mystery=False)
            (walk_dir / "finds.json").write_text(json.dumps(finds, indent=2, ensure_ascii=False), "utf-8")
            return f
    raise ValueError("unknown photo")


def end_walk(data):
    walk_dir = walk_path(data["walk"])
    finds = load_finds(walk_dir)
    if not finds:
        return {"error": "No finds yet - go snap something!"}
    slim = [{k: f.get(k) for k in ("time", "common_name", "also_could_be", "kind", "confidence", "quest",
                                   "visible_features", "look_closer", "mystery", "how_to_tell",
                                   "corrected_from")} for f in finds]
    for f in slim:  # an unambiguous name, so the model doesn't think the walker made the wrong guess
        f["gemma_guessed_wrongly_as"] = f.pop("corrected_from")
    story = ollama_chat([{"role": "user", "content": JOURNAL_PROMPT.format(
        started=f"{walk_dir.name[11:13]}:{walk_dir.name[13:15]}", finds=json.dumps(slim, ensure_ascii=False))}],
        temperature=0.4)
    (walk_dir / "journal.md").write_text(story, "utf-8")
    (walk_dir / "journal.html").write_text(render_journal(walk_dir.name, story, finds), "utf-8")
    return {"journal": f"/walks/{walk_dir.name}/journal.html"}


def render_journal(walk_id, story, finds):
    e = html.escape

    def card(f):
        if f.get("corrected_from"):
            note = f'<small>✏️ You identified it (Gemma guessed: {e(f["corrected_from"])})</small>'
        else:
            note = f'<span>{round(f["confidence"] * 100)}% sure</span>'
        alts = (f"<small>Could also be: {e(', '.join(f['also_could_be']))}</small>"
                if f.get("also_could_be") and not f.get("corrected_from") else "")
        tell = (f"<small>🔍 How to tell: {e(f['how_to_tell'])}</small>"
                if f.get("mystery") and f.get("how_to_tell") else "")
        title = f"Mystery: maybe {f['common_name']}?" if f.get("mystery") else f["common_name"]
        return f"""
  <figure>
    <img src="{e(f['photo'])}" alt="{e(f['common_name'])}" loading="lazy">
    <figcaption><b>{e(title)}</b><span>{e(f['time'])}</span>{note}{alts}{tell}
      <p>{e(f['look_closer'])}</p></figcaption>
  </figure>"""

    solved = "".join(card(f) for f in finds if not f.get("mystery"))
    mystery = "".join(card(f) for f in finds if f.get("mystery"))
    if mystery:
        mystery = (f'<h2>🔍 Mystery finds</h2><p class="date">Still unsolved. Look for the "how to tell" '
                   f'clue next time, or ask someone nearby.</p><section class="finds">{mystery}</section>')
    paras = "".join(f"<p>{e(p)}</p>" for p in story.split("\n") if p.strip())
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Walk {e(walk_id)} · Pocket Naturalist</title>
<link rel="stylesheet" href="/static/journal.css"></head>
<body><main><h1>🌿 Walk journal</h1><p class="date">{e(walk_id.replace('_', ' · '))} · {len(finds)} finds</p>
<section class="story">{paras}</section><section class="finds">{solved}</section>{mystery}
<p class="foot">Identified offline by {e(MODEL)}, running on my own laptop. IDs can be wrong - double-check before relying on them.</p>
</main></body></html>"""


ROUTES = {"/api/walk/start": start_walk, "/api/identify": identify, "/api/correct": correct,
          "/api/walk/end": end_walk}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.path = "/static/index.html"
        if not (self.path.startswith("/static/") or self.path.startswith("/walks/")):
            return self.send_error(404)
        super().do_GET()

    def do_POST(self):
        fn = ROUTES.get(self.path)
        if not fn:
            return self.send_error(404)
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or "{}")
            out, code = fn(data), 200
        except Exception as ex:  # report any failure to the phone instead of hanging
            out, code = {"error": str(ex)}, 500
        body = json.dumps(out, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def lan_ips():
    ips = {i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    return sorted(ip for ip in ips if not ip.startswith("127."))


if __name__ == "__main__":
    WALKS.mkdir(exist_ok=True)
    print(f"🌿 Pocket Naturalist using {MODEL}")
    for ip in lan_ips():
        print(f"   open on your phone: http://{ip}:{PORT}")
    print(f"   or on this laptop:  http://localhost:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
