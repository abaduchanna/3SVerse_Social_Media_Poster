"""Shared 3S Verse native window branding and animated background.

The animation intentionally uses the same artwork and timing as the
3SVerse WiFi Transfer / 3sverse.com hero: 120-second spiral rotation,
140-second orb rotation, and a 12 px / 13-second orb float.
"""
from __future__ import annotations

import ctypes
import io
import math
import os
import sys
import threading
import time
from pathlib import Path


BRAND_DARK = "#07060b"
BRAND_LIGHT = "#f6f7fb"
BRAND_TEXT_DARK = "#10131f"
BRAND_TEXT_LIGHT = "#ffffff"


def _asset_path(name: str) -> str:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return str(base / name)


_EMBED_KEYS = {
    "spiral.webp": "EMBEDDED_SPIRAL_B64",
    "orb.webp": "EMBEDDED_ORB_B64",
    "3sverse_logo_header.png": "EMBEDDED_LOGO_B64",
    "3sverse_icon.ico": "EMBEDDED_ICO_B64",
}


def _asset_bytes(name: str) -> bytes:
    """Embedded-first brand bytes (CI bakes them into the exe as base64);
    disk copy next to the module is the fallback."""
    key = _EMBED_KEYS.get(name)
    if key:
        try:
            import base64
            import embedded_brand_assets as _e
            raw = getattr(_e, key, None)
            if raw:
                return base64.b64decode(raw)
        except Exception:
            pass
    with open(_asset_path(name), "rb") as fh:
        return fh.read()


def _colourref(hex_colour: str) -> int:
    value = hex_colour.lstrip("#")
    red, green, blue = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return red | (green << 8) | (blue << 16)


def _top_level_hwnd(hwnd: int) -> int:
    if os.name != "nt":
        return hwnd
    user32 = ctypes.windll.user32
    parent = user32.GetParent(hwnd)
    while parent:
        hwnd = parent
        parent = user32.GetParent(hwnd)
    return hwnd


def apply_native_window_branding(window, dark: bool = True) -> None:
    """Set the exact website favicon and native Windows title-bar colours."""
    try:
        icon = _asset_path("3sverse_website_favicon.ico")
        if not os.path.exists(icon):
            # Repo / exe fallback: the same 3SV logo mark shipped as
            # 3sverse_icon.ico (v1.0.4 icon parity).
            icon = _asset_path("3sverse_icon.ico")
        if os.path.exists(icon):
            window.iconbitmap(default=icon)
    except Exception:
        pass

    if os.name != "nt":
        return
    try:
        window.update_idletasks()
        hwnd = _top_level_hwnd(int(window.winfo_id()))
        dwm = ctypes.windll.dwmapi
        enabled = ctypes.c_int(1 if dark else 0)
        # DWMWA_USE_IMMERSIVE_DARK_MODE: 20 on current Windows, 19 on
        # older Windows 10 releases.
        result = dwm.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(enabled), ctypes.sizeof(enabled))
        if result != 0:
            dwm.DwmSetWindowAttribute(
                hwnd, 19, ctypes.byref(enabled), ctypes.sizeof(enabled))

        caption = ctypes.c_uint(_colourref("#090d26" if dark else "#eef1f7"))
        text = ctypes.c_uint(_colourref(BRAND_TEXT_LIGHT if dark else BRAND_TEXT_DARK))
        border = ctypes.c_uint(_colourref("#090d26" if dark else "#d5d9e5"))
        for attribute, value in ((35, caption), (36, text), (34, border)):
            dwm.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value))
        ctypes.windll.user32.SetWindowPos(
            hwnd, 0, 0, 0, 0, 0,
            0x0001 | 0x0002 | 0x0004 | 0x0020 | 0x0040)
    except Exception:
        pass


