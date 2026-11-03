#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_campaign.py — one command that creates EVERYTHING the Social Assistant
extensions upload: branded images, 9:16 reel/shorts videos, captions,
descriptions and hashtags — laid out in the exact CAMPAIGN-FOLDERS.md tree.

    python make_campaign.py                       # 30-day campaign, current month
    python make_campaign.py --month 2026-12       # any month
    python make_campaign.py --days 8              # quick week-long sprint
    python make_campaign.py --seed 7              # reshuffle the copy variants
    python make_campaign.py --no-videos           # images + text only (no ffmpeg needed)
    python make_campaign.py --out "D:/Campaigns"  # custom output location

What you get (one folder per extension, ready to link):

    <out>/3SVerse-Social-Campaign/
    ├── 1-Facebook-Group-Posting/        caption.txt + hashtags.txt + post-media.jpg
    ├── 2-Facebook-Live-Group-Poster/    live-link.txt + message.txt + hashtags.txt
    ├── 3-Meta-Planner-Scheduler/        campaign.md + images/ (1080x1350) + videos/ (9:16 mp4)
    ├── 4-LinkedIn-Campaign-Uploader/    campaign.md + images/ (1200x627 PNG)
    └── 5-YouTube-Campaign-Uploader/     campaign.md + videos/ (9:16 mp4)

Filenames follow the day-number contract the extensions scan for
(day-7.mp4 / reel-3.mp4 / Day 4.png — see CAMPAIGN-FOLDERS.md), captions are
"## Day N — Title" blocks whose production notes are auto-filtered by the
extensions, and the run ends with a verify pass that parses the output back
with the SAME rules as the extension code and prints each extension's queue.

Copy engine: offline template system in the 3SVerse voice — awareness → pain
→ proof → offer arc, per-product copy pairs (VidaPay pain lines only ever
attach to VidaPay tools, and so on), 8–12 hashtags per day, no two identical
hashtag lines. Videos need ffmpeg on PATH; without it everything else is
still produced and the mp4s are reported as warnings, not errors.

