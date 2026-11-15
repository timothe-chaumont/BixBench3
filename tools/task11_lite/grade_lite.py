"""Grade only the four downstream artifacts; supplied counts never earn a score."""
import json
import tempfile
from pathlib import Path
from bixbench3.gcp_runner import download_manifest_package
from bixbench3.grading import grade_paper

EXCLUDED = 'tempo_seq_filtered_counts'

def grade_existing_artifacts(*, task, artifacts_dir, grades_dir=None, ground_truth_parent=None):
    if ground_truth_parent:
        Path(ground_truth_parent).mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix='lite-grader-', dir=ground_truth_parent) as tmp:
        root = Path(tmp)
        download_manifest_package(task.grader_manifest_url, root,
                                  expected_manifest_sha256=task.grader_manifest_sha256)
        spec = json.loads(next(root.rglob('artifacts_grading.json')).read_text())
        spec['artifacts'] = [a for a in spec['artifacts'] if a['artifact_id'] != EXCLUDED]
        spec['artifact_count'] = len(spec['artifacts'])
        assert spec['artifact_count'] == 4
        result = grade_paper(spec, agent_artifacts_dir=Path(artifacts_dir),
                            ground_truth_root=root, artifact_grades_dir=grades_dir)
        return result
