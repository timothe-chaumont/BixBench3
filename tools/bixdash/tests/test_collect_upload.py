import importlib.util
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def collect():
    path = Path(__file__).parents[1] / 'vm/collect.py'
    spec = importlib.util.spec_from_file_location('bixdash_collect', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _files(tmp_path):
    paths = []
    for name in ('meta.json', 'latest.json', 'history.jsonl'):
        (tmp_path / name).write_text('{}\n')
        paths.append(tmp_path / name)
    return paths


def test_upload_writes_each_object_by_exact_name_without_listing(collect, tmp_path):
    with patch.object(collect, '_access_token', return_value='tok'), \
            patch.object(collect.urllib.request, 'urlopen', return_value=MagicMock()) as urlopen:
        status = collect.gs_put_many(_files(tmp_path), 'gs://team-bucket/_dashboard/run-1/')
    assert status['ok'] and status['error'] is None
    urls = [call.args[0].full_url for call in urlopen.call_args_list]
    assert urls == [
        f'https://storage.googleapis.com/upload/storage/v1/b/team-bucket/o?uploadType=media&name=_dashboard%2Frun-1%2F{name}'
        for name in ('meta.json', 'latest.json', 'history.jsonl')
    ]
    assert all(call.args[0].get_method() == 'POST' for call in urlopen.call_args_list)
    assert urlopen.call_args_list[0].args[0].get_header('Authorization') == 'Bearer tok'


def test_upload_reports_refused_write(collect, tmp_path):
    refused = urllib.error.HTTPError('u', 403, 'Forbidden', {}, BytesIO(b'{"error": {"message": "no create access"}}'))
    with patch.object(collect, '_access_token', return_value='tok'), \
            patch.object(collect.urllib.request, 'urlopen', side_effect=refused):
        status = collect.gs_put_many(_files(tmp_path), 'gs://team-bucket/_dashboard/run-1/')
    assert not status['ok']
    assert status['error'] == 'HTTP 403: no create access'