Requires: Python 3.8+, Pillow. Optional: ffmpeg (reels/shorts).
Developed by www.3SVerse.com (c) 2026 — independent vendor.
"""

import argparse
import math
import os
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import date, timedelta

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:
    print("Pillow is required:  pip install pillow")
    sys.exit(1)

# ════════════════════════════════════════════════════════════════════
# Brand tokens — the 3sverse.com dark-hero palette (same ramp as the
# LinkedIn Poster / License Studio: canvas #07060b, warm-white ink,
# cyan/periwinkle/magenta accent ramp + lime OK).
# ════════════════════════════════════════════════════════════════════
BG = (7, 6, 11)
PANEL = (13, 12, 20)
FIELD = (18, 16, 26)
BORDER = (35, 33, 48)
TEXT = (245, 241, 230)
DIM = (155, 151, 179)
CYAN = (110, 231, 239)
PERI = (120, 166, 255)
MAGENTA = (228, 75, 215)
LIME = (199, 239, 112)
DANGER = (239, 106, 82)
ACCENTS = (CYAN, PERI, MAGENTA)

BRAND = "3SVerse"
SITE = "3sverse.com"

# ════════════════════════════════════════════════════════════════════
# Fonts — Windows-first (Segoe UI ships with every Windows box), then
# macOS, then Linux, then Pillow's built-in bitmap fallback.
# ════════════════════════════════════════════════════════════════════
_FONT_DIRS = [
    r"C:\Windows\Fonts",
    "/System/Library/Fonts",
    "/System/Library/Fonts/Supplemental",
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/truetype/noto",
    "/usr/share/fonts/truetype/chinese",
]
_FONT_FILES = {
    "bold": ["segoeuib.ttf", "arialbd.ttf", "SegoeUI-Bold.ttf",
             "DejaVuSans-Bold.ttf", "NotoSansSC-Bold.ttf",
             "NotoSans-Bold.ttf"],
    "regular": ["segoeui.ttf", "arial.ttf", "SegoeUI.ttf",
                "DejaVuSans.ttf", "NotoSansSC-Regular.ttf",
                "NotoSans-Regular.ttf"],
    "mono": ["consola.ttf", "DejaVuSansMono.ttf", "Menlo.ttc"],
}
_font_cache = {}


def _find_font(kind, size):
    key = (kind, size)
    if key in _font_cache:
        return _font_cache[key]
    candidates = []
    for d in _FONT_DIRS:
        for name in _FONT_FILES[kind]:
            candidates.append(os.path.join(d, name))
    for path in candidates:
        if os.path.exists(path):
            try:
                f = ImageFont.truetype(path, size)
                _font_cache[key] = f
                return f
            except Exception:
                continue
    f = ImageFont.load_default()
    _font_cache[key] = f
    return f


# ════════════════════════════════════════════════════════════════════
# Content engine — product cards carry their OWN pain/fix/proof/offer
# lines, so a day about a VidaPay tool can never receive 3SVerse-POS
# copy and vice versa (per-family allowlist by construction).
# ════════════════════════════════════════════════════════════════════
PRODUCTS = [
    {
        "name": "3SVerse WiFi Transfer",
        "family": "3sverse",
        "hook": ["Phone shop file transfers eating your whole afternoon?",
                 "Still moving phone data with cables and prayers?",
                 "Every phone swap shouldn't feel like an IT project."],
        "pain": ["Cable-by-cable transfers cap a shop at a handful of "
                 "phones a day — and one interrupted copy means starting "
                 "over.",
                 "Staff queue at one 'transfer PC' while customers wait. "
                 "Slow handovers read as amateur work."],
        "fix": ["WiFi Transfer moves contacts, photos and apps "
                 "phone-to-phone over your own network — batch after "
                 "batch, no cables, no re-dos.",
                 "Queue ten phones, not ten cables. WiFi Transfer runs "
                 "the whole handover from one screen."],
        "proof": ["Shops run morning-to-close transfer days without a "
                  "single cable touch.",
                  "One tech now handles the workload that used to need "
                  "three."],
        "offer": ["This month: WiFi Transfer is onboarding shops with "
                  "zero setup calls — plug in and go.",
                  "Bundle WiFi Transfer with License Studio and save on "
                  "the pair."],
        "tags": ["#WiFiTransfer", "#PhoneShop", "#DataTransfer",
                 "#PhoneRepair", "#RepairShop", "#DeviceSetup",
                 "#RetailTech"],
    },
    {
        "name": "3SVerse License Studio",
        "family": "3sverse",
        "hook": ["Software licenses tracked in a notebook? In 2026?",
                 "Where did that license key go — again?",
                 "License chaos is silent revenue loss."],
        "pain": ["Keys live in spreadsheets and chat threads. Nobody "
                 "knows what's sold, what's assigned, what's still "
                 "stock — until a customer comes back twice.",
                 "Manual license handouts get re-sold by mistake. Every "
                 "duplicate key is money you already lost."],
        "fix": ["License Studio issues, tracks and audits every key "
                "from one console — live stock, per-device assignment, "
                "zero double-sells.",
                 "One dashboard for every license you sell: issued, "
                 "assigned, expiring, done."],
        "proof": ["Dealers run four-figure license volumes with no "
                  "spreadsheet in sight.",
                  "Audit time on license questions dropped from hours "
                  "to seconds."],
        "offer": ["License Studio bundles are live this month — one "
                  "console, every key accounted for.",
                  "Ask about the shop starter bundle: License Studio + "
                  "POS in one plan."],
        "tags": ["#LicenseStudio", "#LicenseManagement", "#KeyManagement",
                 "#SoftwareReseller", "#DigitalGoods", "#RetailTools"],
    },
    {
        "name": "3SVerse POS",
        "family": "3sverse",
        "hook": ["Your POS shouldn't need a training course.",
                 "Checkout queues are where shops lose regulars.",
                 "Still ringing up phones on paper invoices?"],
        "pain": ["Bloated POS systems slow the counter to a crawl — "
                 "and staff fall back to handwritten receipts 'just for "
                 "today'. Every day.",
                 "Stock counts live in three places and disagree in "
                 "all of them. Shrinkage hides in the gap."],
        "fix": ["3SVerse POS rings fast, tracks every unit's IMEI, and "
                "keeps stock honest across counters — built for phone "
                "and accessory retail.",
                 "Scan, sell, done. POS keeps inventory and sales in "
                 "one truthful place."],
        "proof": ["Counters cut checkout to seconds — even on the "
                  "weekend rush.",
                  "First clean stock audit in months, one afternoon "
                  "after switching."],
        "offer": ["POS onboarding is free this month for new shops.",
                  "Ask for the counter bundle: POS + License Studio."],
        "tags": ["#PointOfSale", "#POS", "#RetailPOS", "#PhoneShop",
                 "#InventoryManagement", "#SmallBusinessTools"],
    },
    {
        "name": "3SVerse Bridge",
        "family": "3sverse",
        "hook": ["Your tools don't talk. That's the problem.",
                 "Five apps, zero sync, one giant headache.",
                 "Copy-paste is not an integration strategy."],
        "pain": ["Every platform holds its own copy of the truth. "
                 "Someone 'syncs' them by hand — until two systems "
                 "disagree and a customer pays for it.",
                 "Manual re-entry between tools wastes hours weekly and "
                 "breeds typos nobody catches until invoices go out."],
        "fix": ["Bridge connects your 3SVerse tools (and the services "
                "around them) so data lands everywhere once — entered "
                "one time, synced everywhere.",
                 "One entry, every system updated. Bridge is the "
                 "plumbing your stack was missing."],
        "proof": ["Teams killed their nightly copy-paste ritual in "
                  "week one.",
                  "End-of-day reconciliation went from a task to a "
                  "glance."],
        "offer": ["Bridge early-access seats are open — reply to get "
                  "on the list.",
                  "Bridge + any 3SVerse tool bundles at a launch "
                  "discount."],
        "tags": ["#Automation", "#SystemIntegration", "#WorkflowTools",
                 "#BusinessAutomation", "#NoMoreCopyPaste", "#RetailTech"],
    },
    {
        "name": "VidaPay Rebate Tools",
        "family": "vidapay",
        "hook": ["Rebates don't get lost. You just never filed them.",
                 "How much rebate money expired this quarter?",
                 "Unfiled rebates are donated profit."],
        "pain": ["Rebate filings live in carrier portals, email threads "
                 "and sticky notes. Miss a window, lose the payout — "
                 "and nobody can say how much leaked.",
                 "Claims get rejected for a mismatch you could have "
                 "caught in seconds — if any tool told you."],
        "fix": ["VidaPay Rebate Filing pulls every pending rebate into "
                "one pipeline — filed, tracked, and chased to payout.",
                 "Every claim, every status, one screen. Rebate Filing "
                 "turns rebate soup into a checklist."],
        "proof": ["Dealers recovered four figures of 'forgotten' "
                  "rebates in the first month.",
                  "Rejection rates dropped once every filing carried "
                  "matching data."],
        "offer": ["Rebate audit is free this month: we show you what's "
                  "unfiled, you keep the recovery.",
                  "Ask for the dealer filing bundle before quarter "
                  "close."],
        "tags": ["#VidaPay", "#Rebates", "#RebateFiling",
                 "#WirelessDealer", "#CellPhoneDealer", "#DealerProfit"],
    },
    {
        "name": "VidaPay Incentive Extractor",
        "family": "vidapay",
        "hook": ["Incentive reports are where hours go to die.",
                 "Still copy-pasting carrier incentive PDFs?",
                 "Your incentives are in there. You just can't get to "
                 "them."],
        "pain": ["Every carrier's incentive statement is a different "
                 "maze. Someone rebuilds the numbers by hand every "
                 "cycle — slowly, and wrong just often enough.",
                 "By the time reports are collated, the payout window "
                 "for disputing is half gone."],
        "fix": ["Incentive Extractor reads the statements and hands "
                "you clean, per-store numbers — same day the report "
                "drops.",
                 "From raw carrier PDFs to line-item totals without "
                 "touching a keyboard."],
        "proof": ["Monthly reporting went from two days to twenty "
                  "minutes.",
                  "Disputes got caught INSIDE the window for the first "
                  "time ever."],
        "offer": ["Send us one statement — we'll show you the extracted "
                  "numbers before you pay anything.",
                  "Extractor + Rebate Filing is the full back-office "
                  "bundle."],
        "tags": ["#VidaPay", "#Incentives", "#DealerReporting",
                 "#WirelessRetail", "#CarrierIncentives", "#BackOffice"],
    },
    {
        "name": "VidaPay Device Ordering",
        "family": "vidapay",
        "hook": ["Ordering phones shouldn't be a second job.",
                 "Dead stock in the back, sold-out in the front?",
                 "Ordering by feel is how margin dies."],
        "pain": ["Orders go in by memory and gut feel. Hot models run "
                 "dry mid-week while slow SKUs pile up as dead cash on "
                 "a shelf.",
                 "Price and incentive changes never make it into the "
                 "order — so the 'safe' reorder quietly eats margin."],
        "fix": ["Device Ordering reads your sales velocity and current "
                "incentives, then builds the reorder for you — approve "
                "instead of guess.",
                 "The right units, the right counts, ordered in "
                 "minutes — with the math shown."],
        "proof": ["Reorder time dropped from an evening to a coffee "
                  "break.",
                  "Dead stock stopped growing the first month on "
                  "auto-planned orders."],
        "offer": ["Free order-plan review this month: bring your last "
                  "reorder, we'll show the gaps.",
                  "Ordering bundles with Inventory Audit for the full "
                  "stock picture."],
        "tags": ["#VidaPay", "#DeviceOrdering", "#InventoryPlanning",
                 "#WirelessDealer", "#StockManagement", "#Prepaid"],
    },
    {
        "name": "VidaPay Inventory Audit",
        "family": "vidapay",
        "hook": ["Inventory audits after close are cruel and unusual.",
                 "Count night: pizza, flashlights, and quietly wrong "
                 "numbers.",
                 "Your stock count is a snapshot. Your stock is a "
                 "movie."],
        "pain": ["Quarterly physical counts eat an evening per store "
                 "and still land stale the moment the doors open.",
                 "Shrinkage, mis-ships and unlogged transfers hide "
                 "between counts — surfacing months later as pure "
                 "loss."],
        "fix": ["Inventory Audit reconciles shipments, sales and "
                "counts continuously — flags drift the day it starts, "
                "not the quarter after.",
                 "No more count nights: live reconciliation keeps every "
                 "store's numbers honest daily."],
        "proof": ["Stores cut count nights to zero while shrinking "
                  "shrinkage.",
                  "A mis-shipped pallet got caught the same day — not "
                  "at quarter close."],
        "offer": ["Run one free drift audit on your busiest store this "
                  "month.",
                  "Audit + Device Ordering = the no-surprises stock "
                  "bundle."],
        "tags": ["#InventoryAudit", "#VidaPay", "#Shrinkage",
                 "#InventoryControl", "#WirelessDealer", "#RetailOps"],
    },
]
FAMILIES = sorted({p["family"] for p in PRODUCTS})

# Brand-level days (family "brand"): the vendor story itself.
BRAND_CARD = {
    "name": "3SVerse",
    "family": "brand",
    "hook": ["One vendor. Every tool your shop runs on.",
             "Software built BY phone people, FOR phone people.",
             "Stop stitching five vendors into one workflow."],
    "pain": ["Tools from four vendors, four logins, four invoices — "
             "and none of them know the others exist.",
             "Generic software ignores how phone retail actually "
             "works: IMEIs, rebates, transfers, licensing."],
    "fix": ["3SVerse builds the whole counter: transfers, licenses, "
            "POS, inventory, rebates — one vendor, one standard, tools "
            "that talk.",
            "From the back office to the counter glass, 3SVerse ships "
            "the stack phone shops actually need."],
    "proof": ["One vendor, one invoice, one support line — dealers "
              "keep the stack and drop the chaos.",
              "Built from years inside wireless retail, not guessed "
              "from a template."],
    "offer": ["Get the full 3SVerse walkthrough this month — one call, "
              "your stack, mapped.",
              "Bundle season: pair any two 3SVerse tools and the "
              "second seat comes along."],
    "tags": ["#3SVerse", "#RetailSoftware", "#PhoneShopSoftware",
             "#WirelessRetail", "#RetailTech", "#SmallBusinessTech"],
}

STAGES = ["awareness", "pain", "proof", "offer"]


def _pick(rng, seq, used, salt=0):
    """Pick an unused item from seq (recycle when exhausted)."""
    pool = [x for x in seq if x not in used]
    if not pool:
        used.clear()
        pool = list(seq)
    return pool[(rng.randrange(len(pool)) + salt) % len(pool)]


def _day_plan(i, days, rng, used_tags, used_hooks, used_hash_lines):
    """Build one day's copy. Stage arc: awareness → pain → proof → offer."""
    stage = STAGES[min(3, (i * 4) // max(1, days))]
    # every ~5th day is a brand day; rest rotate the product cards
    if i % 5 == 4:
        card = BRAND_CARD
    else:
        card = PRODUCTS[i % len(PRODUCTS)]
    hook = _pick(rng, card["hook"], used_hooks, salt=stage.__len__())
    # per-family copy pairs: byline/stackline never claim a VidaPay tool
    # is a 3SVerse product or vice versa
    if card["family"] == "brand":
        byline = "One vendor, one standard: %s." % BRAND
        stackline = "The whole counter, from one vendor."
    else:
        byline = "Part of the %s toolkit: %s." % (BRAND, card["name"])
        stackline = "%s is part of the %s stack." % (card["name"], BRAND)
    body_pool = {
        "awareness": [hook, card["fix"][0], byline],
        "pain": [hook, card["pain"][i % len(card["pain"])],
                 card["fix"][i % len(card["fix"])]],
        "proof": [hook, card["proof"][i % len(card["proof"])],
                  stackline],
        "offer": [hook, card["offer"][i % len(card["offer"])],
                  card["fix"][i % len(card["fix"])]],
    }[stage]
    lines = []
    for ln in body_pool:
        if ln not in lines:
            lines.append(ln)
    # site mention at least every third day
    if (i % 3) == 0 or stage == "offer":
        lines.append("→ %s" % SITE)
    body = "\n\n".join(lines)
    # hashtags: card tags + family/broad reach, 8–12, unique per campaign
    broad = ["#SmallBusiness", "#Automation", "#RetailTech",
             "#BusinessGrowth", "#Entrepreneur", "#TechTools",
             "#Productivity", "#SmallBusinessTech", "#SaaS",
             "#WirelessRetail", "#CellPhoneDealer", "#RetailOps",
             "#ShopLocal", "#BusinessTools", "#StartupTools"]
    tag_pool = list(card["tags"])
    if card["family"] == "brand":
        tag_pool += ["#3SVerseStack", "#OneVendor"]
    if stage == "offer":
        tag_pool += ["#Offer", "#BundleDeal", "#LimitedTime"]
    if stage == "proof":
        tag_pool += ["#CustomerStory", "#CaseStudy"]
    tags, seen = [], set()
    for t in tag_pool:
        if t not in seen:
            tags.append(t)
            seen.add(t)
    while len(tags) < 9:
        t = _pick(rng, broad, set())
        if t not in seen:
            tags.append(t)
            seen.add(t)
    tags = tags[: rng.randint(9, 12)]
    hash_line = " ".join(tags)
    guard = 0
    while hash_line in used_hash_lines and guard < 50:
        rng.shuffle(tags)
        hash_line = " ".join(tags[: rng.randint(9, 12)])
        guard += 1
    used_hash_lines.add(hash_line)
    title = _title_for(i, card, stage, rng)
    return {"day": i + 1, "stage": stage, "card": card, "title": title,
            "hook": hook, "body": body, "hashtags": hash_line}


_TITLE_TPL = {
    "awareness": ["Meet {name}", "Say hello to {name}", "{name}, explained"],
    "pain": ["The real cost of doing it manually", "This is where shops leak money",
             "The workflow that's quietly draining you"],
    "proof": ["What changes with {name}", "Week one with {name}", "The before/after"],
    "offer": ["This month at 3SVerse", "Bundle season is open", "Claim this month's deal"],
}


def _title_for(i, card, stage, rng):
    if stage in ("awareness", "proof") and "{name}" in " ".join(_TITLE_TPL[stage]):
        return rng.choice(_TITLE_TPL[stage]).format(
            name=card["name"].replace("3SVerse ", "").replace("VidaPay ", ""))
    return rng.choice(_TITLE_TPL[stage])


# ════════════════════════════════════════════════════════════════════
# Month plan — which day gets a reel (YouTube+Meta videos), which gets
# a story, which gets a plain feed post. Tilt: Tue/Thu + weekend for
# reels, stories mid-week; everything else is a feed post.
# ════════════════════════════════════════════════════════════════════
def build_plan(first_day, days, seed):
    rng = random.Random(seed)
    used_hooks, used_hash = set(), set()
    plan = [_day_plan(i, days, rng, set(), used_hooks, used_hash)
            for i in range(days)]
    # cadence by day index: ~2 reels + 1 story per week, posts between —
    # a 30-day month lands ≈17 feed posts · 9 reels/shorts · 4 stories.
    for i, d in enumerate(plan):
        if i % 7 in (1, 5):
            d["format"] = "reel"        # video day (Meta reels + YouTube)
        elif i % 7 == 3:
            d["format"] = "story"       # 9:16 story image (Meta)
        else:
            d["format"] = "post"        # feed post image
    return plan


def month_days(month=None):
    """(first_day, days_in_month) for YYYY-MM or the current month."""
    if month:
        y, m = (int(x) for x in month.split("-"))
    else:
        t = date.today()
        y, m = t.year, t.month
    first = date(y, m, 1)
    nxt = date(y + (m == 12), (m % 12) + 1, 1)
    return first, (nxt - first).days

# ════════════════════════════════════════════════════════════════════
# Card renderer — branded dark canvas: soft rings + glow orb, eyebrow,
# wrapped headline, gradient bar, day badge, brand footer.
# ════════════════════════════════════════════════════════════════════
def _rr(draw, box, r, **kw):
    try:
        draw.rounded_rectangle(box, radius=r, **kw)
    except AttributeError:  # Pillow < 8.2
        draw.rectangle(box, **kw)


def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _base_canvas(w, h, accent, rng):
    """Dark canvas + 2 soft rings + glow orb in the accent color."""
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    # vertical panel tint at the bottom third
    for y in range(int(h * 0.62), h):
        t = (y - h * 0.62) / (h * 0.38)
        d.line([(0, y), (w, y)],
               fill=tuple(int(a + (b - a) * t * 0.9)
                          for a, b in zip(BG, PANEL)))
    # glow orb
    orb = Image.new("RGB", (w, h), BG)
    od = ImageDraw.Draw(orb)
    r = int(min(w, h) * (0.34 + rng.random() * 0.10))
    cx = int(w * (0.72 + rng.random() * 0.2))
    cy = int(h * (0.18 + rng.random() * 0.14))
    od.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent)
    orb = orb.filter(ImageFilter.GaussianBlur(int(min(w, h) * 0.16)))
    img = Image.blend(img, orb, 0.22)
    # rings (additive glow — keeps canvas depth, no alpha flatten)
    from PIL import ImageChops
    cx2, cy2 = int(w * 0.16), int(h * 0.86)
    for rad, frac in ((int(min(w, h) * 0.55), 0.55),
                      (int(min(w, h) * 0.75), 0.35)):
        ring = Image.new("RGB", (w, h), (0, 0, 0))
        rd = ImageDraw.Draw(ring)
        col = tuple(int(b * frac) for b in accent)
        rd.ellipse([cx2 - rad, cy2 - rad, cx2 + rad, cy2 + rad],
                   outline=col, width=3)
        ring = ring.filter(ImageFilter.GaussianBlur(3))
        img = ImageChops.add(img, ring)
        d = ImageDraw.Draw(img)
    return img


def _grad_bar(img, y, h, x0, x1):
    d = ImageDraw.Draw(img)
    w = x1 - x0
    for x in range(w):
        t = x / max(1, w - 1) * 2
        if t < 1:
            c = tuple(int(a + (b - a) * t) for a, b in zip(CYAN, PERI))
        else:
            c = tuple(int(a + (b - a) * (t - 1))
                      for a, b in zip(PERI, MAGENTA))
        d.line([(x0 + x, y), (x0 + x, y + h)], fill=c)


def render_card(day, d, w, h, accent, rng, scene=None):
    """Branded card. scene=None → full day card; scene dict → video frame."""
    img = _base_canvas(w, h, accent, rng)
    dr = ImageDraw.Draw(img)
    pad = int(w * 0.075)
    landscape = h <= w
    f_eyebrow = _find_font("bold", int(w * 0.026))
    f_head = _find_font("bold", int(w * (0.052 if landscape else 0.078)))
    f_sub = _find_font("regular", int(w * (0.030 if landscape else 0.036)))
    f_badge = _find_font("mono", int(w * 0.028))
    f_foot = _find_font("regular", int(w * 0.024))

    if scene:
        eyebrow, head, sub = scene["eyebrow"], scene["head"], scene["sub"]
        badge = scene.get("badge", "")
    else:
        stage_up = d["stage"].upper()
        eyebrow = "%s · %s" % (BRAND.upper(), stage_up)
        head = d["title"]
        sub = d["hook"]
        badge = "DAY %d" % d["day"]

    # eyebrow
    dr.text((pad, int(h * (0.12 if landscape else 0.085))), eyebrow,
            font=f_eyebrow, fill=accent)
    # headline (wrapped; fewer lines on landscape so nothing overlaps)
    y = int(h * (0.22 if landscape else 0.15))
    max_w = w - pad * 2
    for ln in _wrap(dr, head, f_head, max_w)[:(2 if landscape else 4)]:
        dr.text((pad, y), ln, font=f_head, fill=TEXT)
        y += int(f_head.size * 1.16)
    # gradient bar under headline
    _grad_bar(img, y + int(h * 0.02), max(3, int(w * 0.006)),
              pad, pad + int(w * 0.22))
    y += int(h * (0.035 if landscape else 0.045))
    # sub lines
    for ln in _wrap(dr, sub, f_sub, max_w)[:(2 if landscape else 4)]:
        dr.text((pad, y), ln, font=f_sub, fill=DIM)
        y += int(f_sub.size * 1.4)
    # day badge (pill) — bottom strip, clear of the sub text
    if badge:
        bw = dr.textlength(badge, font=f_badge)
        by0 = int(h - w * (0.115 if landscape else 0.10))
        bx0 = pad
        _rr(dr, [bx0, by0, bx0 + bw + pad * 0.7, by0 + int(w * 0.055)],
            int(w * 0.028), fill=FIELD, outline=BORDER, width=2)
        dr.text((bx0 + pad * 0.35, by0 + int(w * 0.012)), badge,
                font=f_badge, fill=accent)
    # footer
    foot = "%s · %s" % (BRAND, SITE)
    dr.text((w - pad - dr.textlength(foot, font=f_foot), h - int(h * 0.045)),
            foot, font=f_foot, fill=DIM)
    return img


def render_story(d, rng):
    """1080x1920 story/reel cover (Meta story day)."""
    accent = ACCENTS[d["day"] % len(ACCENTS)]
    return render_card(d["day"], d, 1080, 1920, accent, rng)


def render_post(d, rng, size=(1080, 1350)):
    accent = ACCENTS[d["day"] % len(ACCENTS)]
    return render_card(d["day"], d, size[0], size[1], accent, rng)


def render_linkedin(d, rng, size=(1200, 627)):
    accent = ACCENTS[(d["day"] + 1) % len(ACCENTS)]
    return render_card(d["day"], d, size[0], size[1], accent, rng)


# ════════════════════════════════════════════════════════════════════
# Video renderer — 9:16 silent H.264 via ffmpeg stdin (raw frames).
# Scenes: HOOK → PROBLEM → FIX → CTA, crossfade between scenes,
# progress bar along the bottom. ~16 s at 20 fps.
# ════════════════════════════════════════════════════════════════════
VW, VH, FPS, SECS = 1080, 1920, 20, 16


def _scenes(d):
    card = d["card"]
    return [
        {"eyebrow": "%s · DAY %d" % (BRAND.upper(), d["day"]),
         "head": d["hook"], "sub": "%s — %s" % (card["name"], d["stage"]),
         "badge": d["stage"].upper()},
        {"eyebrow": "THE PROBLEM", "head": card["pain"][d["day"] % len(card["pain"])],
         "sub": "Sound familiar?", "badge": "PAIN"},
        {"eyebrow": "THE FIX", "head": card["fix"][d["day"] % len(card["fix"])],
         "sub": card["name"], "badge": "THE FIX"},
        {"eyebrow": BRAND.upper(), "head": "→ %s" % SITE,
         "sub": d["hook"], "badge": "%s · DAY %d" % (BRAND.upper(), d["day"])},
    ]


def _video_frames(d, rng):
    """Yield RGB bytes frame by frame (keeps memory flat)."""
    scenes = _scenes(d)
    n_sc = len(scenes)
    total = FPS * SECS
    per = total // n_sc
    fade = int(FPS * 0.6)
    base = []
    for sc in scenes:
        base.append(render_card(d["day"], d, VW, VH,
                                ACCENTS[d["day"] % len(ACCENTS)],
                                rng, scene=sc))
    # pre-render at slightly larger size for the ken-burns zoom
    big = [b.resize((VW + 60, VH + 106), Image.LANCZOS) for b in base]
    for f in range(total):
        si = min(n_sc - 1, f // per)
        t = f / max(1, total - 1)
        # zoom drift within scene
        z = 1.0 + 0.035 * ((f % per) / per)
        bw, bh = big[si].size
        nw, nh = int(bw / z), int(bh / z)
        x0 = (bw - nw) // 2
        y0 = (bh - nh) // 2
        frame = big[si].crop((x0, y0, x0 + nw, y0 + nh)).resize((VW, VH),
                                                                Image.BILINEAR)
        # crossfade into the NEXT scene near the boundary
        if si < n_sc - 1:
            delta = (si + 1) * per - f
            if 0 < delta <= fade:
                a = 1.0 - delta / (fade + 1.0)
                a = min(1.0, max(0.0, a))
                nxt = base[si + 1]
                frame = Image.blend(frame, nxt, a)
        dr = ImageDraw.Draw(frame)
        # progress bar
        bar_h = 10
        dr.rectangle([0, VH - bar_h, VW, VH], fill=PANEL)
        dr.rectangle([0, VH - bar_h, int(VW * t), VH], fill=CYAN)
        yield frame.tobytes()


def render_video(d, rng, out_path, w=VW, h=VH, fps=FPS, secs=SECS):
    """Pipe Pillow frames into ffmpeg → H.264 yuv420p + faststart."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", "%dx%d" % (w, h), "-r", str(fps), "-i", "-",
           "-an", "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "23", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", out_path]
    global VW, VH, FPS, SECS
    ovw, ovh, ofps, osecs = VW, VH, FPS, SECS
    VW, VH, FPS, SECS = w, h, fps, secs
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        try:
            for chunk in _video_frames(d, random.Random(rng)):
                proc.stdin.write(chunk)
        except BrokenPipeError:
            pass
        finally:
            try:
                proc.stdin.close()
            except BrokenPipeError:
                pass
            rc = proc.wait()
        if rc != 0:
            raise RuntimeError("ffmpeg exited %d" % rc)
    finally:
        VW, VH, FPS, SECS = ovw, ovh, ofps, osecs

# ════════════════════════════════════════════════════════════════════
# campaign.md + extension folders — byte-level faithful to the
# contract the extensions scan (## Day N — Title, --- separators,
# hashtag line last, [image]/[video] note lines auto-filtered).
# ════════════════════════════════════════════════════════════════════
def day_block(d, media_note=True):
    # NOTE: annotation lines use ONLY the bold prefixes every extension
    # filters (**Creative hook:** / **CTA:** — see each lib.js), so they
    # can never leak into a real caption. [image]/[video] lines are NOT
    # safe: the Meta lib does not filter them.
    lines = ["## Day %d — %s" % (d["day"], d["title"]), ""]
    lines += d["body"].split("\n")
    lines.append("")
    if media_note:
        lines.append("**Creative hook:** %s" % d["hook"])
        lines.append("**CTA:** → %s" % SITE)
        lines.append("")
    lines.append(d["hashtags"])
    return "\n".join(lines)


def build_campaign_md(plan):
    return "\n\n---\n\n".join(day_block(d) for d in plan) + "\n"


def write_text_folders(out_root, plan):
    """Extensions 1 & 2: the paste-me text files."""
    d1 = plan[0]
    f1 = os.path.join(out_root, "1-Facebook-Group-Posting")
    os.makedirs(f1, exist_ok=True)
    with open(os.path.join(f1, "caption.txt"), "w",
              encoding="utf-8") as fh:
        fh.write("%s\n\n%s\n\n%s\n" % (d1["title"], d1["body"],
                                       d1["hashtags"]))
    with open(os.path.join(f1, "hashtags.txt"), "w",
              encoding="utf-8") as fh:
        fh.write(d1["hashtags"] + "\n")
    f2 = os.path.join(out_root, "2-Facebook-Live-Group-Poster")
    os.makedirs(f2, exist_ok=True)
    with open(os.path.join(f2, "live-link.txt"), "w",
              encoding="utf-8") as fh:
        fh.write("PASTE-YOUR-FACEBOOK-LIVE-URL-HERE\n")
    with open(os.path.join(f2, "message.txt"), "w",
              encoding="utf-8") as fh:
        fh.write("%s — we are LIVE: %s\n\nJoin in and bring your "
                 "questions.\n" % (BRAND, d1["hook"]))
    with open(os.path.join(f2, "hashtags.txt"), "w",
              encoding="utf-8") as fh:
        fh.write(d1["hashtags"] + "\n")


# ════════════════════════════════════════════════════════════════════
# Verify — parse the output back with the SAME rules as the extension
# code (ported from lib.js) and print each extension's queue.
# ════════════════════════════════════════════════════════════════════
MEDIA_RE = re.compile(r"\.(md|png|jpe?g|webp|gif|mp4|mov|webm|m4v)$", re.I)
DAY_RE = re.compile(r"(?:day|reel)[-_ ]?(\d{1,3})", re.I)
VIDEO_EXT = (".mp4", ".mov", ".webm", ".m4v")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif")
FILTERED_LINE = re.compile(
    r"^(!\[|\[(?:image|video|reel|creative)\]"
    r"|\*\*(?:campaign stage|creative hook|cta|image|video|reel):)", re.I)


def parse_campaign_md(text):
    r"""Faithful port of lib.js parseLinkedInCampaign:
    split on ^## Day\s+, day = leading digits of the heading line,
    caption = block up to ^---$ with note lines filtered."""
    out = []
    for block in re.split(r"^## Day\s+", text, flags=re.M)[1:]:
        nl = block.find("\n")
        heading = (block[:nl] if nl >= 0 else block).strip()
        m = re.match(r"^(\d{1,3})\b", heading)
        day = int(m.group(1)) if m else 0
        if not day:
            continue
        raw = (block[nl + 1:] if nl >= 0 else "")
        raw = re.split(r"^---\s*$", raw, flags=re.M)[0]
        caption = "\n".join(
            ln for ln in raw.split("\n")
            if ln.strip() and not FILTERED_LINE.match(ln.strip()))
        caption = re.sub(r"\n{3,}", "\n\n", caption).strip()
        if caption:
            title = re.sub(r"^\d+\s+[—-]\s*", "", heading).strip()
            out.append({"day": day, "title": title, "caption": caption})
    return sorted(out, key=lambda e: e["day"])


def scan_folder(folder, exts):
    files = []
    for name in os.listdir(folder):
        p = os.path.join(folder, name)
        if os.path.isfile(p) and name.lower().endswith(exts):
            files.append(p)
    return files


def verify(out_root, days, expect_videos=True):
    """Returns (ok, report_lines). Warnings don't fail; violations do."""
    rep, ok = [], True
    folders = {"meta": "3-Meta-Planner-Scheduler",
               "linkedin": "4-LinkedIn-Campaign-Uploader",
               "youtube": "5-YouTube-Campaign-Uploader"}
    parsed = {}
    for key, sub in folders.items():
        folder = os.path.join(out_root, sub)
        mds = [f for f in scan_folder(folder, (".md",))
               if "## Day" in open(f, encoding="utf-8").read()]
        if len(mds) != 1:
            rep.append("FAIL %s: expected exactly 1 campaign.md with Day "
                       "headings, found %d" % (key, len(mds)))
            ok = False
            continue
        entries = parse_campaign_md(open(mds[0], encoding="utf-8").read())
        parsed[key] = (entries, folder)
        missing_days = [n for n in range(1, days + 1)
                        if n not in [e["day"] for e in entries]]
        if missing_days:
            rep.append("FAIL %s: campaign.md missing Day headings for %s"
                       % (key, missing_days[:5]))
            ok = False
        for e in entries:
            if not re.search(r"#[A-Za-z0-9_]+", e["caption"]):
                rep.append("FAIL %s Day %d: no hashtag line in caption"
                           % (key, e["day"]))
                ok = False
            if len(e["caption"]) > 2200:
                rep.append("WARN %s Day %d: caption %d chars (long)"
                           % (key, e["day"], len(e["caption"])))
    # media ↔ day matching per folder
    for key in ("meta", "youtube"):
        if key not in parsed:
            continue
        entries, folder = parsed[key]
        vids = scan_folder(os.path.join(folder, "videos"), VIDEO_EXT) \
            if os.path.isdir(os.path.join(folder, "videos")) else []
        imgs = scan_folder(os.path.join(folder, "images"), IMAGE_EXT) \
            if os.path.isdir(os.path.join(folder, "images")) else []
        vdays = [int(DAY_RE.search(os.path.basename(v)).group(1))
                 for v in vids if DAY_RE.search(os.path.basename(v))]
        idays = [int(DAY_RE.search(os.path.basename(i)).group(1))
                 for i in imgs if DAY_RE.search(os.path.basename(i))]
        if len(vdays) != len(set(vdays)) or len(idays) != len(set(idays)):
            rep.append("FAIL %s: duplicate day number in filenames"
                       % key)
            ok = False
        video_days = sorted(set(vdays))
        if key == "youtube":
            head = ", ".join(str(x) for x in video_days[:6])
            more = "… (+%d more)" % (len(video_days) - 6) \
                if len(video_days) > 6 else ""
            rep.append("YouTube queue: %d video day(s)%s"
                       % (len(video_days),
                          " [%s%s]" % (head, more) if video_days else ""))
            if expect_videos and not video_days:
                rep.append("WARN YouTube: no day-N.mp4 videos found — "
                           "ffmpeg missing? Run again with ffmpeg on "
                           "PATH.")
        else:
            n_reels = len(video_days)
            n_story = len([1 for i in idays
                           if i not in video_days])
            rep.append("Meta queue: %d reel day(s) · %d story/post "
                       "image day(s)" % (n_reels, n_story))
            if expect_videos and not video_days:
                rep.append("WARN Meta: no reel videos (ffmpeg missing?)")
    if "linkedin" in parsed:
        entries, folder = parsed["linkedin"]
        imgs = scan_folder(os.path.join(folder, "images"), IMAGE_EXT)
        rep.append("LinkedIn queue: %d image post(s) (PNG, 1200x627)"
                   % len(imgs))
        if len(imgs) < days:
            rep.append("FAIL LinkedIn: %d/%d day images present"
                       % (len(imgs), days))
            ok = False
    if not os.path.exists(os.path.join(
            out_root, "1-Facebook-Group-Posting", "caption.txt")):
        rep.append("FAIL extension 1: caption.txt missing")
        ok = False
    return ok, rep


# ════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════
def have_ffmpeg():
    return shutil.which("ffmpeg") is not None


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Generate the full campaign content pack for the "
                    "3SVerse Social Assistant extensions.")
    ap.add_argument("--month", help="YYYY-MM (default: current month)")
    ap.add_argument("--days", type=int, help="campaign length override")
    ap.add_argument("--seed", type=int, default=None,
                    help="copy shuffle seed (default: derived from month)")
    ap.add_argument("--out", default=None,
                    help="output parent folder (default: ./generated)")
    ap.add_argument("--no-videos", action="store_true",
                    help="skip mp4 rendering (images + text only)")
    ap.add_argument("--force", action="store_true",
                    help="re-render files even if they already exist")
    args = ap.parse_args(argv)

    first_day, month_len = month_days(args.month)
    days = args.days or month_len
    seed = args.seed if args.seed is not None \
        else int(first_day.strftime("%Y%m%d"))
    out_root = os.path.abspath(args.out or "generated")
    campaign_root = os.path.join(out_root, "3SVerse-Social-Campaign")
    t0 = time.time()
    print("make_campaign — %d days from %s · seed %d" %
          (days, first_day.isoformat(), seed))
    if args.no_videos:
        print("videos: skipped (--no-videos)")
    elif not have_ffmpeg():
        print("videos: SKIPPED — ffmpeg not on PATH "
              "(images + text still generated)")

    plan = build_plan(first_day, days, seed)

    # folder skeleton
    meta = os.path.join(campaign_root, "3-Meta-Planner-Scheduler")
    li = os.path.join(campaign_root, "4-LinkedIn-Campaign-Uploader")
    yt = os.path.join(campaign_root, "5-YouTube-Campaign-Uploader")
    for sub, mk in ((meta, ("images", "videos")), (li, ("images",)),
                    (yt, ("videos",))):
        for m in mk:
            os.makedirs(os.path.join(sub, m), exist_ok=True)

    # captions
    md = build_campaign_md(plan)
    for sub in (meta, li, yt):
        with open(os.path.join(sub, "campaign.md"), "w",
                  encoding="utf-8") as fh:
            fh.write(md)
    write_text_folders(campaign_root, plan)

    # media
    rng = random.Random(seed ^ 0x5EED)
    do_videos = (not args.no_videos) and have_ffmpeg()
    n_img = n_vid = 0
    for d in plan:
        fmt = d["format"]
        # Meta: feed/story images always; reel videos on video days
        meta_img = os.path.join(meta, "images", "day-%d.jpg" % d["day"])
        if args.force or not os.path.exists(meta_img):
            img = render_story(d, rng) if fmt == "story" \
                else render_post(d, rng)
            img.save(meta_img, "JPEG", quality=90)
        n_img += 1
        # LinkedIn: 1200x627 PNG every day
        li_img = os.path.join(li, "images", "day-%d.png" % d["day"])
        if args.force or not os.path.exists(li_img):
            render_linkedin(d, rng).save(li_img, "PNG")
        # videos on reel days → Meta videos/ + YouTube videos/
        if fmt == "reel":
            if do_videos:
                mp4 = os.path.join(meta, "videos", "day-%d.mp4" % d["day"])
                if args.force or not os.path.exists(mp4):
                    render_video(d, seed + d["day"], mp4)
                yt_mp4 = os.path.join(yt, "videos", "day-%d.mp4" % d["day"])
                if args.force or not os.path.exists(yt_mp4):
                    shutil.copyfile(mp4, yt_mp4)  # same short, YouTube slot
                n_vid += 1
            else:
                print("WARN Day %d marked reel but videos disabled — "
                      "day will queue as image-only" % d["day"])
        sys.stdout.write("\rmedia: day %d/%d" % (d["day"], days))
        sys.stdout.flush()
    print()

    # extension-1 hero media (day 1 image copy)
    hero = os.path.join(campaign_root, "1-Facebook-Group-Posting",
                        "post-media.jpg")
    if not os.path.exists(hero):
        shutil.copyfile(os.path.join(meta, "images", "day-1.jpg"), hero)

    ok, rep = verify(campaign_root, days, expect_videos=do_videos)
    print("\n%s" % ("─" * 62))
    for ln in rep:
        print(ln)
    print("%s" % ("─" * 62))
    n_reels = len([1 for d in plan if d["format"] == "reel"])
    n_story = len([1 for d in plan if d["format"] == "story"])
    print("plan: %d feed posts · %d reels/shorts · %d stories"
          % (days - n_reels - n_story, n_reels, n_story))
    if ok:
        print("verify: OK — %d days, %d images, %d videos in %s "
              "(%.1fs)" % (days, n_img, n_vid,
                           os.path.relpath(campaign_root), time.time() - t0))
        print("next: link each extension to its folder inside "
              "3SVerse-Social-Campaign/ and run your queues.")
        return 0
    print("verify: FAILED — fix the FAIL lines above and re-run "
          "(re-runs resume; nothing is re-rendered needlessly).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
