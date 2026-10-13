import json
import os
import random
import re
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import requests

OPTIONS_FILE = "/data/options.json"
PHOTO_DIR = Path("/share/city_photo")
MANIFEST = PHOTO_DIR / "collections.json"
EVENT_PHOTO = "city_photo_updated"
EVENT_COLLECTIONS = "city_photo_collections_changed"
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN")
UNSPLASH_API = "https://api.unsplash.com"
UNSPLASH_HOURLY_LIMIT = 50


def log(msg):
    print(msg, flush=True)


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def fire_event(event_type, data):
    if not SUPERVISOR_TOKEN:
        log("No SUPERVISOR_TOKEN, can't notify Home Assistant")
        return
    try:
        r = requests.post(
            f"http://supervisor/core/api/events/{event_type}",
            headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}"},
            json=data,
            timeout=10,
        )
        if r.status_code != 200:
            log(f"Event {event_type} failed: {r.status_code} {r.text}")
    except Exception as e:
        log(f"Event {event_type} error: {e}")


def build_jobs(opts):
    """One job per collection + orientation. 'both' becomes two jobs."""
    jobs = []
    seen = set()
    for c in opts.get("collections", []):
        name = (c.get("name") or "").strip()
        slug = slugify(name)
        terms = [t.strip() for t in c.get("search_terms", []) if t.strip()]
        if not slug or not terms:
            log(f"Skipping collection '{name}': needs a name and at least one search term")
            continue
        if slug in seen:
            log(f"Skipping '{name}': another collection already uses that name")
            continue
        seen.add(slug)
        choice = c.get("orientation", "landscape")
        orientations = ["landscape", "portrait"] if choice == "both" else [choice]
        for orientation in orientations:
            jobs.append(
                {"slug": slug, "name": name, "orientation": orientation, "terms": terms}
            )
    return jobs


def write_manifest(jobs):
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    data = [
        {"slug": j["slug"], "name": j["name"], "orientation": j["orientation"]}
        for j in jobs
    ]
    MANIFEST.write_text(json.dumps(data))


def fetch_photo(job, key, size):
    headers = {"Authorization": f"Client-ID {key}"}
    term = random.choice(job["terms"])
    label = f"{job['slug']}/{job['orientation']}"
    log(f"[{label}] fetching: {term}")

    resp = requests.get(
        f"{UNSPLASH_API}/photos/random",
        headers=headers,
        params={"query": term, "orientation": job["orientation"]},
        timeout=15,
    )
    if resp.status_code == 401:
        log("Unsplash says your Access Key is bad (401). Check the add-on config.")
        return
    if resp.status_code == 403:
        log("Unsplash says rate limit hit (403). Raise the interval or cut collections.")
        return
    if resp.status_code != 200:
        log(f"[{label}] Unsplash error: {resp.status_code}")
        return

    data = resp.json()
    img = requests.get(data["urls"][size], timeout=60)
    if img.status_code != 200:
        log(f"[{label}] download failed: {img.status_code}")
        return

    base = f"{job['slug']}_{job['orientation']}"
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    final = PHOTO_DIR / f"{base}.jpg"
    tmp = PHOTO_DIR / f".{base}.tmp"
    tmp.write_bytes(img.content)
    os.replace(tmp, final)  # atomic, HA never reads a half-written file

    meta = {
        "slug": job["slug"],
        "name": job["name"],
        "orientation": job["orientation"],
        "search_term": term,
        "photographer": data.get("user", {}).get("name"),
        "photo_url": data.get("links", {}).get("html"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    (PHOTO_DIR / f"{base}.json").write_text(json.dumps(meta))

    try:  # Unsplash API rules ask for this ping when a photo is used
        requests.get(data["links"]["download_location"], headers=headers, timeout=10)
    except Exception:
        pass

    log(f"[{label}] saved ({len(img.content) // 1024} KB)")
    fire_event(EVENT_PHOTO, meta)


def idle(reason):
    log(reason)
    while True:
        time.sleep(3600)


def main():
    with open(OPTIONS_FILE) as f:
        opts = json.load(f)

    key = opts.get("unsplash_access_key")
    if not key:
        idle("No Unsplash Access Key set. Add it in the Configuration tab, then restart.")

    jobs = build_jobs(opts)
    if not jobs:
        idle("No valid collections configured. Add one in the Configuration tab.")

    interval = opts["interval_minutes"]
    per_hour = len(jobs) * 60 / interval
    log(f"{len(jobs)} images per cycle, about {per_hour:.0f} Unsplash requests/hour")
    if per_hour > UNSPLASH_HOURLY_LIMIT * 0.9:
        log("WARNING: that's close to Unsplash's 50/hour limit. Raise the interval.")

    write_manifest(jobs)
    time.sleep(10)
    fire_event(EVENT_COLLECTIONS, {})

    while True:
        for job in jobs:
            try:
                fetch_photo(job, key, opts["image_size"])
            except Exception as e:
                log(f"Error on {job['slug']}/{job['orientation']}: {e}")
                log(traceback.format_exc())
            time.sleep(2)
        time.sleep(interval * 60)


if __name__ == "__main__":
    main()
