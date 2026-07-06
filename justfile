set windows-shell := ["pwsh", "-NoLogo", "-NoProfileLoadTime", "-Command"]

mod release

# Show available commands
default:
    @just --list

# Build the project
build:
    {{ ninja }} pylib qt

# Build and run Anki in development mode
run *args:
    {{ run_script }} {{ args }}

# Build and run Anki in optimized (release) mode
run-optimized *args:
    {{ if os() == "windows" { "$env:RELEASE='1'; .\\run.bat" } else { "RELEASE=1 ./run" } }} {{ args }}

# Watch web sources and rebuild/reload Anki's web stack on change (macOS/Linux)
web-watch:
    ./tools/web-watch

# Rebuild and reload Anki's web stack without restarting (macOS/Linux)
rebuild-web:
    ./tools/rebuild-web

# Build wheels (needed for some platforms)
wheels:
    {{ ninja }} wheels

# Build and run all checks (lint + test) - lets ninja handle dependencies
check:
    {{ ninja }} pylib qt check

# Run all tests (Rust, Python, TypeScript). Pass --coverage to enforce coverage, and --html to include HTML reports.
[arg("coverage", long="coverage", value="--coverage")]
[arg("html", long="html", value="--html")]
test coverage='' html='':
    just {{ if coverage == "--coverage" { "coverage " + html } else { "_test" } }}

# Run coverage for all test stacks. Pass --html to also generate HTML reports.
[arg("html", long="html", value="--html")]
coverage html='':
    just _coverage-rust {{ html }}
    just _coverage-py {{ html }}
    just _coverage-ts {{ html }}

# Run Rust tests. Pass --coverage to enforce Rust coverage, and --html to include an HTML report.
[arg("coverage", long="coverage", value="--coverage")]
[arg("html", long="html", value="--html")]
test-rust coverage='' html='':
    just {{ if coverage == "--coverage" { "_coverage-rust " + html } else { "_test-rust" } }}

# Run Python tests (pylib + qt). Pass --coverage to enforce coverage, and --html to include HTML reports.
[arg("coverage", long="coverage", value="--coverage")]
[arg("html", long="html", value="--html")]
test-py coverage='' html='':
    just {{ if coverage == "--coverage" { "_coverage-py " + html } else { "_test-py" } }}

# Run TypeScript/Svelte Vitest tests. Pass --coverage to enforce coverage, and --html to include an HTML report.
[arg("coverage", long="coverage", value="--coverage")]
[arg("html", long="html", value="--html")]
test-ts coverage='' html='':
    just {{ if coverage == "--coverage" { "_coverage-ts " + html } else { "_test-ts" } }}

# Run Playwright end-to-end tests. Pass --ui to open the interactive UI.
[arg("ui", long="ui", value="--ui")]
test-e2e ui='': _install-playwright-browsers
    {{ ninja }} pyenv ts:generated pylib qt
    {{ playwright_env }} {{ yarn }} test:e2e {{ ui }}

[private]
_test:
    {{ ninja }} check:rust_test check:pytest check:vitest

[private]
_test-rust:
    {{ ninja }} check:rust_test

[private]
_test-py:
    {{ ninja }} check:pytest

[private]
_test-ts:
    {{ ninja }} check:vitest

[private]
_coverage-rust html='':
    {{ if os_family() == "windows" { "tools\\coverage\\coverage-rust" } else { "tools/coverage/coverage-rust" } }} {{ html }}

[private]
_coverage-py html='':
    {{ ninja }} pylib qt
    just _coverage-py-pylib {{ html }}
    just _coverage-py-qt {{ html }}

[private]
_coverage-py-pylib html='':
    {{ if os_family() == "windows" { "tools\\coverage\\coverage-py" } else { "tools/coverage/coverage-py" } }} pylib {{ html }}

[private]
_coverage-py-qt html='':
    {{ if os_family() == "windows" { "tools\\coverage\\coverage-py" } else { "tools/coverage/coverage-py" } }} qt {{ html }}

