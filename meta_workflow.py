#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
3SVerse LinkedIn Poster — Meta Planner Mode (browser workflow).

Faithful Python/Selenium port of the 3SVerse Meta Planner Scheduler
Chrome extension (3SVerse_Social_Campaign_Assistant/meta-planner-scheduler
v1.6.0). Same command-for-command CDP driving against the user's own
logged-in Chrome session in a dedicated profile: content.js locators and
state → META_STATE_JS via execute_script; background.js scheduleItem →
MetaPoster.schedule_item(); trusted CDP input (Input.dispatchMouseEvent /
insertText / dispatchKeyEvent + Emulation focus emulation); media attach
via Page.setInterceptFileChooserDialog + DOM.setFileInputFiles
(backendNodeId + detached input nodeId fallback); Planner's native
schedule fields (dd/mm/yyyy date inputs + hours/minutes spinbuttons for
BOTH Facebook and Instagram) typed with trusted keys and verified against
Meta's own rendered values; per-item running/completed/failed state in
meta_progress.json (completed items skip on rerun). Every step verifies
itself like the proven web_workflow.py template: each control resolve
logs WHICH selector strategy matched, and every failed wait raises
WorkflowError with Meta's on-screen summary so failures are actionable.

Developed by www.3SVerse.com (c) 2026
Independent vendor — not affiliated with Meta, Facebook or Instagram.
"""

import json
import os
import time
import unicodedata
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

PROFILE_SUBDIR = "meta"
DEFAULT_DASH_URL = ("https://business.facebook.com/latest/content_calendar"
                    "?business_id=4880742675547794&asset_id=1376773818846890")
VIDEO_EXTS = (".mp4", ".mov", ".webm", ".m4v")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")

# ── content.js port: locators + state snapshot (chrome-free JS) ──────
# Same selectors/labels as the extension's content script, each resolver
# returning WHICH strategy matched so Python can log it.
META_STATE_JS = r"""
const __norm = v => String(v || "").normalize("NFKC").replace(/\s+/g, " ").trim().toLowerCase();
const __visible = e => Boolean(e && e.getClientRects().length && e.ownerDocument.defaultView.getComputedStyle(e).visibility !== "hidden");
const __enabled = e => __visible(e) && !e.matches(":disabled,[aria-disabled='true']"); const __checked = e => Boolean(e && (e.checked || e.getAttribute("aria-checked") === "true" || e.getAttribute("aria-pressed") === "true" || e.getAttribute("aria-selected") === "true"));
const __label = e => __norm(__textFor(e)); const __menuItems = () => [...document.querySelectorAll('[role="menuitem"]')].filter(__visible);
const __modalRoot = () => [...document.querySelectorAll('[role="dialog"]')].filter(__visible).slice(-1)[0] || document.body; const __modalButtons = () => [...__modalRoot().querySelectorAll('button,[role="button"]')].filter(__visible);
const __enabledExact = text => __modalButtons().filter(e => __norm(e.innerText || e.getAttribute("aria-label")) === __norm(text) && !e.matches(':disabled,[aria-disabled="true"]')).slice(-1)[0];
const __exactHeading = text => [...document.querySelectorAll('[role="heading"],h1,h2,h3,h4')].find(e => __visible(e) && __norm(e.innerText || e.textContent) === __norm(text)); const __routeFor = t => t === "reel" ? /\/reels_composer\/?$/ : t === "story" ? /\/story_composer\/?$/ : /\/composer\/?$/;
const __captionEditor = () => [...document.querySelectorAll('textarea,[contenteditable="true"][role="textbox"],[contenteditable="true"][role="combobox"],input[type="text"]')].filter(__visible).find(e => /write in the dialogue box|write.*post|caption|describe/i.test((e.getAttribute("aria-label") || "") + " " + (e.placeholder || "")));
const __controls = () => [...document.querySelectorAll('button,[role="button"],[role="menuitem"],[role="checkbox"],[role="radio"],[role="switch"],input[type="checkbox"],input[type="radio"],label')].filter(__visible);
const __textFor = e => { const direct = e.innerText || e.getAttribute("aria-label") || ""; if (direct) return direct; if (e.id) { const l = document.querySelector('label[for="' + CSS.escape(e.id) + '"]'); if (l) return l.innerText || l.getAttribute("aria-label") || ""; } const wrap = e.closest("label"); return wrap ? (wrap.innerText || wrap.getAttribute("aria-label") || "") : ""; };
function __composerReady(type) {
  const has = t => Boolean(__controls().find(e => __label(e) === __norm(t)));
  if (type === "reel") return __routeFor(type).test(location.pathname) && has("Add video") && Boolean(__captionEditor()) && has("Cancel") && has("Next");
  if (type === "story") return __routeFor(type).test(location.pathname) && Boolean(__exactHeading("Create Story")) && has("Add photo/video") && has("Cancel") && has("Share");
  return __routeFor(type).test(location.pathname) && Boolean(__exactHeading("Create post")) && has("Add photo/video") && Boolean(__captionEditor()) && has("Cancel") && has("Publish");
}
function __createPostButton() { return __controls().find(e => __label(e) === "create post"); } function __createMenuItem(text) { return __menuItems().find(e => __label(e) === __norm(text)); }
function __createMenuButton() { const post = __createPostButton(); const arrow = post ? (post.closest('[role="group"]') || {}).querySelector('[role="button"][aria-haspopup="menu"]') : null; return __visible(arrow) ? arrow : null; }
function __fbIgStatus(type) {
  const section = type === "story" ? "share to" : "post to";
  const heading = [...document.querySelectorAll('[role="heading"],h1,h2,h3,h4')].find(e => __visible(e) && __norm(e.innerText) === section);
  if (!heading) return "no-section";
  let node = heading;
  while (node && node !== document.body) { const accounts = [...node.querySelectorAll("img")].filter(__visible).map(img => __norm(img.alt)); if (accounts.includes("facebook") && accounts.includes("instagram")) return "ok"; node = node.parentElement; }
  return "not-both";
}
function __uploadTarget() {
  const pool = [...document.querySelectorAll('button,[role="button"],label')].filter(__visible);
  const exact = /^(add|upload) (video|photo|photos|media|photo\/video|photos\/videos)$/i, loose = /add (video|photo|media)|upload (video|photo|media)/i, nameOf = e => (e.innerText || e.getAttribute("aria-label") || "");
  return pool.find(e => exact.test(__norm(nameOf(e)))) || pool.find(e => loose.test(nameOf(e))) || null;
}
function __reelStageKey() { return [...document.querySelectorAll('button,[role="button"]')].filter(__visible).map(e => __norm(e.getAttribute("aria-label") || e.innerText)).filter(l => /^(create|edit|share) (pending|completed) status$/.test(l)).join("|"); }
function __storyShareSwitch() { return [...document.querySelectorAll('[role="switch"],input[type="checkbox"]')].find(e => __visible(e) && /share to facebook story/i.test(e.getAttribute("aria-label") || "")); } function __postScheduleSwitch() { return [...document.querySelectorAll('[role="switch"],input[type="checkbox"]')].find(e => __visible(e) && __norm(__textFor(e)) === "set date and time"); }
function __scheduleChoice(type) { if (type === "post") return __postScheduleSwitch(); return [...document.querySelectorAll('button,[role="button"],[role="radio"],[role="checkbox"],input[type="radio"],input[type="checkbox"]')].find(e => __visible(e) && __label(e) === "schedule"); }
function __dateFields() {
  let inputs = [...document.querySelectorAll("input[placeholder='dd/mm/yyyy']")].filter(__visible);
  if (inputs.length >= 2) return { strategy: "input[placeholder='dd/mm/yyyy']", inputs };
  inputs = [...__modalRoot().querySelectorAll("input")].filter(__visible).filter(x => ((x.placeholder || "").indexOf("d") >= 0 && (x.placeholder || "").indexOf("y") >= 0) || /\d{1,2}[\/.-]\d{1,2}[\/.-]\d{2,4}/.test(x.value || ""));
  if (inputs.length >= 2) return { strategy: "modal date-mask/value fallback", inputs };
  return { strategy: "", inputs: [] };
}
function __spinbuttons(kind) {
  const wantMax = kind === "hours" ? "23" : "59";
  let inputs = [...document.querySelectorAll("input[role='spinbutton'][aria-label='" + kind + "']")].filter(__visible);
  if (inputs.length >= 2) return { strategy: "spinbutton[aria-label=" + kind + "]", inputs };
  inputs = [...document.querySelectorAll("input[role='spinbutton']")].filter(__visible).filter(x => (x.getAttribute("aria-valuemax") || "") === wantMax);
  if (inputs.length >= 2) return { strategy: "spinbutton[aria-valuemax=" + wantMax + "]", inputs };
  return { strategy: "", inputs: [] };
}
function __scheduleMatches(dateText, timeText) {
  const parts = String(dateText || "").split("-");
  const times = String(timeText || "").split(":").map(Number);
  const dates = __dateFields().inputs, hours = __spinbuttons("hours").inputs, minutes = __spinbuttons("minutes").inputs;
  if (parts.length !== 3 || times.length !== 2 || dates.length < 2 || hours.length < 2 || minutes.length < 2) return false;
  const wanted = __norm(Number(parts[2]) + " " + new Date(Number(parts[0]), Number(parts[1]) - 1, 1).toLocaleString("en", { month: "long" }) + " " + parts[0]);
  const dateOk = dates.every(input => __norm(input.value).includes(wanted));
  const timeOk = hours.every(input => Number(input.getAttribute("aria-valuenow")) === times[0]) && minutes.every(input => Number(input.getAttribute("aria-valuenow")) === times[1]);
  return dateOk && timeOk;
}
function __shareStep(type) {
  const rootText = __norm(__modalRoot().innerText);
  if (type === "reel") return /scheduling options/.test(rootText);
  if (type === "post") return /create post/.test(rootText) && Boolean(__postScheduleSwitch());
  return /create story/.test(rootText) && Boolean(__scheduleChoice("story"));
}
function __confirmationSeen() {
  const live = [...document.querySelectorAll('[role="alert"],[role="status"],[aria-live]')].filter(__visible).map(e => e.innerText || e.textContent || "").join(" ");
  const text = __norm(live + " " + document.body.innerText);
  const patterns = [/you scheduled a (?:post|reel|story) through meta business suite/, /your (?:facebook |instagram )?(?:post|reel|story) (?:has been|is|was) scheduled/, /(?:post|reel|story) (?:has been )?scheduled successfully/, /(?:post|reel|story) scheduled\b/, /successfully scheduled (?:your )?(?:post|reel|story)/, /your (?:facebook |instagram )?(?:post|reel|story) (?:has been|is|was) published/, /(?:post|reel|story) (?:has been )?published successfully/];
  return patterns.some(pattern => pattern.test(text));
}
function __screenSummary() {
  const headings = [...document.querySelectorAll("h1,h2,h3")].filter(__visible).map(e => (e.innerText || "").trim()).filter(Boolean).slice(-4);
  const buttons = __controls().map(e => __textFor(e).trim()).filter(Boolean).slice(-12);
  return "screen=[" + headings.join(" > ") + "], controls=[" + buttons.join(" | ") + "], url=" + location.href;
}
function __clickable(el) {
  el.scrollIntoView({ block: "center", inline: "center" });
  el.focus({ preventScroll: true });
  const rect = el.getBoundingClientRect();
  const x = rect.left + rect.width / 2, y = rect.top + rect.height / 2;
  const hit = document.elementFromPoint(x, y);
  if (!hit || !(hit === el || el.contains(hit))) return null;
  return { x, y, label: __textFor(el).trim() };
}
function __resolvePoint(spec) {
  const pool = __controls();
  let candidates = [], how = "";
  if (spec.target === "createDropdown") {
    const post = __createPostButton();
    const arrow = post ? (post.closest('[role="group"]') || {}).querySelector('[role="button"][aria-haspopup="menu"]') : null;
    candidates = arrow && __visible(arrow) ? [arrow] : [];
    how = "Create split-button arrow ([role=button][aria-haspopup=menu])";
  } else if (spec.target === "createReel" || spec.target === "createStory") {
    const wanted = __norm(spec.target === "createReel" ? "Create reel" : "Create Story");
    candidates = __menuItems().filter(e => __label(e) === wanted);
    how = "menu item exact '" + wanted + "'";
    if (!candidates.length) { candidates = __menuItems().filter(e => __label(e).indexOf(wanted) >= 0); how = "menu item containing '" + wanted + "'"; }
  } else {
    const labels = (spec.labels || []).map(__norm);
    candidates = pool.filter(__enabled).filter(e => labels.includes(__label(e)));
    how = "exact label " + JSON.stringify(spec.labels || []);
    if (!candidates.length) { candidates = pool.filter(__enabled).filter(e => labels.some(l => __label(e).indexOf(l) >= 0)); how = "label containing " + JSON.stringify(spec.labels || []); }
    if (spec.requireChecked === true) candidates = candidates.filter(__checked);
    if (spec.requireChecked === false) candidates = candidates.filter(e => !__checked(e));
  }
  const el = spec.preferLast ? candidates.slice(-1)[0] : candidates[0];
  const want = spec.target || (spec.labels || []).join(" / ");
  if (!el) return { ok: false, error: "Meta control was not found: " + want + "; " + __screenSummary() };
  const point = __clickable(el);
  if (!point) return { ok: false, error: "Meta control is covered by another element: " + want + "; " + __screenSummary() };
  point.ok = true; point.strategy = how;
  return point;
}
function __uploadPoint() {
  const el = __uploadTarget();
  if (!el) return { ok: false, error: "Meta's visible upload button was not found; " + __screenSummary() };
  const point = __clickable(el);
  if (!point) return { ok: false, error: "Meta's upload button is covered by another element; " + __screenSummary() };
  point.ok = true; point.strategy = "upload button text (Add video/photo/media)";
  return point;
}
function __focusScheduleField(kind, index) {
  const found = kind === "date" ? __dateFields() : __spinbuttons(kind);
  const field = found.inputs[index] || null;
  if (!field) return { ok: false, error: "Meta's " + kind + " schedule field #" + (index + 1) + " (Facebook and Instagram) was not available; " + __screenSummary() };
  field.focus();
  if (field.select) field.select();
  return { ok: true, strategy: found.strategy, value: field.value || "" };
}
function __focusCaptionEditor() {
  const editor = __captionEditor();
  if (!editor) return { ok: false, error: "Meta's caption box was not found; " + __screenSummary() };
  editor.scrollIntoView({ block: "center", inline: "center" });
  editor.focus();
  if (editor.isContentEditable) document.execCommand("selectAll", false);
  return { ok: document.activeElement === editor || editor.contains(document.activeElement), strategy: "caption aria-label/placeholder match" };
}
function __focusLabel(text) {
  const wanted = __norm(text);
  const button = [...document.querySelectorAll('button,[role="button"]')].filter(__visible).filter(e => !e.matches(':disabled,[aria-disabled="true"]')).filter(e => __norm(e.innerText || e.getAttribute("aria-label")) === wanted).slice(-1)[0];
  if (!button) return { ok: false, error: "Meta's " + text + " button could not receive keyboard focus; " + __screenSummary() };
  button.scrollIntoView({ block: "center", inline: "center" });
  button.focus({ preventScroll: true });
  return { ok: document.activeElement === button || button.contains(document.activeElement) };
}
function __uploadWatch(fileName, type) {
  const text = document.body.innerText || "";
  const percentages = [...text.matchAll(/(?:^|\s)(\d{1,3})%/g)].map(m => Number(m[1])).filter(Number.isFinite);
  return { progress: percentages.length ? Math.max(...percentages) : -1,
    previewReady: /safe to publish|no copyright issues|reels?\s*\u00b7\s*\d+\s*seconds?/i.test(text),
    actionReady: Boolean(type === "reel" ? __enabledExact("Next") : type === "post" ? __enabledExact("Publish") : __enabledExact("Share")),
    fileSeen: Boolean(fileName) && text.indexOf(fileName) >= 0, summary: __screenSummary() };
}
function __launch() {
  const composerish = __routeFor("post").test(location.pathname) || __routeFor("reel").test(location.pathname) || __routeFor("story").test(location.pathname);
  return { plannerReady: location.pathname.includes("content_calendar") && Boolean(__createPostButton()) && Boolean(__createMenuButton()),
    composerReady: Boolean(__uploadTarget() || __captionEditor()),
    signedIn: Boolean(__createPostButton()) || Boolean(__captionEditor()) || Boolean(__uploadTarget()) || composerish,
    summary: __screenSummary() };
}
function __state(itemType, captionNorm, dateText, timeText) {
  const dates = __dateFields();
  const kind = itemType || "";
  return { url: location.href, online: navigator.onLine === true,
    plannerReady: location.pathname.includes("content_calendar") && Boolean(__createPostButton()) && Boolean(__createMenuButton()),
    reelMenuReady: Boolean(__createMenuItem("Create reel")), storyMenuReady: Boolean(__createMenuItem("Create Story")),
    composerReady: kind ? __composerReady(kind) : false, fbIg: kind ? __fbIgStatus(kind) : "",
    uploadReady: Boolean(__uploadTarget()), captionReady: Boolean(__captionEditor()),
    nextReady: Boolean(__enabledExact("Next")), stageKey: kind === "reel" ? __reelStageKey() : kind,
    shareStep: kind ? __shareStep(kind) : false,
    captionRetained: kind === "story" ? true : Boolean(captionNorm) && __norm(__modalRoot().innerText).indexOf(captionNorm) >= 0,
    scheduleSelected: kind ? (__checked(__scheduleChoice(kind)) || dates.inputs.length >= 2) : false,
    storyAvailable: Boolean(__storyShareSwitch()), storyOn: __checked(__storyShareSwitch()),
    fieldsReady: dates.inputs.length >= 2, dateFieldStrategy: dates.strategy,
    scheduleMatches: (dateText && timeText) ? __scheduleMatches(dateText, timeText) : false,
    finalReady: Boolean(__enabledExact("Schedule")), confirmation: __confirmationSeen(),
    summary: __screenSummary() };
}
"""


class WorkflowError(Exception):
    pass


class LoginRequired(WorkflowError):
    pass


def _norm(text):
    return " ".join(unicodedata.normalize("NFKC", str(text or "")).split()).strip().lower()


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def item_type_of(item):
    """Extension buildQueue: video → reel, image → post, Format line wins."""
    fmt = str((item or {}).get("format") or "").strip().lower()
    if fmt in ("post", "reel", "story"):
        return fmt
    media = [m for m in ((item or {}).get("media") or []) if m]
    return "reel" if any(str(m).lower().endswith(VIDEO_EXTS) for m in media) else "post"


def caption_of(item):
    """CAMPAIGN-FOLDERS.md: hashtags are ordinary caption lines."""
    parts = [str((item or {}).get("text") or "").strip(), str((item or {}).get("hashtags") or "").strip()]
    return "\n\n".join(p for p in parts if p)


def pick_media(item, item_type, log=None):
    media = [str(m) for m in ((item or {}).get("media") or []) if m]
    if not media:
        raise WorkflowError("Day %s has no media file — Meta needs exactly one file per scheduled item (video for Reel, image for post/story)." % (item or {}).get("day"))
    if item_type == "reel":
        videos = [m for m in media if m.lower().endswith(VIDEO_EXTS)]
        if not videos:
            raise WorkflowError("Day %s is a Reel but no .mp4/.mov/.webm video was matched to it — Meta's Reel composer only accepts video." % (item or {}).get("day"))
        return videos[0]
    if item_type == "post":
        images = [m for m in media if m.lower().endswith(IMAGE_EXTS)]
        if images:
            return images[0]
    if len(media) > 1 and log:
        log("Day %s: %d media files matched — attaching %s" % ((item or {}).get("day"), len(media), media[0]))
    return media[0]


def item_key(item):
    """Progress key "<normpath-folder>|<day>" (proven shell pattern)."""
    media = [m for m in ((item or {}).get("media") or []) if m]
    folder = os.path.dirname(os.path.abspath(str(media[0]))) if media else ""
    return "%s|%s" % (os.path.normpath(folder or "no-media"), (item or {}).get("day"))


def exact_post_composer_url(planner_url):
    """background.js exactPostComposerUrl(): never touch the split button."""
    parts = urlparse(planner_url or DEFAULT_DASH_URL)
    query = dict(parse_qsl(parts.query))
    query["ref"] = "biz_web_content_manager_calendar_view"
    query["context_ref"] = "CONTENT_CALENDAR"
    return urlunparse((parts.scheme or "https", parts.netloc, "/latest/composer/", "", urlencode(query), ""))


def _schedule_literals(date_text, hhmm):
    """background.js trustedScheduleInput(): raw dd/mm/yyyy insert text and
    the digit strings typed into the hours/minutes spinbuttons."""
    year, month, day = str(date_text).strip().split("-")
    hours, minutes = str(hhmm).strip().split(":")
    return "%s/%s/%s" % (day, month, year), hours, minutes


class MetaPoster:
    """One Selenium Chrome session driving the extension workflow."""

    def __init__(self, profile_root, dashboard_url=DEFAULT_DASH_URL, log=None):
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        self.dashboard_url = dashboard_url or DEFAULT_DASH_URL
        self.log = log or (lambda msg: None)
        profile_dir = os.path.join(profile_root, PROFILE_SUBDIR)
        os.makedirs(profile_dir, exist_ok=True)
        opts = Options()
        # Same flags as web_workflow.py: own profile, no crash bubble, and
        # perf-log capability so Page.fileChooserOpened can be intercepted.
        for flag in ("--user-data-dir=%s" % profile_dir, "--profile-directory=Default",
                     "--no-first-run", "--no-default-browser-check",
                     "--disable-session-crashed-bubble", "--hide-crash-restore-bubble",
                     "--window-size=1280,900"):
            opts.add_argument(flag)
        opts.set_capability("goog:loggingPrefs", {"performance": "ALL", "browser": "ALL"})
        self.driver = webdriver.Chrome(options=opts)
        self.driver.set_page_load_timeout(90)
        self._ctx = {"type": "", "caption": "", "date": "", "time": ""}

    # ── low-level CDP (same commands as the extension) ────────────────
    def _state(self):
        ctx = self._ctx
        suffix = (" return __state(" + json.dumps(ctx["type"]) + ", " + json.dumps(ctx["caption"])
                  + ", " + json.dumps(ctx["date"]) + ", " + json.dumps(ctx["time"]) + ");")
        return self.driver.execute_script(META_STATE_JS + suffix)

    def _watch(self, file_name):
        suffix = (" return __uploadWatch(" + json.dumps(file_name) + ", " + json.dumps(self._ctx["type"]) + ");")
        return self.driver.execute_script(META_STATE_JS + suffix)

    def _wait_state(self, predicate, timeout, description):
        started = time.time()
        state = None
        while time.time() - started < timeout:
            self._login_check()
            state = self._state()
            if predicate(state):
                return state
            time.sleep(0.4)
        raise WorkflowError("%s; %s" % (description, (state or {}).get("summary", "state unavailable")))

    def _login_check(self):
        try:
            url = self.driver.current_url or ""
        except Exception:
            return
        if "/login" in url or "/checkpoint" in url or "authwall" in url:
            raise LoginRequired("Meta is asking you to sign in — open the Chrome window that this app launched, sign in to Facebook/Business Suite, then start the scheduler again (completed items are skipped automatically).")

    def _focus_emulation(self):
        try:
            self.driver.execute_cdp_cmd("Emulation.setFocusEmulationEnabled", {"enabled": True})
        except Exception:
            pass

    def _click_point(self, point):
        self.driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": point["x"], "y": point["y"]})
        for etype in ("mousePressed", "mouseReleased"):
            self.driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": etype, "x": point["x"], "y": point["y"], "button": "left", "clickCount": 1})

    def _click_spec(self, spec, description):
        res = self.driver.execute_script(META_STATE_JS + " return __resolvePoint(" + json.dumps(spec) + ");")
        if not res or not res.get("ok"):
            raise WorkflowError((res or {}).get("error", "Meta control was not found: %s" % description))
        self._focus_emulation()
        self._click_point(res)
        self.log("clicked %s — matched via %s (%r)" % (description, res.get("strategy", ""), res.get("label", "")))

    def _key(self, key, code, vk, modifiers=0, keyup=False, text=None):
        params = {"type": "keyUp" if keyup else "rawKeyDown", "key": key, "code": code,
                  "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk, "modifiers": modifiers}
        if text is not None:
            params["text"] = text
            params["unmodifiedText"] = text
        self.driver.execute_cdp_cmd("Input.dispatchKeyEvent", params)

    def _press(self, key, code, vk, modifiers=0):
        self._key(key, code, vk, modifiers)
        self._key(key, code, vk, modifiers, keyup=True)

    def _select_all(self):
        self._press("a", "KeyA", 65, modifiers=2)

    def _type_digits(self, value):
        for char in str(value):
            vk = ord(char)
            self._key(char, "Digit%s" % char, vk, text=char)
            self._key(char, "Digit%s" % char, vk, keyup=True)

    def _key_activate(self, label):
        """trustedKeyActivate(): focus the button, then press Enter."""
        res = self.driver.execute_script(META_STATE_JS + " return __focusLabel(" + json.dumps(label) + ");")
        if not res or not res.get("ok"):
            raise WorkflowError((res or {}).get("error", "Meta's %s button could not receive keyboard focus." % label))
        self._focus_emulation()
        self._press("Enter", "Enter", 13)

    def _wait_file_chooser(self, timeout_s):
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                entries = self.driver.get_log("performance")
            except Exception:
                entries = []
            for entry in entries:
                try:
                    msg = json.loads(entry["message"])["message"]
                except Exception:
                    continue
                if msg.get("method") == "Page.fileChooserOpened":
                    backend = msg.get("params", {}).get("backendNodeId")
                    if backend:
                        return backend
            time.sleep(0.25)
        return None

    def _detached_file_input(self):
        """background.js fallback: Meta keeps its input detached — find the
        last input[type=file] through the DOM domain and use its nodeId."""
        try:
            root = self.driver.execute_cdp_cmd("DOM.getDocument", {"depth": -1, "pierce": True})
            found = self.driver.execute_cdp_cmd("DOM.querySelectorAll", {"nodeId": root["root"]["nodeId"], "selector": 'input[type="file"]'})
            node_ids = found.get("nodeIds") or []
            return node_ids[-1] if node_ids else None
        except Exception:
            return None

    # ── background.js port ────────────────────────────────────────────
    def hard_open(self, target_url):
        """hardOpenWorkflow(): real navigation through about:blank so no
        item ever reuses Meta's previous SPA composer state."""
        self.driver.get("about:blank")
        self._wait_loaded()
        self.driver.get(target_url)
        self._wait_loaded()
        target = urlparse(target_url)
        started = time.time()
        url = ""
        while time.time() - started < 90:
            self._login_check()
            try:
                url = self.driver.current_url or ""
            except Exception:
                url = ""
            current = urlparse(url)
            if current.netloc == target.netloc and current.path == target.path:
                time.sleep(1.2)
                return
            time.sleep(0.25)
        raise WorkflowError("Meta did not open the exact workflow link (still at %s)." % url)

    def _wait_loaded(self, timeout=60):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.driver.execute_script("return document.readyState") == "complete":
                    return
            except Exception:
                pass
            time.sleep(0.3)
        raise WorkflowError("Meta did not finish loading in time.")

    def open_signed_in(self, start_url):
        self.hard_open(start_url)
        started = time.time()
        state = {}
        while time.time() - started < 60:
            self._login_check()
            try:
                state = self.driver.execute_script(META_STATE_JS + " return __launch();")
            except Exception:
                state = {}
            if state.get("signedIn"):
                self.log("Meta Business Suite session detected — ready.")
                return
            time.sleep(0.5)
        raise LoginRequired("Meta Business Suite did not open signed in — open the Chrome window this app launched, sign in to Facebook (and pick your Page/Business asset), then start the scheduler again. %s" % state.get("summary", ""))

    def open_from_planner(self, item_type):
        if item_type == "post":
            self._wait_state(lambda s: s["composerReady"], 30, "Meta's exact Create post composer did not become ready")
        else:
            self._wait_state(lambda s: s["plannerReady"], 30, "Meta Planner did not become ready")
            self._click_spec({"target": "createDropdown"}, "Create split-button dropdown")
            menu_flag = "reelMenuReady" if item_type == "reel" else "storyMenuReady"
            self._wait_state(lambda s: s[menu_flag], 15, "Meta's Create dropdown did not open")
            self._click_spec({"target": "createReel" if item_type == "reel" else "createStory"}, "Create %s menu item" % item_type)
        self._wait_state(lambda s: s["composerReady"], 60, "Meta did not open the %s composer selected from Planner" % item_type)
        state = self._state()
        section = "Share to" if item_type == "story" else "Post to"
        if state.get("fbIg") == "no-section":
            raise WorkflowError("Meta's visible '%s' section was not found; %s" % (section, state.get("summary", "")))
        if state.get("fbIg") != "ok":
            raise WorkflowError("Facebook and Instagram are not both selected in Meta's '%s' control. Select both once, then retry; %s" % (section, state.get("summary", "")))

    def upload_media(self, media_path):
        if not media_path or not os.path.exists(media_path):
            raise WorkflowError("Media file %r does not exist on disk — fix the campaign folder path and retry." % media_path)
        point = self.driver.execute_script(META_STATE_JS + " return __uploadPoint();")
        if not point or not point.get("ok"):
            raise WorkflowError((point or {}).get("error", "Meta's visible upload button was not found."))
        self._focus_emulation()
        self.driver.execute_cdp_cmd("Page.enable", {})
        self.driver.execute_cdp_cmd("DOM.enable", {})
        self.driver.execute_cdp_cmd("Runtime.enable", {})
        self.driver.execute_cdp_cmd("Page.setInterceptFileChooserDialog", {"enabled": True})
        try:
            self._click_point(point)
            self.log("clicked upload button — matched via %s (%r)" % (point.get("strategy", ""), point.get("label", "")))
            backend = self._wait_file_chooser(12)
            if backend:
                self.log("native file chooser intercepted — attaching %s" % os.path.basename(media_path))
                self.driver.execute_cdp_cmd("DOM.setFileInputFiles", {"files": [os.path.abspath(media_path)], "backendNodeId": backend})
            else:
                node = self._detached_file_input()
                if not node:
                    raise WorkflowError("Meta ignored the trusted click on %r and exposed no file input; %s" % (point.get("label", "upload"), self._state().get("summary", "")))
                self.log("detached file input fallback (nodeId) — attaching %s" % os.path.basename(media_path))
                self.driver.execute_cdp_cmd("DOM.setFileInputFiles", {"files": [os.path.abspath(media_path)], "nodeId": node})
        finally:
            try:
                self.driver.execute_cdp_cmd("Page.setInterceptFileChooserDialog", {"enabled": False})
            except Exception:
                pass

    def wait_upload_complete(self, file_name):
        """content.js waitForCompletedUpload(): percentages, preview text,
        stall detection (0% for 45s / no advance for 90s)."""
        item_type = self._ctx["type"]
        started = time.time()
        last_progress = -1
        last_advance = time.time()
        watch = {}
        while time.time() - started < 300:
            self._login_check()
            watch = self._watch(file_name)
            if watch["actionReady"] and (item_type != "reel" or watch["progress"] >= 100 or watch["previewReady"] or watch["fileSeen"]):
                self.log("upload finished for %s (progress %s%%)" % (file_name, watch["progress"]))
                return
            if watch["progress"] > last_progress:
                last_progress = watch["progress"]
                last_advance = time.time()
            if watch["progress"] == 0 and time.time() - last_advance > 45:
                raise WorkflowError("Meta upload for %s stayed at 0%% for 45 seconds; %s" % (file_name, watch["summary"]))
            if 0 < watch["progress"] < 100 and time.time() - last_advance > 90:
                raise WorkflowError("Meta upload for %s stopped advancing at %s%%; %s" % (file_name, watch["progress"], watch["summary"]))
            time.sleep(0.7)
        raise WorkflowError("Meta did not complete the upload for %s within 5 minutes; %s" % (file_name, watch.get("summary", "state unavailable")))

    def prepare_caption(self, item_type):
        if item_type == "story":
            return False
        res = self.driver.execute_script(META_STATE_JS + " return __focusCaptionEditor();")
        if not res or not res.get("ok"):
            raise WorkflowError((res or {}).get("error", "Meta's caption box was not found."))
        self.log("caption box focused (%s)" % (res.get("strategy") or "aria/placeholder match"))
        return True

    def type_caption(self, caption):
        self.prepare_caption(self._ctx["type"])
        self._focus_emulation()
        self._select_all()
        self.driver.execute_cdp_cmd("Input.insertText", {"text": caption})
        self._wait_state(lambda s: s["captionRetained"], 15, "Meta did not retain the complete caption and hashtags")

    def _click_next_verified(self, previous_stage):
        """foregroundTrustedNext(): mouse click verified, then Enter."""
        self._click_spec({"labels": ["Next"], "preferLast": True}, "Next")
        predicate = lambda s: s["shareStep"] or (s["stageKey"] and s["stageKey"] != previous_stage)
        try:
            return self._wait_state(predicate, 15, "Meta did not accept the Edit-stage mouse click")
        except WorkflowError:
            self.log("Next click did not advance the reel stage — retrying with a focused Enter key")
            self._key_activate("Next")
            return self._wait_state(predicate, 45, "Meta ignored both the Edit-stage mouse click and focused Enter")

    def _activate_schedule(self, item_type):
        labels = ["Set date and time"] if item_type == "post" else ["Schedule"]
        for _ in range(3):
            self._click_spec({"labels": labels, "requireChecked": False}, "Schedule option (%s)" % labels[0])
            try:
                self._wait_state(lambda s: s["fieldsReady"], 5, "Meta did not show the Facebook and Instagram date fields")
                self.log("schedule fields visible after clicking %r (%s)" % (labels[0], self._state().get("dateFieldStrategy", "")))
                return
            except WorkflowError:
                time.sleep(0.3)
        raise WorkflowError("Meta did not activate the Schedule option; %s" % self._state().get("summary", ""))

    def reach_schedule_step(self, item_type):
        """reachTrustedScheduleStep(): caption check, reel Next stages,
        story switch, then the native Schedule option + fields."""
        self._wait_state(lambda s: s["online"] is not False, 60, "Meta is offline; waiting for the Internet connection to return")
        if item_type != "story":
            self._wait_state(lambda s: s["captionRetained"], 15, "Meta did not retain the complete caption and hashtags")
        if item_type == "reel":
            state = self._state()
            transitions = 0
            while not state.get("shareStep") and transitions < 3:
                self.log("reel stage %d: %s — clicking Next" % (transitions + 1, state.get("stageKey") or "unknown"))
                state = self._click_next_verified(state.get("stageKey"))
                transitions += 1
            if not state.get("shareStep"):
                raise WorkflowError("Meta did not reach the Share/Scheduling step after %d verified stage transitions; %s" % (transitions, state.get("summary", "")))
        else:
            self._wait_state(lambda s: s["shareStep"], 30, "Meta did not expose the %s scheduling controls" % item_type)
        state = self._state()
        if state.get("storyAvailable") and not state.get("storyOn"):
            self._click_spec({"labels": ["Share to Facebook story"], "requireChecked": False}, "Share to Facebook story switch")
            self._wait_state(lambda s: s["storyOn"], 10, "Meta did not enable Facebook Story sharing")
        state = self._state()
        if not state.get("scheduleSelected"):
            self._activate_schedule(item_type)
        self._wait_state(lambda s: s["fieldsReady"], 15, "Meta schedule controls were not ready")

    def fill_schedule(self, date_text, hhmm):
        """trustedScheduleInput(): both Facebook and Instagram fields."""
        try:
            insert_date, hours, minutes = _schedule_literals(date_text, hhmm)
        except Exception:
            raise WorkflowError("Bad schedule values %r / %r — need YYYY-MM-DD and HH:MM." % (date_text, hhmm))
        entries = [("date", 0, insert_date, True), ("date", 1, insert_date, True), ("hours", 0, hours, False),
                   ("hours", 1, hours, False), ("minutes", 0, minutes, False), ("minutes", 1, minutes, False)]
        for kind, index, value, insert in entries:
            res = self.driver.execute_script(META_STATE_JS + " return __focusScheduleField(" + json.dumps(kind) + ", " + json.dumps(index) + ");")
            if not res or not res.get("ok"):
                raise WorkflowError((res or {}).get("error", "Meta's %s schedule field #%d was not available." % (kind, index + 1)))
            self.log("schedule %s #%d focused (%s)" % (kind, index + 1, res.get("strategy") or "selector"))
            self._focus_emulation()
            self._select_all()
            if insert:
                self.driver.execute_cdp_cmd("Input.insertText", {"text": value})
            else:
                self._type_digits(value)
            self._press("Tab", "Tab", 9)
        self._wait_state(lambda s: s["scheduleMatches"], 15, "Meta did not accept the requested Facebook and Instagram date/time")
        self._wait_state(lambda s: s["finalReady"], 15, "Meta's final Schedule button did not become ready")

    def verify_scheduled(self):
        """content.js verifyScheduled(): Meta's own confirmation text."""
        self._wait_state(lambda s: s["confirmation"], 180, "Meta did not confirm the scheduled item with its own scheduled/published notice")
        time.sleep(5)

    def schedule_item(self, item):
        """background.js scheduleItem() for one queue item."""
        item_type = item_type_of(item)
        caption = caption_of(item)
        media_path = pick_media(item, item_type, self.log)
        date_text = str(item.get("date") or "")
        hhmm = str(item.get("time") or "")
        target = exact_post_composer_url(self.dashboard_url) if item_type == "post" else self.dashboard_url
        self._ctx = {"type": item_type, "caption": _norm(caption), "date": date_text, "time": hhmm}
        self.log("Day %s → Meta %s composer (media %s)" % (item.get("day"), item_type, media_path))
        last_error = None
        prepared = False
        for attempt in (1, 2, 3):
            if attempt > 1:
                self.log("Meta attempt %d of 3 — reopening a clean composer" % attempt)
            try:
                self.hard_open(target)
                self.open_from_planner(item_type)
                self.upload_media(media_path)
                self.wait_upload_complete(os.path.basename(media_path))
                self.prepare_caption(item_type)
                prepared = True
                break
            except WorkflowError as exc:
                last_error = exc
        if not prepared:
            raise WorkflowError("Meta upload failed after 3 attempts: %s" % last_error)
        if item_type == "story":
            self.log("story composer: Meta shows no caption box — the caption stays in the campaign folder only")
        else:
            self.type_caption(caption)
        self.reach_schedule_step(item_type)
        self.fill_schedule(date_text, hhmm)
        self._click_spec({"labels": ["Schedule"], "preferLast": True}, "final Schedule")
        self.verify_scheduled()
        try:
            self.hard_open(target)
        except WorkflowError:
            self.log("Meta resisted the post-run navigation — forcing the URL for the next item")
            self.driver.get(target)
        return True

    def close(self):
        try:
            self.driver.quit()
        except Exception:
            pass


