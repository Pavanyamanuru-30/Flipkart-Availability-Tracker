#!/usr/bin/env python3
"""Scan Flipkart serviceability of a product across Indian pincodes.

Uses Flipkart's internal page-fetch API (the same call the website makes),
passing a locationContext pincode and reading the "serviceable" flag from
the buy-box data.

Modes:
  district : one pincode per district (~750 requests, fast overview)
  state    : one pincode per state (~36 requests, sanity check)
  full     : every unique pincode (~19,300 requests — hours, use after district scan)

Usage:
  python3 flipkart_pin_scanner.py "<flipkart product url>" --mode district
  python3 flipkart_pin_scanner.py "<url>" --mode full --out results.csv
  python3 flipkart_pin_scanner.py "<url>" --pins 110001,560001
"""

import argparse
import csv
import gzip
import io
import json
import random
import re
import sys
import threading
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

API = "https://1.rome.api.flipkart.com/api/4/page/fetch"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "X-User-Agent": UA + " FKUA/website/42/website/Desktop",
    "Origin": "https://www.flipkart.com",
    "Referer": "https://www.flipkart.com/",
    "Content-Type": "application/json",
    "Accept-Encoding": "gzip",
}

RE_SERVICEABLE = re.compile(r'"serviceable":(true|false)')
RE_SLA = re.compile(r'"slaText":"([^"]*)"')
RE_NO_PIN = re.compile(r'No Pincode')
RE_OOS_AREA = re.compile(r'out of stock in this area', re.I)
RE_AVAIL = re.compile(r'"availabilityStatus":"([^"]*)"')

print_lock = threading.Lock()


def product_path(url: str) -> str:
    """Extract the /slug/p/itm...?pid=... path Flipkart's API expects."""
    p = urlparse(url)
    if "flipkart.com" not in p.netloc and not url.startswith("/"):
        sys.exit(f"Not a flipkart.com URL: {url}")
    pid = ""
    m = re.search(r'[?&]pid=([A-Z0-9]+)', url)
    if m:
        pid = f"?pid={m.group(1)}"
    if "/p/" not in p.path:
        sys.exit("URL must be a product page (contains /p/)")
    return p.path + pid


def check_pin(path: str, pin: str, retries: int = 4) -> dict:
    body = json.dumps({"pageUri": path, "locationContext": {"pincode": pin}}).encode()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(API, data=body, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                text = raw.decode("utf-8", errors="ignore")
            if RE_NO_PIN.search(text):
                return {"pincode": pin, "status": "UNKNOWN_PIN", "delivery": ""}
            avail = RE_AVAIL.search(text)
            avail = avail.group(1) if avail else ""
            m = RE_SERVICEABLE.search(text)
            if not m:
                if RE_OOS_AREA.search(text):
                    return {"pincode": pin, "status": "NOT_SERVICEABLE", "delivery": avail}
                return {"pincode": pin, "status": "PARSE_ERROR", "delivery": avail}
            if m.group(1) == "true" and avail != "OUT_OF_STOCK":
                sla = RE_SLA.search(text)
                return {"pincode": pin, "status": "SERVICEABLE",
                        "delivery": sla.group(1) if sla else avail}
            return {"pincode": pin, "status": "NOT_SERVICEABLE", "delivery": avail}
        except urllib.error.HTTPError as e:
            if e.code in (403, 429, 500, 502, 503):
                time.sleep(2 ** attempt + random.random() * 2)
                continue
            return {"pincode": pin, "status": f"HTTP_{e.code}", "delivery": ""}
        except Exception:
            time.sleep(2 ** attempt + random.random())
    return {"pincode": pin, "status": "FAILED", "delivery": ""}


def load_pins(csv_path: str, mode: str, states: set) -> list:
    """Return [(pincode, state, district)] per mode. CSV = data.gov.in directory."""
    seen_pin, seen_dist, seen_state, out = set(), set(), set(), []
    with open(csv_path, encoding="utf-8", errors="ignore") as f:
        for row in csv.DictReader(f):
            pin = row["Pincode"].strip()
            st, dist = row["StateName"].strip(), row["District"].strip()
            if states and st.upper() not in states:
                continue
            if not pin.isdigit() or pin in seen_pin:
                continue
            if mode == "district":
                if (st, dist) in seen_dist:
                    continue
                seen_dist.add((st, dist))
            elif mode == "state":
                if st in seen_state:
                    continue
                seen_state.add(st)
            seen_pin.add(pin)
            out.append((pin, st, dist))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="Flipkart product URL")
    ap.add_argument("--mode", choices=["state", "district", "full"], default="district")
    ap.add_argument("--pins", help="comma-separated pincodes (overrides --mode)")
    ap.add_argument("--states", help="comma-separated state names to limit scan")
    ap.add_argument("--csv", default="pincode_full.csv", help="pincode directory CSV")
    ap.add_argument("--out", default="scan_results.csv")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--delay", type=float, default=0.15,
                    help="per-worker sleep between requests")
    args = ap.parse_args()

    path = product_path(args.url)
    print(f"Product path: {path}")

    if args.pins:
        targets = [(p.strip(), "", "") for p in args.pins.split(",")]
    else:
        states = {s.strip().upper() for s in args.states.split(",")} if args.states else set()
        targets = load_pins(args.csv, args.mode, states)

    # resume: skip pins already in output file
    done = set()
    out_path = Path(args.out)
    if out_path.exists():
        with open(out_path) as f:
            done = {r["pincode"] for r in csv.DictReader(f)}
        print(f"Resuming — {len(done)} pincodes already scanned")
    targets = [t for t in targets if t[0] not in done]
    print(f"Scanning {len(targets)} pincodes with {args.workers} workers "
          f"(mode={args.mode})")

    meta = {p: (st, d) for p, st, d in targets}
    new_file = not out_path.exists()
    f = open(out_path, "a", newline="")
    writer = csv.writer(f)
    if new_file:
        writer.writerow(["pincode", "state", "district", "status", "delivery"])

    counts = {}
    t0 = time.time()

    def worker(pin):
        time.sleep(random.random() * args.delay * 2)
        return check_pin(path, pin)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(worker, p): p for p, _, _ in targets}
        for i, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            st, dist = meta.get(r["pincode"], ("", ""))
            writer.writerow([r["pincode"], st, dist, r["status"], r["delivery"]])
            counts[r["status"]] = counts.get(r["status"], 0) + 1
            if i % 25 == 0 or i == len(futs):
                f.flush()
                rate = i / (time.time() - t0)
                eta = (len(futs) - i) / rate if rate else 0
                with print_lock:
                    print(f"  {i}/{len(futs)}  {counts}  "
                          f"({rate:.1f}/s, ETA {eta/60:.0f}m)", flush=True)
    f.close()

    print("\n=== Summary ===")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")
    ok = [r for r in csv.DictReader(open(out_path)) if r["status"] == "SERVICEABLE"]
    if ok:
        by_state = {}
        for r in ok:
            by_state.setdefault(r["state"] or "?", []).append(r)
        print("\nServiceable locations by state:")
        for stt, rows in sorted(by_state.items(), key=lambda x: -len(x[1])):
            sample = ", ".join(f'{r["district"]}({r["pincode"]})' for r in rows[:5])
            print(f"  {stt}: {len(rows)} — {sample}")
    print(f"\nFull results: {out_path}")


if __name__ == "__main__":
    main()
