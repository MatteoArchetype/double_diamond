import pytest
from dd_research_runtime.action_executor import execute_registered_action

class State:
    def __init__(self): self.change_log = []
    def _change(self, op, ids, detail=''): self.change_log.append({'operation':op,'ids':ids,'detail':detail})
class Cycle:
    def __init__(self): self.events = []
    def record(self, step, status, reason): self.events.append((step,status,reason))
def decision(action, gate=False, reason=None):
    return {'highest_value_action':action,'gate_required':gate,'gate_reason':reason}

def test_registered_executor_logs_result_without_evidence_conversion():
    state, cycle = State(), Cycle()
    result = execute_registered_action(state, cycle, decision('retrieve'),
        executors={'retrieve':lambda **kw:{'status':'completed','summary':'Retrieved candidate pages','evidence_ids':['unverified-id']}})
    assert result.status == 'completed'
    assert state.change_log[-1]['operation'] == 'action_execution'
    assert state.change_log[-1]['detail']['state_updated'] is False
    assert cycle.events[-1][0:2] == ('action_execution','completed')
    assert result.output['evidence_ids'] == ['unverified-id']
    assert not hasattr(state, 'evidence') or state.evidence == {}

def test_gate_blocks_executor_and_logging():
    called=[]; state=State()
    result=execute_registered_action(state,Cycle(),decision('request_human_input',True,'Approval'),
        executors={'retrieve':lambda **kw:called.append(True)})
    assert result.status == 'paused_for_human' and not called and not state.change_log

def test_stop_is_control_only():
    called=[]
    result=execute_registered_action(State(),Cycle(),decision('stop'),executors={'stop':lambda **kw:called.append(True)})
    assert result.status == 'stopped' and not called

def test_missing_executor_rejected():
    with pytest.raises(ValueError,match='no executor'):
        execute_registered_action(State(),Cycle(),decision('retrieve'),executors={})

def test_output_must_have_status():
    with pytest.raises(TypeError,match='string status'):
        execute_registered_action(State(),Cycle(),decision('retrieve'),executors={'retrieve':lambda **kw:{'summary':'missing'}})

def test_status_must_be_supported():
    with pytest.raises(ValueError,match='unsupported executor status'):
        execute_registered_action(State(),Cycle(),decision('retrieve'),executors={'retrieve':lambda **kw:{'status':'magic'}})

def test_unknown_action_rejected():
    with pytest.raises(ValueError,match='not executable'):
        execute_registered_action(State(),Cycle(),decision('send_email'),executors={})

def test_human_review_result_pauses():
    result=execute_registered_action(State(),Cycle(),decision('retrieve'),executors={'retrieve':lambda **kw:{'status':'needs_human_review','summary':'Review result'}})
    assert result.status == 'paused_for_human'
