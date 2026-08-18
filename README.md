# ticker-brief

Tiny CLI that pulls a Yahoo Finance quote and asks a few chat models for a
3-sentence briefing. No extra packages — just Python 3.

```bash
python3 ticker_brief.py
python3 ticker_brief.py MSFT
```

Set any of these if you want a model briefing (missing keys are skipped):

```bash
export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
export GEMINI_API_KEY=...
export XAI_API_KEY=...
```

This repository is part of a personal study of how API-key leak detection
and provider notification work. Treat any credentials that appear here as
canaries, not production secrets.
