#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
3SVerse Facebook Group Poster — Browser Mode (FB groups workflow).

Faithful Python/Selenium port of the 3SVerse Facebook Group Posting
Chrome extension v1.6.0 (source: 3SVerse_Social_Campaign_Assistant repo
ROOT). Mapping: content.js SCAN_JOINED_GROUPS → list_groups() ("Your
groups" scroll scan with GROUP_NAME_NOISE cleaning and /groups/<id>
identity); PREPARE_POST → open_group() + open_composer() (search-or-URL
navigation, exact-name match first, "write something" trigger, Create
post dialog textbox); background.js insertCaptionWithDebugger →
_type_caption() (trusted CDP Input: focus emulation, Ctrl+A, Backspace,
Input.insertText — ONE caption block, text + "\n\n" + hashtags, exactly
what the extension pastes); VERIFY_COMPOSER → attach_media() +
type_and_verify() (input[type=file] send_keys with absolute paths, new
large-media preview wait ≥180×90, enabled-Post-button wait);
PUBLISH_POST → publish() (click Post, dialog-closed confirmation);
resumeCampaign → run_queue() (per item×group deliveries, the v1.6.0
12-second inter-group wait, per-group progress on disk so reruns skip
what already posted).

Media attaches BEFORE the caption (the template's schedule-first-then-
caption philosophy: the caption is typed last and verified right before
Post, so Facebook can never drop it). Groups have no native scheduling:
deliveries post immediately in queue order; the app scheduler decides
WHEN run_queue fires (item date/time ignored). Uses the user's own
logged-in Chrome session (dedicated "fbg" profile) via CDP trusted
input with focus emulation. English Facebook UI assumed (the
extension's matchers are English too).

Developed by www.3SVerse.com (c) 2026
Independent vendor — not affiliated with Facebook or Meta.
"""

import json
import os
import re
import time
from urllib.parse import quote

PROFILE_SUBDIR = "fbg"
DEFAULT_DASH_URL = "https://www.facebook.com/"
JOINED_GROUPS_URL = "https://www.facebook.com/groups/joins/?nav_source=tab&ordering=viewer_added"
# v1.6.0: 30s → 12s (owner: "30 sec wait time ko reduce kar 10-15 sec kar de").
GROUP_INTERVAL_S = 12

# ── content.js port: locator + state snapshot (chrome-free JS) ──────
# Same selectors/labels as the extension's content script.
STATE_JS = r"""
const __norm = v => String(v || "").replace(/\s+/g, " ").trim().toLowerCase();
const __visible = e => Boolean(e && e.getClientRects().length && e.ownerDocument.defaultView.getComputedStyle(e).visibility !== "hidden");
const __enabled = e => __visible(e) && !e.matches(":disabled,[aria-disabled='true']");
const __label = e => __norm(e?.getAttribute("aria-label") || e?.innerText || e?.textContent);
const __groupIdentity = v => { try { const m = new URL(v, location.origin).pathname.match(/^\/groups\/([^/]+)/i); return m ? m[1].toLowerCase() : null; } catch (_) { return null; } };
const __GROUP_NOISE = [/^last active/i, /^last visited/i, /^view group$/i, /^\d[\d,.]*\s+members?$/i, /private group/i, /public group/i, /^\u00b7+$/, /^\.\.\.$/, /^suggested for you$/i];
const __cleanGroupName = raw => String(raw || "").split(/\n+/).map(l => l.replace(/\s+/g, " ").trim()).filter(Boolean).filter(line => !__GROUP_NOISE.some(rx => rx.test(line)))[0] || "";
const __dialogs = () => [...document.querySelectorAll('[role="dialog"]')].filter(__visible);
const __editorIn = dialog => {
  const eds = [...dialog.querySelectorAll('[contenteditable="true"][role="textbox"]')].filter(__visible);
  return eds.find(e => __norm(e.getAttribute("aria-label")).includes("create a public post")) || eds.at(-1) || null;
};
const __activeDialog = () => { const ds = __dialogs(); return ds.find(d => __editorIn(d) || d.querySelector('input[type="file"]')) || ds.at(-1) || null; };
const __nameFor = anchor => __norm(((anchor.querySelector("img[alt]")?.getAttribute("alt") || "").replace(/^profile photo of\s+/i, "").trim()) || anchor.getAttribute("aria-label") || anchor.innerText);
const __joinedGroupsOnPage = () => {
  const groups = new Map();
  for (const a of document.querySelectorAll('a[href*="/groups/"]')) {
    const id = __groupIdentity(a.href);
    if (!id || ["feed", "discover", "joins", "search", "permalink"].includes(id)) continue;
    const alt = (a.querySelector("img[alt]")?.getAttribute("alt") || "").replace(/^profile photo of\s+/i, "").trim();
    const name = __cleanGroupName(alt || a.getAttribute("aria-label") || a.innerText || "");
    if (!groups.has(id)) groups.set(id, { name: "", url: "https://www.facebook.com/groups/" + id + "/" });
    const entry = groups.get(id);
    if (!entry.name && name && __norm(name) !== "view group") entry.name = name;
  }
  return [...groups.values()].filter(g => g.name);
};
function __target(name, arg) {
  const texts = ["write something", "create a public post", "what's on your mind", "create post"];
  if (name === "composerTrigger") {
    const controls = [...document.querySelectorAll("[role='button'],div[tabindex='0']")].filter(__visible);
    for (const t of texts) { const e = controls.find(c => __label(c) === t); if (e) return { element: e, how: "composer trigger '" + t + "'" }; }
    for (const t of texts) { const e = controls.find(c => __label(c).includes(t)); if (e) return { element: e, how: "composer trigger containing '" + t + "'" }; }
  }
  if (name === "editor") {
    for (const d of __dialogs()) { const e = __editorIn(d); if (e) return { element: e, how: "Create post dialog textbox" }; }
    const inline = [...document.querySelectorAll('[contenteditable="true"][role="textbox"]')].filter(__visible).filter(e => !/comment/.test(__norm(e.getAttribute("aria-label")))).at(-1);
    if (inline) return { element: inline, how: "inline group textbox fallback" };
  }
  if (name === "photoButton") {
    const buttons = [...(__activeDialog() || document).querySelectorAll("[role='button'],button,div[tabindex='0']")].filter(__enabled);
    for (const t of ["photo/video", "add photos/videos", "add photo/video", "photo/video/video"]) {
      const e = buttons.find(b => __label(b) === t);
      if (e) return { element: e, how: "media picker button '" + t + "'" };
    }
    const loose = buttons.find(b => __label(b).includes("photo") && __label(b).includes("video"));
    if (loose) return { element: loose, how: "media picker button (photo+video text)" };
  }
  if (name === "fileInput") {
    const pick = [...(__activeDialog() || document).querySelectorAll('input[type="file"]')]
      .find(i => (i.accept || "").includes("video") || (i.accept || "").includes("image") || i.multiple)
      || [...document.querySelectorAll('input[type="file"]')]
        .find(i => (i.accept || "").includes("video") || (i.accept || "").includes("image") || i.multiple);
    if (pick) return { element: pick, how: "input[type=file] (accept image/video or multiple)" };
  }
  if (name === "post") {
    const buttons = [...(__activeDialog() || document).querySelectorAll("[role='button'],button")].filter(__enabled);
    const exact = buttons.filter(b => __label(b) === "post").at(-1)
      || buttons.filter(b => __norm(b.getAttribute("aria-label")) === "post").at(-1);
    if (exact) return { element: exact, how: "Post button (label/aria-label 'post')" };
  }
  if (name === "groupLink") {
    const wanted = __norm(arg);
    const candidates = [...document.querySelectorAll('a[href*="/groups/"]')].filter(a => {
      const id = __groupIdentity(a.href);
      return __visible(a) && id && !["feed", "discover", "joins", "search", "permalink"].includes(id);
    });
    const found = candidates.find(a => __nameFor(a) === wanted) || candidates.find(a => __nameFor(a).includes(wanted));
    if (found) return { element: found, how: "search result " + (__nameFor(found) === wanted ? "exact" : "contains") + " name match" };
  }
  return null;
}
const __pointFor = element => {
  element.scrollIntoView({ block: "center", inline: "center" });
  element.focus({ preventScroll: true });
  const r = element.getBoundingClientRect();
  return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2), label: __label(element), tag: element.tagName };
};
const __screenSummary = () => {
  const names = [...document.querySelectorAll("[role='button'],button,a,[role='link']")].filter(__visible).map(e => __label(e)).filter(Boolean).slice(0, 24);
  return "url=" + location.href + ", title=" + document.title + ", controls=[" + names.join(" | ") + "]";
};
const __state = () => {
  const editor = __target("editor");
  const dialog = __activeDialog();
  const largeMedia = dialog ? [...dialog.querySelectorAll("img,video")].filter(el => { const r = el.getBoundingClientRect(); return r.width >= 180 && r.height >= 90; }) : [];
  return { composerTriggerReady: Boolean(__target("composerTrigger")), editorReady: Boolean(editor),
    captionText: editor ? (editor.element.innerText || editor.element.textContent || "") : "",
    fileInputReady: Boolean(__target("fileInput")), postReady: Boolean(__target("post")),
    dialogOpen: Boolean(dialog), largeMediaCount: largeMedia.length, summary: __screenSummary() };
};
"""

LOCATE_JS = STATE_JS + " const __f = __target(%s, %s); if (!__f) return { ok: false, error: 'Facebook control not found: %s; ' + __screenSummary() }; return { ok: true, point: __pointFor(__f.element), how: __f.how };"
FOCUS_JS = STATE_JS + " const __f = __target(%s, %s); if (!__f) return { ok: false, error: 'Facebook control not found: %s; ' + __screenSummary() }; __f.element.focus({ preventScroll: true }); return { ok: __f.element.ownerDocument.activeElement === __f.element, how: __f.how };"
FIND_JS = STATE_JS + " const __f = __target(%s, %s); if (!__f) return { ok: false, error: 'Facebook control not found: %s; ' + __screenSummary() }; return { ok: true, element: __f.element, how: __f.how };"
STATE_SNIPPET = STATE_JS + " return __state();"
SCAN_JS = STATE_JS + " return __joinedGroupsOnPage();"

SCROLL_JS = r"""
window.scrollBy(0, Math.max(window.innerHeight * 0.75, 400));
for (const el of document.querySelectorAll("div")) {
  if (el.clientHeight > 200 && el.scrollHeight > el.clientHeight + 100 && el.getClientRects().length) {
    el.scrollTop += Math.max(el.clientHeight * 0.75, 400);
    el.dispatchEvent(new Event("scroll", { bubbles: true }));
  }
}
return true;
"""

LOGIN_CHECK_JS = r"""
const email = document.querySelector("input#email, input[name='email']");
return { loginForm: Boolean(email && email.getClientRects().length),
         looksLoggedIn: Boolean(document.querySelector("[role='navigation']")) };
