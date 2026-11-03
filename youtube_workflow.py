#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
3SVerse LinkedIn Poster — YouTube Studio Mode (youtube workflow).

Faithful Python/Selenium port of the 3SVerse YouTube Campaign Uploader
Chrome extension (youtube-campaign-uploader v1.2.2) on the proven
web_workflow.py architecture: content.js locators/state → STATE_JS via
execute_script; background.js upload() → StudioPoster.upload_item();
trusted CDP input (dispatchMouseEvent/insertText/dispatchKeyEvent +
focus emulation); media attached via send_keys on Studio's
input[type=file]; scheduling via Studio's native Schedule radio +
date/time; Shorts rule ("Format: short" meta / #Shorts in the caption /
"short" in the filename) enforced by guaranteeing "#Shorts" in the
description; per-item running/completed/failed state persisted in
youtube_progress.json — completed days are skipped on rerun.

Runs against the user's own logged-in YouTube session (dedicated
"youtube" profile under the app's chrome-profile dir) in a normal
Chrome window — no API token, no OAuth consent screen. Everything types
and clicks through CDP trusted input with focus emulation, so the
window may sit in the background while Studio receives the upload.

Developed by www.3SVerse.com (c) 2026
Independent vendor — not affiliated with YouTube or Google.
"""

import json
import os
import re
import time
from datetime import datetime

PROFILE_SUBDIR = "youtube"
DEFAULT_DASH_URL = "https://studio.youtube.com/"

# ── content.js port: locator + state snapshot (chrome-free JS) ──────
# Same dense selectors as the extension's content script. target() is a
# selector try-list per control: stable CSS id first, then aria-label,
# then visible text, then CSS structure — Studio changes often, so every
# control has at least two ways to be found.
STATE_JS = r"""
const norm=v=>String(v||"").normalize("NFKC").replace(/\s+/g," ").trim().toLowerCase();const visible=e=>Boolean(e&&e.getClientRects().length&&getComputedStyle(e).visibility!=="hidden");const enabled=e=>visible(e)&&!e.matches(":disabled,[disabled],[aria-disabled='true']");const text=e=>norm(e?.getAttribute("aria-label")||e?.innerText||e?.textContent);const all=s=>[...document.querySelectorAll(s)];const controls=()=>all("button,[role=button],a,[role=link],tp-yt-paper-item,ytcp-button,tp-yt-paper-radio-button").filter(visible);
const MENU_SCOPES="ytd-popup-container,tp-yt-paper-dialog,[role=dialog],ytd-multi-page-menu-renderer";const ACCOUNT_ITEMS='ytd-account-item-renderer,yt-account-item-renderer,tp-yt-paper-item,[role=menuitem],[role=link],a[href*="/channel/"],a[href^="/@"]';const collapse=v=>norm(v).replace(/[\s@_-]+/g,"");function menuScopes(){const s=all(MENU_SCOPES).filter(visible);return s.length?s:[document.documentElement]}
function exactControl(name){return controls().find(e=>enabled(e)&&text(e)===norm(name))}
function currentChannel(){const candidates=["#entity-name","#channel-name","ytcp-entity-page-header-renderer #title","#account-name","ytd-active-account-header-renderer #channel-title"];for(const s of candidates){const e=document.querySelector(s);if(visible(e)&&text(e))return (e.innerText||e.textContent).trim()}const side=all("#entity-label-container,#channel-title,.account-name").find(visible);return side?(side.innerText||side.textContent).trim():""}
function target(name,arg){
 if(name==="avatar")return document.querySelector("button#avatar-btn")||all("button").find(e=>/account menu|account/.test(text(e)));
 if(name==="switchAccount")return all("a,ytd-compact-link-renderer,tp-yt-paper-item").find(e=>visible(e)&&text(e).includes("switch account"));
 if(name==="viewAllChannels")return all("a,tp-yt-paper-item,[role=link],button,ytcp-button").find(e=>visible(e)&&/view all channels/.test(text(e)));
 if(name==="channel"){const want=norm(arg),wcol=collapse(arg);const matchers=[e=>norm(e.innerText||e.textContent)===want,e=>norm((e.innerText||e.textContent||"").split("\n")[0])===want,e=>collapse(e.innerText||e.textContent)===wcol||collapse((e.innerText||e.textContent||"").split("\n")[0])===wcol];const scoped=menuScopes().filter(s=>s!==document.documentElement);const pool=scoped.length?[...new Set(scoped.flatMap(s=>[...s.querySelectorAll(ACCOUNT_ITEMS)]))].concat(all(ACCOUNT_ITEMS).filter(e=>!scoped.some(s=>s.contains(e)))):all(ACCOUNT_ITEMS);for(const match of matchers){const hit=pool.filter(visible).find(match);if(hit)return hit.closest("ytd-account-item-renderer,yt-account-item-renderer,tp-yt-paper-item,a,[role=link],[role=menuitem]")||hit}return null}
 if(name==="create")return document.querySelector('button[aria-label="Create"]')||exactControl("Create");
 if(name==="uploadVideo")return all("tp-yt-paper-item,[role=menuitem],button").find(e=>enabled(e)&&/upload video/.test(text(e)));
 if(name==="fileInput")return all('input[type="file"]').find(e=>!e.disabled);
 if(name==="title")return document.querySelector("#title-textarea div#textbox")||all('div#textbox[contenteditable="true"]').filter(visible)[0];
 if(name==="description")return document.querySelector("#description-textarea div#textbox")||all('div#textbox[contenteditable="true"]').filter(visible)[1];
 if(name==="showMore")return document.querySelector("ytcp-button#toggle-button")||controls().find(e=>enabled(e)&&text(e)==="show more");
 if(name==="tags")return document.querySelector('input[aria-label="Tags"]');
 if(name==="notKids")return document.querySelector('tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]')||all("tp-yt-paper-radio-button").find(e=>/not made for kids/.test(text(e)));
 if(name==="next")return document.querySelector("ytcp-button#next-button")||exactControl("Next");
 if(name==="schedule")return document.querySelector('tp-yt-paper-radio-button[name="SCHEDULE"]')||all("tp-yt-paper-radio-button").find(e=>text(e)==="schedule");
 if(name==="date")return all("ytcp-datepicker input,input").find(e=>visible(e)&&(/date/.test(norm(e.getAttribute("aria-label")))||/date/.test(norm(e.id))));
 if(name==="time")return all("ytcp-time-of-day-picker input,input").find(e=>visible(e)&&(/time/.test(norm(e.getAttribute("aria-label")))||/time/.test(norm(e.id))));
 if(name==="done")return document.querySelector("ytcp-button#done-button")||controls().find(e=>enabled(e)&&/^(schedule|publish|done)$/.test(text(e)));
 if(name==="close")return document.querySelector("ytcp-button#close-button")||controls().find(e=>enabled(e)&&/^(close|done)$/.test(text(e)));
 if(name==="contentNav")return all("a,tp-yt-paper-item,tp-yt-paper-tab,[role=tab],[role=link]").filter(visible).find(e=>text(e)==="content"||/\/videos\/?$/.test(e.getAttribute("href")||""));
 return null}
