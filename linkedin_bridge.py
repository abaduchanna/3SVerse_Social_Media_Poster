#!/usr/bin/env python3
# linkedin_bridge.py — uniform adapter around the proven LinkedIn WebPoster.
# Exposes the same run_queue interface as meta/youtube/fbg workflows so the
# Social Media Poster shell can drive all four platforms identically.
import json
import os
import time

import web_workflow as ww

PROFILE_SUBDIR = "linkedin"
DEFAULT_DASH_URL = ww.DASHBOARD_URL_DEFAULT
WorkflowError = ww.WebError
LoginRequired = ww.LoginRequired


def _profile_dir(profile_root):
    return os.path.join(profile_root, PROFILE_SUBDIR)


def ensure_driver(start_url, profile_root, log=None):
    """One WebPoster session (own Chrome user-data-dir per platform)."""
    return ww.WebPoster(_profile_dir(profile_root),
                        dashboard_url=start_url or DEFAULT_DASH_URL,
                        log=log or (lambda m, c=None: None))


def progress_path(store_dir_path):
    return os.path.join(store_dir_path, "linkedin_progress.json")


def load_progress(store_dir_path):
    try:
        with open(progress_path(store_dir_path), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_progress(store_dir_path, progress):
    try:
        with open(progress_path(store_dir_path), "w",
                  encoding="utf-8") as f:
            json.dump(progress, f, indent=1)
    except Exception:
        pass


def run_queue(items, cfg, store_dir_path, log, stop_check=None):
    """items: [{"day","title","text","hashtags","media":[paths],
               "date","time","_key"}] — one LinkedIn post per item.
    Schedules each through the real composer (schedule-first-then-caption).
    Returns {"done","failed","skipped"}."""
    log = log or (lambda m, c=None: None)
    prog = load_progress(store_dir_path)
    done = failed = skipped = 0
    poster = None
    try:
        poster = ensure_driver(cfg.get("dash_url") or "", store_dir_path,
                               log)
        for it in items:
            if stop_check and stop_check():
                log("stopped by user", "#f5c518")
                break
            key = it.get("_key") or "linkedin|%s" % it.get("day", 0)
            if (prog.get(key) or {}).get("status") == "completed":
                log("skip (already scheduled in Chrome): %s"
                    % it.get("title", ""), "#9b97b3")
                skipped += 1
                continue
            media = it.get("media") or []
            if not media:
                log("skip (no image/video for LinkedIn): Day %s"
                    % it.get("day"), "#f5c518")
                skipped += 1
                prog[key] = {"status": "skipped",
                             "detail": "no media"}
                save_progress(store_dir_path, prog)
                continue
            caption = it.get("text", "")
            if it.get("hashtags"):
                caption = (caption.rstrip() + "\n\n"
                           + it["hashtags"]).strip()
            log("Day %s — %s …" % (it.get("day"), it.get("title", "")),
                "#78a6ff")
            prog[key] = {"status": "running",
                         "detail": it.get("title", ""),
                         "updatedAt": time.strftime("%Y-%m-%d %H:%M:%S")}
            save_progress(store_dir_path, prog)
            try:
                poster.post_item(media[0], caption,
                                 it.get("date"), it.get("time"))
                prog[key] = {"status": "completed",
                             "detail": it.get("title", ""),
                             "scheduled": "%s %s" % (it.get("date"),
                                                     it.get("time")),
                             "updatedAt": time.strftime(
                                 "%Y-%m-%d %H:%M:%S")}
                done += 1
                log("Day %s scheduled for %s %s ✓"
                    % (it.get("day"), it.get("date"), it.get("time")),
                    "#c7ef70")
            except Exception as exc:
                prog[key] = {"status": "failed",
                             "detail": str(exc)[:300],
                             "updatedAt": time.strftime(
                                 "%Y-%m-%d %H:%M:%S")}
                failed += 1
                log("Day %s FAILED: %s" % (it.get("day"), exc),
                    "#ef6a52")
            save_progress(store_dir_path, prog)
    finally:
        if poster is not None:
            poster.close()
    return {"done": done, "failed": failed, "skipped": skipped}
