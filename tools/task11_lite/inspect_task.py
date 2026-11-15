"""Downstream task 11 with the upstream agent/tools and a short explicit budget."""
from inspect_ai import Task, task
from bixbench3.inspect_harness.scorers import output_collection
from bixbench3.inspect_harness.dataset import load_cases_dataset
from bixbench3.inspect_harness.solvers import bixbench3_agent, prepare_case_workspace

@task
def task11_lite(dataset_path: str, effort: str = 'xhigh') -> Task:
    return Task(dataset=load_cases_dataset(dataset_path, time_limit_seconds=600),
                setup=prepare_case_workspace(), solver=bixbench3_agent(),
                scorer=output_collection(), sandbox=('docker', '/opt/bixbench3/sandbox/compose.yaml'),
                message_limit=150, time_limit=600,
                metadata={'effort': effort, 'scope': 'task11-lite-downstream-v1',
                          'artifact_grading': 'host_after_inspect_exit'})
