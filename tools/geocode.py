#!/usr/bin/env python3
"""Place restaurants on the map from their street addresses (deterministic, no AI).

Inputs : data/restaurants.json   one record per restaurant (hand-editable source of truth)
Outputs: data/restaurants.json   lat/lng + geo{confidence, source} filled in for records that lack them
         data/geocode_cache.json every Nominatim answer, so reruns never repeat a request
         data/review.csv         records that could not be placed confidently, for a human to fix
         restaurants.js          (with --emit) the file the map page loads

A record that already has a lat/lng with geo.source == "manual" is never touched: hand-placed wins.
Confidence: high = Nominatim matched the house number; low = street/area-level guess (left off the
map unless --include-low); none = no result.

    python3 tools/geocode.py run --contact you@example.com --emit restaurants.js
    python3 tools/geocode.py emit                  # rebuild restaurants.js without any network use
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
RESTAURANTS = os.path.join(DATA, "restaurants.json")
CACHE = os.path.join(DATA, "geocode_cache.json")
REVIEW = os.path.join(DATA, "review.csv")
NOMINATIM = "https://nominatim.openstreetmap.org/search"
MIN_DELAY = 1.1  # Nominatim's usage policy: at most one request per second
# Greater Seattle (west, south, east, north); results outside it are not trusted.
VIEWBOX = (-122.65, 47.30, -121.80, 47.85)
FIELDS = ["id", "name", "address", "neighborhood", "cuisine", "price", "description", "sources", "lat", "lng", "geo"]


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def slugify(name, neighborhood=""):
    s = re.sub(r"[^a-z0-9]+", "-", f"{name} {neighborhood}".lower()).strip("-")
    return s or "restaurant"


def maps_url(r):
    """Google Maps search link from name + address (no API key needed)."""
    q = urllib.parse.quote_plus(f"{r['name']} {r.get('address', '')}".strip())
    return f"https://www.google.com/maps/search/?api=1&query={q}"


def directions_url(r):
    q = urllib.parse.quote_plus(f"{r['name']} {r.get('address', '')}".strip())
    return f"https://www.google.com/maps/dir/?api=1&destination={q}"


def query_for(address):
    """Nominatim wants a city; Times lists often give just a street address."""
    a = address.strip()
    if not re.search(r"\b(WA|Washington)\b", a, re.I):
        a += ", Seattle, WA"
    return a


def in_viewbox(lat, lng):
    w, s, e, n = VIEWBOX
    return s <= lat <= n and w <= lng <= e


def classify(hit, address):
    """(lat, lng, confidence) from a Nominatim hit, or None."""
    if not hit:
        return None
    lat, lng = float(hit["lat"]), float(hit["lon"])
    if not in_viewbox(lat, lng):
        return None
    wanted = re.match(r"\s*(\d+)", address)
    got = (hit.get("address") or {}).get("house_number")
    return lat, lng, "high" if wanted and got and wanted.group(1) == got.split("-")[0] else "low"


def merge(old, new):
    """Fold a newly extracted record into an existing one: union the sources, keep hand edits."""
    out = dict(old)
    for k, v in new.items():
        if k == "sources":
            have = {s.get("url") for s in out.get("sources", [])}
            out["sources"] = out.get("sources", []) + [s for s in v if s.get("url") not in have]
        elif v and not out.get(k):
            out[k] = v
    return out


def load(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save(path, obj):
    tmp = path + ".partial"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, path)


def fetch(address, contact):
    url = NOMINATIM + "?" + urllib.parse.urlencode({
        "q": query_for(address), "format": "jsonv2", "limit": 1, "addressdetails": 1, "countrycodes": "us",
        "viewbox": "{},{},{},{}".format(VIEWBOX[0], VIEWBOX[3], VIEWBOX[2], VIEWBOX[1]), "bounded": 1})
    req = urllib.request.Request(url, headers={"User-Agent": f"SeattleRestaurantsMap/1.0 ({contact})"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        hits = json.load(resp)
    return hits[0] if hits else None


def cmd_run(args):
    records, cache = load(RESTAURANTS, []), load(CACHE, {})
    review, last = [], 0.0
    for r in records:
        if r.get("geo", {}).get("source") == "manual" and r.get("lat") is not None:
            continue
        addr = (r.get("address") or "").strip()
        if not addr:
            review.append((r, "no address"))
            continue
        if addr not in cache:
            wait = MIN_DELAY - (time.time() - last)
            if wait > 0:
                time.sleep(wait)
            last = time.time()
            try:
                cache[addr] = fetch(addr, args.contact)
            except Exception as e:  # network trouble: stop, keep what we have, rerun resumes from the cache
                log(f"stopping: {e}")
                break
            save(CACHE, cache)
        res = classify(cache[addr], addr)
        if res:
            r["lat"], r["lng"] = round(res[0], 6), round(res[1], 6)
            r["geo"] = {"confidence": res[2], "source": "nominatim"}
        else:
            r["lat"] = r["lng"] = None
            r["geo"] = {"confidence": "none", "source": "nominatim"}
        if r["geo"]["confidence"] != "high":
            review.append((r, r["geo"]["confidence"]))
    save(RESTAURANTS, records)
    with open(REVIEW, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "address", "problem", "lat", "lng"])
        for r, why in review:
            w.writerow([r["id"], r["name"], r.get("address", ""), why, r.get("lat"), r.get("lng")])
    log(f"{len(records)} records, {len(review)} need review (data/review.csv)")
    if args.emit:
        emit(args.emit, args.include_low)


def emit(path, include_low=False):
    keep = {"high", "med"} | ({"low"} if include_low else set())
    out = []
    for r in load(RESTAURANTS, []):
        geo = r.get("geo", {})
        if r.get("lat") is None or (geo.get("confidence") not in keep and geo.get("source") != "manual"):
            continue
        out.append({k: r[k] for k in FIELDS if k in r and k != "geo"})
    out.sort(key=lambda r: r["name"].lower())
    with open(os.path.join(ROOT, path), "w", encoding="utf-8") as f:
        f.write("// Generated by tools/geocode.py from data/restaurants.json. Do not edit by hand.\n")
        f.write("const RESTAURANTS = " + json.dumps(out, ensure_ascii=False, indent=1) + ";\n")
    log(f"wrote {path}: {len(out)} restaurants on the map")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="geocode records that lack coordinates")
    run.add_argument("--contact", required=True, help="your email; goes in the User-Agent")
    run.add_argument("--emit", help="also write the map's data file (e.g. restaurants.js)")
    run.add_argument("--include-low", action="store_true")
    em = sub.add_parser("emit", help="rebuild restaurants.js from data/restaurants.json (offline)")
    em.add_argument("--out", default="restaurants.js")
    em.add_argument("--include-low", action="store_true")
    args = p.parse_args()
    if args.cmd == "run":
        cmd_run(args)
    else:
        emit(args.out, args.include_low)


if __name__ == "__main__":
    main()
