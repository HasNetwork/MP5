# PLAN - Adobe PS (Inter IIT TM 15.0), day-1 selection assignment

Brief: `Adobe PS 1-Day Selection Assignment.md` (today's task); main PS: `Adobe.md`.
Institute/programme: **IIT Bhilai, BTech CSE** (user's institute; PS requires "our institute").
Deadline: 2026-11-10 21:30 IST.

## Phases
| Phase | Status | Detail |
|---|---|---|
| 1-1 Source discovery | done | .agents/PLAN/1-1.md |
| 1-2 Pipeline (ingest/parse/validate/chunk/export) | done | .agents/PLAN/1-2.md |
| 1-3 Docs: README, SOURCES (generated), DATA_QUALITY, IDEAS | done | .agents/PLAN/1-3.md |
| 2-x Day 2: embeddings via LiteLLM (EMBEDDING_MODEL env) | not started | consume data/processed/chunks.jsonl |

## Key decisions (why)
- Primary source = Courses of Study Oct 2026 (2023 batch onwards); legacy 2023 doc only for code aliases + batch-scoped rules.
- No "Minor" exists at IIT Bhilai -> modelled BTech (Honours) by specialisation; no CGPA cut-off published (null, not guessed).
- Rules stored as anchors -> pipeline extracts verbatim text; fails if anchor missing.
- Validator fails loudly; exceptions only via data/manual/validation_waivers.csv with reason.
- TLS: truststore (OS store) because iitbhilai.ac.in sends incomplete chain; verification never disabled.
