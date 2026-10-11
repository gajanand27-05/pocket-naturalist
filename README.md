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

## The Indian field guide (`field_guide.csv`)

On real walks in Karnataka, stock Gemma **saw plants correctly but named them like an American field guide**. Castor became "Virginia Creeper", moringa became "Purslane", curry leaf became "Chinese Fringe Tree", and a four o'clock flower became "Mexicaner".

`field_guide.csv` is a plain list of **107 common Indian plants** (garden, kitchen, roadside, weeds, trees, houseplants). Each has its English name, local names, type and the **key features that tell it apart**. It's added to Gemma's prompt (plants only, A–Z, with a "never force a match" rule) so Gemma matches what it sees against local vocabulary. **Edit the CSV to adapt it to your own region.** `FIELD_GUIDE=0` turns it off.

## Accuracy

Measured on 28 labelled photos (22 from my own walks, 6 internet photos), first answer only:

| Setup | Correct | My garden photos |
|---|---|---|
| Stock `gemma4:12b` | 13/28 | 8/22 |
| **+ field guide** | **20/28** | **16/22** |

On my real 17-photo walk (15 with a known answer): **4/15 → 10/15**.

Also tried and measured, then dropped: Qwen3.5 9B, MiniCPM-V 4.5, Qwen2.5-VL 3B, Gemma 4 12B QAT on llama.cpp (with and without an MTP drafter), and a **LoRA fine-tune of Gemma 4 12B** on 1,193 photos from the [DIMPSAR dataset](https://data.mendeley.com/datasets/748f8jkphb) (Pushpa B.R. & N. Shobha Rani, *Data in Brief* 2023, CC BY 4.0) on an NVIDIA DGX Spark. The fine-tune gained +1/28 and became 100% confident on everything, so the 107-line field guide won.

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

Settings, all optional: `MODEL=<any Ollama vision model>`, `FIELD_GUIDE=0` (turn the field guide off), `OLLAMA_URL`, `PORT`.

## Honest limitations

- **Gemma's self-rated confidence varies.** The same vine photo scored 75% on one run and 85% on the next, so it doesn't always trigger the second look. On my first real walk, Gemma got 6 of 7 plants right and called a butterfly pea vine "Creeping Charlie". Checking the real vine for blue flowers solved it, which is the reason the "how to tell" and "I know it" features exist.
- **Birds are hard for a 12B model.** In testing, a female house sparrow was confidently called a "Jungle Babbler", though "House Sparrow" showed up in its alternatives. So the app always shows **what it saw** and what it **could also be**, and turns anything below 80% confidence into a "Mystery find" instead of a confident answer. The model rates its own confidence, so treat that number as a hint, not a measurement.
- Scientific names and "fun facts" are **deliberately left out**, because the model made them up. Tips are limited to details visible in the photo.
- It never tells you whether something is safe to eat or touch. Don't use it for that.
- **Birds and insects aren't covered by the field guide yet.** In testing, a house sparrow was still misnamed.
- Plants missing from the field guide can still be misnamed; the "could also be" list, Mystery finds and ✏️ corrections are there for that.
- Each photo takes about 30–40 seconds on an RTX 3050 laptop GPU (6 GB), plus about 40 seconds when it takes a second look.

## License

MIT
