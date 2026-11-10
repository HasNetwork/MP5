# Data quality report: IIT Bhilai BTech CSE (Part D)

All numbers come from `data/processed/quality_stats.json`, regenerated on every run. Full findings are in `reports/quality_stats.md`.

## What was collected

| Entity | Count | Notes |
|---|---|---|
| Courses | **59** | 29 core (14 IC, 1 PL, 13 PC, 1 NC) and 30 CSE program electives. Covers every course in the 2023-onwards CSE curriculum that has a syllabus, plus every CSE elective below the 700 level |
| Prerequisite edges | 30 | All `hard`. 6 resolved from legacy codes, 1 unresolved (waived, see below) |
| Academic rules | **38** | Verbatim quotes. Credit limits 6, online/MOOC credit 10, CGPA 5, prerequisite 5, Honours/minor 4, other 8 |
| Open resources | **53** | 30 NPTEL, 22 MIT OCW, 1 MIT Missing Semester. Each fetched live and snapshotted |
| Skills / course–skill / resource–skill links | 30 / 79 / 89 | 22 skills linked to at least one course, 23 to at least one resource |
| Modules | 2,575 | 422 syllabus topics + 2,153 NPTEL lessons |
| Chunks | **338** | 59 course overviews, 65 syllabus, 38 rule, 53 resource overviews, 123 lesson groups. 9–225 words, mean 75 |

## Field fill rate (%)

- **Courses**: code, title, department, credits, semester, type, mode, syllabus, prerequisite text, source URL and retrieved_on are all **100**.
- **Rules**: text, category, applies_to, page and source are 100. `numeric_limit`/`unit` are 65.8, because 13 rules are procedural with no number (e.g. "prior permission from DUGC").
- **Resources**: title, licence, format, mapped courses and source are 100. `instructor` and `duration_hours_est` are 56.6 (NPTEL only: OCW snapshots have no hour count, so they get a "~1 semester" basis instead). `description` is 43.4 (OCW only).
- **Skills**: `parent_skill` is 70.0, because the 9 root skills have no parent by design.

## Checks the validator runs and what it caught

Blocking errors: duplicate course code · non-numeric credits · record without source_url or retrieved_on · prerequisite naming a missing course · hard-prerequisite cycle · self-prerequisite · resource mapped to an unknown course · resource with no licence or title · rule anchor not found in its source. Warnings: semester-order violation, category credit sum ≠ requirement, variable credits, unused skill. Ingest also re-verifies the sha256 of every raw file. `tests/test_validate.py` injects each blocking defect and asserts it is caught (11 tests pass).

**Real problems it caught in the official sources:**
1. **Stale course codes in the 2026 document.** CSP402, CSP352 and CSL616 cite prerequisites by their *2023* codes (IC100, CS202, CS204, CS250, CS251, IC150). Five were resolved through `code_aliases.csv` (matching title or syllabus, basis recorded per row). **IC150 (Applied Digital Logic Design) has no current equivalent.** It stays unresolved with a written waiver (`requires_in_catalogue=false`). Run `python run_pipeline.py --no-waivers` to see it fail.
2. **PC credits: 49 parsed vs 52 required.** The gap is UGQ301 (Interdisciplinary UG Project, 3 credits), which is in the curriculum but has no syllabus block in the PDF.
3. **CSL302** is garbled in the two-column category table ("SL302"). It is recovered from the semester grid, and the inference is logged.
4. My own parser bugs that the checks and spot-checks surfaced (now fixed): a wrapped department heading leaking into a syllabus, and alternating labs (CYP102/PHP102) getting only one semester.
5. One open-resource URL in my seed list was a 404 (OCW 18.05). Ingest caught it and it was replaced with the correct offering.

## Missing or uncertain

- **No "Minor" exists** in IIT Bhilai documents. The closest is BTech (Honours) by specialisation, and **no numeric CGPA cut-off is published** for it.
- **Conflicts between sources** are kept, not merged: total credits 144 (2023+ batch) vs 240 (legacy batch); V#/NPTEL course size "1-2 credits" (CoS-2026) vs "1-3 credits" (UG Manual). Each rule's `applies_to` and `notes` say which batch and which side of the conflict it belongs to.
- **Elective semesters** are the PE-slot semesters (6–8). Actual per-term offerings are not on the public website. The institute circulates a term-wise course list (slots, instructors) by internal DoAA email, but I **excluded it on purpose** because it is not publicly available. With permission it is the natural source for a `course_offerings` table.
- **Overlap percentages** often reference legacy codes (e.g. "CS608 (100%)"). They are kept as raw text and not yet resolved.
- **Skill links are keyword-based.** 15 courses have none (mostly non-CS institute core such as chemistry and physics, plus CSL511 and CSL609). Depth is inferred from course level, not from learning outcomes. There are known false positives: NPTEL 106102220 (an AI course) is linked to systems security through generic words. Each link stores its matched keywords in `evidence`, so these can be reviewed.
- **Licences** for NPTEL and OCW come from the providers' site-wide terms, not checked page by page. The institute PDFs carry no open licence.
- **Resource durations** are estimates (NPTEL: lessons × ~30 min).

## How a teammate can verify a sample

1. `python -m pipeline.spotcheck --n 10 --seed <any>` prints random courses, rules and resources, each next to the exact source page text, with a clickable `source_url#page=N` and a `verbatim_in_source` check for rules.
2. Open the URL and compare title, credits, L-T-P and prerequisites (courses) or the quote (rules). For resources, compare the title and instructor on the provider page.
3. `sha256sum data/raw/...` against `data/raw/manifest.json` proves the raw file is what was downloaded on `retrieved_on`. `python run_pipeline.py --refresh` re-fetches and re-checks everything.
