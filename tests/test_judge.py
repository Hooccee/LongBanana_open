import csv
import json
import sys
import time
from pathlib import Path

from openclaw_longbanana import config
from openclaw_longbanana.generation import run as generation_run
from openclaw_longbanana.judge import answer_parser, prompts, runner, run_agent_judge_static
from openclaw_longbanana.release import build_tasks


def _task(tmp_path: Path) -> dict:
    candidate = tmp_path / "candidate.png"
    ref = tmp_path / "ref.png"
    candidate.write_bytes(b"candidate")
    ref.write_bytes(b"ref")
    return {
        "harness": "openclaw",
        "backend": "gemini",
        "case_id": "case-1",
        "data_index": "1",
        "category": "entity_check",
        "question": "Does the candidate match the reference object?",
        "guide": "Visible object identity should match.",
        "options": ["correct", "incorrect", "uncertain"],
        "candidate_path": str(candidate),
        "refs": [str(ref)],
    }


def _write_tasks_jsonl(path: Path, tasks: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for task in tasks:
            f.write(json.dumps(task) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _private_field_names() -> list[str]:
    return [
        "human" + "_answer",
        "vlm" + "_answer",
        "source" + "_question_en",
        "source" + "_case_name",
        "gold" + "_answer",
        "ground" + "_truth",
    ]


def test_parse_answer_reads_openclaw_json_payload_text_before_debug_prompt():
    raw = json.dumps(
        {
            "payloads": [
                {
                    "text": '<answer>{"answer":"correct","reason":"visible grip","evidence":["hand on rifle"]}</answer>',
                    "mediaUrl": None,
                }
            ],
            "meta": {
                "finalPromptText": '<answer>{"answer":"one option from the task options"}</answer>',
                "finalAssistantVisibleText": '<answer>{"answer":"correct","reason":"visible grip","evidence":["hand on rifle"]}</answer>',
            },
        }
    )

    parsed = answer_parser.parse_agent_answer(raw, ["correct", "incorrect", "uncertain"])

    assert parsed.answer == "correct"
    assert parsed.is_pass is True
    assert parsed.is_invalid is False
    assert parsed.reason == "visible grip"


def test_load_openclaw_model_config_uses_env(monkeypatch):
    monkeypatch.setenv("OPENCLAW_MODEL_PROVIDER", "test-provider")
    monkeypatch.setenv("OPENCLAW_MODEL_ID", "test-model")
    monkeypatch.setenv("OPENCLAW_MODEL_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("OPENCLAW_MODEL_API_KEY", "test-key")
    monkeypatch.setenv("OPENCLAW_MAX_TOKENS", "16384")

    model_cfg = config.load_openclaw_model_config()

    assert model_cfg.model_ref == "test-provider/test-model"
    assert model_cfg.provider_config()["models"][0]["maxTokens"] == 16384


def test_no_proxy_default_does_not_hardcode_private_domains():
    assert config.no_proxy_default() == "localhost,127.0.0.1"


def test_generation_prompt_matches_main_openclaw_harness(tmp_path: Path, monkeypatch):
    text = generation_run._build_base_prompt(
        {
            "case_id": "gen-1",
            "prompt": "Create a studio product shot.",
            "refs": ["/tmp/ref.png"],
            "background": "/tmp/bg.png",
        },
        tmp_path / "out",
        "gemini",
        90000,
    )

    assert "Goal: generate a single image for case ." in text
    assert "Active image backend: gemini  (fixed for this run; the image-gen tool cannot be re-routed)." in text
    assert "Backend API reference (available if you need it):" in text
    assert "Use `view_reference_image` to inspect the listed files before generating." in text
    assert "small shortlist" not in text
    assert "OPENCLAW_MAX_REFERENCE_INSPECTIONS" not in text


def test_generation_prompt_injects_backend_specific_local_reference(tmp_path: Path):
    expected = {
        "firered": "firered_image_for_agents.md",
        "firered-agent": "firered_agent_image_for_agents.md",
        "hidream": "hidream_image_for_agents.md",
    }
    task = {
        "case_id": "gen-local",
        "prompt": "Create a composed product image.",
        "refs": ["/tmp/ref.png"],
    }

    for backend, filename in expected.items():
        text = generation_run._build_base_prompt(
            task, tmp_path / backend, backend, 3600
        )
        assert f"Active image backend: {backend}" in text
        assert filename in text
        for other_filename in set(expected.values()) - {filename}:
            assert other_filename not in text


def test_generation_prompt_ignores_private_task_fields(tmp_path: Path):
    task = {
        "case_id": "gen-1",
        "prompt": "Create a studio product shot.",
        "refs": ["/tmp/ref.png"],
        "background": "/tmp/bg.png",
        "source_case_id": "SECRET_SOURCE_CASE",
        "sample_uid": "SECRET_SAMPLE_UID",
        "dataset": "SECRET_DATASET",
        "candidate_path": "SECRET_CANDIDATE_PATH",
        "target_image": "SECRET_TARGET_IMAGE",
        "answer": "SECRET_ANSWER",
    }

    text = generation_run._build_base_prompt(task, tmp_path / "out", "gemini", 90000)

    for forbidden in (
        "SECRET_SOURCE_CASE",
        "SECRET_SAMPLE_UID",
        "SECRET_DATASET",
        "SECRET_CANDIDATE_PATH",
        "SECRET_TARGET_IMAGE",
        "SECRET_ANSWER",
    ):
        assert forbidden not in text


def test_judge_prompt_ignores_private_task_fields(tmp_path: Path):
    task = _task(tmp_path)
    private_values = {
        "source_case_id": "SECRET_SOURCE_CASE",
        "sample_uid": "SECRET_SAMPLE_UID",
        "dataset": "SECRET_DATASET",
        "source_question_en": "SECRET_SOURCE_QUESTION",
        "human_answer": "SECRET_HUMAN_ANSWER",
        "gold": "SECRET_GOLD",
        "gold_answer": "SECRET_GOLD_ANSWER",
        "ground_truth": "SECRET_GROUND_TRUTH",
    }
    task.update(private_values)

    text = prompts.build_openclaw_subagent_judge_prompt(task, "pipe")

    for forbidden in private_values:
        assert forbidden not in text
    for forbidden in private_values.values():
        assert forbidden not in text


def test_release_build_tasks_outputs_blind_openclaw_schema(tmp_path: Path):
    release_root = tmp_path / "release"
    sample_dir = release_root / "samples" / "LAC" / "LAC-001"
    refs_dir = sample_dir / "refs"
    background_dir = sample_dir / "background"
    target_dir = sample_dir / "target"
    refs_dir.mkdir(parents=True)
    background_dir.mkdir()
    target_dir.mkdir()
    (refs_dir / "ref_01.png").write_bytes(b"ref")
    (background_dir / "background_01.png").write_bytes(b"bg")
    (target_dir / "target_image.png").write_bytes(b"target")
    (sample_dir / "crowd_nl_tasks.json").write_text(
        json.dumps(
            {
                "crowd_tasks": [
                    {
                        "task_id": "entity_check:item",
                        "task_type": "entity_check",
                        "question": "SECRET_SOURCE_QUESTION",
                        "question_zh": "候选图是否匹配参考图？",
                        "instruction_zh": "只依据可见证据判断。",
                        "guide": "visible evidence only",
                        "options": ["correct", "incorrect", "uncertain"],
                        "option_guide_zh": {
                            "correct": "匹配",
                            "incorrect": "不匹配",
                            "uncertain": "无法判断",
                        },
                        "asset_bundle": {
                            "reference_images": [
                                {"ref_image_path": "refs/ref_01.png"},
                            ],
                        },
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with (release_root / "manifest.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "dataset",
                "category",
                "case_id",
                "sample_uid",
                "source_case_id",
                "source_case_name",
                "release_case_dir",
                "target_image",
                "prompt_en",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "dataset": "SECRET_DATASET",
                "category": "LAC",
                "case_id": "LAC-001",
                "sample_uid": "SECRET_SAMPLE_UID",
                "source_case_id": "SECRET_SOURCE_CASE",
                "source_case_name": "SECRET_SOURCE_NAME",
                "release_case_dir": "samples/LAC/LAC-001",
                "target_image": "samples/LAC/LAC-001/target/target_image.png",
                "prompt_en": "Create a clean image.",
            }
        )

    manifest = build_tasks.build_tasks(release_root)
    generation_rows = _read_jsonl(release_root / "openclaw" / "generation_tasks.jsonl")
    judge_rows = _read_jsonl(release_root / "openclaw" / "judge_tasks_target.jsonl")

    assert manifest["generation_task_count"] == 1
    assert manifest["judge_task_count"] == 1
    assert set(generation_rows[0]) == {"case_id", "prompt_en", "refs", "background_image_path"}
    assert set(judge_rows[0]) == {
        "harness",
        "backend",
        "case_id",
        "data_index",
        "task_id",
        "category",
        "question",
        "guide",
        "options",
        "option_desc",
        "candidate_path",
        "refs",
    }
    assert judge_rows[0]["data_index"] == "LAC-001#001"
    dumped = json.dumps({"generation": generation_rows, "judge": judge_rows}, ensure_ascii=False)
    for forbidden in (
        "SECRET_DATASET",
        "SECRET_SAMPLE_UID",
        "SECRET_SOURCE_CASE",
        "SECRET_SOURCE_NAME",
        "SECRET_SOURCE_QUESTION",
    ):
        assert forbidden not in dumped


def test_open_source_package_has_no_private_analysis_modules_or_fields():
    package_root = Path(__file__).resolve().parents[1]
    targets = [
        package_root / "src",
        package_root / "examples",
        package_root / "README.md",
        package_root / "pyproject.toml",
    ]
    text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for target in targets
        for path in ([target] if target.is_file() else sorted(target.rglob("*")))
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix in {".py", ".md", ".json", ".jsonl", ".toml"}
    )

    for forbidden in _private_field_names():
        assert forbidden not in text
    for forbidden in (
        "agreement" + ".py",
        "disagreement" + "_dataset",
        "merged" + "_csv",
        "balanced" + "_experiment",
        "easy" + "_agree",
    ):
        assert forbidden not in text


def test_generation_openclaw_config_matches_main_shape(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OPENCLAW_MODEL_PROVIDER", "test-provider")
    monkeypatch.setenv("OPENCLAW_MODEL_ID", "test-model")
    monkeypatch.setenv("OPENCLAW_MODEL_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("OPENCLAW_MODEL_API_KEY", "test-key")
    monkeypatch.setenv("OPENCLAW_MODEL_API", "openai-completions")
    monkeypatch.setenv("OPENCLAW_MODEL_ALLOW_PRIVATE_NETWORK", "1")
    monkeypatch.setenv(
        "FIRERED_SERVICE_URL",
        "http://fire-red-aggregate.internal:18083",
    )
    config_path = tmp_path / "openclaw.json"
    state_dir = tmp_path / "state"
    output_dir = tmp_path / "out"
    image_config = tmp_path / "image_gen_config.json"
    image_config.write_text("{}", encoding="utf-8")

    generation_run._write_openclaw_config(
        config_path=config_path,
        state_dir=state_dir,
        output_dir=output_dir,
        backend="gemini",
        timeout_s=90000,
        image_config=image_config,
    )

    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    defaults = cfg["agents"]["defaults"]
    provider = cfg["models"]["providers"]["test-provider"]
    mcp_env = cfg["mcp"]["servers"]["image-gen"]["env"]
    assert defaults["model"] == {"primary": "test-provider/test-model"}
    assert defaults["workspace"] == "~/.openclaw/workspace"
    assert defaults["skipBootstrap"] is True
    assert "mode" not in cfg["models"]
    assert provider["request"]["allowPrivateNetwork"] is True
    assert provider["models"][0]["maxTokens"] == 8192
    assert mcp_env["IMAGE_OUTPUT_DIR"] == "${IMAGE_OUTPUT_DIR}"
    assert mcp_env["IMAGE_GENERATE_OUTPUT_DIR"] == "${IMAGE_OUTPUT_DIR}"
    assert (
        mcp_env["FIRERED_SERVICE_URL"]
        == "http://fire-red-aggregate.internal:18083"
    )


def test_openclaw_env_uses_vertex_subagent_shape_and_16k_tokens(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OPENCLAW_JUDGE_PROVIDER", "google-vertex")
    monkeypatch.setenv("AGENT_JUDGE_GEMINI_MODEL", "gemini-test")
    monkeypatch.setenv("OPENCLAW_MODEL_PROVIDER", "test-provider")
    monkeypatch.setenv("OPENCLAW_MODEL_ID", "gemini-test")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project-test")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "global")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "credentials.json"))
    monkeypatch.setenv("AGENT_JUDGE_OPENCLAW_GATEWAY_PORT", "49152")
    monkeypatch.setenv("AGENT_JUDGE_OPENCLAW_GATEWAY_CALL_TIMEOUT_MS", "300000")
    monkeypatch.delenv("OPENCLAW_GATEWAY_CALL_TIMEOUT_MS", raising=False)
    monkeypatch.delenv("LONGBANANA_DATA_ROOT", raising=False)
    monkeypatch.setattr(runner, "_google_vertex_access_token", lambda credentials_path: "token-test")
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    candidate = media_dir / "candidate.png"
    ref = media_dir / "ref.png"
    candidate.write_bytes(b"candidate")
    ref.write_bytes(b"ref")

    env, cleanup_root = runner._build_openclaw_env(
        openclaw_judge_subagents=True,
        media_paths=[candidate, ref],
    )
    try:
        cfg = json.loads(Path(env["OPENCLAW_CONFIG_PATH"]).read_text())
        config_media = (Path(env["OPENCLAW_CONFIG_PATH"]).parent / "media").resolve()
        workspace = Path(cfg["agents"]["defaults"]["workspace"])
        for specialist in cfg["agents"]["list"][1:]:
            assert specialist["skills"] == []
            instructions = (Path(specialist["workspace"]) / "AGENTS.md").read_text()
            assert "no file-reading tool call is needed" in instructions
            assert "Return one JSON object" in instructions
    finally:
        import shutil

        shutil.rmtree(cleanup_root, ignore_errors=True)

    assert cfg["agents"]["defaults"]["model"] == "google-vertex/gemini-test"
    assert workspace == config.PROJECT_ROOT
    assert config_media == media_dir.resolve()
    provider = cfg["models"]["providers"]["google-vertex"]
    assert provider["api"] == "google-generative-ai"
    assert provider["apiKey"] == "<authenticated>"
    assert provider["headers"]["Authorization"] == "Bearer token-test"
    assert provider["models"][0]["maxTokens"] == 16384
    main_tools = cfg["agents"]["list"][0]["tools"]["allow"]
    assert "sessions_spawn" in main_tools
    assert "subagents" in main_tools
    assert "session_status" in main_tools
    assert "sessions_list" not in main_tools
    assert "sessions_history" not in main_tools
    assert env["OPENCLAW_GATEWAY_CALL_TIMEOUT_MS"] == "300000"
    assert cfg["skills"]["load"]["extraDirs"] == [str(config.DEFAULT_OPENCLAW_SKILLS_DIR)]
    assert "exec" in cfg["tools"]["deny"]


def test_openclaw_env_defaults_gateway_call_timeout_without_private_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("OPENCLAW_JUDGE_PROVIDER", "google")
    monkeypatch.setenv("OPENCLAW_MODEL_PROVIDER", "test-provider")
    monkeypatch.setenv("OPENCLAW_MODEL_ID", "gemini-test")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project-test")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "global")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "credentials.json"))
    monkeypatch.setenv("AGENT_JUDGE_OPENCLAW_GATEWAY_PORT", "49152")
    monkeypatch.delenv("AGENT_JUDGE_OPENCLAW_GATEWAY_CALL_TIMEOUT_MS", raising=False)
    monkeypatch.delenv("OPENCLAW_GATEWAY_CALL_TIMEOUT_MS", raising=False)
    monkeypatch.delenv("LONGBANANA_DATA_ROOT", raising=False)
    monkeypatch.setattr(runner, "_google_vertex_access_token", lambda credentials_path: "token-test")
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    candidate = media_dir / "candidate.png"
    ref = media_dir / "ref.png"
    candidate.write_bytes(b"candidate")
    ref.write_bytes(b"ref")

    env, cleanup_root = runner._build_openclaw_env(
        openclaw_judge_subagents=True,
        media_paths=[candidate, ref],
    )
    try:
        assert env["OPENCLAW_GATEWAY_CALL_TIMEOUT_MS"] == runner.DEFAULT_OPENCLAW_GATEWAY_CALL_TIMEOUT_MS
    finally:
        import shutil

        shutil.rmtree(cleanup_root, ignore_errors=True)


def test_openclaw_stream_completed_answer_waits_for_subagent_completion():
    options = ["correct", "incorrect", "uncertain"]
    answer = '<answer>{"answer":"correct","reason":"visible","evidence":["match"]}</answer>'

    assert runner._stream_has_completed_answer(answer, options) is True
    assert runner._stream_has_completed_answer(f"sessions_spawn\n{answer}", options) is False
    assert runner._stream_has_completed_answer(
        f"sessions_spawn\nChild Session Message Received\n{answer}",
        options,
    ) is True
    assert runner._stream_has_completed_answer(
        f"sessions_spawn\n<!-- CHILD_COMPLETION_EVENT: agent:detector-judge:subagent:abc -->\n{answer}",
        options,
    ) is True
    assert runner._stream_has_completed_answer(
        f"sessions_spawn\n<!-- AGENT_NOTIFICATION: agent:detector-judge:subagent:abc completion arriving -->\n"
        f"<subagent_completion sessionKey=\"agent:detector-judge:subagent:abc\">{{}}</subagent_completion>\n{answer}",
        options,
    ) is True
    assert runner._stream_has_completed_answer(
        f"sessions_spawn\n<!-- OPENCLAW_SUBAGENT_COMPLETION: agent:detector-judge:subagent:abc -->\n{answer}",
        options,
    ) is True
    assert runner._stream_has_completed_answer(
        f"sessions_spawn\n[agent/embedded] embedded run done: runId=abc aborted=false\n{answer}",
        options,
    ) is True


def test_openclaw_session_transcript_fallback_reads_followup_answer(tmp_path: Path):
    state_dir = tmp_path / "state"
    session_dir = state_dir / "agents" / "main" / "sessions"
    session_dir.mkdir(parents=True)
    session_id = "session-1"
    (session_dir / f"{session_id}.jsonl").write_text(
        json.dumps(
            {
                "type": "message",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": '<answer>{"answer":"correct","reason":"visible","evidence":["match"]}</answer>',
                        }
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    text = runner._openclaw_session_transcript_text(
        {"OPENCLAW_STATE_DIR": str(state_dir)},
        session_id,
    )
    parsed = answer_parser.parse_agent_answer(
        f"NO_REPLY\n{text}",
        ["correct", "incorrect", "uncertain"],
    )

    assert parsed.answer == "correct"
    assert parsed.is_invalid is False


def test_streaming_process_stops_when_session_transcript_has_answer(tmp_path: Path):
    state_dir = tmp_path / "state"
    session_dir = state_dir / "agents" / "main" / "sessions"
    session_dir.mkdir(parents=True)
    session_id = "session-1"
    (session_dir / f"{session_id}.jsonl").write_text(
        json.dumps(
            {
                "type": "message",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": '<answer>{"answer":"correct","reason":"visible","evidence":["match"]}</answer>',
                        }
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    started = time.time()
    proc = runner._run_streaming_process(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=tmp_path,
        env=None,
        timeout_s=30,
        log_path=tmp_path / "stream.log",
        answer_options=["correct", "incorrect", "uncertain"],
        session_env={"OPENCLAW_STATE_DIR": str(state_dir)},
        session_id=session_id,
    )

    assert proc.returncode == 0
    assert time.time() - started < 10
    assert "session_transcript" in proc.stdout
    assert "correct" in proc.stdout


def test_run_openclaw_judge_retries_invalid_until_valid(monkeypatch, tmp_path: Path):
    task = _task(tmp_path)
    calls = []

    def fake_once(task, strategy, log_path, timeout_s, account_index=None, openclaw_judge_subagents=False):
        calls.append(log_path)
        if len(calls) == 1:
            return runner._judgment_row(
                task,
                strategy,
                "openclaw",
                answer_parser.parse_agent_answer('<answer>{"answer":"bad"}</answer>', task["options"]),
                1.0,
                "invalid_answer:bad",
            )
        return runner._judgment_row(
            task,
            strategy,
            "openclaw",
            answer_parser.parse_agent_answer(
                '<answer>{"answer":"correct","reason":"visible","evidence":["candidate matches"]}</answer>',
                task["options"],
            ),
            2.0,
            "",
        )

    monkeypatch.setattr(runner, "_run_openclaw_judge_once", fake_once)

    row = runner.run_openclaw_judge(task, "pipe", tmp_path / "judge.log", 30, openclaw_judge_subagents=True, invalid_retries=5)

    assert len(calls) == 2
    assert row["answer"] == "correct"
    assert row["is_invalid"] is False
    assert row["error_msg"].startswith("recovered_after_1_retries")


def test_judge_cli_requires_jsonl_and_passes_subagent_flag(monkeypatch, tmp_path: Path, capsys):
    task = _task(tmp_path)
    tasks_jsonl = tmp_path / "tasks.jsonl"
    _write_tasks_jsonl(tasks_jsonl, [task])
    calls = []

    def fake_run(task, strategy, log_path, timeout_s, account_index=None, openclaw_judge_subagents=False, invalid_retries=5):
        calls.append((task, strategy, openclaw_judge_subagents, invalid_retries))
        parsed = answer_parser.parse_agent_answer(
            '<answer>{"answer":"correct","reason":"visible","evidence":["match"]}</answer>',
            task["options"],
        )
        return runner._judgment_row(task, strategy, "openclaw", parsed, 1.0, "")

    monkeypatch.setattr(run_agent_judge_static, "run_openclaw_judge", fake_run)
    monkeypatch.setattr(run_agent_judge_static, "write_summary", lambda judgments_csv, summary_json: {})

    run_agent_judge_static.main(
        [
            "--tasks-jsonl",
            str(tasks_jsonl),
            "--results-dir",
            str(tmp_path / "results"),
            "--judge-projects",
            "openclaw",
            "--openclaw-judge-subagents",
            "--invalid-retries",
            "5",
            "--workers",
            "1",
        ]
    )

    assert calls == [(task, "pipe", True, 5)]
    assert "planned_runs=1" in capsys.readouterr().out


def test_generation_dry_run_expands_openclaw_plan(tmp_path: Path, capsys):
    tasks_jsonl = tmp_path / "generation_tasks.jsonl"
    _write_tasks_jsonl(
        tasks_jsonl,
        [
            {
                "case_id": "gen-1",
                "prompt": "Create a studio product shot.",
                "refs": ["/tmp/ref.png"],
            }
        ],
    )

    generation_run.main(
        [
            "--tasks-jsonl",
            str(tasks_jsonl),
            "--backends",
            "gemini",
            "--strategies",
            "pipe",
            "--dry-run",
        ]
    )

    out = capsys.readouterr().out
    assert "planned_runs=1" in out
    assert "pipe             openclaw gemini" in out


def test_tasks_jsonl_relative_paths_resolve_from_jsonl_dir(tmp_path: Path):
    task_dir = tmp_path / "release" / "openclaw"
    sample_dir = tmp_path / "release" / "samples" / "BPRO" / "AGG" / "AGG-008"
    task_dir.mkdir(parents=True)
    sample_dir.mkdir(parents=True)
    tasks_jsonl = task_dir / "judge_tasks.jsonl"
    candidate = sample_dir / "target.png"
    ref = sample_dir / "ref.png"
    candidate.write_bytes(b"candidate")
    ref.write_bytes(b"ref")
    _write_tasks_jsonl(
        tasks_jsonl,
        [
            {
                "case_id": "AGG-008",
                "candidate_path": "../samples/BPRO/AGG/AGG-008/target.png",
                "refs": ["../samples/BPRO/AGG/AGG-008/ref.png"],
            }
        ],
    )

    tasks = run_agent_judge_static.load_tasks_jsonl(tasks_jsonl)

    assert tasks[0]["candidate_path"] == str(candidate.resolve())
    assert tasks[0]["refs"] == [str(ref.resolve())]
