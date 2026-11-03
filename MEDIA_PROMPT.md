# MEDIA PROMPT — generate the whole campaign pack with any AI

Paste the prompt below into any AI (ChatGPT, Claude, Gemini, Grok, Midjourney,
Veo, Sora…), fill the five placeholders, and save every output under the exact
filenames it specifies. Then load the platform folders in **3SVerse Social
Media Poster** (LINKEDIN / META / YOUTUBE tabs → Load → tick → Schedule) — or
skip the AI entirely and run **`python make_campaign.py`** (or double-click
`MAKE_CAMPAIGN.bat`), which builds the whole pack offline in one run.

**Placeholders:** `[BUSINESS]` brand name · `[DAYS]` campaign length (e.g. 30) ·
`[TOPIC]` what the campaign sells or says · `[TONE]` voice (bold, friendly…) ·
`[WEBSITE]` link to include.

---

## The prompt

You are the content engine for [BUSINESS] (site: [WEBSITE]). Build a [DAYS]-day
social campaign about [TOPIC] in a [TONE] voice. Produce TEXT first, then MEDIA
for each day. Copy arc: days 1–30% awareness → 30–60% pain/problem → 60–85%
proof/feature → last 15% offer/CTA ending with "[WEBSITE]".

### 1) captions — one `campaign.md` per platform folder

For each day write a block exactly in this shape:

```
## Day N — [hook title ≤ 60 chars]

[2–4 short caption lines. Line 1 = the hook. Concrete, no fluff.]

[optional 1–2 more lines]

#Tag1 #Tag2 #Tag3 #Tag4 #Tag5 #Tag6 #Tag7 #Tag8

---
```

Rules the parsers enforce — follow them exactly:
- Heading MUST be `## Day N — Title` (N = 1…[DAYS], em-dash or hyphen).
- The LAST line of every block is the hashtag line: 6–10 unique tags, each
  starting with `#`, nothing else on the line. Never repeat the same tag set
  on consecutive days.
- Optional annotation lines (auto-filtered, safe to include): `**Format:**`
  (post / reel / story / short), `**Creative hook:**`, `**CTA:**`,
  `**Image:**`, `**Video:**`.
- Paragraph breaks are preserved — blank lines matter.
- Save one variant as `3-Meta-Planner-Scheduler/campaign.md`, one as
  `4-LinkedIn-Campaign-Uploader/campaign.md`, one as
  `5-YouTube-Campaign-Uploader/campaign.md` (platform-tuned wording; the
  YouTube Day title becomes the video title — first 100 characters).

### 2) media — exact filenames

Meta folder (`3-Meta-Planner-Scheduler/`):
- `images/day-N.jpg` — feed posts & stories, 1080×1350 (4:5) or 1080×1920 story
- `videos/day-N.mp4` — Reels, 9:16 vertical 1080×1920, H.264, 15–60 s

LinkedIn folder (`4-LinkedIn-Campaign-Uploader/`):
- `images/day-N.png` — 1200×627 landscape cards
- `videos/day-N.mp4` — optional video-post days, 9:16 or 16:9

YouTube folder (`5-YouTube-Campaign-Uploader/`):
- `videos/day-N.mp4` — every day that uploads; Shorts get `**Format:** short`
  in campaign.md and/or `#Shorts` kept in the caption

FB Groups folder (`1-Facebook-Group-Posting/`):
- `caption.txt` (full caption incl. hashtags), `hashtags.txt` (extra block),
  `post-media.jpg` or `post-media.mp4` — exactly one media file

### 3) image style

[BUSINESS] brand: dark canvas (#07060b → #0d0c14 gradient), thin glowing ring
motif, one bold headline in white, small accent line in cyan (#6ee7ef) /
periwinkle (#78a6ff), generous margins, no stock-photo faces, no lorem text.
Every image carries the headline from that day's hook — nothing else.

### 4) video script (per 15–60 s vertical)

Silent-safe storyboard: SCENE 1 (0–3 s) HOOK — the day's title, huge type;
SCENE 2 (3–10 s) PROBLEM — one stat or pain line; SCENE 3 (10–20 s) FIX —
how [TOPIC] solves it, feature card; SCENE 4 (last 5 s) CTA — "[WEBSITE]" +
brand wordmark. Add a subtle progress bar. Export 1080×1920 MP4 H.264.

---

## Then: schedule it

1. Open **3SVerse Social Media Poster** (`python social_media_poster.py`).
2. Each tab → **Browse** → pick that platform's folder → **Load**.
3. Tick the days → **Schedule…** → start date + time → the app drives the
   real platform composer (Planner / Studio / LinkedIn) and commits native
   schedules — posts publish even when the app is closed.
4. FB GROUPS tab: paste caption + hashtags, add media, **Scan** groups,
   tick, **Run Now**.

Nothing twice: progress files per platform make every rerun resume-safe
(skip-completed), and MISSED slots are flagged instead of re-posted.
