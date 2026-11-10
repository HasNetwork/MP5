# Quality stats (generated)

## Counts

| Entity | Count |
|---|---|
| courses | 59 |
| prerequisites | 30 |
| rules | 38 |
| resources | 53 |
| resource_courses | 68 |
| skills | 30 |
| course_skills | 79 |
| resource_skills | 89 |
| modules | 2575 |
| programme_requirements | 7 |
| semester_slots | 10 |
| chunks | 338 |

## Fill rate per field (%)

**courses**: code 100.0, title 100.0, department 100.0, credits 100.0, semesters_offered 100.0, course_type 100.0, mode 100.0, syllabus 100.0, prereq_text 100.0, overlap_text 100.0, source_url 100.0, retrieved_on 100.0

**rules**: rule_id 100.0, category 100.0, text 100.0, numeric_limit 65.8, unit 65.8, applies_to 100.0, page 100.0, source_url 100.0

**resources**: title 100.0, provider 100.0, licence 100.0, format 100.0, duration_hours_est 56.6, instructor 56.6, description 43.4, maps_to_courses 100.0, source_url 100.0, retrieved_on 100.0

**prerequisites**: course_code 100.0, requires_code 100.0, kind 100.0, group_logic 100.0

**skills**: skill_id 100.0, name 100.0, parent_skill 70.0, level 100.0

## Validator findings

- **waive** `prereq_missing_course` CSP402->IC150: prerequisite 'IC150' not found in current Courses of Study - waiver: Source defect: CoS-2026 lists legacy code IC150 (Applied Digital Logic Design, CoS-2023) as a prerequisite of CSP402. No current course covers it 1:1 (ECL101 Basic Electronics only partly). Kept as an unresolved edge (requires_in_catalogue=false) rather than guessing; to be confirmed with the CSE DUGC.
- **warning** `core_course_without_syllabus` UGQ301: listed in CSE curriculum but no syllabus block parsed
- **warning** `category_credit_mismatch` PC: sum of parsed PC course credits=49.0 vs required 52.0
- **info** `category_inferred` CSL302: code garbled in two-column category table; inferred PC from semester grid

## Legacy-code resolutions

- CSP352: `IC100` -> `CSL100`
- CSP402: `IC100` -> `CSL100`
- CSP402: `CS204` -> `CSL251`
- CSP402: `CS250` -> `CSL301`
- CSP402: `CS251` -> `CSL302`
- CSL616: `CS202` -> `CSL252`
