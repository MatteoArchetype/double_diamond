"""Offline criterion-linked research decisions. Synthetic evidence and simulated approvals only."""
import argparse
import json
import tempfile
from pathlib import Path
from .runtime import ResearchState
from .persistent_ingestion import PersistentEvidenceStore
from .retrieval_validation import validate_retrieval_output
from .evidence_review import review_retrieval
from .double_diamond import transition_action,reframing_action,stage_currency
from .gate_transactions import binding
from .reporting import report_is_current,export_report
from .checkpoints import create_checkpoint,restore_checkpoint


def _run(folder):
    state=ResearchState(research_id='synthetic-double-diamond-learning-loop')
    state.create_gate('publication','publication','Publish','Human review required','Approve exact content')
    store=PersistentEvidenceStore(folder/'research.sqlite');store.initialize(state)
    def auth(actor,permission):return actor=='fixture-actor' and permission in {'evidence_ingest','analysis_write','workflow_write','gate_propose','gate_decide'}
    actor='fixture-actor'
    def options(oid):return dict(operation_id=oid,actor=actor,rationale='Synthetic fixture; simulated authorization, not actual human approval',expected_state_revision=store.load()[1],authorize=auth)
    def write(command,oid):return store.apply_workflow(command,**options(oid))
    def approve(action,gid):
        store.apply_gate(dict(type='propose',gate_id=gid,action=action),**options(gid+'-proposal'))
        store.apply_gate(dict(type='decide',gate_id=gid,decision='approve',proposal_digest=binding(action)),**options(gid+'-decision'))
    def move(target,kind='advance',reason='Synthetic fixture progression'):
        state,revision=store.load();gid='fixture-gate-'+str(revision)
        approve(transition_action(state,target,reason),gid)
        write(dict(type=kind,to_phase=target,reason=reason,gate_id=gid),'fixture-transition-'+str(revision))
    doc=dict(source_id='synthetic-example',title='Synthetic example',publisher='Fixture generator',url='https://example.invalid/dd-fixture',retrieved_at='2026-10-22',passage='SYNTHETIC EXAMPLE: one observation does not explain every context.',content_location='fixture line 1',provenance='synthetic',synthetic=True,independence_cluster='fixture-only')
    validation=validate_retrieval_output('retrieve',dict(status='completed',documents=[doc]));snapshots={'synthetic-example':dict(text=doc['passage'],location=doc['content_location'])}
    review=review_retrieval(validation,snapshots=snapshots,reviewer=actor,decision='approved',rationale='Simulated fixture review only')
    store.ingest(validation,review,operation_id='fixture-intake',expected_state_revision=0,expected_ledger_revision=0,authorize=auth,source_snapshots=snapshots)
    store.apply_analysis([dict(type='add_claim',record=dict(claim_id='C1',claim='SYNTHETIC EXAMPLE: interpretation remains provisional.',claim_type='descriptive',disposition='unresolved',status='draft',evidence_ids=['synthetic-example']))],**options('fixture-claim'))
    write(dict(type='start_criteria_research',workflow_id='DD-fixture',brief='Explore competing interpretations of the synthetic example',scope='Synthetic only; no real users, product delivery or experiment',questions=['Which explanation is supported?'],max_alternatives=2,max_visits=8),'fixture-start')
    discover=dict(evidence_ids=['synthetic-example'],notes='Explore evidence and missing perspectives',perspectives=['Fixture observation','Affected users: not studied'],limitations='No user engagement; one synthetic example')
    define=dict(problem='Explain the example',claim_ids=['C1'],uncertainty_ids=[],success_criteria=['Explain the observation within its context','Establish whether the explanation transfers'])
    develop=dict(alternatives=[dict(alternative_id='A'+str(i),hypothesis='Synthetic explanation '+str(i),test='Compare the explanation with the fixture observation',claim_ids=['C1'],evidence_ids=['synthetic-example'],limitations='Synthetic only') for i in range(2)])
    deliver=dict(selected_alternative_id='A0',evaluations=[dict(evaluation_id='E1',alternative_id='A0',method='Synthetic passage comparison; no experiment',evidence_ids=['synthetic-example'],outcome='inconclusive',limitations='Synthetic only')],decision='revise',summary='The comparison is inconclusive; return to framing',claim_ids=['C1'],limitations='No real-world conclusion')
    deliver['criterion_assessments']=[dict(criterion_index=0,outcome='unknown',evaluation_ids=['E1'],rationale='The synthetic comparison remains inconclusive',next_research='Acquire an independently reviewed contextual observation'),dict(criterion_index=1,outcome='unknown',evaluation_ids=[],rationale='No transfer evidence has been gathered',next_research='Test the explanation in a different context')]
    for phase,value,target in [('discover',discover,'define'),('define',define,'develop'),('develop',develop,'deliver')]:
        write(dict(type='record',phase=phase,record=value),'fixture-record-'+phase);move(target)
    write(dict(type='record',phase='deliver',record=deliver),'fixture-first-evaluation')
    first_visits=store.load()[0].workflow['visits']
    write(dict(type='finish',outcome='escalated',reason='Inconclusive evaluation requires a new framing'),'fixture-escalate')
    write(dict(type='report',report_id='before-iteration'),'fixture-first-report')
    move('define','reopen','Inconclusive evaluation requires a narrower problem frame')
    changed=dict(define,problem='Identify what remains unknown about the example')
    approve(reframing_action(store.load()[0],changed),'fixture-reframe')
    write(dict(type='record',phase='define',record=changed,gate_id='fixture-reframe'),'fixture-revised-define')
    move('develop');write(dict(type='record',phase='develop',record=develop),'fixture-revised-alternatives')
    move('deliver');final=dict(deliver,decision='stop_unresolved',summary='Stop with uncertainty; the synthetic material supports no real-world answer')
    write(dict(type='record',phase='deliver',record=final),'fixture-final-evaluation')
    write(dict(type='finish',outcome='stopped',reason='The bounded synthetic comparison is complete; uncertainty remains explicit'),'fixture-stop')
    write(dict(type='report',report_id='after-iteration'),'fixture-final-report')
    state,revision=store.load();checks=dict(
        four_named_phases=set(state.workflow['records'])=={'discover','define','develop','deliver'},
        iteration_preserves_original_records=state.workflow['visits'][:4]==first_visits,
        seven_bounded_visits=len(state.workflow['visits'])==7,
        reframing_approved=state.human_gates['fixture-reframe']['status']=='executed',
        selected_alternative_evaluated=bool(state.workflow['records']['deliver']['evaluations']),
        unresolved_outcome_explicit=state.workflow['records']['deliver']['decision']=='stop_unresolved',
        latest_stage_bindings_current=all(stage_currency(state).values()),
        older_report_stale=not report_is_current(state,'before-iteration'),
        final_report_current=report_is_current(state,'after-iteration'),
        synthetic_origin_preserved=state.outputs['after-iteration']['claims'][0]['evidence_origin']=='synthetic_only',
        publication_pending=state.human_gates['publication']['status']=='pending_review',
        host_acceptance_blocked=not store.acceptance_status('after-iteration')['structurally_ready'])
    trace=state.outputs['after-iteration']['decision_trace']
    checks['criteria_coverage']=len(trace['criteria'])==2
    checks['unmet_criteria_have_research_actions']=all(row['next_research'] for row in trace['criteria'] if row['outcome']!='met')
    checks['no_recommendation_with_unknown_criteria']=trace['all_criteria_met'] is False and trace['decision']=='stop_unresolved'
    export_report(folder/'research.sqlite','after-iteration',folder/'research-draft.md')
    create_checkpoint(store,folder/'checkpoint.zip');restore_checkpoint(folder/'checkpoint.zip',folder/'restored.sqlite')
    checks['checkpoint_preserves_iteration']=PersistentEvidenceStore(folder/'restored.sqlite').load()[0].snapshot()==state.snapshot()
    if not all(checks.values()):raise RuntimeError('Double Diamond fixture invariant failed')
    result=dict(fixture_only=True,live_sources_used=False,identity='simulated fixture callback',mvp_ready=False,checks=checks,state_revision=revision,phase_visits=7,
                limitations=['No real user research, prototype testing, product launch or actual human acceptance occurred.'])
    (folder/'demo-report.json').write_text(json.dumps(result,indent=2)+'\n');return result


def run_demo(destination=None):
    if destination is None:
        with tempfile.TemporaryDirectory(prefix='dd-learning-loop-') as folder:return _run(Path(folder))
    folder=Path(destination).absolute();folder.mkdir(mode=0o700,exist_ok=False);return _run(folder)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--keep');args=parser.parse_args(argv)
    print(json.dumps(run_demo(args.keep),indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
