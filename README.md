# 🌿 Pocket Naturalist

An offline field guide for walks. Snap a plant, bird or bug on your phone. **Gemma 4**, running on a laptop in your backpack, tells you what it probably is, what to look at more closely, and gives you a small quest to find next. When you finish, it writes a journal of your walk.

You don't need mobile signal, a cloud API or an account. Your photos never leave your own devices.

Built for the [Hacktoberfest 2026 Open-Source AI Challenge, Week 1: "Touch Grass"](https://dev.to/challenges/hacktoberfest-week1-2026-10-05).

## How it works

```
phone (browser) ──hotspot Wi-Fi, no internet──▶ laptop: server.py ──▶ Ollama ──▶ gemma4:12b (vision)
```

1. **Start a walk.** You get your first quest, read aloud by the phone's built-in offline voice.
2. **📷 Snap a find.** Gemma lists the features it can see, ranks its top 3 guesses, picks one, and gives a "look closer" tip plus your next quest.
3. **End walk.** Gemma writes a short journal using only what you actually found. It's saved to `walks/<date>/journal.html` along with your photos.

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

- **Birds are hard for a 12B model.** In testing, a female house sparrow was confidently called a "Jungle Babbler", though "House Sparrow" showed up in its alternatives. So the app always shows **what it saw** and what it **could also be**, and calls something "Not sure… maybe X" below 60% confidence. The model rates its own confidence, so treat that number as a hint, not a measurement.
- Scientific names and "fun facts" are **deliberately left out**, because the model made them up. Tips are limited to details visible in the photo.
- It never tells you whether something is safe to eat or touch. Don't use it for that.
- Each photo takes about 20–35 seconds on an RTX 3050 laptop GPU (6 GB).

## License

MIT
