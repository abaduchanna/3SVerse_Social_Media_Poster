#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════════════
# 3SVERSE SOCIAL MEDIA POSTER v2.0.0 — one console, four platform tabs.
#
#   LINKEDIN / META / YOUTUBE / FB GROUPS — every tab drives the REAL
#   workflow of its 3SVerse browser extension (Campaign Uploader v1.3.0,
#   Meta Planner Scheduler v1.6.0, YouTube Campaign Uploader, FB Group
#   Posting v1.6.0) through the user's own logged-in Chrome via
#   Selenium/CDP — own Chrome profile per platform, verify-every-step,
#   skip-completed-on-rerun, resume-safe progress files.
#
#   No official API anywhere (owner order): what the extension does,
#   this does — native platform scheduling included, so a scheduled post
#   publishes even when this app is closed. The 15-second scheduler marks
#   slots MISSED instead of double-posting.
#
#   Developed by www.3SVerse.com (c) 2026 — not affiliated with LinkedIn,
#   Meta, YouTube or Facebook.
# ═══════════════════════════════════════════════════════════════════════════
import json
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, ttk

import linkedin_poster as lp          # branding + store helpers (proven)
import linkedin_bridge
import meta_workflow
import youtube_workflow
import fbg_workflow

APP_NAME = "3SVerse Social Media Poster"
VERSION = "2.0.0"

BG = lp.BG
PANEL = lp.PANEL
FIELD = lp.FIELD
TEXT = lp.TEXT
DIM = lp.DIM
CYAN = lp.CYAN
LIME = lp.LIME
WARN = lp.WARN
DANGER = lp.DANGER
PERI = lp.PERI
FONT = lp.FONT
MONO = lp.MONO
HEAD_FONT = lp.HEAD_FONT

STORE_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                         "3SVerse", "SocialMediaPoster")
CHROME_ROOT = os.path.join(STORE_DIR, "chrome")
MEDIA_TYPES = (".png", ".jpg", ".jpeg", ".webp", ".gif")
VIDEO_TYPES = (".mp4", ".mov", ".webm", ".m4v")

PLATS = {
    "linkedin": {"label": "LINKEDIN", "accent": PERI, "wf": linkedin_bridge,
                 "sub": "4-LinkedIn-Campaign-Uploader",
                 "needs": "image or video — one post per day"},
    "meta": {"label": "META", "accent": "#8a7bff", "wf": meta_workflow,
             "sub": "3-Meta-Planner-Scheduler",
             "needs": "video = Reel · image = post · Format: story"},
    "youtube": {"label": "YOUTUBE", "accent": DANGER, "wf": youtube_workflow,
                "sub": "5-YouTube-Campaign-Uploader",
                "needs": "videos only — title/tags/Shorts rule applied"},
    "fbg": {"label": "FB GROUPS", "accent": LIME, "wf": fbg_workflow,
            "sub": "1-Facebook-Group-Posting",
            "needs": "caption + hashtags + media → ticked groups"},
}


def store_dir():
    os.makedirs(STORE_DIR, exist_ok=True)
    os.makedirs(CHROME_ROOT, exist_ok=True)
    return STORE_DIR


def cfg_path():
    return os.path.join(store_dir(), "config.json")


