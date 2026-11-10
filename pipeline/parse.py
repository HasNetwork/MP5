"""Stage 2 - Parse & normalise raw files into in-memory entity tables (`kb` dict of lists).

Normalisation applied everywhere:
  * course codes: upper-case, no spaces, legacy codes mapped via data/manual/code_aliases.csv
  * credits: float (e.g. "4.5"), None + note for "Variable"
  * semesters: roman numerals -> int 1..8, label "Sem N"
  * department: from the "Courses offered in the Discipline of ..." heading the course sits under
  * every record carries source_id, source_url (with #page=N where known), retrieved_on, source_type
Problems are NOT silently fixed: anything odd goes into kb["parse_issues"] for the validator.
"""
from __future__ import annotations

import csv
import json
import re
from html import unescape
from pathlib import Path

import pdfplumber

from .paths import INSTITUTE, INTERIM, MANUAL, PROGRAMME_ID, RAW

CODE_RE = re.compile(r"\b([A-Z]{2,3}\d{3})\b")
HEADER_RE = re.compile(r"^([A-Z]{2,3}\d{3})\s+(\S.*)$")
CREDIT_RE = re.compile(r"^([\d.]+|[Vv]ariable)\s+Credits?\s*(?:\(([^)]*)\))?", re.I)
DEPT_RE = re.compile(r"^Courses offered in the Discipline of (.+)$", re.I)
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8}
NONE_RE = re.compile(r"^(none|nil|na|n/a|-|no)\.?$", re.I)


# ---------------------------------------------------------------- helpers
def _csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def norm_code(raw: str, aliases: dict) -> str:
    c = re.sub(r"\s+", "", raw or "").upper().rstrip("*")
    return aliases.get(c, c)


def pdf_pages(source_id: str, manifest: dict) -> list[str]:
    """Text per page; cached in data/interim keyed by the raw file's sha256."""
    entry = manifest[source_id]
    cache = INTERIM / f"{source_id}.{entry['sha256'][:12]}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    with pdfplumber.open(RAW / entry["file"]) as pdf:
        pages = [p.extract_text() or "" for p in pdf.pages]
    INTERIM.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
    return pages


def provenance(source_id: str, manifest: dict, page: int | None = None) -> dict:
    e = manifest[source_id]
    return {
        "source_id": source_id,
        "source_url": e["url"] + (f"#page={page}" if page else ""),
        "retrieved_on": e.get("retrieved_on"),
        "source_type": e["source_type"],
    }


def find_page(pages: list[str], needle: str, start_page: int = 0) -> int | None:
    n = norm_space(needle)[:60]
    for i in range(start_page, len(pages)):
        if n in norm_space(pages[i]):
            return i + 1
    return None


