import pytest

from dd_research.research_controller import run_bounded_research_controller


class Dummy:
    pass


def test_records_one_decision_without_executing_action():
    calls = []
    def step(state, cycle, **context):
        calls.append(context)
        return {"highest_value_action": "retrieve"}
    result = run_bounded_research_controller(
        Dummy(), Dummy(), step_fn=step,
        step_context={"question": "What evidence is missing?"},
        max_steps=5,
    )
    assert result.status == "decision_recorded"
    assert len(result.steps) == 1
    assert result.steps[0]["step_index"] == 1
    assert len(calls) == 1


def test_human_gate_pauses_controller():
    result = run_bounded_research_controller(
        Dummy(), Dummy(),
        step_fn=lambda *a, **k: {
            "highest_value_action": "request_human_input",
            "gate_reason": "Scope approval is required.",
        },
        step_context={}, max_steps=3,
    )
    assert result.status == "paused_for_human"
    assert "approval" in result.reason.lower()


def test_stop_action_stops_controller():
    result = run_bounded_research_controller(
        Dummy(), Dummy(),
        step_fn=lambda *a, **k: {"highest_value_action": "stop"},
        step_context={}, max_steps=2,
    )
    assert result.status == "stopped"


@pytest.mark.parametrize("budget", [0, -1, True, 1.5, "3"])
def test_invalid_budget_is_rejected(budget):
    with pytest.raises(ValueError, match="max_steps"):
        run_bounded_research_controller(
            Dummy(), Dummy(), step_fn=lambda *a, **k: {},
            step_context={}, max_steps=budget,
        )


def test_non_dictionary_action_is_rejected():
    with pytest.raises(TypeError, match="dictionary"):
        run_bounded_research_controller(
            Dummy(), Dummy(), step_fn=lambda *a, **k: "retrieve",
            step_context={}, max_steps=1,
        )
