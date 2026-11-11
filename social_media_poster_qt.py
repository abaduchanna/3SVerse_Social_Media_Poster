#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════════════
# 3SVERSE SOCIAL MEDIA POSTER (PySide6/Qt build) — one console, four platform
# tabs. Same workflows as the Tkinter build (social_media_poster.py); only
# the UI toolkit differs. See that file's module docstring for the full
# feature description.
#
# Branding note: the Tkinter build's animated ring/orb brand canvas
# (branding_runtime.BrandAnimation) is decorative and is NOT reproduced
# here - this port focuses on functional parity (four tabs, folder
# scan/load, scheduling, FB Groups posting) over the decorative animation,
# given the scope of this migration pass. The native dark Windows title
# bar IS reproduced (same DWM approach, see native_titlebar_qt.py).
# ═══════════════════════════════════════════════════════════════════════════
import base64
import io
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta

import linkedin_bridge
import meta_workflow
import youtube_workflow
import fbg_workflow

APP_NAME = "3SVerse Social Media Poster"
VERSION = "3.0.2"

# Same brand palette as linkedin_poster.py's BG/PANEL/.../GRAD constants -
# copied as literal values instead of `import linkedin_poster as lp` because
# linkedin_poster.py imports tkinter at module level (its own standalone
# __main__ tool), which would reintroduce a Tk dependency into this
# otherwise tkinter-free Qt build for zero functional benefit (only these
# color constants were ever used from it here).
BG = "#07060b"
PANEL = "#0d0c14"
FIELD = "#12101a"
BORDER = "#232130"
TEXT = "#f5f1e6"
DIM = "#9b97b3"
CYAN = "#6ee7ef"
PERI = "#78a6ff"
MAGENTA = "#e44bd7"
LIME = "#c7ef70"
DANGER = "#ef6a52"
WARN = "#f5c518"
GRAD = (CYAN, PERI, MAGENTA)
FONT = "Segoe UI"
MONO = "Consolas"

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

LOGO_FILES = {"linkedin": "brand_linkedin.png", "meta": "brand_meta.png",
              "youtube": "brand_youtube.png", "fbg": "brand_facebook.png"}


def _script_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _asset_path(name):
    here = _script_dir()
    for base in (here, getattr(sys, "_MEIPASS", here)):
        p = os.path.join(base, name)
        if os.path.exists(p):
            return p
    return os.path.join(here, name)


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
# Campaign folder scanner — UNCHANGED from the Tkinter build (pure logic)
# ═══════════════════════════════════════════════════════════════════════════
DAY_NUM = re.compile(r"day[-_ ]?(\d{1,3})|reel[-_ ]?(\d{1,3})", re.I)
DAY_HEAD = re.compile(r"^##\s*Day\s*(\d{1,3})\s*[—-]\s*(.*)$", re.I | re.M)
ANN = re.compile(r"^\*\*(.+?):\*\*\s*(.*)$")
FMT_LINE = re.compile(r"^Format:\s*(\S[\w -]*)$", re.I)
TAG_RE = re.compile(r"^(#[A-Za-z0-9_]+\s*)+$")


def scan_campaign(folder):
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
                if fm:
                    meta["format"] = fm.group(1).strip()
                    continue
                if TAG_RE.match(s):
                    tags.append(s)
                    continue
                body.append(line)
        flush()

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
                d["video"] = path
            elif ext in MEDIA_TYPES:
                d = days.setdefault(day, _blank(day))
                if not d["image"]:
                    d["image"] = path
    return [days[d] for d in sorted(days)]


def platform_items(plat, posts, slots, cfg):
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


# ==========================================================
# QT UI LAYER
# ==========================================================
from PySide6.QtCore import Qt, QObject, Signal, QTimer
from PySide6.QtGui import QIcon, QPixmap, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QTextEdit, QFileDialog, QMessageBox, QDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QScrollArea,
    QGridLayout, QFrame
)

try:
    from native_titlebar_qt import sync_titlebar_qt
except ImportError:
    def sync_titlebar_qt(window, dark=True):
        pass