# ---------------------------------------------------------------- courses
def parse_course_blocks(pages: list[str], issues: list) -> list[dict]:
    """Split 'Course Contents' part of CoS-2026 into per-course blocks."""
    lines: list[tuple[int, str]] = []
    for pno, text in enumerate(pages, start=1):
        for ln in text.splitlines():
            ln = ln.strip()
            if not ln or re.fullmatch(r"\d{1,3}", ln):  # drop blank + page-number lines
                continue
            lines.append((pno, ln))

    # first line of the course-contents part
    start = next(i for i, (p, l) in enumerate(lines) if DEPT_RE.match(l) or l.startswith("Course Contents") and p > 50)
    blocks, cur, dept = [], None, None
    i = start
    while i < len(lines):
        pno, ln = lines[i]
        m_dept = DEPT_RE.match(ln)
        if m_dept:
            dept = norm_space(m_dept.group(1))
            i += 1
            # heading may wrap ("...Data Science and Artificial" / "Intelligence"): absorb short continuation
            while i < len(lines) and not HEADER_RE.match(lines[i][1]) and len(lines[i][1].split()) <= 3:
                dept = norm_space(dept + " " + lines[i][1])
                i += 1
            continue
        m = HEADER_RE.match(ln)
        # header = CODE Title, followed within 2 lines by "N Credits (L-T-P)"
        if m:
            look = [lines[j][1] for j in range(i + 1, min(i + 3, len(lines)))]
            k = next((n for n, l in enumerate(look) if CREDIT_RE.match(l)), None)
            if k is not None:
                if cur:
                    blocks.append(cur)
                title = norm_space(" ".join([m.group(2)] + look[:k]))
                cm = CREDIT_RE.match(look[k])
                cur = {"code": m.group(1), "title": title, "credits_raw": cm.group(1),
                       "ltp": cm.group(2), "dept": dept, "page": pno, "body": []}
                i += k + 2
                continue
        if cur:
            cur["body"].append(ln)
        i += 1
    if cur:
        blocks.append(cur)

    for b in blocks:
        body = " ".join(b.pop("body"))
        pm = re.search(r"Pre-?requisites?\(?s?\)?\s*:\s*(.*?)(?=Overlap with\s*:|$)", body, re.I)
        om = re.search(r"Overlap with\s*:\s*(.*?)(?=(?:[A-Z][a-z]|$))", body)
        b["prereq_text"] = norm_space(pm.group(1)) if pm else None
        rest = body
        if pm:
            rest = rest.replace(pm.group(0), " ")
        ov = re.search(r"Overlap with\s*:\s*((?:[A-Z]{2,3}\d{3}[^A-Za-z]*|NA|Nil|None|N/A)[\s,;.()%\d]*)", rest)
        b["overlap_text"] = norm_space(ov.group(1)) if ov else None
        if ov:
            rest = rest.replace(ov.group(0), " ")
        b["syllabus"] = norm_space(rest)
        if b["prereq_text"] is None:
            issues.append({"check": "missing_prereq_line", "record": b["code"],
                           "detail": "no 'Prerequisite(s):' line found in syllabus block"})
    return blocks


def parse_prereqs(code: str, text: str | None, aliases: dict, raw_aliases_hit: list) -> tuple[list, str | None]:
    """Return (edges, note). Text -> AND-groups split on , ; 'and'; alternatives on 'or'."""
    if not text or NONE_RE.match(text.strip()):
        return [], None
    note = None
    low = text.lower()
    if "equivalent" in low:
        note = "'or equivalent' allowed by source"
    if re.search(r"consent|permission|instructor", low):
        note = (note + "; " if note else "") + "instructor consent mentioned"
    concurrent = set(CODE_RE.findall(re.sub(r".*?(([A-Z]{2,3}\d{3}[ ,and]*)+)could be taken concurrently.*", r"\1", text)
                                    )) if "concurrent" in low else set()
    kind_default = "recommended" if re.search(r"recommend|desirable|preferred|advisable", low) else "hard"
    edges = []
    parts = re.split(r",|;|\band\b|\.\s", text)
    for g, part in enumerate(parts, start=1):
        codes = CODE_RE.findall(part)
        if not codes:
            continue
        logic = "any_of" if re.search(r"\bor\b|/", part) and len(codes) > 1 else "all_of"
        for c in codes:
            n = norm_code(c, aliases)
            if n != c:
                raw_aliases_hit.append((code, c, n))
            edges.append({
                "course_code": code, "requires_code": n, "requires_code_raw": c,
                "kind": "concurrent" if c in concurrent else kind_default,
                "group_id": f"{code}-G{g}", "group_logic": logic,
            })
    # de-dup (same code can appear twice, e.g. "MAL403 or equivalent ... MAL403")
    seen, uniq = set(), []
    for e in edges:
        if e["requires_code"] not in seen:
            seen.add(e["requires_code"])
            uniq.append(e)
    return uniq, note