[private]
_coverage-ts html='':
    {{ ninja }} node_modules ts:generated
    {{ if os_family() == "windows" { "tools\\coverage\\coverage-ts" } else { "tools/coverage/coverage-ts" } }} {{ html }}

[private]
_install-playwright-browsers:
    {{ ninja }} node_modules
    {{ playwright_env }} {{ yarn }} playwright install chromium

# Check formatting (fast, no build needed)
fmt:
    {{ ninja }} check:format

# Fix formatting
fix-fmt:
    {{ ninja }} format

# Run linting and type checking (requires build outputs)
lint:
    {{ ninja }} \
        check:clippy \
        check:mypy \
        check:ruff \
        check:eslint \
        check:svelte \
        check:typescript

# Fix auto-fixable lint issues (ruff + eslint)
fix-lint:
    {{ ninja }} fix:ruff fix:eslint

# Run minilints (copyright, contributors, licenses)
minilints:
    {{ ninja }} check:minilints

# Fix minilints (update licenses.json)
fix-minilints:
    {{ ninja }} fix:minilints

# Sync translation files
ftl-sync:
    {{ ninja }} ftl-sync

# Deprecate translation strings
ftl-deprecate:
    {{ ninja }} ftl-deprecate

# Build documentation site
docs:
    {{ uv }} run --group docs sphinx-build -b html docs out/docs/html
    @echo "Docs built at out/docs/html/index.html"

# Build and serve documentation site
docs-serve:
    {{ uv }} run --group docs sphinx-autobuild docs out/docs/html --host 127.0.0.1 --port 8000

# Build Rust API docs
docs-rust:
    cargo doc --open

# Dispatch CI workflow on a given branch or tag
ci branch:
    gh workflow run ci.yml --ref {{ branch }}

# Run Complexipy in regression-only mode
complexipy-diff:
    {{ ninja }} check:complexipy-diff

# Remove build outputs from out/ (pass keep-env to keep node_modules/pyenv); macOS/Linux
clean *args:
    ./tools/clean {{ args }}

# Vantage (MCAT): seeded speed benchmark on a synthetic 50k deck -> p50/p95/worst
# + PERF_RESULTS.md. Pass args through, e.g. `just bench --cards 100000`. (macOS/Linux)
bench *args:
    {{ ninja }} pylib
    {{ vpy }} vantage_tools/bench.py {{ args }}

# Vantage: held-out memory calibration -> memory_calibration.json (macOS/Linux)
eval-memory:
    {{ ninja }} pylib
    {{ vpy }} vantage_tools/evaluate_memory.py

# Vantage: held-out performance calibration -> performance_results.json (macOS/Linux)
eval-performance:
    {{ ninja }} pylib
    {{ vpy }} vantage_tools/evaluate_performance.py

# Vantage: paraphrase transfer-gap harness -> paraphrase_results.json (macOS/Linux)
eval-paraphrase:
    {{ ninja }} pylib
    {{ vpy }} vantage_tools/evaluate_paraphrase.py

# Vantage: 3-arm interleaving ablation (mixed/off/blocked) -> ablation_results.json (macOS/Linux)
ablation:
    {{ ninja }} pylib
    {{ vpy }} vantage_tools/ablation_interleave.py

# Vantage: leakage scan (eval items vs training corpus) -> leakage_report.json (macOS/Linux)
leakage:
    {{ vpy }} vantage_tools/leakage_check.py

# Vantage: readiness score-mapping anchors + sensitivity + pilot-ingest harness (macOS/Linux)
score-map:
    {{ ninja }} pylib
    {{ vpy }} vantage_tools/score_mapping.py

# Vantage: desktop<->phone scoring parity (Python core vs mobile_scoring.js via node) (macOS/Linux)
parity:
    {{ ninja }} pylib
    {{ vpy }} vantage_tools/scoring_parity_test.py