def _qss():
    return f"""
        QWidget {{ background: {BG}; color: {TEXT}; font-family: "{FONT}"; }}
        QLabel {{ background: transparent; }}
        QLineEdit, QTextEdit {{
            background: {FIELD}; color: {TEXT}; border: none; border-radius: 3px;
            padding: 5px; selection-background-color: {CYAN};
        }}
        QPushButton {{
            background: {FIELD}; color: {TEXT}; border: none; border-radius: 3px;
            padding: 6px 14px; font-weight: bold;
        }}
        QPushButton:hover {{ color: {CYAN}; }}
        QTableWidget {{
            background: {FIELD}; color: {TEXT}; gridline-color: {BORDER};
            border: none;
        }}
        QHeaderView::section {{
            background: {PANEL}; color: {DIM}; border: none; padding: 4px;
            font-family: "{MONO}"; font-weight: bold;
        }}
        QCheckBox {{ background: transparent; }}
        QScrollArea {{ border: none; }}
    """


class RunBridge(QObject):
    log = Signal(str, str)   # message, color (hex or "")
    state = Signal(str, str)  # state text, color


class PlatformTab(QWidget):
    def __init__(self, app, plat):
        super().__init__()
        self.app = app
        self.plat = plat
        self.spec = PLATS[plat]
        self.posts = []
        self.busy = False
        self.stop_event = threading.Event()
        self.rows = {}
        self.group_vars = {}
        self._bridge = RunBridge()
        self._bridge.log.connect(self._on_log)
        self._bridge.state.connect(self._on_state)
        if plat != "fbg":
            self._build()
        else:
            self._build_fbg()

    def _logo_label(self, height=20):
        path = _asset_path(LOGO_FILES.get(self.plat, ""))
        if os.path.exists(path):
            pix = QPixmap(path)
            if not pix.isNull():
                pix = pix.scaledToHeight(height, Qt.SmoothTransformation)
                lbl = QLabel()
                lbl.setPixmap(pix)
                return lbl
        return None

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 10, 18, 4)

        top = QHBoxLayout()
        logo = self._logo_label(22)
        head_lbl = QLabel(("  " if logo else "") + self.spec["label"])
        head_lbl.setStyleSheet(f"color: {self.spec['accent']}; font-weight: bold; font-size: 16px;")
        if logo:
            top.addWidget(logo)
        top.addWidget(head_lbl)
        sub = QLabel("  ·  extension workflow in your own Chrome")
        sub.setStyleSheet(f"color: {DIM}; font-size: 9pt;")
        top.addWidget(sub)
        top.addStretch(1)
        outer.addLayout(top)

        row = QHBoxLayout()
        flbl = QLabel("Campaign folder")
        flbl.setStyleSheet(f"color: {DIM};")
        row.addWidget(flbl)
        self.folder_edit = QLineEdit(self.app.cfg.get("folder_" + self.plat, ""))
        row.addWidget(self.folder_edit, 1)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse)
        row.addWidget(browse_btn)
        load_btn = QPushButton("Load")
        load_btn.clicked.connect(self.load_folder)
        row.addWidget(load_btn)
        outer.addLayout(row)

        wants = QLabel("Wants: %s" % self.spec["needs"])
        wants.setStyleSheet(f"color: {DIM}; font-size: 8pt;")
        outer.addWidget(wants)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["", "Day", "Title", "Media", "Schedule", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.cellClicked.connect(self._on_cell_click)
        outer.addWidget(self.table, 1)

        btns = QHBoxLayout()
        b1 = QPushButton("Select All")
        b1.clicked.connect(self.select_all)
        btns.addWidget(b1)
        b2 = QPushButton("Clear")
        b2.clicked.connect(self.clear_sel)
        btns.addWidget(b2)
        b3 = QPushButton("Run Now")
        b3.clicked.connect(self.run_now)
        btns.addWidget(b3)
        b4 = QPushButton("Schedule...")
        b4.clicked.connect(self.schedule_dialog)
        btns.addWidget(b4)
        b5 = QPushButton("Stop")
        b5.clicked.connect(self.stop_run)
        btns.addWidget(b5)
        btns.addStretch(1)
        self.state_lbl = QLabel("")
        self.state_lbl.setStyleSheet(f"color: {DIM};")
        btns.addWidget(self.state_lbl)
        outer.addLayout(btns)

    def _build_fbg(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        outer = QHBoxLayout()
        outer.setContentsMargins(18, 10, 18, 6)
        root.addLayout(outer, 1)

        left = QVBoxLayout()
        cap_lbl = QLabel("Caption")
        cap_lbl.setStyleSheet(f"color: {DIM};")
        left.addWidget(cap_lbl)
        self.cap_txt = QTextEdit()
        self.cap_txt.setStyleSheet(f"font-family: {MONO};")
        left.addWidget(self.cap_txt, 3)
        tag_lbl = QLabel("Hashtags")
        tag_lbl.setStyleSheet(f"color: {DIM};")
        left.addWidget(tag_lbl)
        self.tag_txt = QTextEdit()
        self.tag_txt.setStyleSheet(f"font-family: {MONO};")
        self.tag_txt.setMaximumHeight(70)
        left.addWidget(self.tag_txt)
        mrow = QHBoxLayout()
        add_btn = QPushButton("Add media...")
        add_btn.clicked.connect(self.add_media)
        mrow.addWidget(add_btn)
        self.media_lbl = QLabel("no media (text-only post)")
        self.media_lbl.setStyleSheet(f"color: {DIM}; font-size: 8pt;")
        mrow.addWidget(self.media_lbl)
        mrow.addStretch(1)
        left.addLayout(mrow)
        outer.addLayout(left, 1)

        right = QVBoxLayout()
        glbl = QLabel("Groups (joined)")
        glbl.setStyleSheet(f"color: {DIM};")
        right.addWidget(glbl)
        gbtns = QHBoxLayout()
        scan_btn = QPushButton("Scan")
        scan_btn.clicked.connect(self.scan_groups)
        gbtns.addWidget(scan_btn)
        all_btn = QPushButton("All")
        all_btn.clicked.connect(lambda: self._groups_all(True))
        gbtns.addWidget(all_btn)
        none_btn = QPushButton("None")
        none_btn.clicked.connect(lambda: self._groups_all(False))
        gbtns.addWidget(none_btn)
        right.addLayout(gbtns)
        self.groups_scroll = QScrollArea()
        self.groups_scroll.setWidgetResizable(True)
        self.groups_container = QWidget()
        self.groups_layout = QVBoxLayout(self.groups_container)
        self.groups_layout.setAlignment(Qt.AlignTop)
        self.groups_scroll.setWidget(self.groups_container)
        right.addWidget(self.groups_scroll, 1)
        outer.addLayout(right, 0)

        btns = QHBoxLayout()
        run_btn = QPushButton("Run Now")
        run_btn.clicked.connect(self.run_now)
        btns.addWidget(run_btn)
        stop_btn = QPushButton("Stop")
        stop_btn.clicked.connect(self.stop_run)
        btns.addWidget(stop_btn)
        btns.addStretch(1)
        self.state_lbl = QLabel("")
        self.state_lbl.setStyleSheet(f"color: {DIM};")
        btns.addWidget(self.state_lbl)
        root.addLayout(btns)

    # ── folder / list ───────────────────────────────────────────────
    def browse(self):
        d = QFileDialog.getExistingDirectory(self, "Select campaign folder",
                                              self.folder_edit.text() or store_dir())
        if d:
            self.folder_edit.setText(d)
            self.load_folder()

    def load_folder(self):
        folder = self.folder_edit.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.information(self, APP_NAME, "Pick a valid campaign folder.")
            return
        try:
            self.posts = scan_campaign(folder)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, "Could not read campaign: %s" % exc)
            return
        cfg = self.app.cfg
        cfg["folder_" + self.plat] = folder
        save_cfg(cfg)
        self.refresh_table()
        self.app.log("%s: %d days found in %s"
                     % (self.spec["label"], len(self.posts), os.path.basename(folder)))

    def refresh_table(self):
        slots = self.app.slots
        folder = self.folder_edit.text()
        items = platform_items(self.plat, self.posts, slots, {"folder": folder})
        self.rows = {it["_key"]: it for it in items}
        self.table.setRowCount(0)
        for it in items:
            media = ("video" if (it["media"] and it["media"][0].lower().endswith(VIDEO_TYPES))
                     else ("image" if it["media"] else "—"))
            sched = ("%s %s" % (it["date"], it["time"])) if it["date"] else ""
            status = {"completed": "done", "failed": "failed",
                      "running": "running..."}.get(it["status"], it["status"] or "")
            r = self.table.rowCount()
            self.table.insertRow(r)
            tick_item = QTableWidgetItem("" if it["status"] != "completed" else "v")
            tick_item.setData(Qt.UserRole, it["_key"])
            self.table.setItem(r, 0, tick_item)
            self.table.setItem(r, 1, QTableWidgetItem("Day %d" % it["day"]))
            self.table.setItem(r, 2, QTableWidgetItem(it["title"]))
            self.table.setItem(r, 3, QTableWidgetItem(media))
            self.table.setItem(r, 4, QTableWidgetItem(sched))
            status_item = QTableWidgetItem(status)
            if it["status"] == "completed":
                status_item.setForeground(Qt.green)
            elif it["status"] == "failed":
                status_item.setForeground(Qt.red)
            self.table.setItem(r, 5, status_item)

    def _on_cell_click(self, row, col):
        if col == 0:
            item = self.table.item(row, 0)
            key = item.data(Qt.UserRole)
            if self.rows.get(key, {}).get("status") == "completed":
                return
            item.setText("X" if item.text() != "X" else "")

    def selected_items(self):
        out = []
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item.text() == "X":
                key = item.data(Qt.UserRole)
                out.append(dict(self.rows[key]))
        return out

    def select_all(self):
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item.text() != "v":
                item.setText("X")

    def clear_sel(self):
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item.text() == "X":
                item.setText("")

    # ── scheduling ────────────────────────────────────────────────────
    def schedule_dialog(self):
        sel = self.selected_items()
        if not sel:
            QMessageBox.information(self, APP_NAME, "Tick the posts to schedule.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Schedule %d posts — %s" % (len(sel), self.spec["label"]))
        dlg.setStyleSheet(_qss())
        grid = QGridLayout(dlg)
        grid.addWidget(QLabel("Start date (YYYY-MM-DD)"), 0, 0)
        e1 = QLineEdit(datetime.now().strftime("%Y-%m-%d"))
        grid.addWidget(e1, 0, 1)
        grid.addWidget(QLabel("Posting time (HH:MM)"), 1, 0)
        e2 = QLineEdit(self.app.cfg.get("post_time", "09:00"))
        grid.addWidget(e2, 1, 1)
        grid.addWidget(QLabel("Interval (days)"), 2, 0)
        e3 = QLineEdit("1")
        grid.addWidget(e3, 2, 1)

        def ok():
            try:
                start = datetime.strptime(e1.text().strip(), "%Y-%m-%d")
                hhmm = e2.text().strip()
                datetime.strptime(hhmm, "%H:%M")
                step = max(1, int(e3.text().strip() or "1"))
            except Exception:
                QMessageBox.critical(dlg, APP_NAME, "Bad date/time/interval.")
                return
            self.app.cfg["post_time"] = hhmm
            save_cfg(self.app.cfg)
            slots = self.app.slots
            for i, it in enumerate(sel):
                when = start + timedelta(days=step * i)
                slots[it["_key"]] = {"date": when.strftime("%Y-%m-%d"),
                                     "time": hhmm, "plat": self.plat, "title": it["title"]}
            save_schedule(slots)
            self.refresh_table()
            self.app.log("%s: %d posts scheduled from %s (native scheduling — "
                        "publishes even if the app is closed)"
                        % (self.spec["label"], len(sel), start.strftime("%Y-%m-%d")), LIME)
            dlg.accept()

        sched_btn = QPushButton("Schedule")
        sched_btn.clicked.connect(ok)
        grid.addWidget(sched_btn, 3, 0, 1, 2)
        dlg.exec()

    # ── run ───────────────────────────────────────────────────────────
    def run_now(self):
        if self.busy:
            QMessageBox.information(self, APP_NAME, "A run is already active.")
            return
        if self.plat == "fbg":
            self._run_fbg()
            return
        sel = self.selected_items()
        if not sel:
            QMessageBox.information(self, APP_NAME, "Tick at least one post.")
            return
        resp = QMessageBox.question(
            self, APP_NAME,
            "Schedule %d ticked posts starting today via %s?" % (len(sel), self.spec["label"]))
        if resp != QMessageBox.Yes:
            return
        slots = self.app.slots
        hhmm = self.app.cfg.get("post_time", "09:00")
        start = datetime.now()
        for i, it in enumerate(sel):
            when = start + timedelta(days=i)
            slots[it["_key"]] = {"date": when.strftime("%Y-%m-%d"), "time": hhmm,
                                 "plat": self.plat, "title": it["title"]}
        save_schedule(slots)
        self.refresh_table()
        items = []
        for it in sel:
            if it["status"] == "completed" or not it["date"]:
                continue
            items.append(it)
        if not items:
            self.app.log("%s: nothing to run (all done)" % self.spec["label"], WARN)
            return
        self.busy = True
        self.stop_event.clear()
        self.state_lbl.setText("running — Chrome will open...")
        self.state_lbl.setStyleSheet(f"color: {self.spec['accent']};")
        threading.Thread(target=self._work, args=(items,), daemon=True).start()

    def _work(self, items, cfg_override=None):
        wf = self.spec["wf"]
        cfg = cfg_override or {}

        def stop_check():
            return self.stop_event.is_set()

        def item_log(m, c=None):
            self._bridge.log.emit("[%s] %s" % (self.spec["label"], m), c or "")

        try:
            res = wf.run_queue(items, cfg, store_dir(), item_log, stop_check)
            item_log("done — %d scheduled/posted, %d failed, %d skipped"
                     % (res["done"], res["failed"], res["skipped"]),
                     LIME if not res["failed"] else WARN)
        except Exception as exc:
            item_log("run failed: %s" % exc, DANGER)
        finally:
            self.busy = False
            self._bridge.state.emit("idle", DIM)
            if self.plat != "fbg":
                QTimer.singleShot(0, self.refresh_table)

    def _on_log(self, msg, color):
        self.app.log(msg, color or None)

    def _on_state(self, text, color):
        self.state_lbl.setText(text)
        self.state_lbl.setStyleSheet(f"color: {color};")

    def stop_run(self):
        self.stop_event.set()
        self.app.log("%s: stop requested" % self.spec["label"], WARN)

    # ── FB GROUPS specifics ───────────────────────────────────────────
    def add_media(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select media",
            filter="Media (*.png *.jpg *.jpeg *.webp *.gif *.mp4 *.mov *.webm *.m4v)")
        if paths:
            self.app.cfg["fbg_media"] = list(paths)
            save_cfg(self.app.cfg)
            self.media_lbl.setText("%d file(s): %s..." % (len(paths), os.path.basename(paths[0])))

    def scan_groups(self):
        self.state_lbl.setText("scanning groups...")
        self.state_lbl.setStyleSheet(f"color: {CYAN};")

        def work():
            wf = fbg_workflow
            try:
                drv = wf.ensure_driver(wf.DEFAULT_DASH_URL, store_dir(), lambda m, c=None: self._bridge.log.emit(m, c or ""))
                groups = wf.list_groups(drv, lambda m, c=None: self._bridge.log.emit(m, c or ""))
                drv.quit()
            except Exception as exc:
                self._bridge.log.emit("group scan failed: %s" % exc, DANGER)
                groups = []
            QTimer.singleShot(0, lambda: self._show_groups(groups))

        threading.Thread(target=work, daemon=True).start()

    def _show_groups(self, groups):
        while self.groups_layout.count():
            item = self.groups_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self.group_vars = {}
        saved = set(self.app.cfg.get("fbg_groups", []))
        for name in groups:
            cb = QCheckBox(name)
            cb.setChecked(name in saved)
            self.groups_layout.addWidget(cb)
            self.group_vars[name] = cb
        self.state_lbl.setText("%d groups found" % len(groups) if groups else "idle")
        self.state_lbl.setStyleSheet(f"color: {DIM if groups else WARN};")

    def _groups_all(self, on):
        for cb in self.group_vars.values():
            cb.setChecked(on)

    def _run_fbg(self):
        caption = self.cap_txt.toPlainText().strip()
        tags = self.tag_txt.toPlainText().strip()
        if not caption and not tags:
            QMessageBox.information(self, APP_NAME, "Write a caption first.")
            return
        groups = [n for n, cb in self.group_vars.items() if cb.isChecked()]
        if not groups:
            QMessageBox.information(self, APP_NAME, "Scan and tick groups first.")
            return
        self.app.cfg["fbg_groups"] = groups
        save_cfg(self.app.cfg)
        media = self.app.cfg.get("fbg_media", [])
        items = [{"day": 1, "title": caption[:60], "text": caption,
                  "hashtags": tags, "media": list(media),
                  "_key": "fbg|%d" % int(time.time())}]
        self.busy = True
        self.stop_event.clear()
        self.state_lbl.setText("posting to %d groups..." % len(groups))
        self.state_lbl.setStyleSheet(f"color: {LIME};")
        threading.Thread(target=self._work, args=(items, {"groups": groups}), daemon=True).start()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("%s  v%s" % (APP_NAME, VERSION))
        self.setStyleSheet(_qss())
        self.cfg = load_cfg()
        self.slots = load_schedule()
        self._log_bridge = RunBridge()
        self._log_bridge.log.connect(self._append_log)

        icon_path = _asset_path("3sverse_icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._header(outer)

        self.tabbar = QHBoxLayout()
        tabbar_wrap = QWidget()
        tabbar_wrap.setLayout(self.tabbar)
        outer.addWidget(tabbar_wrap)

        self.stack_container = QWidget()
        self.stack_layout = QVBoxLayout(self.stack_container)
        self.stack_layout.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.stack_container, 1)

        self.frames = {}
        self.tab_btns = {}
        for key, spec in PLATS.items():
            tab = PlatformTab(self, key)
            self.frames[key] = tab
            self.stack_layout.addWidget(tab)
            tab.hide()
            btn = QPushButton(spec["label"])
            btn.setFlat(True)
            btn.setStyleSheet(f"color: {DIM}; font-weight: bold; padding: 8px 10px;")
            btn.clicked.connect(lambda checked=False, k=key: self.show_tab(k))
            self.tabbar.addWidget(btn)
            self.tab_btns[key] = btn
        self.tabbar.addStretch(1)

        self._logbar(outer)
        self._footer(outer)

        self.show_tab("linkedin")
        self.resize(1240, 820)

        threading.Thread(target=self._scheduler_loop, daemon=True).start()

    def _header(self, outer):
        band = QVBoxLayout()
        band.setContentsMargins(24, 26, 24, 14)
        band.setAlignment(Qt.AlignHCenter)
        logo_path = _asset_path("3sverse_logo_header.png")
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path)
            if not pix.isNull():
                pix = pix.scaledToHeight(60, Qt.SmoothTransformation)
                lbl = QLabel()
                lbl.setPixmap(pix)
                lbl.setAlignment(Qt.AlignHCenter)
                band.addWidget(lbl)
        else:
            lbl = QLabel("3SVERSE")
            lbl.setStyleSheet(f"color: {CYAN}; font-weight: bold; font-size: 17pt;")
            lbl.setAlignment(Qt.AlignHCenter)
            band.addWidget(lbl)

        trow = QHBoxLayout()
        trow.setAlignment(Qt.AlignHCenter)
        l1 = QLabel("SOCIAL MEDIA ")
        l1.setStyleSheet(f"color: {TEXT}; font-size: 20pt;")
        trow.addWidget(l1)
        l2 = QLabel("POSTER")
        l2.setStyleSheet(f"color: {CYAN}; font-size: 20pt;")
        trow.addWidget(l2)
        trow_wrap = QWidget()
        trow_wrap.setLayout(trow)
        band.addWidget(trow_wrap, 0, Qt.AlignHCenter)

        eyebrow = QLabel("3SVERSE · FOUR-PLATFORM CAMPAIGN CONSOLE")
        eyebrow.setStyleSheet(f"color: {DIM}; font-family: {MONO}; font-size: 7pt; font-weight: bold;")
        eyebrow.setAlignment(Qt.AlignHCenter)
        band.addWidget(eyebrow)

        band_wrap = QWidget()
        band_wrap.setLayout(band)
        outer.addWidget(band_wrap)

        gradbar = QFrame()
        gradbar.setFixedHeight(3)
        gradbar.setStyleSheet(f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                              f"stop:0 {GRAD[0]}, stop:0.5 {GRAD[1]}, stop:1 {GRAD[2]});")
        outer.addWidget(gradbar)

    def show_tab(self, key):
        for k, tab in self.frames.items():
            if k == key:
                tab.show()
            else:
                tab.hide()
        for k, btn in self.tab_btns.items():
            btn.setStyleSheet(f"color: {PLATS[k]['accent'] if k == key else DIM}; "
                              f"background: {FIELD if k == key else 'transparent'}; "
                              f"font-weight: bold; padding: 8px 10px;")

    def _logbar(self, outer):
        bar = QFrame()
        bar.setStyleSheet(f"background: {PANEL};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 7, 14, 7)
        self.log_lbl = QLabel("ready — load a campaign folder and schedule")
        self.log_lbl.setStyleSheet(f"color: {DIM}; font-family: {MONO}; font-size: 9pt;")
        lay.addWidget(self.log_lbl)
        outer.addWidget(bar)

    def _footer(self, outer):
        bar = QFrame()
        bar.setStyleSheet(f"background: {PANEL}; border-top: 1px solid {BORDER};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 6, 18, 6)
        vendor = QLabel("Independent vendor — not affiliated with LinkedIn, Meta, YouTube or Facebook")
        vendor.setStyleSheet(f"color: {DIM}; font-size: 8pt;")
        lay.addWidget(vendor)
        lay.addStretch(1)
        center = QLabel("(c) 2026 3SVerse · Developed by www.3sverse.com")
        center.setStyleSheet(f"color: {DIM}; font-size: 8pt;")
        lay.addWidget(center)
        lay.addStretch(1)
        ver = QLabel("v%s" % VERSION)
        ver.setStyleSheet(f"color: {DIM}; font-family: {MONO}; font-size: 8pt;")
        lay.addWidget(ver)
        about = QPushButton("About")
        about.setFlat(True)
        about.setStyleSheet(f"color: {PERI}; text-decoration: underline;")
        about.clicked.connect(self.about)
        lay.addWidget(about)
        outer.addWidget(bar)

    def log(self, msg, color=None):
        self._log_bridge.log.emit(datetime.now().strftime("%H:%M:%S") + "  " + msg, color or "")

    def _append_log(self, msg, color):
        self.log_lbl.setText(msg)
        self.log_lbl.setStyleSheet(f"color: {color or DIM}; font-family: {MONO}; font-size: 9pt;")

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
                due = datetime.strptime("%s %s" % (s["date"], s["time"]), "%Y-%m-%d %H:%M")
            except Exception:
                continue
            if due <= now:
                if now - due > timedelta(minutes=30):
                    s["missed"] = True
                    changed = True
                    self.log("MISSED slot %s %s (%s) — tick it and use Run Now"
                             % (s["date"], s["time"], s.get("title", "")), WARN)
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
        folder = (tab.folder_edit.text() if plat != "fbg" else "")
        items = platform_items(plat, posts, {key: s}, {"folder": folder})
        it = next((x for x in items if x["_key"] == key), None)
        if it is None or not it["date"]:
            self.log("[%s] slot fired but post not loaded — load the folder and re-schedule" % plat, WARN)
            return
        threading.Thread(target=self._fire_work, args=(plat, wf, [it]), daemon=True).start()

    def _fire_work(self, plat, wf, items):
        try:
            res = wf.run_queue(items, {}, store_dir(), lambda m, c=None: self.log("[%s] %s" % (plat, m), c))
            self.log("[%s] scheduler run — %d done, %d failed" % (plat, res["done"], res["failed"]),
                     LIME if not res["failed"] else WARN)
        except Exception as exc:
            self.log("[%s] scheduler run failed: %s" % (plat, exc), DANGER)

    def about(self):
        QMessageBox.information(
            self, "About — %s" % APP_NAME,
            "%s v%s\n\nFour tabs, four real extension workflows through "
            "your own logged-in Chrome:\n\n"
            "- LINKEDIN - Campaign Uploader v1.3.0 workflow\n"
            "- META - Planner Scheduler v1.6.0\n"
            "- YOUTUBE - Campaign Uploader\n"
            "- FB GROUPS - Group Posting v1.6.0\n\n"
            "Own Chrome profile per platform, native scheduling.\n\n"
            "Developed by www.3SVerse.com (c) 2026" % (APP_NAME, VERSION))

    def closeEvent(self, event):
        try:
            save_schedule(self.slots)
            save_cfg(self.cfg)
        except Exception:
            pass
        event.accept()


def _enable_dpi_awareness():
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def main():
    _enable_dpi_awareness()
    app = QApplication(sys.argv)
    win = MainWindow()
    sync_titlebar_qt(win, dark=True)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