function value(name){const e=target(name);return e?("value" in e?e.value:e.innerText||e.textContent||""):""}
function summary(){return "url="+location.href+", channel="+(currentChannel()||"unknown")+", controls=["+controls().map(text).filter(Boolean).slice(0,20).join(" | ")+"]"}
function point(e){e.scrollIntoView({block:"center",inline:"center"});e.focus({preventScroll:true});const r=e.getBoundingClientRect();return{x:r.left+r.width/2,y:r.top+r.height/2}}
function describe(e){const id=e.id?" #"+e.id:"";const label=e.getAttribute("aria-label")||(e.innerText||e.textContent||"").trim();return e.tagName.toLowerCase()+id+" '"+String(label||"").slice(0,40)+"'"}
function state(){const body=norm(document.body.innerText);return{url:location.href,currentChannel:currentChannel(),avatarReady:Boolean(target("avatar")),switchReady:Boolean(target("switchAccount")),accountListReady:Boolean(all("ytd-account-item-renderer,yt-account-item-renderer").find(visible))||all(MENU_SCOPES).some(s=>visible(s)&&[...s.querySelectorAll("ytd-account-item-renderer,yt-account-item-renderer,tp-yt-paper-item,[role=menuitem]")].some(visible)),viewAllChannelsReady:Boolean(target("viewAllChannels")),createReady:Boolean(target("create")),uploadVideoReady:Boolean(target("uploadVideo")),fileReady:Boolean(target("fileInput")),detailsReady:Boolean(target("title"))&&Boolean(target("description")),title:value("title"),description:value("description"),tags:value("tags"),nextReady:Boolean(target("next")&&enabled(target("next"))),scheduleReady:Boolean(target("schedule")),date:value("date"),time:value("time"),doneReady:Boolean(target("done")&&enabled(target("done"))),uploadComplete:/checks complete|upload complete|processing complete|finished processing/.test(body)&&!/uploading\s+\d{1,2}%/.test(body),success:/video (?:uploaded|scheduled|published)|upload complete/.test(body)&&Boolean(target("close")),summary:summary()}}
"""

STATE_SNIPPET = STATE_JS + " const __s = state(); __s.body = norm(document.body.innerText); return __s;"
# Arguments reach the JS as arguments[0]/[1] — %-formatting would collide with the literal % inside the uploadComplete regex above.
LOCATE_JS = (STATE_JS + " const __e = target(arguments[0], arguments[1]);"
             " if (!__e) return { ok: false, error: 'YouTube control not found: ' + arguments[0] + '; ' + summary() };"
             " return { ok: true, point: point(__e), info: describe(__e) };")
FOCUS_JS = (STATE_JS + " const __e = target(arguments[0], arguments[1]);"
            " if (!__e) return { ok: false, error: 'YouTube did not focus the ' + arguments[0] + ' field; ' + summary() };"
            " __e.focus({ preventScroll: true }); return { ok: document.activeElement === __e };")
FILE_INPUT_JS = (STATE_JS + " const __e = target('fileInput'); if (!__e) return null; __e.scrollIntoView({ block: 'center' }); return __e;")

class WorkflowError(Exception):
    pass

class LoginRequired(WorkflowError):
    pass

def _norm(s):
    return " ".join(str(s or "").split()).strip().lower()

def _clean(s):
    return str(s or "").replace("\r", "").strip()

def _stamp():
    return datetime.now().isoformat(timespec="seconds")

def schedule_values(date_text, hhmm):
    """background.js scheduleValues(): ISO date + HH:MM → Studio fields."""
    year, month, day = str(date_text).split("-")
    hours, minutes = [int(x) for x in str(hhmm).split(":")]
    return {"date": "%s/%s/%s" % (month, day, year),
            "time": "%d:%02d %s" % (hours % 12 or 12, minutes,
                                    "PM" if hours >= 12 else "AM")}

def _title_for(item):
    """lib.js parseCampaign: Day title → video title, first 100 chars."""
    title = _clean(item.get("title"))
    return (title or "3S Verse - Day %s" % (item.get("day") or "?"))[:100]

def _item_media(item):
    media = item.get("media") or []
    if isinstance(media, str):
        media = [media]
    return [str(p) for p in media if str(p).strip()]

def _description_for(item):
    """Description = caption text + hashtag block (paragraph breaks kept),
    with "#Shorts" appended per the extension's Shorts rule: 'Format:
    short' meta / #Shorts in the caption / 'short' in the filename."""
    fmt = _clean(item.get("format")).lower()
    caption = "%s %s" % (item.get("text") or "", item.get("hashtags") or "")
    is_short = fmt in ("short", "shorts") or (not fmt and (
        "#shorts" in caption.lower()
        or any("short" in os.path.basename(p).lower()
               for p in _item_media(item))))
    parts = [p for p in (_clean(item.get("text")),
                         _clean(item.get("hashtags"))) if p]
    description = "\n\n".join(parts)
    if is_short and "#shorts" not in description.lower():
        description = (description + "\n\n#Shorts").strip()
    return description