def parse_programme_structure(manifest: dict, pages: list[str], issues: list) -> tuple[dict, list, list]:
    """CSE curriculum pages: category per core course (p.21), semester grid (p.22), requirement table."""
    src = manifest["iitbh_cos_2026"]
    cse_page = next(i for i, t in enumerate(pages) if t.strip().startswith("BTech in Computer Science and Engineering")
                    and "Institute core (IC) courses" in t)
    with pdfplumber.open(RAW / src["file"]) as pdf:
        pg = pdf.pages[cse_page]
        w, h = pg.width, pg.height
        cols = [pg.crop((0, 0, w / 2, h)).extract_text() or "", pg.crop((w / 2, 0, w, h)).extract_text() or ""]
        grid_page = cse_page + 1
        tables = pdf.pages[grid_page].extract_tables()

    text = "\n".join(cols)
    # requirement table
    reqs = []
    for label, cat in [("Institute core (IC) courses", "IC"), ("Program linked (PL) courses", "PL"),
                       ("Program core (PC) courses", "PC"), ("Program elective (PE) courses", "PE"),
                       ("Open elective (OE) Courses", "OE"), ("Liberal art (LA) courses", "LA"),
                       ("Non-graded core (NC) courses", "NC")]:
        m = re.search(re.escape(label) + r"\s+([\d.]+)\s*(units)?", text)
        if not m:
            issues.append({"check": "requirement_unparsed", "record": cat, "detail": label})
            continue
        reqs.append({"programme_id": PROGRAMME_ID, "category": cat, "min_credits": float(m.group(1)),
                     "unit": "units" if m.group(2) else "credits",
                     **provenance("iitbh_cos_2026", manifest, cse_page + 1)})

    # category per course from section headings (first occurrence wins)
    category = {}
    sections = re.split(r"(Institute core \(IC\) courses\nCourse|Program linked \(PL\) Courses|Program core \(PC\) courses)", text)
    cur = None
    for s in sections:
        if s.startswith("Institute core"):
            cur = "IC"
        elif s.startswith("Program linked"):
            cur = "PL"
        elif s.startswith("Program core"):
            cur = "PC"
        elif cur:
            for c in CODE_RE.findall(s):
                category.setdefault(c, cur)
    # right column continues the PC list
    for c in CODE_RE.findall(cols[1]):
        category.setdefault(c, "PC")

    # semester grid: rows = [Sem, c1..c7, credits]; 3 rows per semester (codes, names, L-T-P-C)
    sem_of, slots = {}, []
    rows = [r for t in tables for r in t]
    sem, block = None, []
    for r in rows:
        first = (r[0] or "").strip()
        if first in ROMAN:
            if block:
                _grid_block(sem, block, sem_of, slots)
            sem, block = ROMAN[first], [r]
        elif sem:
            block.append(r)
    if block:
        _grid_block(sem, block, sem_of, slots)
    n_sems = len({s for v in sem_of.values() for s in v})
    if n_sems < 7:
        issues.append({"check": "semester_grid", "record": "CSE grid", "detail": f"only {n_sems} semesters parsed"})
    for s in slots:
        s.update(provenance("iitbh_cos_2026", manifest, grid_page + 1))
    # grid codes missing from category table (PDF column split garbles 'CSL302') -> PC if CS, else flag
    for c in sem_of:
        if c not in category:
            if c.startswith("CS"):
                category[c] = "PC"
                issues.append({"check": "category_inferred", "record": c, "severity": "info",
                               "detail": "code garbled in two-column category table; inferred PC from semester grid"})
            elif c.startswith(("NCN", "LAN")):
                category[c] = "NC"
            else:
                issues.append({"check": "category_unknown", "record": c, "detail": "in grid but not in category table"})
    return {"category": category, "semester": sem_of, "cse_page": cse_page + 1, "grid_page": grid_page + 1}, reqs, slots


