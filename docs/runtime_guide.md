# OpenClaw LongBanana Runtime Guide

Runtime implementation for multi-reference image generation with an
agent loop and an automated visual judge. This repository contains the runtime
code used to run OpenClaw-based generation, prepare release task JSONL files,
and evaluate candidate images with an optional subagent judge.

Run the commands below from the repository root. Runtime task files omit
source-provenance labels, and local credentials are configured separately.

## What Is Included

- OpenClaw agent image generation with the `pipe` strategy.
- Backend-isolated image generation MCP servers for Gemini, Azure, and
  Seedream-compatible image backends.
- A static visual judge for candidate images.
- Optional OCR, detection/counting, layout, and identity subagents for
  evidence gathering during judging.
- A release-task converter that builds OpenClaw JSONL files from a benchmark
  release directory.
- Offline tests for prompt construction, task loading, task conversion, retry
  behavior, and anonymous release-safety checks.

Image assets, model credentials, API keys, and private runtime configuration
are not bundled with this code release.

## Repository Layout

```text
openclaw-longbanana/
├── openclaw-runtime/          # vendored OpenClaw runtime build artifacts
├── image-gen-mcp/             # image backend MCP servers
├── openclaw_skills/           # visual judge subagent skills
├── src/openclaw_longbanana/   # Python generation, judge, and release tools
├── examples/                  # placeholder task/config examples
└── tests/                     # offline tests
```

## Requirements

- Python 3.11 or newer.
- Node.js 22.12 or newer for the OpenClaw runtime.
- A configured image-generation backend for live generation.
- A configured vision-language model endpoint for live judging.
- A benchmark release directory containing task JSONL files and image assets.

The offline tests do not require model credentials.

## Installation

```bash
cd openclaw-longbanana
python -m pip install -e '.[test]'

cd image-gen-mcp
npm install
npm run build
cd ..
```

Check that OpenClaw can start:

```bash
node openclaw-runtime/openclaw.mjs --help
```

## Configuration

Copy the example environment file and fill in local credentials outside version
control:

```bash
cp .env.example .env
```

The Python entry points load `./.env` automatically. Parent-shell environment
variables override values from `.env`.

Do not commit private values such as:

- model endpoint URLs;
- API keys;
- service-account paths or files;
- proxy hosts;
- local dataset paths.

The checked-in `.env.example` contains placeholders only.

## Benchmark Release Tasks

The runtime consumes two JSONL task files:

- `generation_tasks.jsonl` for image generation;
- `judge_tasks_target.jsonl` or another judge-task JSONL for visual judging.

Paths inside release JSONL files may be relative to the directory containing
the JSONL file. This allows a benchmark release to be moved as a self-contained
directory.

### Build Tasks From A Release Directory

If the benchmark release contains a manifest and per-case task definitions,
build OpenClaw task files with:

```bash
python -m openclaw_longbanana.release.build_tasks \
  --release-root /path/to/benchmark_release
```

This writes:

```text
/path/to/benchmark_release/openclaw/generation_tasks.jsonl
/path/to/benchmark_release/openclaw/judge_tasks_target.jsonl
/path/to/benchmark_release/openclaw/task_manifest.json
```

Runtime JSONL files are kept blind: generation tasks contain only the prompt,
references, and optional background image; judge tasks contain only the
candidate image, references, checklist question, guide, and answer options.

## Generation

Dry-run one generation task:

```bash
python -m openclaw_longbanana.generation.run \
  --tasks-jsonl /path/to/benchmark_release/openclaw/generation_tasks.jsonl \
  --backends gemini \
  --strategies pipe \
  --results-dir runs/generation_smoke \
  --limit 1 \
  --dry-run
```

Run live generation after credentials and image assets are configured:

```bash
python -m openclaw_longbanana.generation.run \
  --tasks-jsonl /path/to/benchmark_release/openclaw/generation_tasks.jsonl \
  --backends gemini \
  --strategies pipe \
  --results-dir runs/generation \
  --workers 1
```

