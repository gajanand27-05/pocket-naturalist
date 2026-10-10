# 🌿 Pocket Naturalist

An offline field guide for walks. Snap a plant, bird or bug on your phone. **Gemma 4**, running on a laptop in your backpack, tells you what it probably is, what to look at more closely, and gives you a small quest to find next. When you finish, it writes a journal of your walk.

You don't need mobile signal, a cloud API or an account. Your photos never leave your own devices.

Built for the [Hacktoberfest 2026 Open-Source AI Challenge, Week 1: "Touch Grass"](https://dev.to/challenges/hacktoberfest-week1-2026-10-05).

## How it works

```
phone (browser) ──same Wi-Fi or hotspot, no internet──▶ laptop: server.py ──▶ Ollama ──▶ gemma4:12b (vision)
```

1. **Start a walk.** You get your first quest, read aloud by the phone's built-in offline voice.
2. **📷 Snap a find**, or **🖼️ add photos from your gallery** later. You don't have to carry the laptop: take photos in the garden with your normal camera, then add them at home. The journal uses each photo's own capture time.
3. Gemma lists the features it can see, ranks its top 3 guesses, picks one, and gives a "look closer" tip plus your next quest.
4. **Not sure? It looks again.** Below 80% confidence, Gemma describes the subject's structure first (simple or compound leaves, growth habit, markings) and then names it from that description.
5. **Still not sure? It becomes a 🔍 Mystery find.** Instead of guessing, it gives you **one thing to check on the real plant** that would separate its guesses ("blue flowers mean butterfly pea…"). That sends you back outside instead of back to the screen.
6. **✏️ I know what this is.** If you know better, correct it. The journal credits you and records what Gemma guessed.
7. **End walk.** Gemma writes a short journal using only what you actually found, with unsolved mystery finds in their own section. It's saved to `walks/<date>/journal.html` with your photos.

## Run it

Requirements: Python 3.10+ and [Ollama](https://ollama.com). No pip packages are needed.

```bash
ollama pull gemma4:12b
python server.py
```

It prints a `http://<laptop-ip>:8000` address. Then:

1. Turn on your **phone's hotspot** and connect the laptop to it.
2. Open the printed address in the phone's browser.
3. Put the laptop in your bag and go outside.

On Windows, allow Python through the firewall for that network the first time.

Settings, all optional: `MODEL=qwen2.5vl:3b` (any Ollama vision model), `OLLAMA_URL`, `PORT`.

## Honest limitations

- **Gemma's self-rated confidence varies.** The same vine photo scored 75% on one run and 85% on the next, so it doesn't always trigger the second look. On my first real walk, Gemma got 6 of 7 plants right and called a butterfly pea vine "Creeping Charlie". Checking the real vine for blue flowers solved it, which is the reason the "how to tell" and "I know it" features exist.
- **Birds are hard for a 12B model.** In testing, a female house sparrow was confidently called a "Jungle Babbler", though "House Sparrow" showed up in its alternatives. So the app always shows **what it saw** and what it **could also be**, and turns anything below 80% confidence into a "Mystery find" instead of a confident answer. The model rates its own confidence, so treat that number as a hint, not a measurement.
- Scientific names and "fun facts" are **deliberately left out**, because the model made them up. Tips are limited to details visible in the photo.
- It never tells you whether something is safe to eat or touch. Don't use it for that.
- Each photo takes about 20–35 seconds on an RTX 3050 laptop GPU (6 GB), plus about 40 seconds when it takes a second look.

## License

MIT