def _grid_block(sem: int, block: list, sem_of: dict, slots: list) -> None:
    codes_row = block[0]
    ltpc_row = block[2] if len(block) > 2 else [None] * len(codes_row)
    name_row = block[1] if len(block) > 1 else [None] * len(codes_row)
    for j in range(1, len(codes_row) - 1):
        cell = (codes_row[j] or "").strip()
        name = norm_space(name_row[j] or "")
        for c in CODE_RE.findall(cell):
            sem_of.setdefault(c, [])
            if sem not in sem_of[c]:
                sem_of[c].append(sem)  # e.g. CYP102/PHP102 alternate between Sem 1 and Sem 2
        if name in ("PE", "OE", "LA Courses") or "XXX" in cell:
            ltpc = (ltpc_row[j] or "").strip()
            cred = ltpc.split("-")[-1] if ltpc else ""
            slots.append({"programme_id": PROGRAMME_ID, "semester": sem, "semester_label": f"Sem {sem}",
                          "slot_type": {"LA Courses": "LA"}.get(name, name or "PE"),
                          "credits": float(cred) if re.fullmatch(r"[\d.]+", cred) else None})


# ---------------------------------------------------------------- rules
def parse_rules(manifest: dict, page_cache: dict, issues: list) -> list[dict]:
    out = []
    for r in _csv(MANUAL / "rules_seed.csv"):
        pages = page_cache[r["source_id"]]
        full = norm_space(" ".join(pages))
        s = full.find(norm_space(r["quote_start"]))
        e = full.find(norm_space(r["quote_end"]), s) if s >= 0 else -1
        if s < 0 or e < 0:
            issues.append({"check": "rule_anchor_not_found", "record": r["rule_id"],
                           "detail": f"anchor not found in {r['source_id']}"})
            continue
        quote = full[s: e + len(norm_space(r["quote_end"]))]
        page = find_page(pages, r["quote_start"])
        out.append({
            "rule_id": r["rule_id"], "category": r["category"], "text": quote,
            "numeric_limit": float(r["numeric_limit"]) if r["numeric_limit"] else None,
            "unit": r["unit"] or None, "comparator": r["comparator"] or None,
            "applies_to": r["applies_to"], "programme_id": PROGRAMME_ID, "notes": r["notes"] or None,
            "page": page, **provenance(r["source_id"], manifest, page),
        })
    return out


# ---------------------------------------------------------------- resources
def parse_resources(manifest: dict, issues: list) -> tuple[list, list]:
    resources, modules = [], []
    for row in _csv(MANUAL / "resources_seed.csv"):
        rid = row["resource_id"]
        m = manifest.get(rid)
        if not m or m.get("status") != 200:
            issues.append({"check": "resource_unreachable", "record": rid, "detail": f"status={m and m.get('status')}"})
            continue
        raw = (RAW / m["file"]).read_text(encoding="utf-8", errors="replace")
        rec = {"resource_id": rid, "provider": row["provider"], "provider_ref": row["provider_ref"],
               "url": row["url"], "licence": row["licence"], "maps_to_courses": row["maps_to_courses"],
               "notes": row["notes"] or None}
        if row["provider"] == "NPTEL":
            d = json.loads(raw)["nodes"][1]["data"]
            o = d[d[0]["courseOutline"]]
            lessons = []
            for u in d[o["units"]] or []:
                for li in d[d[u]["lessons"]]:
                    lessons.append(norm_space(d[d[li]["name"]]))
            rec.update(title=norm_space(d[o["title"]]), instructor=norm_space(d[o["professor"]]),
                       offered_by=norm_space(d[o["instituteName"]]), format=(d[o["contentType"]] or "").lower() or None,
                       n_lessons=len(lessons),
                       duration_hours_est=round(len(lessons) * 0.5, 1),
                       duration_basis="estimate: lesson count x ~30 min per NPTEL lecture video",
                       description=None)
        else:
            t = re.search(r"<title>(.*?)</title>", raw, re.S)
            desc = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', raw) or \
                re.search(r'<meta[^>]+property="og:description"[^>]+content="([^"]*)"', raw)
            title = unescape(norm_space(t.group(1))) if t else None
            if title:
                title = title.split(" | ")[0]
            lessons = []
            rec.update(title=title, instructor=None, offered_by=row["provider"],
                       format=row["format_hint"] or None, n_lessons=None,
                       duration_hours_est=None,
                       duration_basis="rough: one university semester (~14 weeks); provider gives no hour count",
                       description=unescape(norm_space(desc.group(1))) if desc else None)
        rec.update(provenance(rid, manifest))
        rec["source_url"] = row["url"]  # cite the human-readable page, raw snapshot is in manifest
        resources.append(rec)
        for n, name in enumerate(lessons, start=1):
            modules.append({"module_id": f"{rid}-L{n:03d}", "parent_id": rid, "parent_type": "resource",
                            "order": n, "summary": name, "source_url": row["url"],
                            "retrieved_on": m["retrieved_on"], "source_type": "open-licence"})
    return resources, modules


