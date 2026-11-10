"""Stage 1 - Ingest: download every source untouched into data/raw/ and record a manifest.

Raw files are never modified. The manifest records URL, retrieval date, sha256 and HTTP
status so each downstream record can point back to the exact bytes it came from.
Downloads are cached: re-running without --refresh reuses data/raw/ (reproducible, offline).
"""
from __future__ import annotations

import csv
import hashlib
import json
import time
import urllib.robotparser
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests
import truststore

# Use the OS trust store (iitbhilai.ac.in serves an incomplete chain that certifi rejects;
# the OS store completes it via AIA). Verification stays ON.
truststore.inject_into_ssl()

from .paths import MANUAL, RAW

USER_AGENT = "IITBh-KB-Pipeline/0.1 (academic project; polite crawler)"
DELAY_S = 1.5  # rate limit between network requests
TIMEOUT_S = 90

# Official institute documents. The site serves PDFs behind index.php?pid=... URLs.
INSTITUTE_SOURCES = [
    {
        "source_id": "iitbh_cos_2026",
        "url": "https://www.iitbhilai.ac.in/index.php?pid=new_schedule_programs",
        "file": "institute/iitbh_courses_of_study_2026.pdf",
        "title": "IIT Bhilai Courses of Study, October 2026 (applicable for 2023 batch onwards)",
        "source_type": "official",
        "licence": "Public institute document (no open licence stated; used for non-commercial academic purposes)",
    },
    {
        "source_id": "iitbh_cos_2023",
        "url": "https://www.iitbhilai.ac.in/index.php?pid=schedule_programs",
        "file": "institute/iitbh_courses_of_study_2023.pdf",
        "title": "IIT Bhilai Courses of Study, June 2023 (applicable for students admitted till 2022-23-W) - LEGACY",
        "source_type": "official",
        "licence": "Public institute document (no open licence stated; used for non-commercial academic purposes)",
    },
    {
        "source_id": "iitbh_ug_manual",
        "url": "https://www.iitbhilai.ac.in/index.php?pid=ug_manual",
        "file": "institute/iitbh_ug_manual.pdf",
        "title": "IIT Bhilai UG Manual (academic rules and procedures)",
        "source_type": "official",
        "licence": "Public institute document (no open licence stated; used for non-commercial academic purposes)",
    },
    {
        "source_id": "iitbh_courses_study_index",
        "url": "https://www.iitbhilai.ac.in/index.php?pid=courses_study",
        "file": "institute/iitbh_courses_study_index.html",
        "title": "IIT Bhilai 'Courses of study' index page (shows which document applies to which batch)",
        "source_type": "official",
        "licence": "Public institute web page",
    },
]


def _robots_allows(url: str, cache: dict) -> bool:
    parts = urlparse(url)
    base = f"{parts.scheme}://{parts.netloc}"
    if base not in cache:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = requests.get(base + "/robots.txt", headers={"User-Agent": USER_AGENT}, timeout=30)
            # 404 => no restrictions (RFC 9309); anything else parsed as-is
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except requests.RequestException:
            rp.parse([])
        cache[base] = rp
    return cache[base].can_fetch(USER_AGENT, url)


def resource_sources() -> list[dict]:
    """Open-resource pages to snapshot. NPTEL pages are JS apps, so we save the
    page's public SvelteKit data endpoint (__data.json), which holds title, instructor and lesson list."""
    out = []
    with open(MANUAL / "resources_seed.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["provider"] == "NPTEL":
                url = f"https://nptel.ac.in/courses/{row['provider_ref']}/__data.json"
                file = f"resources/nptel_{row['provider_ref']}.json"
            else:
                url = row["url"]
                file = f"resources/{row['resource_id'].lower()}.html"
            out.append({
                "source_id": row["resource_id"], "url": url, "file": file,
                "title": f"{row['provider']} {row['provider_ref']}",
                "source_type": "open-licence", "licence": row["licence"],
            })
    return out


def run(refresh: bool = False) -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    manifest_path = RAW / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    robots: dict = {}
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    fetched = cached = failed = 0

    for src in INSTITUTE_SOURCES + resource_sources():
        dest = RAW / src["file"]
        prev = manifest.get(src["source_id"])
        if dest.exists() and prev and prev.get("status") == 200 and not refresh:
            # raw files must stay byte-identical to what was fetched
            if hashlib.sha256(dest.read_bytes()).hexdigest() != prev.get("sha256"):
                raise RuntimeError(f"[ingest] {dest} no longer matches its manifest sha256 - raw data was modified")
            cached += 1
            continue
        entry = {k: src[k] for k in ("url", "file", "title", "source_type", "licence")}
        if not _robots_allows(src["url"], robots):
            entry.update(status="blocked_by_robots", retrieved_on=date.today().isoformat())
            manifest[src["source_id"]] = entry
            failed += 1
            continue
        try:
            r = session.get(src["url"], timeout=TIMEOUT_S)
            entry["status"] = r.status_code
            if r.status_code == 200:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(r.content)  # untouched bytes
                entry["sha256"] = hashlib.sha256(r.content).hexdigest()
                entry["content_type"] = r.headers.get("Content-Type", "")
                entry["bytes"] = len(r.content)
                fetched += 1
            else:
                failed += 1
        except requests.RequestException as e:
            entry["status"] = f"error: {type(e).__name__}"
            failed += 1
        entry["retrieved_on"] = date.today().isoformat()
        manifest[src["source_id"]] = entry
        time.sleep(DELAY_S)

    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[ingest] fetched={fetched} cached={cached} failed={failed} -> {RAW}")
    return manifest
