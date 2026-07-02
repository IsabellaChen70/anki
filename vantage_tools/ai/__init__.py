# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Vantage AI card-generation safety + sourcing + evaluation layer.

Offline, deterministic, and AI-OFF by default (spec-ai-cardgen.md). The modules
are written to run as standalone scripts (each adds its own directory to the path
when executed), e.g.:

    python3 vantage_tools/ai/eval_cardgen.py   # recall@k, checker, AI-off proof
    python3 vantage_tools/ai/canary.py         # prompt-injection canary

Data files: corpus.json (named sources), synonyms.json (domain aliases),
gold_set.json (question -> span), retrofit_items.json (SourceRefs for existing
practice.js items).
"""
