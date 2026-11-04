# 3SVerse Social Media Poster

**Developed by www.3SVerse.com (c) 2026** · Independent vendor — not affiliated with LinkedIn, Meta, YouTube or Facebook.

One console, four platform tabs — **LINKEDIN · META · YOUTUBE · FB GROUPS** — each driving the **real workflow of its 3SVerse browser extension** through the user's own logged-in Chrome (Selenium/CDP). No official API anywhere: what the extension does, this does — including **native platform scheduling**, so a scheduled post publishes even when the app is closed.

| Tab | Extension workflow ported | What it does |
|---|---|---|
| LINKEDIN | Campaign Uploader v1.3.0 | Day-matched image **or** video post to the company page — composer flow: Create → media → Next → **Schedule-first-then-caption** → verified |
| META | Meta Planner Scheduler v1.6.0 | Day-matched Reels / image posts / Stories to the FB Page + Instagram via Business Suite **Planner**, scheduled natively |
| YOUTUBE | YouTube Campaign Uploader | Day-matched video/Short via **Studio** — Day title → video title, hashtags → tags, Shorts rule (`Format: short` / `#Shorts`) |
| FB GROUPS | FB Group Posting v1.6.0 | Caption + hashtags + media → **ticked joined groups**, group scanner, per-group progress, ~12 s inter-group wait |

Shared architecture (the proven one): **own Chrome profile per platform** (`%APPDATA%\3SVerse\SocialMediaPoster\chrome\<platform>`), verify-every-step, **resume-safe progress files** (`<platform>_progress.json` — completed items are skipped on every rerun), stop button, one shared **15-second scheduler** with **MISSED flags** — nothing ever posts twice.

---

## Run it

```
pip install selenium pillow
python social_media_poster.py
```

1. **Generate the campaign pack** — two ways:
   - Offline, one command: **`python make_campaign.py`** (or double-click `MAKE_CAMPAIGN.bat`) — builds branded images (1200×627 LinkedIn cards, 1080×1350 posts, 1080×1920 stories), 9:16 reel/short MP4s (PIL frames + ffmpeg, ~16 s HOOK → PROBLEM → FIX → CTA), and `campaign.md` captions + unique hashtags for all platform folders in one run:
     ```
     python make_campaign.py                  # full month
     python make_campaign.py --month 2026-12  # any month
     python make_campaign.py --days 8         # quick sprint
     python make_campaign.py --no-videos      # images + text only
     ```
   - Or with any AI: paste **[MEDIA_PROMPT.md](MEDIA_PROMPT.md)** into ChatGPT/Claude/Gemini/Veo/Sora and save the outputs under the filenames it specifies (same folder contract as [CAMPAIGN-FOLDERS.md](CAMPAIGN-FOLDERS.md)).
2. **LINKEDIN / META / YOUTUBE tabs** → Browse → pick that platform's folder → **Load** → tick days → **Run Now** (starts today) or **Schedule…** (pick start date/time/interval). The app opens its own Chrome window per platform — sign in once, the workflow takes over and commits **native schedules** (Planner / Studio / LinkedIn), so publishing survives app closure.
3. **FB GROUPS tab** → paste caption + hashtags → **Add media…** → **Scan** → tick groups → **Run Now**.

Campaign folders follow the same contract the extensions use: `## Day N — Title` blocks in `campaign.md`, media matched by the `day-N` / `reel-N` number in the filename, one image + one video per day (details: `CAMPAIGN-FOLDERS.md`).

## What changed in v3.0.0

- **Complete UI/UX overhaul to the Xfer / License Studio design language**: stacked centered hero header (3SVerse wordmark on top, "SOCIAL MEDIA POSTER" two-tone headline, eyebrow sub-heading), tri-gradient cyan→periwinkle→magenta bar, License Studio footer (vendor left · developed-by center · version + About right).
- **Dark everywhere, guaranteed**: the post-list `ttk.Treeview` and its scrollbar are now styled dark (`clam` base) — the last white panel is gone.
- **Brand art baked in**: the four official platform marks, the header wordmark and the window icon are embedded into the exe as base64 (`embedded_brand_assets.py`, generated in CI) and load **embedded-first** with a PhotoImage fallback — the marks can never silently fall back to text-only tabs again (the v2.x exe missed Pillow on the runner).
- **Window opens centered** on the screen exactly like the Xfer PC window (`Center: true`) — no more force-maximize.
- **Fonts standardized**: Segoe UI body/headings always; mono follows the xfer `gui.go` stack (DM Mono → Cascadia Mono → Consolas).
- Native DWM dark title bar + website favicon (from v2.2.0) retained.

## What changed in v2.0.0

- The whole app is now **Social Media Poster** — four equal tabs instead of a single LinkedIn console.
- The official-API path (developer app, tokens, OAuth) is **gone** — every tab runs the matching extension workflow in your own Chrome.
- `meta_workflow.py`, `youtube_workflow.py`, `fbg_workflow.py` added (Selenium ports of the three extensions); `linkedin_bridge.py` reuses the proven `web_workflow.py` engine behind the uniform `run_queue` interface.
- Shared scheduler, progress files, store and branding moved to `%APPDATA%\3SVerse\SocialMediaPoster\`.
- `make_campaign.py` + `MAKE_CAMPAIGN.bat` + `MEDIA_PROMPT.md` ship with the app.

## Settings & storage

Everything lives in `%APPDATA%\3SVerse\SocialMediaPoster\`: `config.json` (folders, post time, groups, media picks), `schedule.json` (slots with `fired`/`missed` flags), `<platform>_progress.json` (resume state), `chrome\<platform>\` (per-platform Chrome profiles — signing in once per platform is enough).

## Build

`build-poster.yml` (GitHub Action) packages the Windows EXE via Nuitka onefile on every push to main (the release asset IS the exe).

## License

MIT — see [LICENSE](LICENSE).
