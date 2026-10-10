"""Pocket Naturalist: an offline field guide powered by Gemma running locally via Ollama.

Run:  python server.py
Then open the printed URL on your phone (phone hotspot -> laptop joins it; no internet needed).
"""
import base64
import datetime
import html
import json
import os
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
- Candidate names are plain English common names only. No Latin, no brackets.
- look_closer: one short tip pointing at a detail VISIBLE in this photo that helps tell this species
  apart (e.g. "notice the grey crown and pale cheek"). Describe only what the photo shows; no trivia.
- next_quest: one small, concrete thing to go find OUTSIDE next, inspired by this find
  (e.g. "find a leaf with jagged edges"). Keep it doable within a few minutes of walking.
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
        "kind": {"type": "string", "enum": ["plant", "bird", "insect", "fungus", "animal", "other"]},
        "confidence": {"type": "number"},
        "look_closer": {"type": "string"},
        "next_quest": {"type": "string"},
    },
    "required": ["visible_features", "candidates", "best_index", "kind", "confidence",
                 "look_closer", "next_quest"],
}

JOURNAL_PROMPT = """Write a warm, short nature journal entry (120-200 words, plain prose, no headings,
no lists) about this walk, in second person ("you"). Mention the finds in order and how the quests
led from one to the next. Mention uncertainty honestly where confidence was low. End with one line
inviting the walker to go back outside soon.
Use ONLY the facts in the data below. Do not invent weather, light, scenery, sounds, or extra finds.

Walk started: {started}
Finds (JSON): {finds}"""


def ollama_chat(messages, fmt=None):
    body = {"model": MODEL, "stream": False, "think": False, "messages": messages,
            "options": {"temperature": 0.1}}
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
    find["confidence"] = max(0.0, min(1.0, float(find.get("confidence", 0))))
    cands = find.pop("candidates") or [{"common_name": "Unknown"}]
    best = find.pop("best_index", 0)
    best = best if 0 <= best < len(cands) else 0
    find["common_name"] = cands[best]["common_name"]
    find["also_could_be"] = [c["common_name"] for i, c in enumerate(cands) if i != best]
    find.update(photo=photo, quest=data.get("quest"),
                time=datetime.datetime.now().strftime("%H:%M"))
    finds.append(find)
    (walk_dir / "finds.json").write_text(json.dumps(finds, indent=2, ensure_ascii=False), "utf-8")
    return find


def end_walk(data):
    walk_dir = walk_path(data["walk"])
    finds = load_finds(walk_dir)
    if not finds:
        return {"error": "No finds yet - go snap something!"}
    slim = [{k: f[k] for k in ("time", "common_name", "kind", "confidence", "quest")} for f in finds]
    story = ollama_chat([{"role": "user", "content": JOURNAL_PROMPT.format(
        started=f"{walk_dir.name[11:13]}:{walk_dir.name[13:15]}", finds=json.dumps(slim, ensure_ascii=False))}])
    (walk_dir / "journal.md").write_text(story, "utf-8")
    (walk_dir / "journal.html").write_text(render_journal(walk_dir.name, story, finds), "utf-8")
    return {"journal": f"/walks/{walk_dir.name}/journal.html"}


def render_journal(walk_id, story, finds):
    e = html.escape
    cards = "".join(f"""
  <figure>
    <img src="{e(f['photo'])}" alt="{e(f['common_name'])}" loading="lazy">
    <figcaption><b>{e(f['common_name'])}</b>
      <span>{e(f['time'])} · {round(f['confidence'] * 100)}% sure</span>
      {f'<small>Could also be: {e(", ".join(f["also_could_be"]))}</small>' if f.get('also_could_be') else ''}
      {f'<small>Quest: {e(f["quest"])}</small>' if f.get('quest') else ''}
      <p>{e(f['look_closer'])}</p></figcaption>
  </figure>""" for f in finds)
    paras = "".join(f"<p>{e(p)}</p>" for p in story.split("\n") if p.strip())
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Walk {e(walk_id)} · Pocket Naturalist</title>
<link rel="stylesheet" href="/static/journal.css"></head>
<body><main><h1>🌿 Walk journal</h1><p class="date">{e(walk_id.replace('_', ' · '))} · {len(finds)} finds</p>
<section class="story">{paras}</section><section class="finds">{cards}</section>
<p class="foot">Identified offline by {e(MODEL)} on a laptop in a backpack. IDs can be wrong - double-check before relying on them.</p>
</main></body></html>"""


ROUTES = {"/api/walk/start": start_walk, "/api/identify": identify, "/api/walk/end": end_walk}


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
