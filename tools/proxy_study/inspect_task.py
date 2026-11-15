"""Use the selected committed harness; override resource limits only."""
from inspect_ai import task
from bixbench3.inspect_harness import tasks as selected

@task
def proxy_study(dataset_path: str, effort: str='xhigh', budget_seconds: int=600):
    selected.TIME_LIMIT_SECONDS = int(budget_seconds)
    selected.MESSAGE_LIMIT = 5000
    result = selected.bixbench3_cases(dataset_path=dataset_path, effort=effort)
    result.time_limit = int(budget_seconds)
    result.message_limit = 5000
    result.metadata = {**(result.metadata or {}), 'proxy_study':'task11-prospective-v2'}
    return result