def _start_poster(start_url, profile_root, log):
    poster = MetaPoster(profile_root, dashboard_url=start_url, log=log)
    try:
        poster.open_signed_in(start_url)
    except Exception:
        poster.close()
        raise
    return poster


def ensure_driver(start_url, profile_root, log=None):
    """Start Chrome (own user-data-dir = os.path.join(profile_root,
    PROFILE_SUBDIR)), open start_url, verify the user is logged in (else
    raise LoginRequired with a clear message), return the driver. The
    workflow helpers stay reachable on the returned driver as
    ``driver._meta_poster`` (call ``driver._meta_poster.close()`` to end
    a session created this way)."""
    poster = _start_poster(start_url or DEFAULT_DASH_URL, profile_root, log)
    driver = poster.driver
    driver._meta_poster = poster
    return driver


def run_queue(items, cfg, store_dir_path, log, stop_check=None):
    """items: list of dicts: {"day":int,"title":str,"text":str,
    "hashtags":str,"media":[abs paths],"date":"YYYY-MM-DD",
    "time":"HH:MM","format":"post|reel|story"}.
    cfg: {"dash_url": optional override, "profile_root": optional}.
    Drives the workflow per item, skips completed via the progress file,
    logs every step through log(msg), honors stop_check() between items,
    returns {"done":n,"failed":n,"skipped":n}. Raises LoginRequired so
    the shell can show its sign-in flow; any other failure marks the
    item failed and stops the queue (proven shell behavior — rerunning
    skips completed items automatically)."""
    log = log or (lambda msg: None)
    cfg = dict(cfg or {})
    progress = load_progress(store_dir_path)
    dash = cfg.get("dash_url") or DEFAULT_DASH_URL
    profile_root = cfg.get("profile_root") or store_dir_path
    counts = {"done": 0, "failed": 0, "skipped": 0}

    def mark(status, detail):
        progress[item_key(item)] = {"status": status, "detail": detail[:300], "updatedAt": _now()}
        save_progress(store_dir_path, progress)

    log("Meta Mode — starting your Chrome with the dedicated %r profile…" % PROFILE_SUBDIR)
    poster = _start_poster(dash, profile_root, log)
    try:
        for item in items or []:
            if stop_check is not None and stop_check():
                log("stopped — remaining Meta items stay queued for the next run.")
                break
            key = item_key(item)
            if (progress.get(key) or {}).get("status") == "completed":
                log("skip (already scheduled in Meta Planner): %s" % (item.get("title") or "Day %s" % item.get("day")))
                counts["skipped"] += 1
                continue
            log("Meta Mode — Day %s %s for %s %s …" % (item.get("day"), item_type_of(item), item.get("date"), item.get("time")))
            mark("running", item.get("title", ""))
            try:
                poster.schedule_item(item)
            except LoginRequired as exc:
                mark("failed", str(exc))
                counts["failed"] += 1
                raise
            except Exception as exc:
                mark("failed", str(exc))
                counts["failed"] += 1
                log("Day %s failed: %s — fix the problem and start Meta Mode again; completed items are skipped automatically." % (item.get("day"), str(exc)[:200]))
                break
            mark("completed", "%s %s" % (item.get("date"), item.get("time")))
            counts["done"] += 1
            time.sleep(3.5)
        return counts
    finally:
        poster.close()


def progress_path(store_dir_path):
    return os.path.join(store_dir_path, "meta_progress.json")


def load_progress(store_dir_path):
    path = progress_path(store_dir_path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_progress(store_dir_path, progress):
    path = progress_path(store_dir_path)
    os.makedirs(store_dir_path, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(progress, f)
    os.replace(tmp, path)