def _tags_for(item):
    """lib.js parseCampaign: hashtags become the video's tags."""
    tags, seen = [], set()
    for source in (item.get("hashtags"), item.get("text")):
        for token in re.findall(r"#[\w-]+", str(source or ""), re.UNICODE):
            tag = token[1:]
            if tag and tag.lower() not in seen:
                seen.add(tag.lower())
                tags.append(tag)
    return ",".join(tags)

class StudioPoster:
    """One Selenium Chrome session driving the extension workflow."""

    def __init__(self, profile_dir, dash_url=DEFAULT_DASH_URL, log=None):
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        self.dash_url = dash_url or DEFAULT_DASH_URL
        self.log = log or (lambda m, c=None: None)
        opts = Options()
        opts.add_argument("--user-data-dir=%s" % profile_dir)
        opts.add_argument("--profile-directory=Default")
        opts.add_argument("--no-first-run")
        opts.add_argument("--no-default-browser-check")
        opts.add_argument("--disable-session-crashed-bubble")
        opts.add_argument("--hide-crash-restore-bubble")
        opts.add_argument("--window-size=1280,900")
        # Chrome options identical to web_workflow.py's
        opts.set_capability("goog:loggingPrefs",
                            {"performance": "ALL", "browser": "ALL"})
        self.driver = webdriver.Chrome(options=opts)
        self.driver.set_page_load_timeout(90)

    # ── low-level CDP (same commands as the extension) ───────────────
    def _state(self):
        return self.driver.execute_script(STATE_SNIPPET)

    def _screen_summary(self):
        try:
            return str(self.driver.execute_script(STATE_JS + " return summary();"))
        except Exception:
            return "state unavailable"

    def _safe_url(self):
        try:
            return self.driver.current_url or ""
        except Exception:
            return ""

    def _login_check(self):
        url = self._safe_url()
        if "accounts.google." in url or "accounts.youtube." in url \
                or "ServiceLogin" in url:
            raise LoginRequired(
                "YouTube is asking you to sign in — open the Chrome window "
                "that this app launched, sign in to the YouTube channel "
                "account, then start the upload again.")

    def _wait_state(self, predicate, timeout, description):
        started, state = time.time(), None
        while time.time() - started < timeout:
            self._login_check()
            try:
                state = self._state()
            except Exception:
                state = None
            if state and predicate(state):
                return state
            time.sleep(0.4)
        raise WorkflowError("%s; %s" % (
            description,
            (state or {}).get("summary") or self._screen_summary()))

    def _locate(self, name, arg=None, timeout=0):
        """Run the target() try-list; optional polling for slow SPA steps."""
        started = time.time()
        while True:
            res = self.driver.execute_script(LOCATE_JS, str(name), str(arg or ""))
            if res and res.get("ok"):
                self.log("Studio control '%s' matched: %s" % (name, res["info"]))
                return res["point"]
            if time.time() - started >= timeout:
                raise WorkflowError((res or {}).get(
                    "error", "YouTube control not found: %s" % name))
            time.sleep(0.4)

    def _focus(self, name, arg=None):
        res = self.driver.execute_script(FOCUS_JS, str(name), str(arg or ""))
        if not res or not res.get("ok"):
            raise WorkflowError((res or {}).get(
                "error", "YouTube did not focus the %s field." % name))

    def _focus_emulation(self):
        try:
            self.driver.execute_cdp_cmd(
                "Emulation.setFocusEmulationEnabled", {"enabled": True})
        except Exception:
            pass

    def _click(self, name, arg=None):
        point = self._locate(name, arg)
        self._focus_emulation()
        self.driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
            "type": "mouseMoved", "x": point["x"], "y": point["y"]})
        for t in ("mousePressed", "mouseReleased"):
            self.driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
                "type": t, "x": point["x"], "y": point["y"],
                "button": "left", "clickCount": 1})

    def _key(self, key, code, vk, modifiers=0, keyup=False):
        self.driver.execute_cdp_cmd("Input.dispatchKeyEvent", {
            "type": "keyUp" if keyup else "rawKeyDown",
            "key": key, "code": code,
            "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk,
            "modifiers": modifiers})

    def _select_all(self):
        self._key("a", "KeyA", 65, modifiers=2)
        self._key("a", "KeyA", 65, modifiers=2, keyup=True)

    def _replace_text(self, name, text, commit="Tab", timeout=0):
        """background.js replace(): select-all + trusted insertText, then an
        optional Tab/Enter commit (commit=None for title/description)."""
        self._locate(name, timeout=timeout)
        self._focus_emulation()
        self._focus(name)
        self._select_all()
        self.driver.execute_cdp_cmd("Input.insertText", {"text": text})
        if commit == "Enter":
            self._key("Enter", "Enter", 13)
            self._key("Enter", "Enter", 13, keyup=True)
        elif commit:
            self._key("Tab", "Tab", 9)
            self._key("Tab", "Tab", 9, keyup=True)

    # ── navigation ───────────────────────────────────────────────────
    def _open(self, url):
        try:
            self.driver.get(url)
        except Exception:
            pass  # Studio may keep streaming; the state waits verify the UI
        self._wait_loaded()

    def _wait_loaded(self, timeout=60):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.driver.execute_script(
                        "return document.readyState") == "complete":
                    return
            except Exception:
                pass
            time.sleep(0.3)
        raise WorkflowError("YouTube did not finish loading in time.")

    def hard_open(self):
        self._open("about:blank")
        self._open(self.dash_url)

    # ── login / channel verification ─────────────────────────────────
    def verify_login(self):
        self._login_check()
        try:
            s = self._wait_state(
                lambda s: s["createReady"] or s["currentChannel"], 90,
                "YouTube Studio did not become ready")
        except WorkflowError:
            raise LoginRequired(
                "YouTube Studio did not load a signed-in channel — open the "
                "Chrome window that this app launched, sign in to YouTube "
                "with your channel account, then start the upload again.")
        self.log("YouTube channel verified: %s"
                 % (s.get("currentChannel") or "Studio ready (signed in)"))

    # ── media attach ─────────────────────────────────────────────────
    def _attach_file(self, path):
        abspath = os.path.abspath(path)
        if not os.path.isfile(abspath):
            raise WorkflowError("Video file not found: %s — put day-N.mp4 "
                                "files in the linked campaign folder." % abspath)
        element = self.driver.execute_script(FILE_INPUT_JS)
        if not element:
            raise WorkflowError("YouTube Studio's video file input did not "
                                "appear; %s" % self._screen_summary())
        self._focus_emulation()
        try:
            element.send_keys(abspath)
        except Exception:
            # Hidden-input fallback: make it interactable, retry.
            self.driver.execute_script(
                "arguments[0].style.cssText+=';display:block!important;"
                "visibility:visible!important;width:10px;height:10px;"
                "opacity:1;';", element)
            element.send_keys(abspath)
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                if self.driver.execute_script(
                        "return arguments[0].files.length", element) == 1:
                    self.log("Video attached to Studio's file input: %s"
                             % os.path.basename(abspath))
                    return
            except Exception:
                return  # Studio replaced the input — details wait verifies
            time.sleep(0.5)
        raise WorkflowError("YouTube Studio did not accept %s into its file "
                            "input — is it a valid .mp4/.mov/.webm/.m4v video?"
                            % os.path.basename(abspath))

    def verify_scheduled(self, title, timeout=150):
        """Verify the scheduled entry shows in Studio's Content list."""
        prefix = _norm(title)[:40]
        if not prefix:
            return
        list_url = ""
        url = self._safe_url()
        if "/channel/" in url:
            tail = url.split("/channel/", 1)[1]
            channel = tail.split("?")[0].split("#")[0].split("/")[0]
            list_url = "%s/channel/%s/videos" % (url.split("/channel/", 1)[0],
                                                 channel)
        next_reload, deadline = 0.0, time.time() + timeout
        while time.time() < deadline:
            self._login_check()
            try:
                body = str(self.driver.execute_script(
                    STATE_JS + " return norm(document.body.innerText);"))
            except Exception:
                body = ""
            if prefix in body:
                self.log("Scheduled video visible in Studio's Content list: "
                         "%s" % title[:60])
                return
            if list_url and time.time() >= next_reload:
                next_reload = time.time() + 15.0
                try:
                    self._open(list_url)
                except WorkflowError:
                    pass
            time.sleep(3.0)
        raise WorkflowError("The scheduled upload '%s' did not appear in "
                            "YouTube Studio's Content list within %d seconds —"
                            " open Studio > Content and check the video's "
                            "state." % (title[:60], int(timeout)))

    # ── background.js upload() port ──────────────────────────────────
    def upload_item(self, item):
        """One video per call: Create → Upload videos → file → details
        (title, description, tags, not-made-for-kids) → 3 Next steps →
        Schedule date/time → wait for checks → Done → verify in the
        Content list. Returns True on success."""
        media = _item_media(item)
        if not media:
            raise WorkflowError("Day %s has no video file attached — name it"
                                " day-%s.mp4 (or reel-%s.mp4) in the linked"
                                " campaign folder."
                                % (item.get("day"), item.get("day"),
                                   item.get("day")))
        path = media[0]
        if len(media) > 1:
            self.log("Day %s: %d media files attached — uploading the first"
                     " one (%s)." % (item.get("day"), len(media),
                                     os.path.basename(path)))
        date_text, hhmm = _clean(item.get("date")), _clean(item.get("time"))
        if (not re.match(r"^\d{4}-\d{2}-\d{2}$", date_text)
                or not re.match(r"^\d{1,2}:\d{2}$", hhmm)):
            raise WorkflowError("Day %s has a bad schedule date/time (date="
                                "%r, time=%r) — expected 'YYYY-MM-DD' and"
                                " 'HH:MM'." % (item.get("day"), date_text,
                                               hhmm))
        title, description = _title_for(item), _description_for(item)
        tags = _tags_for(item)
        self.log("Day %s → %s %s on YouTube (%s)…"
                 % (item.get("day"), date_text, hhmm, os.path.basename(path)))
        self.hard_open()
        self._wait_state(lambda s: s["createReady"], 60,
                         "YouTube Studio's Create button did not appear")
        self._click("create")
        self._wait_state(lambda s: s["uploadVideoReady"], 30,
                         "YouTube Studio's 'Upload videos' option did not appear")
        self._click("uploadVideo")
        self._wait_state(lambda s: s["fileReady"], 30,
                         "YouTube Studio's video file input did not appear")
        self._attach_file(path)
        self._wait_state(lambda s: s["detailsReady"], 180,
                         "YouTube Studio's upload details form did not become "
                         "ready for %s" % os.path.basename(path))
        self._replace_text("title", title, None)
        self._replace_text("description", description, None)
        self._wait_state(
            lambda s: _norm(s["title"]) == _norm(title)
            and _norm(s["description"]) == _norm(description), 20,
            "YouTube Studio did not retain the title, description and hashtags")
        try:
            self._click("notKids")
        except WorkflowError as exc:
            self.log("Made-for-Kids toggle skipped (%s) — Studio may have "
                     "renamed the control." % str(exc)[:100])
        if tags:
            try:
                self._click("showMore")
                self._replace_text("tags", tags, "Enter", timeout=15)
                time.sleep(2.0)
            except WorkflowError as exc:
                raise WorkflowError("Tags were not committed: %s" % exc)
        for step in range(3):
            self._wait_state(lambda s: s["nextReady"], 180,
                             "YouTube Studio's Next button is not ready (step "
                             "%d of 3)" % (step + 1))
            self._click("next")
            time.sleep(1.8)
        self._wait_state(lambda s: s["scheduleReady"], 60,
                         "YouTube Studio's Visibility/Schedule step did not "
                         "appear")
        self._click("schedule")
        time.sleep(0.8)
        wanted = schedule_values(date_text, hhmm)
        self._replace_text("date", wanted["date"], "Tab")
        self._replace_text("time", wanted["time"], "Tab")
        self._wait_state(
            lambda s: _norm(s["date"]).find(_norm(wanted["date"])) >= 0
            and _norm(s["time"]).find(_norm(wanted["time"])) >= 0, 20,
            "YouTube Studio did not retain the requested schedule date/time")
        self._wait_state(
            lambda s: s["uploadComplete"] and s["doneReady"], 1200,
            "YouTube Studio did not finish upload/processing for %s (waited "
            "20 minutes)" % os.path.basename(path))
        self._click("done")
        self._wait_state(lambda s: s["success"] or not s["detailsReady"], 180,
                         "YouTube Studio did not confirm the scheduled upload")
        self.verify_scheduled(title)
        time.sleep(2.5)
        return True

    def close(self):
        try:
            self.driver.quit()
        except Exception:
            pass