# ---------------------------------------------------------------- skills
def link_skills(text_by_id: dict, depth_by_id: dict, skills: list, kind: str) -> list[dict]:
    out = []
    for pid, (title, body) in text_by_id.items():
        t, b = title.lower(), body.lower()
        for s in skills:
            if not s["keywords"]:
                continue
            kws = s["keywords"].split("|")
            in_title = [k for k in kws if re.search(r"\b" + re.escape(k), t)]
            in_body = [k for k in kws if re.search(r"\b" + re.escape(k), b)]
            if in_title or len(set(in_body)) >= 2:
                out.append({f"{kind}_id": pid, "skill_id": s["skill_id"],
                            ("depth" if kind == "course" else "level"): depth_by_id[pid],
                            "evidence": "; ".join(sorted(set(in_title + in_body)))[:200],
                            "method": "keyword match on title/syllabus (data/manual/skills.csv)"})
    return out


def depth_from_code(code: str) -> str:
    lvl = int(re.search(r"\d", code).group())
    return "intro" if lvl <= 2 else "working" if lvl <= 4 else "advanced"


def course_modules(c: dict) -> list[dict]:
    """Split a syllabus into ordered topic modules (on ';' and sentence breaks)."""
    parts = [norm_space(p) for p in re.split(r";|\.\s+(?=[A-Z])", c["syllabus"]) if len(p.split()) >= 3]
    return [{"module_id": f"{c['code']}-M{n:02d}", "parent_id": c["code"], "parent_type": "course",
             "order": n, "summary": p[:400], "source_url": c["source_url"], "retrieved_on": c["retrieved_on"],
             "source_type": c["source_type"]} for n, p in enumerate(parts, start=1)]