Generation task rows accept:

- `case_id`
- `prompt`, `prompt_en`, or `target_description`
- `refs`
- optional `background` or `background_image_path`
- optional `background_image_paths`

Generation rows should not contain target images, candidate paths, answers, or
source-provenance fields.

## Judge

With `--openclaw-judge-subagents`, non-global checks require completed visual
subagent evidence before accepting a verdict. The runner keeps the per-task
Gateway alive, checks the isolated run registry for successful completion and
nonempty child results, then requests a fresh parent verdict using that evidence.
Early parent answers and answers found only in Gateway logs are not accepted.
Child failure, missing evidence, or timeout produces an invalid result eligible
for the configured retry policy. Completion snapshots are saved alongside task
logs as `*.subagents.json`. Global checks and runs without this flag keep their
existing direct-judge behavior.

Visual specialists receive their role instructions inline in isolated bootstrap
workspaces. They do not need to call an unavailable `read` tool to load a skill.
The parent CLI remains alive until child completion is persisted, even if it
prints an early response; the response alone is not a completion signal.

Dry-run one judge task:

```bash
python -m openclaw_longbanana.judge.run_agent_judge_static \
  --tasks-jsonl /path/to/benchmark_release/openclaw/judge_tasks_target.jsonl \
  --judge-projects openclaw \
  --openclaw-judge-subagents \
  --invalid-retries 5 \
  --results-dir runs/judge_smoke \
  --workers 1 \
  --limit 1 \
  --dry-run
```

Run live judging:

```bash
python -m openclaw_longbanana.judge.run_agent_judge_static \
  --tasks-jsonl /path/to/benchmark_release/openclaw/judge_tasks_target.jsonl \
  --judge-projects openclaw \
  --openclaw-judge-subagents \
  --invalid-retries 5 \
  --results-dir runs/judge \
  --workers 1
```

Judge task rows require:

- `harness`
- `backend`
- `case_id`
- `data_index`
- `category`
- `question`
- `guide`
- `options`
- `candidate_path`
- `refs` for non-`global_check` tasks

The judge writes `judgments.csv`, `summary.json`, and per-run logs under the
selected results directory.

## Tests

Run the offline test suite:

```bash
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPYCACHEPREFIX=/tmp/openclaw-longbanana-pycache \
PYTEST_ADDOPTS='-p no:cacheprovider' \
PYTHONPATH=src \
pytest -q
```

Run entry-point dry-runs with the example tasks:

```bash
python -m openclaw_longbanana.generation.run \
  --tasks-jsonl examples/generation_tasks.example.jsonl \
  --dry-run

python -m openclaw_longbanana.judge.run_agent_judge_static \
  --tasks-jsonl examples/judge_tasks.example.jsonl \
  --dry-run
```

## Anonymous Release Checklist

Before uploading this preview to an anonymous code host, verify that the
repository does not include:

- `.env` files;
- service-account JSON files or credential material;
- private proxy or endpoint strings;
- local absolute dataset paths;
- author names, affiliations, usernames, or acknowledgements;
- source-case identifiers or provenance labels in runtime task JSONL files;
- private label, audit, or answer-key columns in runtime task JSONL files.

Useful local checks:

```bash
rg -n "author|affiliation|acknowledg|service-account|api_key|secret|token|proxy" .
PYTHONPATH=src pytest -q
```

Some matches may be legitimate placeholder text in `.env.example` or this
README. Inspect every match before publishing.

## Notes For Reviewers

This code release is designed to be paired with a separate benchmark asset
release. The code path for generation does not require labels or provenance
metadata. The judge path only sees the candidate image, references, checklist
question, guide, and answer options.

Live results depend on the configured model endpoint and image backend. The
offline tests check local code behavior and task-format safety; they do not
verify model quality.

## License

This anonymous preview is provided for review purposes. A final public release
will include the definitive license and citation information.