class BrandAnimation:
    """Exact WiFi Transfer ring/orb animation for a Tk canvas.

    v3.0.1 rewrite — the SAME engine License Studio runs (ported 1:1):
    the art is re-rotated in REAL TIME from the pristine webp at the
    absolute CSS angle (a worker thread rotates, the UI tick only flips
    bitmaps + moves the floats). The old pipeline here (24 pre-rendered
    frames flipped every 5 s = 15-degree hops) is what read as the
    "glitch / jhatal" the owner reported — it is gone.

    Composition = the gui.go #bgart CSS, evaluated on the XFER REFERENCE
    WINDOW (1160x800) so the art renders at the same absolute size as
    the WiFi Transfer dashboard / License Studio at every window size:
      ring  right:-24vw top:-14vh  width:min(52vw,640px)  -> TOP-RIGHT
      orb   left:-10vw  bottom:-22vh width:min(30vw,380px) -> BOTTOM-LEFT
    """

    RING_SPIN_S = 120.0        # gui.go: bgspin 120s linear infinite
    ORB_SPIN_S = 140.0         # gui.go: bgspin 140s linear infinite
    RING_AMP = 16              # gui.go: bgfloatR 16px / 12s
    RING_FLOAT_S = 12.0
    ORB_AMP = 12               # gui.go: bgfloatO 12px / 13s
    ORB_FLOAT_S = 13.0
    RING_OPACITY = 0.9         # site hero match (pristine webp + alpha)
    ORB_OPACITY = 0.95         # site footer match
    TICK_MS = 40               # 25fps UI tick (rotation off-thread)
    MIN_STEP_DEG = 0.05        # re-render every tick -> xfer-smooth
    REF_W = 1160.0             # xfer's opening window (window_windows.go
    REF_H = 800.0              # Width/Height) = the vw/vh reference
    RESIZE_DEBOUNCE_MS = 120   # no mid-drag redraw storms -> no flicker

    def __init__(self, owner, canvas, title: str | None = None):
        self.owner = owner
        self.canvas = canvas
        self.title = title
        self._alive = True
        self._photos = {"ring": None, "orb": None}   # kept referenced
        self._items = {"ring": None, "orb": None}
        self._cx = {"ring": 0.0, "orb": 0.0}         # CSS art centres
        self._cy = {"ring": 0.0, "orb": 0.0}
        self._static = False        # Pillow missing -> static placement
        self._resize_job = None
        self._t0 = time.monotonic()
        self._epoch = 0
        self._target = (0, None, None)
        self._out = {}
        self._lock = threading.Lock()
        self._srcs = self._load()
        if any(self._srcs.values()):
            self._apply_size()
            if not self._static:
                threading.Thread(target=self._render_loop,
                                 daemon=True).start()
                owner.after(self.TICK_MS, self._tick)
        canvas.bind("<Configure>", self._queue_resize, add="+")

    # -- art -----------------------------------------------------------
    def _load(self):
        """Decode the pristine WiFi Transfer webp art once (CSS opacity
        applied exactly like the browser does). No Pillow / no webp ->
        static brand_bg_*.png placement, plain canvas if even those are
        missing."""
        srcs = {"ring": None, "orb": None}
        try:
            from PIL import Image
            for kind, name, opacity in (
                    ("ring", "spiral.webp", self.RING_OPACITY),
                    ("orb", "orb.webp", self.ORB_OPACITY)):
                try:
                    im = Image.open(io.BytesIO(
                        _asset_bytes(name))).convert("RGBA")
                    alpha = im.getchannel("A").point(
                        lambda value, o=opacity: int(value * o))
                    im.putalpha(alpha)
                    srcs[kind] = im
                except Exception:
                    pass
        except Exception:
            pass
        if srcs["ring"] is None and srcs["orb"] is None:
            # Pillow missing (or webp art absent): fall back to the
            # pre-dimmed static PNGs at the correct anchors.
            try:
                import tkinter as tk
                for kind, name in (("ring", "brand_bg_ring.png"),
                                   ("orb", "brand_bg_orb.png")):
                    try:
                        srcs[kind] = tk.PhotoImage(file=_asset_path(name))
                        self._static = True
                    except Exception:
                        pass
            except Exception:
                pass
        return srcs

    # -- geometry (gui.go #bgart, 1160x800 reference) -------------------
    def _apply_size(self):
        self._resize_job = None
        try:
            w = self.canvas.winfo_width() or 1000
            h = self.canvas.winfo_height() or 700
        except Exception:
            return
        rw, rh = self.REF_W, self.REF_H
        targets = {"ring": None, "orb": None}
        ring = self._srcs.get("ring")
        if ring is not None:
            aw = min(0.52 * rw, 640.0)          # 603.2 px at any size
            ah = aw * ring.height / float(ring.width)   # CSS height:auto
            self._cx["ring"] = w + 0.24 * rw - aw / 2.0    # TOP-RIGHT
            self._cy["ring"] = -0.14 * rh + ah / 2.0
            if self._static:
                targets["ring"] = (int(aw), int(ah))
            else:
                targets["ring"] = (aw, ah)
        orb = self._srcs.get("orb")
        if orb is not None:
            aw = min(0.30 * rw, 380.0)          # 348 px at any size
            self._cx["orb"] = -0.10 * rw + aw / 2.0        # BOTTOM-LEFT
            self._cy["orb"] = h + 0.22 * rh - aw / 2.0
            targets["orb"] = (aw, aw)           # orb asset is square
        if self._static:
            self._place_static(targets)
            return
        self._epoch += 1
        with self._lock:
            self._target = (self._epoch, targets["ring"], targets["orb"])

    def _place_static(self, targets):
        try:
            self.canvas.delete("brand_art")
            for kind in ("ring", "orb"):
                src = self._srcs.get(kind)
                if src is None or targets.get(kind) is None:
                    continue
                self.canvas.create_image(
                    self._cx[kind], self._cy[kind], image=src,
                    anchor="center", tags=("brand_art",))
            if self.title:
                self.canvas.create_text(
                    self.canvas.winfo_width() / 2,
                    self.canvas.winfo_height() / 2, text=self.title,
                    font=("Segoe UI", 16, "bold"), fill="#ffffff",
                    tags=("brand_art", "brand_title"))
        except Exception:
            pass

    # -- worker: real-time rotation -------------------------------------
    def _render_loop(self):
        """Rotate the pristine art at the ABSOLUTE CSS angle for the
        current time (never increments, so it cannot drift or jump) and
        re-fit after every window resize (epoch bump)."""
        cur_epoch = -1
        built = {}
        last = {}
        while self._alive:
            try:
                with self._lock:
                    target = self._target
                epoch, ring_t, orb_t = target
                if epoch != cur_epoch:
                    built = {}
                    for kind, tgt in (("ring", ring_t), ("orb", orb_t)):
                        master = self._srcs.get(kind)
                        if tgt is None or master is None:
                            built[kind] = None
                            continue
                        from PIL import Image
                        aw, ah = tgt
                        w = max(2, int(round(aw)))
                        h = max(2, int(round(ah)))
                        art = master.resize((w, h), Image.LANCZOS)
                        # rotate inside a transparent diagonal square so
                        # no corner of the art is ever clipped
                        side = int(math.ceil(math.hypot(w, h)))
                        frame_src = Image.new("RGBA", (side, side),
                                              (0, 0, 0, 0))
                        frame_src.alpha_composite(
                            art, ((side - w) // 2, (side - h) // 2))
                        built[kind] = frame_src
                    cur_epoch = epoch
                    last = {}
                minimized = False
                try:
                    minimized = self.owner.state() == "iconic"
                except Exception:
                    pass
                if not minimized:
                    t = time.monotonic() - self._t0
                    for kind, spin in (("ring", self.RING_SPIN_S),
                                       ("orb", self.ORB_SPIN_S)):
                        src = built.get(kind)
                        if src is None:
                            continue
                        ang = (t % spin) / spin * 360.0
                        prev = last.get(kind)
                        if prev is not None:
                            d = (ang - prev) % 360.0
                            if min(d, 360.0 - d) < self.MIN_STEP_DEG:
                                continue
                        frame = src.rotate(ang, resample=Image.BILINEAR,
                                           expand=False)
                        last[kind] = ang
                        with self._lock:
                            self._out[kind] = frame
            except Exception:
                time.sleep(0.2)   # the bg must never take the app down
            time.sleep(0.008)     # keep up with the 25fps UI tick

    # -- UI tick --------------------------------------------------------
    def _queue_resize(self, _event=None):
        """<Configure> handler — debounced refit (live drags fire a lot)."""
        if self._resize_job is not None:
            try:
                self.owner.after_cancel(self._resize_job)
            except Exception:
                pass
        try:
            self._resize_job = self.owner.after(
                self.RESIZE_DEBOUNCE_MS, self._apply_size)
        except Exception:
            pass

    def _active(self):
        try:
            return bool(self.owner.winfo_exists()) and \
                self.owner.state() != "iconic"
        except Exception:
            return False

    def _tick(self):
        """25fps UI tick: pick up freshly rendered frames (PhotoImage
        must be built on the Tk thread) and move the floats. Float and
        spin both read the ELAPSED clock — the exact CSS behaviour."""
        try:
            if not self._active():
                self._alive = False
                return
            from PIL import ImageTk
            with self._lock:
                frames = {"ring": self._out.pop("ring", None),
                          "orb": self._out.pop("orb", None)}
            c = self.canvas
            t = time.monotonic() - self._t0
            for kind in ("ring", "orb"):
                frame = frames.get(kind)
                if frame is not None:
                    self._photos[kind] = ImageTk.PhotoImage(frame)
                    if self._items[kind] is None:
                        self._items[kind] = c.create_image(
                            self._cx[kind], self._cy[kind],
                            image=self._photos[kind], anchor="center")
                        c.tag_lower(self._items[kind])   # art behind all
                    else:
                        c.itemconfig(self._items[kind],
                                     image=self._photos[kind])
            # CSS float keyframes: 0% -> -amp, 50% -> +amp (an
            # ease-in-out loop is a cosine). Ring 16px/12s, orb 12px/13s.
            if self._items["ring"] is not None:
                dy = -self.RING_AMP * math.cos(
                    2.0 * math.pi * (t % self.RING_FLOAT_S)
                    / self.RING_FLOAT_S)
                c.coords(self._items["ring"], self._cx["ring"],
                         self._cy["ring"] + dy)
            if self._items["orb"] is not None:
                dy = -self.ORB_AMP * math.cos(
                    2.0 * math.pi * (t % self.ORB_FLOAT_S)
                    / self.ORB_FLOAT_S)
                c.coords(self._items["orb"], self._cx["orb"],
                         self._cy["orb"] + dy)
        except Exception:
            pass                      # never let the bg loop kill the app
        if self._alive:
            try:
                self.owner.after(self.TICK_MS, self._tick)
            except Exception:
                pass


def install_branding(window, dark: bool = True, background: str | None = None):
    """Install/update native chrome and one shared root background."""
    apply_native_window_branding(window, dark)
    # Tk can recreate its wrapper HWND while mapping. Re-apply once after
    # realization so the title bar never remains light in dark mode.
    try:
        pending = getattr(window, "_3sv_native_after", None)
        if pending:
            window.after_cancel(pending)
        window._3sv_native_after = window.after(
            120, lambda: apply_native_window_branding(window, dark))
    except Exception:
        pass

    if getattr(window, "_3sv_brand_animation", None) is not None:
        return
    try:
        import tkinter as tk
        canvas = tk.Canvas(
            window, bg=background or (BRAND_DARK if dark else BRAND_LIGHT),
            highlightthickness=0, borderwidth=0, bd=0)
        canvas.place(x=0, y=0, relwidth=1, relheight=1)
        window.tk.call("lower", canvas._w)
        window._3sv_brand_canvas = canvas
        window._3sv_brand_animation = BrandAnimation(window, canvas)
    except Exception:
        pass


def install_header_animation(header_manager):
    """Put the same animation visibly inside a FixedHeaderManager band."""
    try:
        import tkinter as tk
        old = getattr(header_manager, "texture_canvas", None)
        if old is not None:
            old.destroy()
        canvas = tk.Canvas(
            header_manager.header_frame, bg=header_manager.BRAND_NAVY,
            highlightthickness=0, borderwidth=0, bd=0)
        canvas.place(x=0, y=0, relwidth=1, relheight=1)
        header_manager.texture_canvas = canvas
        header_manager._brand_animation = BrandAnimation(
            header_manager.parent, canvas, header_manager.title)
        for edge_name in ("left_frame", "divider_frame", "right_frame"):
            edge = getattr(header_manager, edge_name, None)
            if edge is not None:
                header_manager.header_frame.tk.call("raise", edge._w)
    except Exception:
        pass
