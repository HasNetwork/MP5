# IIT Bhilai BTech CSE: source-traced knowledge base and data pipeline

Adobe PS selection assignment, day 1. This builds a knowledge base for one programme, **BTech in Computer Science and Engineering at IIT Bhilai**, and a reproducible pipeline that takes raw official documents to clean, chunked, metadata-rich files. It stops right before embedding. No embedding or LLM API is called anywhere.

## Run it

```bash
uv sync                          # or: python -m venv .venv && pip install pdfplumber requests truststore
python run_pipeline.py           # raw -> processed, using the committed data/raw/ snapshot (offline, about 1 min)
python run_pipeline.py --refresh # re-download every source politely, then rebuild
python run_pipeline.py --no-waivers  # shows the validator failing loudly on a real source defect (exit 1)
python -m pytest -q tests        # validator tests: one injected defect per required check
```

Exit code 0 means every record validated and the outputs were written. Any unwaived validation error exits 1 and nothing is exported. Two consecutive runs give byte-identical outputs (checked via sha1 of `data/processed/*`).

No `.env` is needed. The pipeline uses no API keys or model calls. The day-2 embedding step will read `EMBEDDING_MODEL` / `LLM_*` per the main PS, but nothing here does.

## What is where

| Path | Contents |
|---|---|
| `data/raw/institute/` | Official IIT Bhilai PDFs, byte-identical to what the site served (sha256 in `data/raw/manifest.json`, re-verified on every run; `.gitattributes` stops git rewriting line endings) |
| `data/raw/resources/` | Snapshot of each open resource: NPTEL `__data.json` (title, instructor, lesson list) or MIT OCW HTML |
| `data/raw/manifest.json` | Per source: URL, retrieved_on, HTTP status, sha256, content type, licence |
| `data/manual/` | The only hand-made inputs (see "Manual entry" below) |
| `data/interim/` | Cached PDF text extraction (git-ignored, rebuilt automatically) |
| `data/processed/` | **Seed data**: every entity as `.csv` + `.json`, `chunks.jsonl`, `validation_report.json`, `quality_stats.json` |
| `pipeline/` | One module per stage: `ingest.py`, `parse.py`, `validate.py`, `chunk.py`, `export.py` |
| `SOURCES.md` | Generated from the manifest: every source with URL, retrieval date and licence |
| `DATA_QUALITY.md` | Part D: data-quality report |
| `IDEAS.md` | Part E: ideas note |
| `reports/quality_stats.md` | Generated counts, fill rates and every validator finding |

## Sources (summary; full list in SOURCES.md)

| Source | Used for |
|---|---|
| **Courses of Study, Oct 2026, "applicable for 2023 batch onwards"** (`pid=new_schedule_programs`, 208 pp.) | **Primary.** Curriculum, semester grid, category credit requirements, and syllabus, L-T-P, prerequisites and overlap for every course |
| Courses of Study, June 2023, "students admitted till 2022-23-W" (`pid=schedule_programs`) | Legacy. Used only to (a) resolve old course codes still cited in the 2026 document and (b) quote rules that apply to older batches (240-credit structure, Honours/specialisation) |
| UG Manual (`pid=ug_manual`) | Academic rules: credit load, overload/underload, prerequisites, overlap, MOOC/NPTEL credit transfer, CGPA, probation, Honours |
| 30 NPTEL courses + 22 MIT OCW courses + MIT Missing Semester | Open learning resources (53), each verified live and snapshotted |

The "Courses of study" index page (`pid=courses_study`) is snapshotted too, because it is the evidence for which document applies to which batch.

## Pipeline design: what each stage does and what to expect from it

