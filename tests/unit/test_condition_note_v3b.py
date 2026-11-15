from bixbench3.inspect_harness.condition_note import CONDITION, GENERIC_NOTE, TASK_NOTES, note_for


def test_v3b_note_selection_and_no_answer_content():
    assert CONDITION.startswith("v3b-")
    assert note_for("10.1016_j.crtox.2021.01.003_v1") == TASK_NOTES["10.1016_j.crtox.2021.01.003_v1"]
    assert note_for("some_other_task") == GENERIC_NOTE
    for text in [*TASK_NOTES.values(), GENERIC_NOTE]:
        assert text.startswith("## Experiment Note")
        lowered = text.lower()
        assert "ground truth" not in lowered and "reference output" not in lowered and "grade" not in lowered