def load_cfg():
    try:
        with open(cfg_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cfg(cfg):
    with open(cfg_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1)


def schedule_path():
    return os.path.join(store_dir(), "schedule.json")


def load_schedule():
    try:
        with open(schedule_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_schedule(sch):
    with open(schedule_path(), "w", encoding="utf-8") as f:
        json.dump(sch, f, indent=1)


# ═══════════════════════════════════════════════════════════════════════════
# Campaign folder scanner — the CAMPAIGN-FOLDERS.md contract, generalized:
# captions from the one campaign.md (## Day N — blocks), media matched by the
# first day/reel number in the filename, one image + one video max per day.
# ═══════════════════════════════════════════════════════════════════════════
DAY_NUM = re.compile(r"day[-_ ]?(\d{1,3})|reel[-_ ]?(\d{1,3})", re.I)
DAY_HEAD = re.compile(r"^##\s*Day\s*(\d{1,3})\s*[—-]\s*(.*)$", re.I | re.M)
ANN = re.compile(r"^\*\*(.+?):\*\*\s*(.*)$")
FMT_LINE = re.compile(r"^Format:\s*(\S[\w -]*)$", re.I)
TAG_RE = re.compile(r"^(#[A-Za-z0-9_]+\s*)+$")


def scan_campaign(folder):
    """→ [{"day","title","text","hashtags","image","video","format","meta"}]"""
    md = None
    for root, _dirs, files in os.walk(folder):
        for f in sorted(files):
            if f.lower().endswith(".md"):
                raw = open(os.path.join(root, f), encoding="utf-8",
                           errors="replace").read()
                if DAY_HEAD.search(raw):
                    md = os.path.join(root, f)
                    break
        if md:
            break
    days = {}

    def _blank(day):
        return {"day": day, "title": "Day %d" % day, "text": "",
                "hashtags": "", "image": None, "video": None,
                "format": "post", "meta": {}}

    if md:
        raw = open(md, encoding="utf-8", errors="replace").read()
        blocks = re.split(r"\n-{3,}\s*\n", raw)
        cur = None
        body, tags, meta = [], [], {}

        def flush():
            nonlocal body, tags, meta
            if cur is None:
                return
            d = days.setdefault(cur["day"], _blank(cur["day"]))
            d["title"] = cur["title"]
            d["text"] = "\n\n".join(body).strip()
            d["hashtags"] = " ".join(tags[-1:]).strip()
            d["meta"] = dict(meta)
            fmt = meta.get("format")
            if fmt:
                d["format"] = str(fmt).lower().strip().split()[0]
            body, tags, meta = [], [], {}

        for block in blocks:
            lines = block.strip().splitlines() if block.strip() else []
            for line in lines:
                s = line.strip()
                hm = DAY_HEAD.match(s)
                if hm:
                    flush()
                    cur = {"day": int(hm.group(1)),
                           "title": hm.group(2).strip()
                           or "Day %s" % hm.group(1)}
                    continue
                if cur is None:
                    continue
                if (not s or s.startswith("## ") or s.startswith("![")
                        or s.startswith("[image]")
                        or s.startswith("[video]")
                        or s.startswith("[reel]")
                        or s.startswith("[creative]")):
                    continue
                am = ANN.match(s)
                if am:
                    meta[am.group(1).strip().lower()] = am.group(2).strip()
                    continue
                fm = FMT_LINE.match(s)
                if fm:  # bare "Format: reel|story|post|short" line — same as
                    meta["format"] = fm.group(1).strip()   # **Format:** form
                    continue
                if TAG_RE.match(s):
                    tags.append(s)
                    continue
                body.append(line)
        flush()

    # media by day number — folder root + images/ + videos/
    for root, _dirs, files in os.walk(folder):
        for f in files:
            m = DAY_NUM.search(f)
            if not m:
                continue
            day = int(m.group(1) or m.group(2))
            if not (1 <= day <= 999):
                continue
            ext = os.path.splitext(f)[1].lower()
            path = os.path.join(root, f)
            if ext in VIDEO_TYPES:
                d = days.setdefault(day, _blank(day))
                d["video"] = path            # last scan wins, as extensions
            elif ext in MEDIA_TYPES:
                d = days.setdefault(day, _blank(day))
                if not d["image"]:
                    d["image"] = path
    return [days[d] for d in sorted(days)]


def platform_items(plat, posts, slots, cfg):
    """Days that can enter this platform's queue, with dates from slots."""
    wf = PLATS[plat]["wf"]
    prog = wf.load_progress(store_dir())
    items = []
    for p in posts:
        if plat == "youtube" and not p["video"]:
            continue
        if plat == "linkedin" and not (p["image"] or p["video"]):
            continue
        if plat == "meta" and not (p["image"] or p["video"]):
            continue
        key = "%s|%d" % (os.path.normpath(cfg.get("folder", "")), p["day"])
        slot = slots.get(key) or {}
        item = {"day": p["day"], "title": p["title"], "text": p["text"],
                "hashtags": p["hashtags"], "meta": p["meta"],
                "media": [m for m in (p["video"], p["image"]) if m],
                "format": p["format"], "date": slot.get("date"),
                "time": slot.get("time"), "_key": key,
                "status": (prog.get(key) or {}).get("status", "")}
        if plat == "linkedin":
            item["media"] = [m for m in (p["video"], p["image"]) if m][:1]
        if plat == "meta":
            if p["format"] == "story":
                item["media"] = [m for m in (p["image"], p["video"]) if m][:1]
            else:
                item["media"] = [m for m in (p["video"], p["image"]) if m][:1]
        items.append(item)
    return items


# ═══════════════════════════════════════════════════════════════════════════
# GUI
# ═══════════════════════════════════════════════════════════════════════════
def make_grad_bar(parent, height=3, c1="#6ee7ef", c2="#78a6ff"):
    cv = tk.Canvas(parent, height=height, highlightthickness=0,
                   bg=parent["bg"])
    cv.bind("<Configure>", lambda e: _paint(cv, c1, c2))
    return cv


def _paint(cv, c1, c2):
    cv.delete("g")
    w = cv.winfo_width()
    if w < 2:
        return
    for x in range(w):
        t = x / max(1, w - 1)
        r = int(0x6e + (0x78 - 0x6e) * t)
        g = int(0xe7 + (0xa6 - 0xe7) * t)
        b = int(0xef + (0xff - 0xef) * t)
        cv.create_line(x, 0, x, cv.winfo_height(),
                       fill="#%02x%02x%02x" % (r, g, b), tags="g")


class PlatformTab(tk.Frame):
    """One platform tab: folder row + post list + Run/Schedule + progress."""

    def __init__(self, app, plat, container):
        super().__init__(container, bg=BG)
        self.app = app
        self.container = container
        self.plat = plat
        self.spec = PLATS[plat]
        self.posts = []
        self.busy = False
        self.stop = threading.Event()
        self._build()

    # ── UI ────────────────────────────────────────────────────────────
    def _build(self):
        pad = {"padx": 18, "pady": (10, 4)}
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", **pad)
        tk.Label(top, text=self.spec["label"], bg=BG,
                 fg=self.spec["accent"],
                 font=(HEAD_FONT, 16, "bold")).pack(side="left")
        tk.Label(top, text="  ·  extension workflow in your own Chrome",
                 bg=BG, fg=DIM, font=(FONT, 9)).pack(side="left")
        if self.plat != "fbg":
            row = tk.Frame(self, bg=BG)
            row.pack(fill="x", padx=18)
            tk.Label(row, text="Campaign folder", bg=BG, fg=DIM,
                     font=(FONT, 9)).pack(side="left")
            self.folder_var = tk.StringVar(
                value=self.app.cfg.get("folder_" + self.plat, ""))
            ent = tk.Entry(row, textvariable=self.folder_var, bg=FIELD,
                           fg=TEXT, bd=0, insertbackground=TEXT,
                           font=(MONO, 9))
            ent.pack(side="left", fill="x", expand=True, padx=8)
            self._btn(row, "Browse…", self.browse).pack(side="left")
            self._btn(row, "Load", self.load_folder).pack(side="left",
                                                          padx=(6, 0))
            tk.Label(self, text="Wants: %s" % self.spec["needs"],
                     bg=BG, fg=DIM, font=(FONT, 8)).pack(
                anchor="w", padx=18, pady=(4, 0))
            self.tree = ttk.Treeview(
                self, columns=("tick", "day", "title", "media",
                               "schedule", "status"),
                show="headings", height=12, selectmode="none")
            for col, w, an in (("tick", 44, "center"), ("day", 52, "center"),
                               ("title", 380, "w"), ("media", 110, "w"),
                               ("schedule", 150, "w"), ("status", 190, "w")):
                self.tree.heading(col, text=col.capitalize())
                self.tree.column(col, width=w, anchor=an)
            self.tree.tag_configure("done", foreground="#5d7a52")
            self.tree.tag_configure("failed", foreground=DANGER)
            self.tree.pack(fill="both", expand=True, padx=18, pady=8)
            self.tree.bind("<Button-1>", self._on_click)
            btns = tk.Frame(self, bg=BG)
            btns.pack(fill="x", padx=18, pady=(0, 6))
            self._btn(btns, "Select All", self.select_all).pack(side="left")
            self._btn(btns, "Clear", self.clear_sel).pack(side="left",
                                                          padx=(8, 0))
            self._btn(btns, "Run Now", self.run_now).pack(side="left",
                                                          padx=(18, 0))
            self._btn(btns, "Schedule…", self.schedule_dialog).pack(
                side="left", padx=(8, 0))
            self._btn(btns, "Stop", self.stop_run).pack(side="left",
                                                        padx=(8, 0))
            self.state_lbl = tk.Label(btns, text="", bg=BG, fg=DIM,
                                      font=(FONT, 9))
            self.state_lbl.pack(side="right")
        else:
            self._build_fbg()

    def _build_fbg(self):
        box = tk.Frame(self, bg=BG)
        box.pack(fill="both", expand=True, padx=18, pady=6)
        left = tk.Frame(box, bg=BG)
        left.pack(side="left", fill="both", expand=True)
        tk.Label(left, text="Caption", bg=BG, fg=DIM,
                 font=(FONT, 9)).pack(anchor="w")
        self.cap_txt = tk.Text(left, bg=FIELD, fg=TEXT, bd=0,
                               insertbackground=TEXT, font=(MONO, 10),
                               height=9, wrap="word")
        self.cap_txt.pack(fill="both", expand=True, pady=(4, 8))
        tk.Label(left, text="Hashtags", bg=BG, fg=DIM,
                 font=(FONT, 9)).pack(anchor="w")
        self.tag_txt = tk.Text(left, bg=FIELD, fg=TEXT, bd=0,
                               insertbackground=TEXT, font=(MONO, 10),
                               height=3, wrap="word")
        self.tag_txt.pack(fill="x", pady=(4, 8))
        mrow = tk.Frame(left, bg=BG)
        mrow.pack(fill="x")
        self._btn(mrow, "Add media…", self.add_media).pack(side="left")
        self.media_lbl = tk.Label(mrow, text="no media (text-only post)",
                                  bg=BG, fg=DIM, font=(FONT, 8))
        self.media_lbl.pack(side="left", padx=8)
        right = tk.Frame(box, bg=BG)
        right.pack(side="left", fill="both", padx=(14, 0))
        tk.Label(right, text="Groups (joined)", bg=BG, fg=DIM,
                 font=(FONT, 9)).pack(anchor="w")
        gbtns = tk.Frame(right, bg=BG)
        gbtns.pack(fill="x", pady=4)
        self._btn(gbtns, "Scan", self.scan_groups).pack(side="left")
        self._btn(gbtns, "All", lambda: self._groups_all(True)).pack(
            side="left", padx=4)
        self._btn(gbtns, "None", lambda: self._groups_all(False)).pack(
            side="left")
        self.groups_box = tk.Frame(right, bg=FIELD, width=270)
        self.groups_box.pack(fill="both", expand=True, pady=(4, 0))
        self.group_vars = {}
        btns = tk.Frame(self, bg=BG)
        btns.pack(fill="x", padx=18, pady=(0, 6))
        self._btn(btns, "Run Now", self.run_now).pack(side="left")
        self._btn(btns, "Stop", self.stop_run).pack(side="left",
                                                    padx=(8, 0))
        self.state_lbl = tk.Label(btns, text="", bg=BG, fg=DIM,
                                  font=(FONT, 9))
        self.state_lbl.pack(side="right")

    def _btn(self, parent, text, cmd):
        b = tk.Label(parent, text=text, bg=FIELD, fg=TEXT, cursor="hand2",
                     font=(FONT, 9, "bold"), padx=12, pady=5)
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.configure(fg=self.spec["accent"]))
        b.bind("<Leave>", lambda e: b.configure(fg=TEXT))
        return b

    # ── folder / list (LinkedIn · Meta · YouTube) ─────────────────────
    def browse(self):
        d = filedialog.askdirectory(
            initialdir=self.folder_var.get() or store_dir())
        if d:
            self.folder_var.set(d)
            self.load_folder()

    def load_folder(self):
        folder = self.folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showinfo(APP_NAME, "Pick a valid campaign folder.")
            return
        try:
            self.posts = scan_campaign(folder)
        except Exception as exc:
            messagebox.showerror(APP_NAME, "Could not read campaign: %s"
                                 % exc)
            return
        cfg = self.app.cfg
        cfg["folder_" + self.plat] = folder
        save_cfg(cfg)
        self.refresh_tree()
        self.app.log("%s: %d days found in %s"
                     % (self.spec["label"], len(self.posts),
                        os.path.basename(folder)))

    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        slots = self.app.slots
        folder = self.folder_var.get()
        items = platform_items(self.plat, self.posts, slots,
                               {"folder": folder})
        self.rows = {it["_key"]: it for it in items}
        for it in items:
            media = ("video" if (it["media"] and it["media"][0].lower()
                                 .endswith(VIDEO_TYPES))
                     else ("image" if it["media"] else "—"))
            sched = ("%s %s" % (it["date"], it["time"])
                     if it["date"] else "")
            status = {"completed": "✓ done",
                      "failed": "failed",
                      "running": "running…"}.get(it["status"],
                                                 it["status"] or "")
            tags = ()
            if it["status"] == "completed":
                tags = ("done",)
            elif it["status"] == "failed":
                tags = ("failed",)
            self.tree.insert("", "end", iid=it["_key"], tags=tags,
                             values=("☐" if it["status"] != "completed"
                                     else "✓",
                                     "Day %d" % it["day"], it["title"],
                                     media, sched, status))

    def _on_click(self, event):
        item = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if item and col == "#1":
            v = self.tree.set(item, "tick")
            self.tree.set(item, "tick", "☑" if v == "☐" else "☐")

    def selected_items(self):
        out = []
        for iid in self.tree.get_children():
            if self.tree.set(iid, "tick") == "☑":
                out.append(dict(self.rows[iid]))
        return out

    def select_all(self):
        for iid in self.tree.get_children():
            if self.tree.set(iid, "tick") != "✓":
                self.tree.set(iid, "tick", "☑")

    def clear_sel(self):
        for iid in self.tree.get_children():
            if self.tree.set(iid, "tick") == "☑":
                self.tree.set(iid, "tick", "☐")

    # ── scheduling ────────────────────────────────────────────────────
    def schedule_dialog(self):
        sel = self.selected_items()
        if not sel:
            messagebox.showinfo(APP_NAME, "Tick the posts to schedule.")
            return
        win = tk.Toplevel(self)
        win.title("Schedule %d posts — %s" % (len(sel),
                                              self.spec["label"]))
        win.configure(bg=BG)
        win.transient(self.winfo_toplevel())
        win.grab_set()
        tk.Label(win, text="Start date (YYYY-MM-DD)", bg=BG, fg=DIM,
                 font=(FONT, 9)).grid(row=0, column=0, sticky="w",
                                      padx=16, pady=(14, 4))
        e1 = tk.Entry(win, bg=FIELD, fg=TEXT, bd=0, font=(MONO, 10),
                      width=16)
        e1.insert(0, datetime.now().strftime("%Y-%m-%d"))
        e1.grid(row=0, column=1, padx=10, pady=(14, 4))
        tk.Label(win, text="Posting time (HH:MM)", bg=BG, fg=DIM,
                 font=(FONT, 9)).grid(row=1, column=0, sticky="w",
                                      padx=16, pady=4)
        e2 = tk.Entry(win, bg=FIELD, fg=TEXT, bd=0, font=(MONO, 10),
                      width=16)
        e2.insert(0, self.app.cfg.get("post_time", "09:00"))
        e2.grid(row=1, column=1, padx=10, pady=4)
        tk.Label(win, text="Interval (days)", bg=BG, fg=DIM,
                 font=(FONT, 9)).grid(row=2, column=0, sticky="w",
                                      padx=16, pady=4)
        e3 = tk.Entry(win, bg=FIELD, fg=TEXT, bd=0, font=(MONO, 10),
                      width=16)
        e3.insert(0, "1")
        e3.grid(row=2, column=1, padx=10, pady=4)

        def ok():
            try:
                start = datetime.strptime(e1.get().strip(), "%Y-%m-%d")
                hhmm = e2.get().strip()
                datetime.strptime(hhmm, "%H:%M")
                step = max(1, int(e3.get().strip() or "1"))
            except Exception:
                messagebox.showerror(APP_NAME, "Bad date/time/interval.")
                return
            self.app.cfg["post_time"] = hhmm
            save_cfg(self.app.cfg)
            slots = self.app.slots
            for i, it in enumerate(sel):
                when = start + timedelta(days=step * i)
                slots[it["_key"]] = {"date": when.strftime("%Y-%m-%d"),
                                     "time": hhmm,
                                     "plat": self.plat,
                                     "title": it["title"]}
            save_schedule(slots)
            self.refresh_tree()
            self.app.log("%s: %d posts scheduled from %s (native "
                         "scheduling — publishes even if the app is "
                         "closed)" % (self.spec["label"], len(sel),
                                      start.strftime("%Y-%m-%d")), LIME)
            win.destroy()
        self._btn(win, "Schedule", ok).grid(row=3, column=0, columnspan=2,
                                            pady=12)

    # ── run ───────────────────────────────────────────────────────────
    def run_now(self, pre_scheduled=False):
        if self.busy:
            messagebox.showinfo(APP_NAME, "A run is already active.")
            return
        if self.plat == "fbg":
            self._run_fbg()
            return
        sel = self.selected_items()
        if not pre_scheduled:
            if not sel:
                messagebox.showinfo(APP_NAME, "Tick at least one post.")
                return
            if not messagebox.askyesno(
                    APP_NAME,
                    "Schedule %d ticked posts starting today via %s?"
                    % (len(sel), self.spec["label"])):
                return
            slots = self.app.slots
            hhmm = self.app.cfg.get("post_time", "09:00")
            start = datetime.now()
            for i, it in enumerate(sel):
                when = start + timedelta(days=i)
                slots[it["_key"]] = {"date": when.strftime("%Y-%m-%d"),
                                     "time": hhmm, "plat": self.plat,
                                     "title": it["title"]}
            save_schedule(slots)
            self.refresh_tree()
        else:
            sel = [it for it in sel if it["date"]]
        items = []
        for it in sel:
            if it["status"] == "completed":
                continue
            if not it["date"]:
                continue
            items.append(it)
        if not items:
            self.app.log("%s: nothing to run (all done)" % self.spec["label"],
                         WARN)
            return
        self.busy = True
        self.stop.clear()
        self.state_lbl.configure(text="running — Chrome will open…",
                                 fg=self.spec["accent"])
        threading.Thread(target=self._work, args=(items,),
                         daemon=True).start()

    def _work(self, items):
        wf = self.spec["wf"]
        log = self.app.log

        def stop_check():
            return self.stop.is_set()

        def item_log(m, c=None):
            log("[%s] %s" % (self.spec["label"], m), c)

        try:
            res = wf.run_queue(items, {"dash_url": ""},
                               store_dir(), item_log, stop_check)
            item_log("done — %d scheduled, %d failed, %d skipped"
                     % (res["done"], res["failed"], res["skipped"]),
                     LIME if not res["failed"] else WARN)
        except Exception as exc:
            item_log("run failed: %s" % exc, DANGER)
            if "sign in" in str(exc).lower():
                messagebox.showinfo(
                    APP_NAME,
                    "Sign in to %s in the Chrome window the app opened, "
                    "then run again." % self.spec["label"].title())
        finally:
            self.busy = False
            self.winfo_toplevel().after(
                0, lambda: self.state_lbl.configure(text="idle", fg=DIM))
            if self.plat != "fbg":
                self.winfo_toplevel().after(0, self.refresh_tree)

    def stop_run(self):
        self.stop.set()
        self.app.log("%s: stop requested" % self.spec["label"], WARN)

    # ── FB GROUPS specifics ───────────────────────────────────────────
    def add_media(self):
        paths = filedialog.askopenfilenames(
            filetypes=[("Media", "*.png *.jpg *.jpeg *.webp *.gif "
                        "*.mp4 *.mov *.webm *.m4v")])
        if paths:
            self.app.cfg["fbg_media"] = list(paths)
            save_cfg(self.app.cfg)
            self.media_lbl.configure(
                text="%d file(s): %s…" % (len(paths),
                                          os.path.basename(paths[0])))

    def scan_groups(self):
        self.state_lbl.configure(text="scanning groups…", fg=CYAN)

        def work():
            wf = fbg_workflow
            try:
                drv = wf.ensure_driver(wf.DEFAULT_DASH_URL, store_dir(),
                                       self.app.log)
                groups = wf.list_groups(drv, self.app.log)
                drv.quit()
            except Exception as exc:
                self.app.log("group scan failed: %s" % exc, DANGER)
                groups = []
            self.winfo_toplevel().after(
                0, lambda: self._show_groups(groups))

        threading.Thread(target=work, daemon=True).start()

    def _show_groups(self, groups):
        for w in self.groups_box.winfo_children():
            w.destroy()
        self.group_vars = {}
        saved = set(self.app.cfg.get("fbg_groups", []))
        for name in groups:
            var = tk.BooleanVar(value=name in saved)
            cb = tk.Checkbutton(self.groups_box, text=name, variable=var,
                                bg=FIELD, fg=TEXT, selectcolor=FIELD,
                                activebackground=FIELD,
                                font=(FONT, 9), anchor="w")
            cb.pack(fill="x", padx=6, pady=1)
            self.group_vars[name] = var
        self.state_lbl.configure(
            text="%d groups found" % len(groups) if groups else "idle",
            fg=DIM if groups else WARN)

    def _groups_all(self, on):
        for var in self.group_vars.values():
            var.set(on)

    def _run_fbg(self):
        caption = self.cap_txt.get("1.0", "end").strip()
        tags = self.tag_txt.get("1.0", "end").strip()
        if not caption and not tags:
            messagebox.showinfo(APP_NAME, "Write a caption first.")
            return
        groups = [n for n, v in self.group_vars.items() if v.get()]
        if not groups:
            messagebox.showinfo(APP_NAME, "Scan and tick groups first.")
            return
        self.app.cfg["fbg_groups"] = groups
        save_cfg(self.app.cfg)
        media = self.app.cfg.get("fbg_media", [])
        items = [{"day": 1, "title": caption[:60], "text": caption,
                  "hashtags": tags, "media": list(media),
                  "_key": "fbg|%d" % int(time.time())}]
        self.busy = True
        self.stop.clear()
        self.state_lbl.configure(text="posting to %d groups…" % len(groups),
                                 fg=LIME)
        threading.Thread(target=self._work,
                         args=(items, {"groups": groups}),
                         daemon=True).start()

    # fbg override: pass cfg through
    def _work(self, items, cfg_override=None):
        wf = self.spec["wf"]
        cfg = cfg_override or {}
        log = self.app.log

        def stop_check():
            return self.stop.is_set()

        def item_log(m, c=None):
            log("[%s] %s" % (self.spec["label"], m), c)

        try:
            res = wf.run_queue(items, cfg, store_dir(), item_log,
                               stop_check)
            item_log("done — %d posted, %d failed, %d skipped"
                     % (res["done"], res["failed"], res["skipped"]),
                     LIME if not res["failed"] else WARN)
        except Exception as exc:
            item_log("run failed: %s" % exc, DANGER)
        finally:
            self.busy = False
            self.winfo_toplevel().after(
                0, lambda: self.state_lbl.configure(text="idle", fg=DIM))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("%s  v%s" % (APP_NAME, VERSION))
        self.configure(bg=BG)
        self.cfg = load_cfg()
        self.slots = load_schedule()
        self._q = queue.Queue()
        self.busy = False
        # centered on open + force-maximized (owner standard)
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(1240, sw - 40), min(820, sh - 60)
        self.geometry("%dx%d+%d+%d" % (w, h, (sw - w) // 2,
                                       (sh - h) // 2))

        def _reassert_zoomed(_w=self):
            try:
                if _w.state() != "zoomed":
                    _w.state("zoomed")
            except Exception:
                pass
        for _d in (10, 250, 800, 1500):
            self.after(_d, _reassert_zoomed)
        self.minsize(980, 640)
        self._header()
        self.body = tk.Frame(self, bg=BG)
        self.body.pack(fill="both", expand=True)
        self._tabs()
        self._logbar()
        self._footer()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        threading.Thread(target=self._scheduler_loop, daemon=True).start()
        self.after(200, self._drain)

    # ── chrome ────────────────────────────────────────────────────────
    def _header(self):
        bar = tk.Frame(self, bg=PANEL)
        bar.pack(fill="x")
        inner = tk.Frame(bar, bg=PANEL)
        inner.pack(fill="x", padx=18, pady=12)
        tk.Label(inner, text="3SVERSE", bg=PANEL, fg=CYAN,
                 font=(HEAD_FONT, 17, "bold")).pack(side="left")
        tk.Label(inner, text=" SOCIAL MEDIA POSTER", bg=PANEL, fg=TEXT,
                 font=(HEAD_FONT, 17, "bold")).pack(side="left")
        tk.Label(inner, text="v%s" % VERSION, bg=PANEL, fg=DIM,
                 font=(MONO, 10)).pack(side="left", padx=(10, 0))
        about = tk.Label(inner, text="About", bg=PANEL, fg=PERI,
                         cursor="hand2", font=(FONT, 9, "underline"))
        about.pack(side="right")
        about.bind("<Button-1>", lambda e: self.about())
        make_grad_bar(bar, height=3).pack(fill="x")

    def _tabs(self):
        self.tabbar = tk.Frame(self.body, bg=PANEL)
        self.tabbar.pack(fill="x")
        self.frames = {}
        self.tab_btns = {}
        container = tk.Frame(self.body, bg=BG)
        container.pack(fill="both", expand=True)
        for i, (key, spec) in enumerate(PLATS.items()):
            tab = PlatformTab(self, key, container)
            self.frames[key] = tab
            b = tk.Label(self.tabbar, text="  %s  " % spec["label"],
                         bg=PANEL, fg=DIM, cursor="hand2",
                         font=(HEAD_FONT, 11, "bold"), pady=9)
            b.pack(side="left", padx=(6 if i == 0 else 2, 2))
            b.bind("<Button-1>", lambda e, k=key: self.show_tab(k))
            self.tab_btns[key] = b
        self.show_tab("linkedin")

    def show_tab(self, key):
        for k, tab in self.frames.items():
            if k == key:
                tab.pack(fill="both", expand=True)
            else:
                tab.pack_forget()
        for k, b in self.tab_btns.items():
            b.configure(fg=PLATS[k]["accent"] if k == key else DIM,
                        bg=FIELD if k == key else PANEL)

    def _logbar(self):
        bar = tk.Frame(self, bg=PANEL)
        bar.pack(fill="x", side="bottom")
        self.log_lbl = tk.Label(bar, text="ready — load a campaign folder "
                                          "and schedule", bg=PANEL, fg=DIM,
                                font=(MONO, 9), anchor="w")
        self.log_lbl.pack(fill="x", padx=14, pady=7)

    def _footer(self):
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", side="bottom")
        tk.Label(bar, text="Developed by www.3SVerse.com (c) 2026 · "
                           "independent vendor — not affiliated with "
                           "LinkedIn, Meta, YouTube or Facebook",
                 bg=BG, fg=DIM, font=(FONT, 8)).pack(pady=4)

    # ── log ───────────────────────────────────────────────────────────
    def log(self, msg, color=None):
        self._q.put((datetime.now().strftime("%H:%M:%S") + "  " + msg,
                     color))

    def _drain(self):
        try:
            while True:
                msg, color = self._q.get_nowait()
                self.log_lbl.configure(text=msg, fg=color or DIM)
        except queue.Empty:
            pass
        self.after(300, self._drain)

    # ── shared 15 s scheduler (MISSED flags, nothing twice) ──────────
    def _scheduler_loop(self):
        while True:
            try:
                self._tick_schedule()
            except Exception:
                pass
            time.sleep(15)

    def _tick_schedule(self):
        now = datetime.now()
        slots = self.slots
        changed = False
        for key, s in list(slots.items()):
            plat = s.get("plat")
            if plat not in ("linkedin", "meta", "youtube"):
                continue
            if s.get("fired") or s.get("missed"):
                continue
            try:
                due = datetime.strptime(
                    "%s %s" % (s["date"], s["time"]), "%Y-%m-%d %H:%M")
            except Exception:
                continue
            if due <= now:
                if now - due > timedelta(minutes=30):
                    s["missed"] = True
                    changed = True
                    self.log("MISSED slot %s %s (%s) — tick it and use "
                             "Run Now" % (s["date"], s["time"],
                                          s.get("title", "")), WARN)
                    continue
                s["fired"] = True
                changed = True
                self.log("scheduler firing %s slot: %s (%s)"
                         % (plat, s.get("title", ""), s["date"]), CYAN)
                self._fire_slot(plat, key, s)
        if changed:
            save_schedule(slots)

    def _fire_slot(self, plat, key, s):
        tab = self.frames.get(plat)
        wf = PLATS[plat]["wf"]
        posts = tab.posts
        folder = (tab.folder_var.get() if plat != "fbg" else "")
        items = platform_items(plat, posts, {key: s},
                               {"folder": folder})
        it = next((x for x in items if x["_key"] == key), None)
        if it is None or not it["date"]:
            self.log("[%s] slot fired but post not loaded — load the "
                     "folder and re-schedule" % plat, WARN)
            return
        threading.Thread(target=self._fire_work, args=(plat, wf, [it]),
                         daemon=True).start()

    def _fire_work(self, plat, wf, items):
        try:
            res = wf.run_queue(items, {}, store_dir(),
                               lambda m, c=None: self.log(
                                   "[%s] %s" % (plat, m), c))
            self.log("[%s] scheduler run — %d done, %d failed"
                     % (plat, res["done"], res["failed"]),
                     LIME if not res["failed"] else WARN)
        except Exception as exc:
            self.log("[%s] scheduler run failed: %s" % (plat, exc),
                     DANGER)

    # ── about / close ─────────────────────────────────────────────────
    def about(self):
        messagebox.showinfo(
            "About — %s" % APP_NAME,
            "%s v%s\n\nFour tabs, four real extension workflows through "
            "your own logged-in Chrome:\n\n"
            "· LINKEDIN — Campaign Uploader v1.3.0 workflow (image or "
            "video, schedule-first-then-caption)\n"
            "· META — Planner Scheduler v1.6.0 (Reels / image posts / "
            "Stories → FB Page + Instagram)\n"
            "· YOUTUBE — Campaign Uploader (Studio upload, Shorts rule, "
            "hashtags as tags)\n"
            "· FB GROUPS — Group Posting v1.6.0 (caption + hashtags + "
            "media → ticked groups)\n\n"
            "Own Chrome profile per platform · verify-every-step · "
            "resume-safe progress · native scheduling (publishes even "
            "when the app is closed) · MISSED flags, never double-posts.\n\n"
            "Generate the campaign with make_campaign.py or "
            "MEDIA_PROMPT.md, load the platform folder, schedule.\n\n"
            "Developed by www.3SVerse.com (c) 2026" % (APP_NAME, VERSION))

    def on_close(self):
        try:
            save_schedule(self.slots)
            save_cfg(self.cfg)
        except Exception:
            pass
        self.destroy()


def main():
    if sys.platform == "win32":
        try:
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    App().mainloop()


if __name__ == "__main__":
    main()
