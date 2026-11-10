# Ideas note: how the buddy would use this data (Part E)

**Split of work.** Hard facts are answered by **code over the tables**: prerequisite graph walks, credit sums against `programme_requirements` and `semester_slots`, and rule checks using `numeric_limit` + `comparator`. **Retrieval over `chunks.jsonl`** only finds the text to quote and explain. The LLM writes the explanation and must cite `rule_id` / course code / `source_url#page`. It never computes a limit or invents a course code: any code it outputs is checked against `courses.csv` first.

## Three questions the buddy can answer well

1. **"I'm in Sem 4 and failed CSL202. What does that block, and what can I still take?"**
   Walk `prerequisites` forward from CSL202: CSL252, CSL253 and CSL301 are blocked, then CSL302 through CSL253, and the electives that need CSL252 (CSL510, CSL512, CSL515, CSL608, …). Cite R-PRE-001 (an F grade blocks registration) and R-PRE-003. Suggest NPTEL 106102064 or MIT 6.006 from `resource_courses` to recover. Every step is deterministic and traceable.

2. **"Can I take an NPTEL course for credit, and how much will it count?"**
   Answer from the rules: at most 6 credits over the whole programme (R-MOOC-001/006), only as OE or PE (R-MOOC-002), DUGC permission before the course starts (R-MOOC-003/007), and a 14-week course counts as 3 credits (R-MOOC-005). Each is a verbatim quote with a page link. The buddy can also flag the 1-2 vs 1-3 credit conflict between the two documents instead of picking one silently.

3. **"I want to work in systems/security. Which electives fit, in what order, and what can I learn before then?"**
   `course_skills` (SK-OS, SK-NET, SK-CRYPTO, SK-SYSSEC) finds CSL503, CSL505, CSL517, CSL559, CSL602, CSL605, CSL614…. Prerequisite edges order them (e.g. CSL503 before CSL602 and CSL614). `semester_slots` shows 3 / 8.5 / 11 PE credits free in Sem 6/7/8. `resource_skills` fills the gap before Sem 6 with open courses (NPTEL 106105162, MIT 6.858). The plan can then be checked against R-CRED-003 (15–21 credits per semester).

## Questions it cannot answer well (yet)

- **"Which electives run next semester, who teaches them, and when?"** Offerings, timetables and instructors aren't in any source used. Elective semesters are only PE-slot ranges.
- **"Am I eligible for Honours/a minor with a 7.2 CGPA?"** The institute publishes no numeric cut-off, and there is no "minor" at all. The buddy can only quote the process and point the student to the DUGC.
- **"Is CSL616 or CSL608 better for placements?" / "How hard is CSL253?"** That needs outcomes, difficulty or student-experience data, none of which exist here (and the survey is out of scope for day 1).
- **"Does CSP402 need Applied Digital Logic Design?"** The source cites a retired code (IC150). The buddy should say the requirement is unclear and name the defect, not guess.
- **Practice and mastery questions.** There is no exercise bank or answer key yet, so the buddy can recommend content but can't test mastery.

## Next steps this data unlocks (day 2+)

Embed `chunks.jsonl`, filtering on `metadata` (course_code, semesters_offered, rule_category, licence) **before** vector search, so a Sem-3 student never retrieves a Sem-7-only elective as "available". Add an exercise bank linked to `skill_id`, and add per-semester offering data once it can be sourced.
