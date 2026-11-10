"""Stage 3 - Validate. Fails loudly (non-zero exit) on any unwaived error.

Errors (block export):
  duplicate_course_code, non_numeric_credits, missing_source_url, missing_retrieved_on,
  prereq_missing_course, prereq_cycle, prereq_self, resource_course_missing, resource_missing_licence,
  rule_anchor_not_found, rule_empty_text, skill_parent_missing, plus any parse issue without a severity.
Warnings (reported, do not block):
  prereq_semester_order, variable_credits, category_credit_mismatch, skill_unused, prereq_outside_programme.
A finding can be downgraded only by a row in data/manual/validation_waivers.csv (check, record, reason),
so every exception is written down and reviewable.
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict

from .paths import MANUAL

ENTITY_KEYS = {
    "courses": "code", "rules": "rule_id", "resources": "resource_id", "modules": "module_id",
    "skills": "skill_id", "programme_requirements": "category", "semester_slots": "semester",
}


def _waivers() -> dict:
    path = MANUAL / "validation_waivers.csv"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return {(r["check"], r["record"]): r["reason"] for r in csv.DictReader(f)}


def find_cycles(edges: list[dict]) -> list[list[str]]:
    graph = defaultdict(list)
    for e in edges:
        if e["kind"] == "hard":
            graph[e["course_code"]].append(e["requires_code"])
    cycles, state = [], {}

    def dfs(n, stack):
        state[n] = 1
        stack.append(n)
        for m in graph.get(n, []):
            if state.get(m) == 1:
                cycles.append(stack[stack.index(m):] + [m])
            elif not state.get(m):
                dfs(m, stack)
        stack.pop()
        state[n] = 2

    for n in list(graph):
        if not state.get(n):
            dfs(n, [])
    return cycles


def run(kb: dict, use_waivers: bool = True) -> dict:
    findings: list[dict] = []

    def add(check, record, detail, severity="error"):
        findings.append({"check": check, "record": str(record), "detail": detail, "severity": severity})

    for i in kb["parse_issues"]:
        add(i["check"], i["record"], i["detail"], i.get("severity", "error"))

    courses = kb["courses"]
    codes = [c["code"] for c in courses]
    for code, n in Counter(codes).items():
        if n > 1:
            add("duplicate_course_code", code, f"appears {n} times")
    for c in courses:
        if c["credits"] is None:
            if (c["credits_raw"] or "").lower() == "variable":
                add("variable_credits", c["code"], "credits are 'Variable' in source", "warning")
            else:
                add("non_numeric_credits", c["code"], f"credits={c['credits_raw']!r}")

    # provenance on every record of every entity
    for ent, key in ENTITY_KEYS.items():
        for r in kb[ent]:
            if not r.get("source_url"):
                add("missing_source_url", f"{ent}:{r.get(key)}", "record has no source_url")
            if ent not in ("skills",) and not r.get("retrieved_on"):
                add("missing_retrieved_on", f"{ent}:{r.get(key)}", "record has no retrieved_on")

    known = set(kb["all_course_codes"])
    in_prog = set(codes)
    sem = {c["code"]: min(c["semesters_offered"]) for c in courses if c["semesters_offered"]}
    for e in kb["prerequisites"]:
        req, crs = e["requires_code"], e["course_code"]
        if req == crs:
            add("prereq_self", crs, "course lists itself as prerequisite")
        if req not in known:
            add("prereq_missing_course", f"{crs}->{req}",
                f"prerequisite '{e['requires_code_raw']}' not found in current Courses of Study")
        elif req not in in_prog:
            add("prereq_outside_programme", f"{crs}->{req}", "prerequisite exists but is outside CSE scope", "warning")
        if e["kind"] == "hard" and crs in sem and req in sem and sem[req] >= sem[crs] \
                and crs in {c["code"] for c in courses if c["course_type"] == "core"}:
            add("prereq_semester_order", f"{crs}->{req}",
                f"core course in Sem {sem[crs]} requires {req} first offered in Sem {sem[req]}", "warning")
    for cyc in find_cycles(kb["prerequisites"]):
        add("prereq_cycle", "->".join(cyc), "hard-prerequisite cycle")

    for rc in kb["resource_courses"]:
        if rc["course_code"] not in in_prog:
            add("resource_course_missing", f"{rc['resource_id']}->{rc['course_code']}", "mapped course not in catalogue")
    for r in kb["resources"]:
        if not r.get("licence"):
            add("resource_missing_licence", r["resource_id"], "no licence recorded")
        if not r.get("title"):
            add("resource_missing_title", r["resource_id"], "title could not be read from raw snapshot")
    for r in kb["rules"]:
        if len(r["text"]) < 20:
            add("rule_empty_text", r["rule_id"], "extracted quote too short")

    skill_ids = {s["skill_id"] for s in kb["skills"]}
    for s in kb["skills"]:
        if s["parent_skill"] and s["parent_skill"] not in skill_ids:
            add("skill_parent_missing", s["skill_id"], s["parent_skill"])
    used = {l["skill_id"] for l in kb["course_skills"]} | {l["skill_id"] for l in kb["resource_skills"]}
    for s in kb["skills"]:
        if s["keywords"] and s["skill_id"] not in used:
            add("skill_unused", s["skill_id"], "no course or resource linked", "warning")

    # PC credits found vs programme requirement
    req = {r["category"]: r["min_credits"] for r in kb["programme_requirements"]}
    for cat in ("IC", "PC", "PL"):
        got = sum(c["credits"] or 0 for c in courses if c["category"] == cat)
        if cat in req and abs(got - req[cat]) > 0.01:
            add("category_credit_mismatch", cat, f"sum of parsed {cat} course credits={got} vs required {req[cat]}",
                "warning")

    waivers = _waivers() if use_waivers else {}
    errors, warnings, waived, info = [], [], [], []
    for f in findings:
        reason = waivers.get((f["check"], f["record"]))
        if reason:
            waived.append({**f, "waiver_reason": reason})
        elif f["severity"] == "error":
            errors.append(f)
        elif f["severity"] == "warning":
            warnings.append(f)
        else:
            info.append(f)
    checks_run = sorted({"duplicate_course_code", "non_numeric_credits", "missing_source_url", "missing_retrieved_on",
                         "prereq_missing_course", "prereq_cycle", "prereq_self", "prereq_outside_programme",
                         "prereq_semester_order", "resource_course_missing", "resource_missing_licence",
                         "resource_missing_title", "rule_anchor_not_found", "rule_empty_text", "skill_parent_missing",
                         "skill_unused", "category_credit_mismatch", "variable_credits", "missing_prereq_line",
                         "semester_grid", "category_unknown", "resource_unreachable", "core_course_without_syllabus"})
    print(f"[validate] errors={len(errors)} warnings={len(warnings)} waived={len(waived)} info={len(info)}")
    return {"checks_run": checks_run, "errors": errors, "warnings": warnings, "waived": waived, "info": info,
            "legacy_alias_resolutions": [{"course": a, "raw": b, "resolved_to": c} for a, b, c in kb["alias_hits"]]}
