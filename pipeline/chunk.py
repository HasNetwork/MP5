"""Stage 4 - Chunk syllabi, rules and resource descriptions into retrieval-sized pieces.

Strategy (deterministic, no model calls):
  * split text on sentence / ';' boundaries, pack units up to MAX_WORDS, carry OVERLAP_WORDS
    of the previous chunk forward so a topic cut at a boundary is still retrievable
  * one 'overview' chunk per course/resource with its structured facts in plain words, so
    questions like "how many credits is CSL252" hit a chunk that states it
  * each rule is its own chunk (rules must stay quotable as a whole)
  * chunk_id is deterministic: <parent_id>::<chunk_type>::<nnn>  -> re-runs produce identical ids
Every chunk carries parent_id, type, provenance and flat filter metadata.
"""
from __future__ import annotations

import hashlib
import re

from .paths import PROGRAMME_ID

MAX_WORDS = 160
OVERLAP_WORDS = 25
LESSONS_PER_CHUNK = 20


def split_text(text: str) -> list[str]:
    units = [u.strip() for u in re.split(r"(?<=[.;:])\s+", text) if u.strip()]
    chunks, cur = [], []
    for u in units:
        words = u.split()
        if len(words) > MAX_WORDS:  # pathological long unit: hard-split
            for i in range(0, len(words), MAX_WORDS - OVERLAP_WORDS):
                chunks.append(" ".join(words[i:i + MAX_WORDS]))
            continue
        if cur and len(cur) + len(words) > MAX_WORDS:
            chunks.append(" ".join(cur))
            cur = cur[-OVERLAP_WORDS:]
        cur += words
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def _chunk(parent_id, parent_type, ctype, n, text, prov, meta) -> dict:
    return {
        "chunk_id": f"{parent_id}::{ctype}::{n:03d}", "parent_id": parent_id, "parent_type": parent_type,
        "chunk_type": ctype, "text": text, "n_words": len(text.split()),
        "content_sha1": hashlib.sha1(text.encode("utf-8")).hexdigest(),
        "source_id": prov["source_id"], "source_url": prov["source_url"], "retrieved_on": prov["retrieved_on"],
        "source_type": prov["source_type"], "metadata": {"programme_id": PROGRAMME_ID, **meta},
    }


def run(kb: dict) -> list[dict]:
    out = []
    skills_by_course: dict = {}
    for l in kb["course_skills"]:
        skills_by_course.setdefault(l["course_id"], []).append(l["skill_id"])
    skills_by_res: dict = {}
    for l in kb["resource_skills"]:
        skills_by_res.setdefault(l["resource_id"], []).append(l["skill_id"])
    prereqs: dict = {}
    for e in kb["prerequisites"]:
        prereqs.setdefault(e["course_code"], []).append(e["requires_code"])

    for c in kb["courses"]:
        meta = {"course_code": c["code"], "department": c["department"], "credits": c["credits"],
                "course_type": c["course_type"], "category": c["category"], "level": c["level"],
                "semesters_offered": c["semesters_offered"], "mode": c["mode"],
                "prerequisites": prereqs.get(c["code"], []), "skill_ids": sorted(skills_by_course.get(c["code"], []))}
        pre = ", ".join(prereqs.get(c["code"], [])) or "none"
        overview = (f"{c['code']} {c['title']} is a {c['credits']}-credit {c['course_type']} course "
                    f"(category {c['category']}) of the {c['department']} discipline at IIT Bhilai, "
                    f"L-T-P {c['L']}-{c['T']}-{c['P']}, offered in {', '.join(c['semester_labels'])} "
                    f"of the BTech CSE curriculum, taught {c['mode']}. Prerequisites: {pre}."
                    + (f" Note: {c['prereq_note']}." if c["prereq_note"] else ""))
        out.append(_chunk(c["code"], "course", "course_overview", 1, overview, c, meta))
        for n, t in enumerate(split_text(c["syllabus"]), start=1):
            out.append(_chunk(c["code"], "course", "course_syllabus", n,
                              f"{c['code']} {c['title']} - syllabus: {t}", c, meta))

    for r in kb["rules"]:
        meta = {"rule_category": r["category"], "numeric_limit": r["numeric_limit"], "unit": r["unit"],
                "comparator": r["comparator"], "applies_to": r["applies_to"], "page": r["page"]}
        for n, t in enumerate(split_text(r["text"]), start=1):
            out.append(_chunk(r["rule_id"], "rule", "rule", n, t, r, meta))

    for r in kb["resources"]:
        courses = [x for x in r["maps_to_courses"].split(";") if x]
        meta = {"provider": r["provider"], "licence": r["licence"], "format": r["format"],
                "duration_hours_est": r["duration_hours_est"], "course_codes": courses,
                "skill_ids": sorted(skills_by_res.get(r["resource_id"], []))}
        dur = f"about {r['duration_hours_est']} hours ({r['duration_basis']})" if r["duration_hours_est"] \
            else r["duration_basis"]
        overview = (f"{r['title']} is an open learning resource from {r['provider']}"
                    + (f" taught by {r['instructor']} ({r['offered_by']})" if r["instructor"] else "")
                    + f". Licence: {r['licence']}. Format: {r['format'] or 'not stated'}. Duration: {dur}. "
                    f"Supports IIT Bhilai courses: {', '.join(courses)}."
                    + (f" {r['description']}" if r["description"] else ""))
        out.append(_chunk(r["resource_id"], "resource", "resource_overview", 1, overview, r, meta))
        lessons = [m["summary"] for m in kb["modules"] if m["parent_id"] == r["resource_id"]]
        for n, i in enumerate(range(0, len(lessons), LESSONS_PER_CHUNK), start=1):
            part = lessons[i:i + LESSONS_PER_CHUNK]
            text = f"{r['title']} ({r['provider']}) lessons {i + 1}-{i + len(part)}: " + "; ".join(part)
            out.append(_chunk(r["resource_id"], "resource", "resource_lessons", n, text, r,
                              {**meta, "lesson_range": [i + 1, i + len(part)]}))

    ids = [c["chunk_id"] for c in out]
    assert len(ids) == len(set(ids)), "duplicate chunk ids"
    print(f"[chunk] chunks={len(out)} (max_words={MAX_WORDS}, overlap={OVERLAP_WORDS})")
    return out