# ---------------------------------------------------------------- main
def run(manifest: dict) -> dict:
    issues: list = []
    aliases = {r["legacy_code"]: r["current_code"] for r in _csv(MANUAL / "code_aliases.csv")}
    pages = {sid: pdf_pages(sid, manifest) for sid in ("iitbh_cos_2026", "iitbh_cos_2023", "iitbh_ug_manual")}

    blocks = parse_course_blocks(pages["iitbh_cos_2026"], issues)
    all_codes = {b["code"] for b in blocks}
    struct, reqs, slots = parse_programme_structure(manifest, pages["iitbh_cos_2026"], issues)

    # programme scope: every core/linked course in the CSE curriculum + all CSE-discipline electives (<700 level)
    pe_semesters = sorted({s["semester"] for s in slots if s["slot_type"] == "PE"})
    courses, edges, alias_hits = [], [], []
    for b in blocks:
        code = b["code"]
        in_core = code in struct["category"]
        is_cs_elective = (b["dept"] or "").startswith("Computer Science") and code not in struct["category"] \
            and int(code[3]) < 7
        if not (in_core or is_cs_elective):
            continue
        cat = struct["category"].get(code, "PE")
        ctype = {"IC": "core", "PL": "core", "PC": "core", "NC": "core"}.get(cat, "elective")
        cr = b["credits_raw"]
        credits = float(cr) if re.fullmatch(r"[\d.]+", cr) else None
        sem = struct["semester"].get(code)
        if sem:
            sems, sem_basis = sorted(sem), "CSE semester grid"
        else:
            sems = pe_semesters
            sem_basis = "PE slot semesters in CSE grid (elective; actual offering decided each semester)"
        ltp = [x.strip() for x in (b["ltp"] or "").split("-")]
        prereq_edges, prereq_note = parse_prereqs(code, b["prereq_text"], aliases, alias_hits)
        edges.extend(prereq_edges)
        courses.append({
            "code": code, "title": b["title"], "department": b["dept"], "programme_id": PROGRAMME_ID,
            "institute": INSTITUTE, "credits": credits, "credits_raw": cr,
            "credits_note": None if credits is not None else "variable credits",
            "L": ltp[0] if len(ltp) > 0 else None, "T": ltp[1] if len(ltp) > 1 else None,
            "P": ltp[2] if len(ltp) > 2 else None,
            "category": cat, "course_type": ctype,
            "semesters_offered": sems, "semester_labels": [f"Sem {s}" for s in sems], "semester_basis": sem_basis,
            "mode": "offline", "mode_basis": "BTech is a fully residential programme (UG Manual 2.4.1)",
            "level": int(code[3]) * 100,
            "syllabus": b["syllabus"], "prereq_text": b["prereq_text"], "prereq_note": prereq_note,
            "overlap_text": b["overlap_text"],
            "page": b["page"], **provenance("iitbh_cos_2026", manifest, b["page"]),
        })

    # core courses in the grid that have no syllabus block in the PDF
    have = {c["code"] for c in courses}
    for code in struct["semester"]:
        if code not in have and code in struct["category"] and struct["category"][code] != "NC":
            issues.append({"check": "core_course_without_syllabus", "record": code,
                           "detail": "listed in CSE curriculum but no syllabus block parsed", "severity": "warning"})

    rules = parse_rules(manifest, pages, issues)
    resources, res_modules = parse_resources(manifest, issues)
    skills = _csv(MANUAL / "skills.csv")
    for s in skills:
        s["source_type"] = "manual"
        s["source_url"] = "data/manual/skills.csv"
    course_skills = link_skills({c["code"]: (c["title"], c["syllabus"]) for c in courses},
                                {c["code"]: depth_from_code(c["code"]) for c in courses}, skills, "course")
    cdepth = {c["code"]: depth_from_code(c["code"]) for c in courses}
    res_lessons = {}
    for m in res_modules:
        res_lessons.setdefault(m["parent_id"], []).append(m["summary"])
    resource_skills = link_skills(
        {r["resource_id"]: (r["title"] or "", " ".join(res_lessons.get(r["resource_id"], [])) + " " + (r["description"] or ""))
         for r in resources},
        {r["resource_id"]: min((cdepth.get(c, "intro") for c in r["maps_to_courses"].split(";")),
                               key=["intro", "working", "advanced"].index) for r in resources},
        skills, "resource")
    resource_courses = [{"resource_id": r["resource_id"], "course_code": c, "method": "manual mapping (resources_seed.csv)"}
                        for r in resources for c in r["maps_to_courses"].split(";") if c]
    modules = [m for c in courses for m in course_modules(c)] + res_modules

    print(f"[parse] courses={len(courses)} prereq_edges={len(edges)} rules={len(rules)} resources={len(resources)} "
          f"modules={len(modules)} skills={len(skills)} course_skills={len(course_skills)} "
          f"resource_skills={len(resource_skills)} issues={len(issues)}")
    return {
        "courses": courses, "prerequisites": edges, "rules": rules, "resources": resources,
        "resource_courses": resource_courses, "skills": skills, "course_skills": course_skills,
        "resource_skills": resource_skills, "modules": modules, "programme_requirements": reqs,
        "semester_slots": slots, "all_course_codes": sorted(all_codes), "alias_hits": alias_hits,
        "aliases": aliases, "parse_issues": issues, "manifest": manifest,
    }
