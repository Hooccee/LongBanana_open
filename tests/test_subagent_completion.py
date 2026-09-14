import json
import subprocess
import time
import sys

import pytest

from openclaw_longbanana.judge import runner


def registry(tmp_path, rows):
    directory = tmp_path / 'subagents'
    directory.mkdir(exist_ok=True)
    (directory / 'runs.json').write_text(json.dumps({'version': 2, 'runs': rows}))
    return {'OPENCLAW_STATE_DIR': str(tmp_path)}


def completed():
    return {'runId': 'child', 'endedAt': 123, 'outcome': {'status': 'ok'},
            'childSessionKey': 'agent:identity-judge:subagent:test',
            'frozenResultText': 'Verified visible identity.'}


def test_pending_child_is_waited_for(tmp_path, monkeypatch):
    env = registry(tmp_path, {'child': {'runId': 'child'}})
    sleeps = []
    def finish(seconds):
        sleeps.append(seconds)
        registry(tmp_path, {'child': completed()})
    monkeypatch.setattr(runner.time, 'sleep', finish)
    result = runner._wait_for_subagent_evidence(env, time.time() + 10, tmp_path / 'log')
    assert sleeps
    assert result['child']['frozenResultText']


@pytest.mark.parametrize('rows', [{}, {'child': {'endedAt': 123, 'outcome': {'status': 'ok'}}}])
def test_missing_evidence_never_passes(tmp_path, rows):
    env = registry(tmp_path, rows)
    with pytest.raises(runner.SubagentCompletionError):
        runner._wait_for_subagent_evidence(env, time.time() + .01, tmp_path / 'log')


def test_failed_child_rejected(tmp_path):
    row = completed()
    row['outcome']['status'] = 'error'
    env = registry(tmp_path, {'child': row})
    with pytest.raises(runner.SubagentCompletionError, match='failed'):
        runner._wait_for_subagent_evidence(env, time.time() + 10, tmp_path / 'log')


def test_empty_frozen_result_fails_even_if_runtime_reports_ok(tmp_path):
    row = completed()
    row.update(frozenResultText=None, frozenResultCapturedAt=456)
    env = registry(tmp_path, {'child': row})
    with pytest.raises(runner.SubagentCompletionError, match='failed'):
        runner._wait_for_subagent_evidence(env, time.time() + 10, tmp_path / 'log')


def test_cli_json_without_newline_does_not_hang(tmp_path):
    response = {'payloads': [{'text': '等待'}], 'meta': {'agentMeta': {'sessionId': 'parent'}}}
    code = 'import sys,time;sys.stdout.write(' + repr(json.dumps(response)) + ');sys.stdout.flush();time.sleep(30)'
    started = time.time()
    result = runner._run_streaming_process(
        [sys.executable, '-c', code], tmp_path, None, 5, tmp_path / 'log',
        stop_on_response=True)
    assert result.returncode == 0
    assert time.time() - started < 5
    assert json.loads(result.stdout) == response


def test_cli_remains_alive_to_record_child_completion(tmp_path):
    env = registry(tmp_path, {'child': {'runId': 'child'}})
    response = {'payloads': [{'text': 'early answer'}], 'meta': {'agentMeta': {'sessionId': 'parent'}}}
    registry_path = str(tmp_path / 'subagents/runs.json')
    code = ('import sys,time,pathlib;sys.stdout.write(' + repr(json.dumps(response))
            + ');sys.stdout.flush();time.sleep(.2);pathlib.Path(' + repr(registry_path)
            + ').write_text(' + repr(json.dumps({'runs': {'child': completed()}}))
            + ');time.sleep(30)')
    result = runner._run_streaming_process(
        [sys.executable, '-c', code], tmp_path, env, 5, tmp_path / 'log',
        stop_on_response=True, wait_for_subagents=True)
    assert result.returncode == 0
    assert runner._subagent_registry_settled(env)


def test_valid_early_answer_requires_fresh_parent_turn(tmp_path, monkeypatch):
    env = registry(tmp_path, {'child': completed()})
    monkeypatch.setattr(runner, '_openclaw_response_session_id', lambda _: 'parent')
    calls = []
    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(
            {'payloads': [{'text': 'fresh answer'}],
             'meta': {'finalPromptText': 'stale valid answer'}}), stderr='')
    monkeypatch.setattr(runner, '_run_streaming_process', run)
    result = runner._run_openclaw_subagent_followup_if_needed(
        proc=subprocess.CompletedProcess([], 0, stdout='stale valid answer'),
        parsed=runner.parse_agent_answer('<answer>{"answer":"correct"}</answer>', ['correct']),
        task={'options': ['correct']}, node_bin='node', env=env,
        log_path=tmp_path / 'log', timeout_s=30, start=time.time())
    assert result.stdout == 'fresh answer'
    assert len(calls) == 1
    assert calls[0][1]['answer_options'] is None
    assert 'Verified visible identity.' in calls[0][0][-3] or any(
        'Verified visible identity.' in arg for arg in calls[0][0])


def test_child_answer_in_prompt_is_not_a_parent_answer(tmp_path, monkeypatch):
    env = registry(tmp_path, {'child': completed()})
    monkeypatch.setattr(runner, '_openclaw_response_session_id', lambda _: 'parent')
    monkeypatch.setattr(runner, '_run_streaming_process', lambda *a, **kw:
        subprocess.CompletedProcess([], 0, stdout=json.dumps({
            'payloads': [], 'meta': {'finalPromptText': '<answer>{"answer":"correct"}</answer>'}})))
    with pytest.raises(runner.SubagentCompletionError, match='missing_fresh_parent'):
        runner._run_openclaw_subagent_followup_if_needed(
            proc=subprocess.CompletedProcess([], 0, stdout='early answer'), parsed=None,
            task={'options': ['correct']}, node_bin='node', env=env,
            log_path=tmp_path / 'log', timeout_s=30, start=time.time())
