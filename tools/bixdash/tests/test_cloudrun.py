import importlib.util
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def server():
    path = Path(__file__).parents[1] / 'dashboard/server.py'
    spec = importlib.util.spec_from_file_location('bixdash_server', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cloudrun_listens_on_injected_port(server, tmp_path):
    with patch.dict('os.environ', {'K_SERVICE': 'bixdash', 'PORT': '8080', 'BIXDASH_TOKEN': 'test-token'}), patch('sys.argv', ['server.py', '--source', str(tmp_path)]), patch.object(server, 'ThreadingHTTPServer') as http:
        server.main()
    assert http.call_args.args[0] == ('0.0.0.0', 8080)
    http.return_value.serve_forever.assert_called_once()


def test_cloudrun_fails_closed_without_shared_token(server, tmp_path):
    with patch.dict('os.environ', {'K_SERVICE': 'bixdash', 'BIXDASH_TOKEN': ''}), patch('sys.argv', ['server.py', '--source', str(tmp_path)]):
        with pytest.raises(RuntimeError, match='BIXDASH_TOKEN is required'):
            server.main()


def test_shared_auth_rejects_missing_or_wrong_tokens(server, tmp_path):
    handler = server.make_handler(server.Source(str(tmp_path)), 'correct-token')
    request = object.__new__(handler)
    request.headers = {}
    assert not request._authorized({})
    assert not request._authorized({'token': ['wrong-token']})
    assert request._authorized({'token': ['correct-token']})
    request.headers = {'Cookie': 'bixdash=correct-token'}
    assert request._authorized({})


def test_public_mode_is_explicit_and_needs_no_token(server, tmp_path):
    with patch.dict('os.environ', {'K_SERVICE': 'bixdash', 'BIXDASH_PUBLIC': '1', 'BIXDASH_TOKEN': ''}), patch('sys.argv', ['server.py', '--source', str(tmp_path)]), patch.object(server, 'ThreadingHTTPServer') as http:
        server.main()
    handler = http.call_args.args[1]
    request = object.__new__(handler)
    request.headers = {}
    assert request._authorized({})


def test_comparison_pages_preserve_auth_and_serve_expected_content(server, tmp_path):
    import threading
    import urllib.request
    import urllib.error
    from http.server import ThreadingHTTPServer

    http = ThreadingHTTPServer(('127.0.0.1', 0), server.make_handler(server.Source(str(tmp_path)), 'test-token'))
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        root = f'http://127.0.0.1:{http.server_port}'
        for path, expected, content_type in [('/comparisons', b'Score vs API cost', 'text/html'), ('/comparisons.js', b'totalTokens', 'text/javascript')]:
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(root + path)
            assert error.value.code == 401
            with urllib.request.urlopen(root + path + '?token=test-token') as response:
                assert response.status == 200
                assert response.headers['Content-Type'].startswith(content_type)
                assert expected in response.read()
    finally:
        http.shutdown()
        http.server_close()
        thread.join(timeout=2)


def test_missing_final_budgets_use_labelled_history_without_changing_raw_data(server, tmp_path):
    import json
    folder = tmp_path / 'run'
    folder.mkdir()
    final = {'score_is_final': True, 'partial_score': .52, 'cost_usd': None,
             'n_model_calls': None, 'elapsed_s': 155}
    (folder / 'latest.json').write_text(json.dumps(final))
    records = [{'cost_usd': 1.9, 'n_model_calls': 188, 'tokens_total': 15000,
                'elapsed_s': 2881, 'ts': 'earlier'}, final]
    (folder / 'history.jsonl').write_text('\n'.join(json.dumps(x) for x in records))
    result = server.Source(str(tmp_path)).run('run')
    assert result['latest'] == final
    assert result['comparison_budget']['cost_usd'] == 1.9
    assert result['comparison_budget']['elapsed_s'] == 2881
    assert result['comparison_budget']['is_lower_bound'] is True


def test_exact_final_budgets_and_unscored_runs_are_not_replaced(server, tmp_path):
    source = server.Source(str(tmp_path))
    exact = {'score_is_final': True, 'cost_usd': 2, 'n_model_calls': 3,
             'tokens_total': 500}
    assert source.comparison_budget(exact, 'missing') is None
    assert source.comparison_budget({'score_is_final': False}, 'missing') is None
    assert source.comparison_budget({'score_is_final': True}, 'missing') is None


def test_final_inspect_usage_sidecar_takes_precedence_over_live_history(server, tmp_path):
    import json
    folder = tmp_path / 'run'
    folder.mkdir()
    exact = {'cost_usd': 3.4, 'n_model_calls': 363, 'tokens_total': 29000,
             'elapsed_s': 8620, 'source': 'final_inspect_eval'}
    (folder / 'final_usage.json').write_text(json.dumps(exact))
    result = server.Source(str(tmp_path)).comparison_budget({'score_is_final': True}, 'run')
    assert result['cost_usd'] == 3.4
    assert result['elapsed_s'] == 8620
    assert result['is_lower_bound'] is False