| # | Stage | Input → output | What it guarantees / what to expect |
|---|---|---|---|
| 1 | **Ingest** (`pipeline/ingest.py`) | URLs → `data/raw/` + `manifest.json` | robots.txt is checked (iitbhilai.ac.in has none, which counts as allowed), 1.5 s between requests, an identifying User-Agent, and TLS verification **on** (the OS trust store via `truststore`, because the institute server sends an incomplete certificate chain). Files are stored untouched. Cached on re-run unless `--refresh`; a cached file whose sha256 no longer matches fails the run. Expect 57 sources, 0 failures. |
| 2 | **Parse & normalise** (`pipeline/parse.py`) | PDFs/JSON/HTML → entity tables | Course blocks are parsed generically from `CODE Title` / `N Credits (L-T-P)` / `Prerequisite(s):` / `Overlap with:`. The two-column curriculum page is cropped column by column, and the semester grid is read as a PDF table. Normalisation: codes upper-cased with no spaces, legacy codes mapped via `code_aliases.csv`; credits as floats ("Variable" becomes null plus a note); semesters as roman numerals to int with a label like `Sem N`; department taken from the section heading the course sits under. Prerequisite text becomes edges with `kind` (hard / concurrent / recommended) and AND-groups / OR-alternatives (`group_id`, `group_logic`). Rules are extracted **verbatim** between anchors from `rules_seed.csv`. Anything odd is recorded as a parse issue, never silently fixed. |
| 3 | **Validate** (`pipeline/validate.py`) | tables → `validation_report.json` | **Errors block export**: duplicate course code, non-numeric credits, record without `source_url`/`retrieved_on`, prerequisite naming a missing course, hard-prerequisite cycle, self-prerequisite, resource mapped to an unknown course, resource without licence/title, rule anchor not found. **Warnings**: prerequisite offered in a later semester than its dependent core course, variable credits, category credit sum ≠ programme requirement, unused skill, prerequisite outside programme scope. An error can be waived only by a row with a written reason in `validation_waivers.csv`. |
| 4 | **Chunk** (`pipeline/chunk.py`) | tables → chunk list | Splits on sentence/`;` boundaries, at most 160 words per piece, 25-word overlap. Adds one *overview* chunk per course/resource stating its facts in words (credits, semester, prerequisites, licence), so factual questions retrieve something. Each rule is kept as one chunk so it stays quotable. Resource lesson lists go in groups of 20. Chunk IDs are deterministic: `<parent_id>::<type>::<nnn>`. |
| 5 | **Export** (`pipeline/export.py`) | → `data/processed/`, `SOURCES.md`, `reports/quality_stats.md` | CSV + JSON per entity, `chunks.jsonl`, fill-rate stats, and a SOURCES.md regenerated from the manifest so it cannot drift. |

The brief allows running on a small sample. This runs on the full programme instead (59 courses, 53 resources), in about a minute with a warm cache.

## Schema

Every entity carries `source_id`, `source_url` (with `#page=N` for PDFs), `retrieved_on` and `source_type` (`official` / `open-licence` / `manual`).