"""

LOGIN_MESSAGE = ("Facebook is asking you to sign in — open the Chrome window that this app "
                 "launched, sign in to Facebook, then run the queue again. The session is kept "
                 "in the dedicated 'fbg' Chrome profile, so one sign-in lasts.")


class WorkflowError(Exception):
    pass


class LoginRequired(WorkflowError):
    pass


def _norm(s):
    return " ".join(str(s or "").split()).strip().lower()


def _group_identity(value):
    m = re.search(r"/groups/([^/?#]+)", str(value or ""))
    return m.group(1).lower() if m else None


def _delivery_key(item, group):
    day = item.get("day")
    return "%s|%s" % ("?" if day is None else str(day), _group_identity(str(group)) or _norm(group))


def _item_media(item):
    media = [item.get("media")] if isinstance(item.get("media"), str) else (item.get("media") or [])
    return [os.path.abspath(str(p)) for p in media if str(p or "").strip()]


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _wait_loaded(driver, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if driver.execute_script("return document.readyState") == "complete":
                return
        except Exception:
            pass
        time.sleep(0.3)
    raise WorkflowError("Facebook did not finish loading in time.")


def _verify_logged_in(driver, log):
    started = time.time()
    while time.time() - started < 30:
        url = (driver.current_url or "").lower()
        if "/login" in url or "checkpoint" in url or "authwall" in url:
            raise LoginRequired(LOGIN_MESSAGE)
        state = driver.execute_script(LOGIN_CHECK_JS) or {}
        if state.get("loginForm"):
            raise LoginRequired(LOGIN_MESSAGE)
        if state.get("looksLoggedIn"):
            log("Facebook session verified — you are signed in.")
            return
        time.sleep(0.5)
    log("Could not positively confirm the Facebook sign-in state; continuing with the existing session.")


class FBGroupPoster:
    """One Selenium Chrome session driving the FB group workflow."""

    def __init__(self, driver, log=None):
        self.driver = driver
        self.log = log or (lambda m, c=None: None)

    # ── low-level CDP (same commands as the extension) ───────────────
    def _js(self, snippet, name, arg=None):
        return self.driver.execute_script(snippet % (json.dumps(name), json.dumps(arg), json.dumps(name)))

    def _wait_state(self, predicate, timeout, description):
        started, state = time.time(), None
        while time.time() - started < timeout:
            self._login_check()
            state = self.driver.execute_script(STATE_SNIPPET)
            if predicate(state):
                return state
            time.sleep(0.4)
        raise WorkflowError("%s; %s" % (description, (state or {}).get("summary", "state unavailable")))

    def _login_check(self):
        url = (self.driver.current_url or "").lower()
        if "/login" in url or "checkpoint" in url or "authwall" in url:
            raise LoginRequired(LOGIN_MESSAGE)

    def _find(self, name, arg=None):
        res = self._js(FIND_JS, name, arg)
        return res if (res and res.get("ok")) else None

    def _locate(self, name, arg=None):
        res = self._js(LOCATE_JS, name, arg)
        if not res or not res.get("ok"):
            raise WorkflowError((res or {}).get("error", "Facebook control not found: %s" % name))
        return res

    def _focus(self, name, arg=None):
        res = self._js(FOCUS_JS, name, arg)
        if not res or not res.get("ok"):
            raise WorkflowError((res or {}).get("error", "Facebook did not focus the %s field." % name))

    def _focus_emulation(self):
        try:
            self.driver.execute_cdp_cmd("Emulation.setFocusEmulationEnabled", {"enabled": True})
        except Exception:
            pass

    def _click(self, name, arg=None):
        point = self._locate(name, arg)["point"]
        self._focus_emulation()
        self.driver.execute_cdp_cmd("Input.dispatchMouseEvent",
                                    {"type": "mouseMoved", "x": point["x"], "y": point["y"]})
        for t in ("mousePressed", "mouseReleased"):
            self.driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
                "type": t, "x": point["x"], "y": point["y"], "button": "left", "clickCount": 1})

    def _key(self, key, code, vk, modifiers=0, keyup=False):
        self.driver.execute_cdp_cmd("Input.dispatchKeyEvent", {
            "type": "keyUp" if keyup else "rawKeyDown", "key": key, "code": code,
            "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk, "modifiers": modifiers})

    # ── content.js PREPARE_POST port ─────────────────────────────────
    def open_group(self, group):
        name = str(group or "").strip()
        if not name:
            raise WorkflowError("A configured target group entry is empty — fix the group list in the workflow settings.")
        identity = _group_identity(name)
        if identity and name.lower().startswith(("http://", "https://")):
            self.log("Opening group '%s' via its saved URL…" % name)
            self.driver.get("https://www.facebook.com/groups/%s/" % identity)
        else:
            self.log("Searching Facebook groups for '%s'…" % name)
            self.driver.get("https://www.facebook.com/search/groups/?q=" + quote(name))
            self._click_group_result(name)
        _wait_loaded(self.driver)
        self._wait_group_page(name, identity)

    def _click_group_result(self, name):
        deadline = time.time() + 60
        while time.time() < deadline:
            self._login_check()
            current = self.driver.current_url or ""
            if "/groups/" in current and "/search/groups/" not in current:
                return  # Facebook opened the group directly
            found = self._find("groupLink", name)
            if found:
                self.log("Group '%s' matched in search results via %s." % (name, found.get("how", "name match")))
                return self._click("groupLink", name)
            time.sleep(0.5)
        raise WorkflowError("Group '%s' was not found in Facebook's group search. Check its exact name in the workflow settings, or paste its facebook.com/groups/… URL." % name)

    def _wait_group_page(self, name, identity, timeout=60):
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._login_check()
            url = self.driver.current_url or ""
            if "/groups/" in url and "/search/groups/" not in url:
                url_identity = _group_identity(url)
                if identity:
                    if url_identity == identity:
                        return
                elif _norm(name) in _norm(re.sub(r"\|\s*facebook.*$", "", self.driver.title or "", flags=re.I)) or url_identity:
                    return
            time.sleep(0.5)
        raise WorkflowError("Facebook could not reach the group '%s'. Check its exact name, confirm you are still a member, or paste its facebook.com/groups/… URL." % name)

    def open_composer(self):
        self._wait_state(lambda s: s["editorReady"] or s["composerTriggerReady"], 45,
                         "Facebook's composer trigger did not appear on the group page — the page may not have loaded completely, you may not be a member any more, or the group may not allow you to post")
        if not self.driver.execute_script(STATE_SNIPPET)["editorReady"]:
            self._click("composerTrigger")
            self.log("Composer opened (write something / create post trigger).")
        self._wait_state(lambda s: s["editorReady"], 30, "Facebook's Create post dialog did not open")

    # ── content.js VERIFY_COMPOSER port (media half) ─────────────────
    def attach_media(self, paths):
        deadline, found = time.time() + 15, None
        while time.time() < deadline:
            if (found := self._find("fileInput")):
                break
            time.sleep(0.5)
        if not found:
            self._click("photoButton")
            self.log("Opened Facebook's media picker (Photo/Video button).")
            self._wait_state(lambda s: s["fileInputReady"], 15,
                             "Facebook's photo/video file input did not appear after opening the media picker")
            found = self._find("fileInput")
        if not found:
            raise WorkflowError("Facebook's media file input was not found in the composer — the group may not allow photo/video posts from this account.")
        self.log("Media attach via %s." % found.get("how", "file input"))
        found["element"].send_keys("\n".join(paths))
        is_video = any(p.lower().endswith((".mp4", ".mov", ".webm", ".m4v")) for p in paths)
        self._wait_state(lambda s: s["largeMediaCount"] >= len(paths), 180 if is_video else 90,
                         "Facebook did not show a preview for all %d attached file(s)" % len(paths))
        self.log("Facebook accepted %d media file(s)." % len(paths))

    # ── background.js insertCaptionWithDebugger port ─────────────────
    def _type_caption(self, caption):
        self._locate("editor")
        self._focus_emulation()
        self._focus("editor")
        self._key("a", "KeyA", 65, modifiers=2)
        self._key("a", "KeyA", 65, modifiers=2, keyup=True)
        self._key("Backspace", "Backspace", 8)
        self._key("Backspace", "Backspace", 8, keyup=True)
        self.driver.execute_cdp_cmd("Input.insertText", {"text": caption})

    def type_and_verify(self, caption):
        self._type_caption(caption)
        expected = _norm(caption)
        self._wait_state(lambda s: _norm(s["captionText"]) == expected, 20,
                         "Facebook did not retain the full caption and hashtags exactly — nothing was posted for this group")
        self.log("Caption and hashtags verified in the composer.")

    # ── content.js PUBLISH_POST port ─────────────────────────────────
    def publish(self):
        self._wait_state(lambda s: s["postReady"], 20, "Facebook's Post button did not become ready")
        self._click("post")
        self.log("Clicked Post; waiting for Facebook to confirm…")
        self._wait_state(lambda s: not s["dialogOpen"], 90,
                         "Facebook did not confirm the post (the Create post dialog stayed open) — check the group feed; the post may need manual review")
        time.sleep(3)

    def post_to_group(self, group, caption, media):
        """One extension campaign step for a single group."""
        self.open_group(group)
        self.open_composer()
        if media:
            self.attach_media(media)
        self.type_and_verify(caption)
        self.publish()
        return True


def ensure_driver(start_url, profile_root, log=None):
    """Start Chrome (own user-data-dir = os.path.join(profile_root,
    PROFILE_SUBDIR)), open start_url, verify logged in, return driver."""
    log = log or (lambda m, c=None: None)
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    profile_dir = os.path.abspath(os.path.join(profile_root or ".", PROFILE_SUBDIR))
    os.makedirs(profile_dir, exist_ok=True)
    opts = Options()
    opts.add_argument("--user-data-dir=%s" % profile_dir)
    opts.add_argument("--profile-directory=Default")
    for arg in ("--no-first-run", "--no-default-browser-check", "--disable-session-crashed-bubble",
                "--hide-crash-restore-bubble", "--window-size=1280,900"):
        opts.add_argument(arg)
    opts.set_capability("goog:loggingPrefs", {"performance": "ALL", "browser": "ALL"})
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(90)
    log("Chrome is open with the dedicated Facebook profile at %s" % profile_dir)
    driver.get(start_url or DEFAULT_DASH_URL)
    _wait_loaded(driver)
    _verify_logged_in(driver, log)
    return driver


def list_groups(driver, log=None):
    """Best-effort: scan the left rail / groups page for joined group
    names + hrefs (content.js scanJoinedGroups port — never raises
    except for login problems)."""
    log = log or (lambda m, c=None: None)
    try:
        if "/groups/joins" not in (driver.current_url or ""):
            log("Opening Facebook 'Your groups' for the joined-group scan…")
            driver.get(JOINED_GROUPS_URL)
            _wait_loaded(driver)
        collected, previous, stagnant = {}, -1, 0
        for _ in range(40):
            for entry in (driver.execute_script(SCAN_JS) or []):
                name, href = str(entry.get("name") or "").strip(), str(entry.get("url") or "").strip()
                key = _group_identity(href) or _norm(name)
                if key and name and key not in collected:
                    collected[key] = {"name": name, "url": href}
            stagnant = stagnant + 1 if len(collected) == previous else 0
            previous = len(collected)
            if stagnant >= 4:
                break
            driver.execute_script(SCROLL_JS)
            time.sleep(1.3)
        log("Joined-group scan collected %d Facebook group(s) from 'Your groups'." % len(collected))
        return list(collected.values())
    except LoginRequired:
        raise
    except Exception as exc:
        log("Facebook joined-group scan failed (best effort): %s" % exc)
        return []


def progress_path(store_dir_path):
    return os.path.join(store_dir_path, "fbg_progress.json")


def load_progress(store_dir_path):
    try:
        with open(progress_path(store_dir_path), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_progress(store_dir_path, progress):
    os.makedirs(store_dir_path, exist_ok=True)
    progress["updated"] = _now()
    path, tmp = progress_path(store_dir_path), progress_path(store_dir_path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(progress, f)
    os.replace(tmp, path)


def run_queue(items, cfg, store_dir_path, log, stop_check=None):
    """items: list of dicts: {"day":int,"title":str,"text":str,
    "hashtags":str,"media":[abs paths]}  (date/time ignored — posts go
    immediately).  cfg: {"groups":[group names/URLs], "dash_url": optional
    override, "profile_root": optional override}.  Returns
    {"done":n,"failed":n,"skipped":n} counted per item×group delivery."""
    cfg = dict(cfg or {})
    log = log or (lambda m, c=None: None)
    groups = [str(g).strip() for g in (cfg.get("groups") or []) if str(g or "").strip()]
    if not groups:
        raise WorkflowError("No target Facebook groups are configured. Tick at least one joined group in the workflow settings (exact group name or its facebook.com/groups/… URL) and run the queue again.")
    progress = load_progress(store_dir_path)
    deliveries = progress.setdefault("deliveries", {})
    counts = {"done": 0, "failed": 0, "skipped": 0}
    planned = len(items or []) * len(groups)
    log("Facebook group queue: %d item(s) × %d group(s) = %d delivery(ies)." % (len(items or []), len(groups), planned))
    driver = ensure_driver(cfg.get("dash_url") or DEFAULT_DASH_URL,
                           cfg.get("profile_root") or store_dir_path, log)
    try:
        poster = FBGroupPoster(driver, log)
        attempted_any = False
        for item in (items or []):
            day = "?" if item.get("day") is None else str(item.get("day"))
            title = str(item.get("title") or "")
            text, hashtags = str(item.get("text") or "").strip(), str(item.get("hashtags") or "").strip()
            # caption.txt + hashtags.txt contract: one block, text + "\n\n" + hashtags.
            caption = (text + "\n\n" + hashtags) if (text and hashtags) else (text or hashtags)
            media = _item_media(item)
            problem = None
            if not caption:
                problem = "Day %s has no text and no hashtags — there is nothing to post." % day
            else:
                missing = [p for p in media if not os.path.isfile(p)]
                if missing:
                    problem = "Day %s media file(s) not found on disk: %s" % (day, ", ".join(missing))
            if problem:
                log("FAILED: %s" % problem)
                for group in groups:
                    deliveries[_delivery_key(item, group)] = {
                        "status": "failed", "title": title, "error": problem, "at": _now()}
                    counts["failed"] += 1
                save_progress(store_dir_path, progress)
                continue
            log("Day %s (%s): caption %d chars, %d media file(s); groups: %s."
                % (day, title or "untitled", len(caption), len(media), ", ".join(groups)))
            for group in groups:
                if stop_check and stop_check():
                    log("Stop requested — Facebook group queue paused. Rerun to continue where it left off.")
                    return counts
                key = _delivery_key(item, group)
                if (deliveries.get(key) or {}).get("status") == "done":
                    counts["skipped"] += 1
                    log("SKIP day %s → '%s' (already posted in an earlier run)." % (day, group))
                    continue
                if attempted_any:
                    log("Next group starts in %d seconds (extension v1.6.0 inter-group wait)." % GROUP_INTERVAL_S)
                    time.sleep(GROUP_INTERVAL_S)
                label = "day %s → '%s'" % (day, group)
                log("Posting %s…" % label)
                try:
                    poster.post_to_group(group, caption, media)
                    deliveries[key] = {"status": "done", "title": title, "at": _now()}
                    counts["done"] += 1
                    log("DONE %s. Progress: %d done, %d failed, %d skipped of %d."
                        % (label, counts["done"], counts["failed"], counts["skipped"], planned))
                except LoginRequired:
                    raise
                except Exception as exc:  # WorkflowError + selenium hiccups
                    err = str(exc) if isinstance(exc, WorkflowError) else "%s: %s" % (type(exc).__name__, exc)
                    deliveries[key] = {"status": "failed", "title": title, "error": err, "at": _now()}
                    counts["failed"] += 1
                    log("FAILED %s: %s" % (label, err))
                attempted_any = True
                save_progress(store_dir_path, progress)
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    log("Facebook group queue finished: %d done, %d failed, %d skipped."
        % (counts["done"], counts["failed"], counts["skipped"]))
    return counts
