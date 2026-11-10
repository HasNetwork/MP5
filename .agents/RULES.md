# Project rules
- Never hand-type course/rule content; add anchors/seeds in data/manual/ and let the pipeline extract.
- Never edit data/raw/ (sha256-checked). Re-fetch with `python run_pipeline.py --refresh`.
- New validator exceptions need a row + reason in data/manual/validation_waivers.csv.
- No LLM/embedding calls in the day-1 pipeline. Day 2: all model calls via LiteLLM, config from env (LLM_MODEL, LLM_API_KEY, LLM_API_BASE, EMBEDDING_MODEL).
- Python via uv/.venv only.
