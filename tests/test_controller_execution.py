import pytest
from dd_research_runtime.controller_execution import run_controller_execution_step

class State:
    def __init__(self): self.change_log=[]; self.evidence={}
    def _change(self, operation, ids, detail=''):
        self.change_log.append((operation, ids, detail))
class Cycle:
    def __init__(self): self.events=[]
    def record(self, step, status, reason): self.events.append((step,status,reason))

def step(action, **kw):
    return lambda state, cycle, **context: {'highest_value_action':action, **kw}

def run(action, executors=None, **kw):
    state,cycle=State(),Cycle()
    result=run_controller_execution_step(state,cycle,step_fn=step(action,**kw),
        step_context={},executors=executors or {})
    return state,cycle,result

def test_completed_execution_does_not_create_evidence():
    state,cycle,result=run('retrieve', {'retrieve':lambda **kw:{'status':'completed','summary':'candidate','evidence_ids':['x']}})
    assert result.status=='completed'
    assert result.controller.steps[0]['step_index']==1
    assert result.execution.events[0]['state_updated'] is False
    assert state.evidence=={}
    assert state.change_log[-1][0]=='action_execution'

def test_human_gate_blocks_execution():
    called=[]
    state,cycle,result=run('retrieve', {'retrieve':lambda **kw:called.append(True)},gate_required=True,gate_reason='Approval')
    assert result.status=='paused_for_human' and result.execution is None
    assert not called and not state.change_log

def test_stop_is_not_executed():
    called=[]
    _,_,result=run('stop',{'stop':lambda **kw:called.append(True)})
    assert result.status=='stopped' and result.execution is None and not called

def test_failure_is_not_reported_as_completion():
    _,_,result=run('audit',{'audit':lambda **kw:{'status':'failed','summary':'no valid source'}})
    assert result.status=='failed' and result.execution.status=='failed'

def test_review_request_pauses():
    _,_,result=run('compare',{'compare':lambda **kw:{'status':'needs_human_review','summary':'conflict'}})
    assert result.status=='paused_for_human'

def test_missing_executor_rejected():
    with pytest.raises(ValueError,match='no executor'):
        run('retrieve')

def test_unapproved_action_rejected():
    with pytest.raises(ValueError,match='not executable'):
        run('publish')

def test_executor_receives_only_explicit_context():
    captured=[]
    state,cycle=State(),Cycle()
    result=run_controller_execution_step(state,cycle,step_fn=step('test'),step_context={},
        executors={'test':lambda **kw:captured.append(kw) or {'status':'no_result'}},
        execution_context={'fixture':'synthetic'})
    assert result.status=='no_result'
    assert captured[0]['context']=={'fixture':'synthetic'}