# Vantage: AI safety evals - retrieval+grounding, 3-way gate, independent held-out,
# real-text (Wikipedia CC BY-SA) grounding, experiment-design gate, wired-LLM-seam
# screening, injection canary (macOS/Linux)
eval-ai:
    {{ vpy }} vantage_tools/ai/eval_cardgen.py
    {{ vpy }} vantage_tools/ai/eval_cardcheck.py
    {{ vpy }} vantage_tools/ai/cardcheck_holdout.py
    {{ vpy }} vantage_tools/ai/eval_realtext_grounding.py
    {{ vpy }} vantage_tools/ai/eval_experiment_design.py
    {{ vpy }} vantage_tools/ai/eval_llm_seam.py
    {{ vpy }} vantage_tools/ai/canary.py

# Vantage: camera-friendly demo runner - prints only the verdict line from the
# leakage scan + AI gate (pass `all` to also run memory + performance). (macOS/Linux)
evals *args:
    vantage_tools/evals {{ args }}

# Vantage: desktop crash test (20x SIGKILL mid-review) -> crash_results.json (macOS/Linux)
crash-test:
    {{ ninja }} pylib
    {{ vpy }} vantage_tools/crash_test.py

# Vantage: offline degrade check (network off -> AI off, apps still score) -> offline_results.json (macOS/Linux)
offline-test:
    {{ ninja }} pylib
    {{ vpy }} vantage_tools/offline_test.py

# Vantage: the whole re-runnable eval suite + unit tests, in order (macOS/Linux).
# Excludes bench/crash/sync (heavier or need a server); run those on their own.
eval-all:
    {{ ninja }} pylib
    cargo test -p anki interleave
    {{ vpy }} -m pytest pylib/tests/test_interleave.py pylib/tests/test_vantage_scoring.py pylib/tests/test_vantage_collect.py -q
    {{ vpy }} vantage_tools/evaluate_memory.py
    {{ vpy }} vantage_tools/evaluate_performance.py
    {{ vpy }} vantage_tools/evaluate_paraphrase.py
    {{ vpy }} vantage_tools/ablation_interleave.py
    {{ vpy }} vantage_tools/leakage_check.py
    {{ vpy }} vantage_tools/ai/eval_cardgen.py
    {{ vpy }} vantage_tools/ai/eval_cardcheck.py
    {{ vpy }} vantage_tools/ai/cardcheck_holdout.py
    {{ vpy }} vantage_tools/ai/eval_realtext_grounding.py
    {{ vpy }} vantage_tools/ai/eval_experiment_design.py
    {{ vpy }} vantage_tools/ai/eval_llm_seam.py
    {{ vpy }} vantage_tools/ai/canary.py
    {{ vpy }} vantage_tools/offline_test.py
    {{ vpy }} vantage_tools/score_mapping.py
    {{ vpy }} vantage_tools/scoring_parity_test.py

# Helpers to get the right commands for the platform

ninja := if os() == "windows" { "tools\\ninja" } else { "./ninja" }
# Vantage eval interpreter (pylib on the path). macOS/Linux; mirrors the bench recipe.
vpy := "PYTHONPATH=pylib:out/pylib out/pyenv/bin/python"
run_script := if os() == "windows" { ".\\run.bat" } else { "./run" }
playwright_env := if os() == "windows" { "set PLAYWRIGHT_BROWSERS_PATH=out\\playwright-browsers&&" } else { "PLAYWRIGHT_BROWSERS_PATH=out/playwright-browsers" }
yarn := if os() == "windows" { "out\\extracted\\node\\yarn.cmd" } else { "out/extracted/node/bin/yarn" }
uv := env("UV_BINARY", if os() == "windows" { "out\\extracted\\uv\\uv" } else { "out/extracted/uv/uv" })
export UV_PROJECT_ENVIRONMENT := if os() == "windows" { "out\\pyenv" } else { "out/pyenv" }