# ── resume-safe progress (youtube_progress.json) ─────────────────────
def progress_path(store_dir_path):
    return os.path.join(store_dir_path, "youtube_progress.json")

def load_progress(store_dir_path):
    try:
        with open(progress_path(store_dir_path), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_progress(store_dir_path, progress):
    os.makedirs(store_dir_path, exist_ok=True)
    tmp = progress_path(store_dir_path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(progress, f)
    os.replace(tmp, progress_path(store_dir_path))

def item_key(item, cfg=None, store_dir_path=None):
    """Progress key: '<normpath-folder>|<day>' (same shape as the shell's
    store keys). Folder = item/cfg 'folder', else the first media file's
    directory."""
    folder = str(item.get("folder") or (cfg or {}).get("folder") or "").strip()
    if not folder:
        media = _item_media(item)
        if media:
            folder = os.path.dirname(os.path.abspath(media[0]))
    return "%s|%s" % (os.path.normpath(folder or str(store_dir_path or "")),
                      item.get("day"))

# ── driver session (shared across runs, like the app shell does) ─────
_SESSION = {"poster": None}

def _poster_alive(poster):
    try:
        _ = poster.driver.current_url
        return True
    except Exception:
        return False

def _stop_requested(stop_check):
    """Accepts a callable OR a threading.Event (the shell passes either)."""
    if stop_check is None:
        return False
    if callable(stop_check):
        try:
            return bool(stop_check())
        except Exception:
            return False
    is_set = getattr(stop_check, "is_set", None)
    return bool(is_set()) if callable(is_set) else False

def _get_poster(cfg, store_dir_path, log):
    poster = _SESSION["poster"]
    dash_url = str(cfg.get("dash_url") or DEFAULT_DASH_URL)
    if poster is not None and _poster_alive(poster):
        poster.dash_url = dash_url
        return poster
    if poster is not None:
        poster.close()
    _SESSION["poster"] = None
    profile_root = str(cfg.get("profile_root")
                       or os.path.join(store_dir_path, "chrome-profile"))
    ensure_driver(dash_url, profile_root, log=log)
    return _SESSION["poster"]

def ensure_driver(start_url, profile_root, log=None):
    """Start Chrome (own user-data-dir = os.path.join(profile_root, PROFILE_SUBDIR)),
    open start_url, verify logged in, return driver."""
    log = log or (lambda m, c=None: None)
    if not profile_root:
        raise WorkflowError("profile_root is required — pass the app's "
                            "chrome-profile directory so a dedicated "
                            "'youtube' subprofile can be used.")
    start_url = str(start_url or DEFAULT_DASH_URL)
    poster = _SESSION["poster"]
    if poster is not None:
        if _poster_alive(poster):
            poster.dash_url = start_url
            poster.hard_open()
            poster.verify_login()
            return poster.driver
        poster.close()
    _SESSION["poster"] = None
    log("starting your Chrome for YouTube Studio (first run may take a minute)…")
    poster = StudioPoster(os.path.join(profile_root, PROFILE_SUBDIR),
                          dash_url=start_url, log=log)
    _SESSION["poster"] = poster
    poster.hard_open()
    poster.verify_login()
    return poster.driver

def run_queue(items, cfg, store_dir_path, log, stop_check=None):
    """items: list of dicts: {"day":int,"title":str,"text":str,"hashtags":str,
        "media":[abs mp4 paths],"date":"YYYY-MM-DD","time":"HH:MM","format":"video|short"}
    cfg: {"dash_url": optional override, "profile_root": optional override}.
    Returns {"done":n,"failed":n,"skipped":n}. Days already marked "completed"
    in youtube_progress.json are skipped. Login/startup failures
    (LoginRequired/WorkflowError from ensure_driver) propagate; a per-item
    failure is recorded as "failed" and stops the queue — rerun resumes past
    completed days."""
    cfg = dict(cfg or {})
    log = log or (lambda m, c=None: None)
    progress = load_progress(store_dir_path)
    counts, plan = {"done": 0, "failed": 0, "skipped": 0}, []
    for item in items or []:
        key = item_key(item, cfg, store_dir_path)
        if (progress.get(key) or {}).get("status") == "completed":
            counts["skipped"] += 1
            log("skip (already scheduled in Chrome): Day %s — %s"
                % (item.get("day"), _title_for(item)))
            continue
        plan.append((key, item))
    if not plan:
        log("YouTube queue: nothing to upload (%d day(s) already completed)."
            % counts["skipped"])
        return counts
    poster = _get_poster(cfg, store_dir_path, log)
    for key, item in plan:
        if _stop_requested(stop_check):
            log("Stopped — remaining YouTube days stay pending; completed "
                "days are skipped on rerun.")
            break
        day = item.get("day")
        log("YouTube upload — Day %s → %s %s …"
            % (day, item.get("date"), item.get("time")))
        progress[key] = {"status": "running", "detail": _title_for(item), "updatedAt": _stamp()}
        save_progress(store_dir_path, progress)
        try:
            poster.upload_item(item)
        except LoginRequired as exc:
            progress[key] = {"status": "failed", "detail": "sign-in needed: %s" % str(exc)[:280], "updatedAt": _stamp()}
            save_progress(store_dir_path, progress)
            counts["failed"] += 1
            log("%s — sign in to YouTube in the opened Chrome window, then start again (completed days are skipped automatically)." % str(exc)[:220])
            break
        except Exception as exc:
            progress[key] = {"status": "failed", "detail": str(exc)[:300], "updatedAt": _stamp()}
            save_progress(store_dir_path, progress)
            counts["failed"] += 1
            log("Day %s failed: %s — fix the problem and start again; completed days are skipped automatically." % (day, str(exc)[:200]))
            break
        progress[key] = {"status": "completed", "detail": "%s %s" % (item.get("date"), item.get("time")), "updatedAt": _stamp()}
        save_progress(store_dir_path, progress)
        counts["done"] += 1
        if not _stop_requested(stop_check):
            time.sleep(4.0)
    log("YouTube queue %s — %d scheduled, %d failed, %d skipped."
        % ("stopped" if _stop_requested(stop_check) else "complete",
           counts["done"], counts["failed"], counts["skipped"]))
    return counts