| Entity (file) | Key fields | Notes / changes vs the starting schema |
|---|---|---|
| Course (`courses`) | code, title, department, credits, L, T, P, category, course_type, semesters_offered, semester_labels, semester_basis, mode, level, syllabus, prereq_text, prereq_note, overlap_text, page | **Added** `category` (IC/PL/PC/PE/NC: the institute's own classes, finer than core/elective/open), `L-T-P` (workload, useful for time planning), `level` (the 500/600 rule gates year of study), `overlap_text` (the 25% overlap rule blocks credit), `semester_basis` (says whether the semester is fixed by the grid or only a PE slot). `prereq_text` is kept raw next to the parsed edges so a human can audit it. |
| Prerequisite edge (`prerequisites`) | course_code, requires_code, requires_code_raw, kind, group_id, group_logic, requires_in_catalogue | **Added** `group_id`/`group_logic` (`all_of`/`any_of`) because sources say "CS202/CSL252" or "A and B"; `requires_code_raw` keeps the legacy code that was resolved; `requires_in_catalogue` flags a known-unresolvable edge instead of dropping it. `kind` adds `concurrent`. |
| Skill (`skills`) | skill_id, name, parent_skill, level, keywords | 30 skills in a two-level tree. `keywords` makes skill linking deterministic and auditable. |
| Course–skill (`course_skills`) | course_id, skill_id, depth, evidence, method | Depth comes from course level (1xx–2xx intro, 3xx–4xx working, 5xx+ advanced); `evidence` lists the matched keywords. |
| Academic rule (`rules`) | rule_id, category, text (verbatim), numeric_limit, unit, comparator, applies_to, notes, page | **Added** `unit` + `comparator` so a rule like "≤ 21 credits per semester" can be checked by code, and `applies_to` (batch scope, because two curricula coexist). |
| Programme requirement (`programme_requirements`) | category, min_credits, unit | **New.** Minimum credits per category for CSE (IC 40.5, PL 4, PC 52, PE 22.5, OE 15, LA 10, NC 12 units). Needed for graduation-gap checks. |
| Semester slot (`semester_slots`) | semester, slot_type (PE/OE/LA), credits | **New.** Elective credits the grid reserves per semester. A planner fills these. |
| Resource (`resources`) | resource_id, title, provider, instructor, offered_by, licence, format, n_lessons, duration_hours_est, duration_basis, description, url | `duration_basis` says how rough the duration is. |
| Resource–course (`resource_courses`) | resource_id, course_code | **New.** Manual mapping (the brief asks for resources "mapped to the courses"). |
| Resource–skill (`resource_skills`) | resource_id, skill_id, level, evidence | Same keyword method as for courses. |
| Module / lesson (`modules`) | module_id, parent_id, parent_type, order, summary | Course modules = syllabus topics in order (422). Resource modules = NPTEL lessons (2,153). |
| Chunk (`chunks.jsonl`) | chunk_id, parent_id, parent_type, chunk_type, text, n_words, content_sha1, source_*, metadata{…} | `metadata` is flat filter fields: course_code, semesters_offered, course_type, category, credits, skill_ids, licence, rule_category, numeric_limit… |

Exercises (bonus) are not included. Day 1 had no time to write and verify an answer key, and unverified answers would hurt the mastery checks they're meant to support.

## Manual entry (disclosed)

Everything in `data/manual/` is hand-authored. None of it is course or rule *content*:
- `rules_seed.csv`: for each rule, a start/end anchor, category, numeric limit, unit and comparator. **The rule text is not typed.** The pipeline extracts it verbatim from the PDF and fails if an anchor is missing.
- `resources_seed.csv`: which open resources to include, their licence (from the provider's terms) and which IIT Bhilai courses they support. **Titles, instructors and lesson lists are read from the fetched snapshot**, not typed.
- `skills.csv`: skill taxonomy and keywords.
- `code_aliases.csv`: 5 legacy→current code mappings, each with its basis.
- `validation_waivers.csv`: 1 accepted defect, with its reason.

## Decisions and assumptions to flag

1. **Current vs legacy curriculum.** Two official curricula coexist: 2023-batch onwards (144 credits) and up to 2022-23 (240 credits). The catalogue uses the **current** one. Legacy rules are kept with `applies_to` naming the batch, so the two never get mixed.
2. **There is no "Minor" programme** in any IIT Bhilai source. The closest equivalent is **BTech (Honours) through courses in another discipline (specialisation)**, captured as `minor_honours` rules. **No numeric CGPA cut-off is published** for it ("conditions … prescribed by the Senate"), so `numeric_limit` is null rather than guessed.
3. **Semesters for electives** are the semesters where the grid reserves PE slots (6–8). Which electives actually run in a given semester is not published, so `semester_basis` says so.
4. **Mode** is `offline` for every institute course, based on "fully residential programme". MOOC credit (online) is governed by the R-MOOC-* rules.
5. **Licences.** The institute PDFs carry no open licence. They are public documents, used non-commercially for this academic exercise. NPTEL is CC BY-SA 4.0 and MIT OCW is CC BY-NC-SA 4.0.

## Data ethics

Only public institute documents and openly licensed content are used: no student records, grades or personal data. Instructor names are those already public on the NPTEL course pages.

## AI disclosure

Built with Claude Code (Anthropic) as a coding assistant: source discovery, pipeline code, tests and drafting of the docs. Every number in the docs comes from pipeline output. Course and rule content comes only from the fetched sources, not from the model.
