"""Each test injects ONE defect the brief requires us to catch and asserts the validator blocks export.
Why it matters: a plan built on a dangling or cyclic prerequisite, a duplicated course or untraceable
record would give a student advice that cannot be checked against the institute's rules."""
import copy

import pytest

from pipeline import validate


def course(code, credits=4.0, raw="4", sem=3, ctype="core", cat="PC"):
    return {"code": code, "credits": credits, "credits_raw": raw, "semesters_offered": [sem],
            "course_type": ctype, "category": cat, "source_url": "u", "retrieved_on": "2026-11-10"}


def edge(c, r, kind="hard"):
    return {"course_code": c, "requires_code": r, "requires_code_raw": r, "kind": kind}


@pytest.fixture
def kb():
    return {
        "parse_issues": [], "courses": [course("CSL201"), course("CSL252", sem=4)],
        "prerequisites": [edge("CSL252", "CSL201")], "all_course_codes": ["CSL201", "CSL252"],
        "rules": [{"rule_id": "R1", "text": "A student shall be allowed a maximum of 6 credits.",
                   "source_url": "u", "retrieved_on": "d"}],
        "resources": [{"resource_id": "X", "licence": "CC BY-SA 4.0", "title": "t", "source_url": "u",
                       "retrieved_on": "d"}],
        "resource_courses": [{"resource_id": "X", "course_code": "CSL201"}],
        "modules": [], "skills": [], "course_skills": [], "resource_skills": [],
        "programme_requirements": [], "semester_slots": [], "alias_hits": [],
    }


def checks(kb):
    return {e["check"] for e in validate.run(kb)["errors"]}


def test_clean_kb_passes(kb):
    assert validate.run(kb)["errors"] == []


def test_prereq_naming_missing_course_fails(kb):
    kb["prerequisites"].append(edge("CSL252", "CSL999"))
    assert "prereq_missing_course" in checks(kb)


def test_prereq_cycle_fails(kb):
    kb["prerequisites"].append(edge("CSL201", "CSL252"))
    assert "prereq_cycle" in checks(kb)


def test_concurrent_mutual_edges_are_not_a_cycle(kb):
    # 'could be taken concurrently' pairs are legal co-registration, not an ordering cycle
    kb["prerequisites"].append(edge("CSL201", "CSL252", kind="concurrent"))
    assert "prereq_cycle" not in checks(kb)


def test_non_numeric_credits_fails(kb):
    kb["courses"][0].update(credits=None, credits_raw="four")
    assert "non_numeric_credits" in checks(kb)


def test_variable_credits_is_only_a_warning(kb):
    kb["courses"][0].update(credits=None, credits_raw="Variable")
    rep = validate.run(kb)
    assert rep["errors"] == [] and any(w["check"] == "variable_credits" for w in rep["warnings"])


def test_duplicate_course_code_fails(kb):
    kb["courses"].append(copy.deepcopy(kb["courses"][0]))
    assert "duplicate_course_code" in checks(kb)


def test_record_without_source_url_fails(kb):
    kb["rules"][0]["source_url"] = ""
    assert "missing_source_url" in checks(kb)


def test_resource_mapped_to_unknown_course_fails(kb):
    kb["resource_courses"].append({"resource_id": "X", "course_code": "CSL777"})
    assert "resource_course_missing" in checks(kb)


def test_resource_without_licence_fails(kb):
    kb["resources"][0]["licence"] = ""
    assert "resource_missing_licence" in checks(kb)


def test_waiver_downgrades_only_the_named_record(kb, tmp_path, monkeypatch):
    kb["prerequisites"] += [edge("CSL252", "IC150"), edge("CSL252", "CSL999")]
    monkeypatch.setattr(validate, "_waivers", lambda: {("prereq_missing_course", "CSL252->IC150"): "documented"})
    rep = validate.run(kb)
    assert [e["record"] for e in rep["errors"]] == ["CSL252->CSL999"]
    assert [w["record"] for w in rep["waived"]] == ["CSL252->IC150"]
