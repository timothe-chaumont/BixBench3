"""Lite must never score its supplied upstream answer or expose downstream answers."""
import importlib.util
import json
from pathlib import Path
import shutil
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'tools/task11_lite'/f'{name}.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_lite_prompt_and_contract_omit_counting_but_keep_downstream_outputs(tmp_path):
    runner = module('run_lite')
    dataset = tmp_path/'dataset'
    dataset.mkdir()
    ids = ['tempo_seq_filtered_counts', 'de', 'gsea', 'hypergeometric', 'dna']
    case = {'task_id': 'paper', 'prompt': {'prompt_path': 'prompt.md'},
            'expected_outputs': [{'artifact_id': x, 'path': f'outputs/{x}.csv'} for x in ids]}
    (dataset/'case.json').write_text(json.dumps(case))
    prompt = '# Task\n## Runtime Limit\n{time_limit}\n## Research Objective\nbiology\n## Method Guidance\nDESeq2 1.28.1\n## Required Outputs\n'
    prompt += ''.join(f'\n### `{x}`\n- Path: outputs/{x}.csv\n' for x in ids)
    (tmp_path/'original-prompt.md').write_text(prompt)
    staged = runner.make_dataset(tmp_path, None)
    updated = json.loads(staged.dataset_path.read_text())
    assert [x['artifact_id'] for x in updated['expected_outputs']] == ids[1:]
    text = (dataset/'prompt.md').read_text()
    assert '### `tempo_seq_filtered_counts`' not in text
    assert all(f'### `{x}`' in text for x in ids[1:])
    assert 'data/provided/counts.csv' in text
    assert 'not the full-task score' in text


@pytest.mark.parametrize('present, expected', [(4, 1.0), (2, 0.5)])
def test_real_grader_uses_four_downstream_artifacts_without_credit_for_supplied_counts(tmp_path, present, expected):
    grader = module('grade_lite')
    truth = tmp_path/'truth'
    (truth/'artifacts').mkdir(parents=True)
    outputs = tmp_path/'outputs'
    outputs.mkdir()
    ids = ['tempo_seq_filtered_counts', 'de', 'gsea', 'hypergeometric', 'dna']
    spec = {'paper_id': 'paper', 'artifact_count': 5, 'artifacts': []}
    for i, name in enumerate(ids):
        (truth/'artifacts'/f'{name}.csv').write_text('id,value\na,1\nb,2\n')
        spec['artifacts'].append({'artifact_id': name,
            'ground_truth': {'path': f'artifacts/{name}.csv', 'format': 'csv'},
            'expected_output': {'path': f'outputs/{name}.csv', 'format': 'csv', 'row_key': 'id'},
            'grading_method': {'checks': [{'metric': 'f1', 'axis': 'rows'}], 'score_combination': 'product'}})
        if 0 < i <= present:
            shutil.copy2(truth/'artifacts'/f'{name}.csv', outputs/f'{name}.csv')
    (truth/'artifacts_grading.json').write_text(json.dumps(spec))
    def download(url, destination, **kwargs):
        shutil.copytree(truth, destination, dirs_exist_ok=True)
    from types import SimpleNamespace
    task = SimpleNamespace(grader_manifest_url='fixture', grader_manifest_sha256='fixture')
    with patch.object(grader, 'download_manifest_package', download):
        result = grader.grade_existing_artifacts(task=task, artifacts_dir=outputs, grades_dir=tmp_path/'grades')
    assert result['artifact_count'] == 4
    assert result['score'] == pytest.approx(expected)
    assert not (tmp_path/'grades/tempo_seq_filtered_counts.json').exists()
