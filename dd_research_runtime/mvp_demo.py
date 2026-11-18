"""Offline fixture vertical slice and explicit MVP gap report; never a real study.

The fixture reviewer callback is a demonstration stub, not authenticated identity.
No network access or actual research publication is performed.
"""
import argparse
import json
import tempfile
import sys
from pathlib import Path

from .runtime import ResearchState, GateRequired
from assessment import DIMENSIONS
from .analysis_transactions import assessment_is_current
from .cycle import ResearchCycle
from .persistent_ingestion import PersistentEvidenceStore
from .persistent_controller import run_persistent_controller_step
from .pending_retrieval import PendingRetrievalQueue
from .checkpoints import create_checkpoint, restore_checkpoint


FIXTURE_ID='synthetic-fixture-1'
FIXTURE_PASSAGE='SYNTHETIC FIXTURE: Example participants chose option A.'


def _fixture_authorize(reviewer,permission):
    return reviewer == 'fixture-reviewer' and permission == 'evidence_ingest'


def _fixture_analysis_authorize(actor,permission):
    return actor == 'fixture-analyst' and permission == 'analysis_write'


def _run(directory):
    state=ResearchState(research_id='offline-fixture-only')
    state.create_gate('publication','publication','Publish fixture example','Explicit human review required','Approve publication')
    store=PersistentEvidenceStore(directory/'fixture.sqlite');store.initialize(state)
    doc=dict(source_id=FIXTURE_ID,title='Synthetic workflow fixture',publisher='Fixture generator',
             url='https://example.invalid/synthetic-fixture',retrieved_at='2026-10-21',
             passage=FIXTURE_PASSAGE,content_location='fixture line 2',provenance='synthetic',
             synthetic=True,independence_cluster='fixture-only',metadata=dict(fixture=True))
    cycle=ResearchCycle('fixture-cycle','Demonstrate reviewed evidence persistence')
    candidate=run_persistent_controller_step(store,cycle,
        step_fn=lambda state,cycle,**context:dict(highest_value_action='retrieve'),step_context={},
        executors={'retrieve':lambda **context:dict(status='completed',documents=[doc],summary='Synthetic fixture only')})
    queue=PendingRetrievalQueue(store);queue.save('fixture-candidate',candidate)
    checks=dict(review_before_ingest=not store.load()[0].evidence and store.ledger.revision() == 0)
    # Reopen the saved handoff; a real reviewer would supply independently acquired snapshots.
    reopened=PersistentEvidenceStore(directory/'fixture.sqlite');queue=PendingRetrievalQueue(reopened)
    checks['review_handoff_reopens']=queue.load('fixture-candidate').status == 'pending'
    snapshots={FIXTURE_ID:dict(text='SYNTHETIC FIXTURE DOCUMENT\n'+FIXTURE_PASSAGE+'\nEND FIXTURE',location='fixture line 2')}
    review=queue.review('fixture-candidate',snapshots=snapshots,reviewer='fixture-reviewer',decision='approved',rationale='Fixture-only simulated reviewer; not real research approval')
    try:
        queue.commit('fixture-candidate',review,source_snapshots=snapshots)
        checks['host_authorization_callback_required']=False
    except PermissionError:
        checks['host_authorization_callback_required']=not reopened.load()[0].evidence
    result=queue.commit('fixture-candidate',review,authorize=_fixture_authorize,source_snapshots=snapshots)
    checks['retry_is_idempotent']=queue.commit('fixture-candidate',review,authorize=_fixture_authorize,source_snapshots=snapshots) == result and reopened.ledger.revision() == 1
    analysis_commands=[
        dict(type='add_claim',record=dict(claim_id='fixture-claim',claim='SYNTHETIC FIXTURE: the bounded example records option A.',claim_type='descriptive',disposition='draft',status='draft',evidence_ids=[FIXTURE_ID])),
        dict(type='add_claim',record=dict(claim_id='fixture-alternative',claim='SYNTHETIC FIXTURE: alternative interpretations remain untested.',claim_type='descriptive',disposition='unresolved',status='draft',evidence_ids=[FIXTURE_ID])),
        dict(type='assess_evidence',assessment_id='fixture-assessment',evidence_id=FIXTURE_ID,claim_id='fixture-claim',dimensions={d:'unknown' for d in DIMENSIONS},limitations=['Synthetic fixture only; no real study'],rationale='Advisory fixture assessment'),
        dict(type='put_uncertainty',record=dict(uncertainty_id='fixture-uncertainty',question='Would any result transfer beyond this synthetic example?',status='open')),
        dict(type='add_contradiction',record=dict(contradiction_id='fixture-contradiction',claim_a='fixture-claim',claim_b='fixture-alternative',issue='Synthetic interpretations require further comparison',disposition='unresolved')),
        dict(type='update_claim',claim_id='fixture-claim',patch=dict(confidence='unknown')),
        dict(type='set_disposition',disposition_id='fixture-disposition',claim_id='fixture-claim',disposition='qualify',rationale='Retain only as a synthetic demonstration',evidence_ids=[FIXTURE_ID],prior_status='draft',new_status='qualified',material_uncertainties=['fixture-uncertainty'],decision_relevance='Fixture only')]
    analysis_commands.append(analysis_commands.pop(2)) # Assess the final qualified claim version.
    reopened.apply_analysis(analysis_commands,operation_id='fixture-analysis',actor='fixture-analyst',rationale='Advisory fixture analysis, not research approval',expected_state_revision=1,authorize=_fixture_analysis_authorize)
    analyzed,analysis_revision=reopened.load()
    checks['analysis_changes_persist']=(analysis_revision == 2 and analyzed.claims['fixture-claim']['status'] == 'qualified' and 'fixture-assessment' in analyzed.assessments and 'fixture-contradiction' in analyzed.contradictions and 'fixture-uncertainty' in analyzed.uncertainties and 'fixture-disposition' in analyzed.claim_dispositions)
    checks['analysis_remains_advisory']=(analyzed.claims['fixture-claim']['analysis_status'] == 'advisory' and analyzed.claims['fixture-claim']['evidence_origin'] == 'synthetic_only' and analyzed.assessments['fixture-assessment']['status'] == analyzed.claim_dispositions['fixture-disposition']['status'] == 'advisory')
    checks['analysis_assessment_is_current']=assessment_is_current(analyzed,'fixture-assessment')
    checks['analysis_audit_reopens']=(PersistentEvidenceStore(directory/'fixture.sqlite').load_analysis_operation('fixture-analysis')['request']['actor'] == 'fixture-analyst' and reopened.mutation_coverage()['analysis_mutations'] == 1)
    from .gate_transactions import binding
    fixture_action=dict(type='gated_action',action='phase_transition',payload=dict(from_phase='fixture',to_phase='fixture-reviewed',fixture_only=True))
    gate_auth=lambda actor,permission:actor=='fixture-human' and permission in {'gate_propose','gate_decide','gate_execute'}
    def gate_write(command,oid,revision,authorize=gate_auth):
        return reopened.apply_gate(command,operation_id=oid,actor='fixture-human',rationale='Simulated fixture decision only',expected_state_revision=revision,authorize=authorize)
    proposal=dict(type='propose',gate_id='fixture-transition',action=fixture_action)
    try:
        gate_write(proposal,'fixture-proposal',2,authorize=None)
        checks['gate_authorization_required']=False
    except PermissionError:checks['gate_authorization_required']=True
    gate_write(proposal,'fixture-proposal',2)
    gate_write(dict(type='decide',gate_id='fixture-transition',decision='approve',proposal_digest=binding(fixture_action)),'fixture-decision',3)
    outcome=gate_write(dict(type='execute',gate_id='fixture-transition',action=fixture_action),'fixture-execution',4)
    checks['durable_gate_decision']=PersistentEvidenceStore(directory/'fixture.sqlite').load()[0].human_gates['fixture-transition']['decision_actor']=='fixture-human'
    checks['gate_retry_is_idempotent']=gate_write(dict(type='execute',gate_id='fixture-transition',action=fixture_action),'fixture-execution',4)==outcome
    from .workflow import transition_action
    from .reporting import export_report, report_is_current
    workflow_auth=lambda actor,permission:actor=='fixture-human' and permission in {'workflow_write','gate_propose','gate_decide'}
    def workflow_write(command):
        revision=reopened.load()[1]
        return reopened.apply_workflow(command,operation_id='fixture-workflow-'+str(revision),actor='fixture-human',rationale='Synthetic workflow demonstration',expected_state_revision=revision,authorize=workflow_auth)
    def workflow_advance(target):
        current,revision=reopened.load();gid='fixture-phase-'+target;action=transition_action(current,target)
        gate_write(dict(type='propose',gate_id=gid,action=action),gid+'-proposal',revision)
        gate_write(dict(type='decide',gate_id=gid,decision='approve',proposal_digest=binding(action)),gid+'-decision',revision+1)
        workflow_write(dict(type='advance',to_phase=target,gate_id=gid))
    def workflow_record(phase,record):workflow_write(dict(type='record',phase=phase,record=record))
    workflow_write(dict(type='start',workflow_id='fixture-workflow',brief='Compare synthetic interpretations within this demonstration.',scope='Synthetic fixture only; no real participants or findings.',questions=['What does the fixture passage record?', 'Which interpretation remains uncertain?'],max_alternatives=2))
    workflow_advance('discovery')
    workflow_record('discovery',dict(evidence_ids=[FIXTURE_ID],notes='Reviewed synthetic passage retained without source repair.'))
    workflow_advance('definition')
    workflow_record('definition',dict(problem='Interpret the bounded synthetic example without real-world generalisation.',claim_ids=['fixture-claim','fixture-alternative'],uncertainty_ids=['fixture-uncertainty']))
    workflow_advance('alternatives')
    workflow_record('alternatives',dict(alternatives=[dict(alternative_id='fixture-option-'+str(i),hypothesis=hypothesis,test='Compare against the synthetic passage; no experiment was run.',outcome='inconclusive',claim_ids=[cid],evidence_ids=[FIXTURE_ID],limitations='A synthetic fixture cannot validate either real-world interpretation.') for i,hypothesis,cid in [(1,'Option A could be context-specific.','fixture-claim'),(2,'Other explanations remain possible.','fixture-alternative')]]))
    workflow_advance('synthesis')
    workflow_record('synthesis',dict(summary='The synthetic passage demonstrates traceability; it establishes no real-world result.',claim_ids=['fixture-claim','fixture-alternative'],limitations='No real participants, independent sources or live tests.'))
    workflow_write(dict(type='finish',outcome='stopped',reason='The fixed fixture comparison is complete; transfer uncertainty remains open.'))
    workflow_write(dict(type='report',report_id='fixture-research-report'))
    report_state,_=reopened.load()
    checks['bounded_workflow_persists']=report_state.workflow['status']=='stopped' and len(report_state.workflow['history'])==4
    checks['workflow_human_pauses_preserved']=all(report_state.human_gates[h['gate_id']]['status']=='executed' for h in report_state.workflow['history'])
    saved_report=report_state.outputs['fixture-research-report']
    checks['traceable_draft_report']=saved_report['status']=='draft' and not saved_report['publication_authorized'] and saved_report['claims'][1]['evidence'][0]['evidence']['finding']==FIXTURE_PASSAGE
    checks['report_preserves_synthetic_and_uncertainty']=all(item['evidence_origin']=='synthetic_only' for item in saved_report['claims']) and saved_report['uncertainties']['fixture-uncertainty']['status']=='open'
    checks['saved_report_is_current']=report_is_current(report_state,'fixture-research-report')
    acceptance=reopened.acceptance_status('fixture-research-report')
    checks['synthetic_fixture_cannot_satisfy_host_acceptance']='real_source_evidence_required' in acceptance['blockers'] and not acceptance['host_accepted']
    export_report(directory/'fixture.sqlite','fixture-research-report',directory/'research-draft.md')
    export_report(directory/'fixture.sqlite','fixture-research-report',directory/'research-draft.json',format='json')
    checks['retry_is_idempotent']=checks['retry_is_idempotent'] and queue.commit('fixture-candidate',review,authorize=_fixture_authorize,source_snapshots=snapshots) == result
    persisted,_=reopened.load()
    checks['synthetic_label_preserved']=persisted.evidence[FIXTURE_ID]['synthetic'] is True and FIXTURE_ID not in persisted.sources
    archived=reopened.load_review('pending/fixture-candidate')
    checks['review_and_snapshots_retained']=archived['review']['record_digest'] == review.record_digest and archived['source_snapshots'] == snapshots
    try:
        persisted.execute_gated('publication','publication')
        checks['unapproved_gate_blocks_publication']=False
    except GateRequired:
        checks['unapproved_gate_blocks_publication']=True
    type_probe=ResearchState()
    type_probe.create_gate('wrong-type','primary_research','Fixture','Check scope','Approve primary research')
    type_probe.approve_gate('wrong-type')
    try:
        type_probe.execute_gated('wrong-type','publication')
        checks['wrong_type_gate_blocks_publication']=False
    except GateRequired:
        checks['wrong_type_gate_blocks_publication']=True
    # Observations demonstrate scope of detached state; they are not durable analysis APIs.
    detached,_=reopened.load()
    detached.add_claim(dict(claim_id='detached-example',claim='Synthetic example only',claim_type='descriptive',disposition='unresolved',evidence_ids=[FIXTURE_ID]))
    detached.approve_gate('publication')
    after,_=reopened.load()
    observations=dict(detached_claim_is_not_persisted='detached-example' not in after.claims,
                      detached_gate_approval_is_not_persisted=after.human_gates['publication']['status'] == 'pending_review')
    checkpoint=create_checkpoint(reopened,directory/'fixture-checkpoint.zip')
    restore_checkpoint(directory/'fixture-checkpoint.zip',directory/'restored.sqlite')
    restored=PersistentEvidenceStore(directory/'restored.sqlite')
    checks['checkpoint_restores_state']=restored.load()[0].snapshot() == after.snapshot() and restored.load_source_snapshots('pending/fixture-candidate') == snapshots
    from .dd_demo import run_demo as run_double_diamond_fixture
    learning_loop=run_double_diamond_fixture()
    checks['double_diamond_iteration_fixture']=all(learning_loop['checks'].values())
    checks['double_diamond_deliver_evaluation']=learning_loop['checks']['selected_alternative_evaluated']
    from .criteria_demo import run_demo as run_criteria_fixture
    criteria_fixture=run_criteria_fixture()
    checks['criteria_linked_research_decision']=all(criteria_fixture['checks'].values())
    checks['unmet_criteria_have_next_research']=criteria_fixture['checks']['unmet_criteria_have_research_actions']
    if not all(checks.values()):
        raise RuntimeError('fixture invariants failed: '+', '.join(k for k,v in checks.items() if not v))
    checks['all_fixture_invariants']=True
    contract=json.loads((Path(__file__).resolve().parents[1]/'MVP_ACCEPTANCE.json').read_text())
    criteria=[]
    for criterion in contract['criteria']:
        item=dict(criterion)
        if criterion['status'] == 'fixture_verified' and not all(checks.get(name,False) for name in criterion['fixture_checks']):
            item['status']='fixture_failed'
        criteria.append(item)
    report=dict(fixture_only=True,live_sources_used=False,reviewer_identity='simulated fixture callback',analysis_actor_identity='simulated fixture callback',
                checks=checks,observations=observations,mvp_ready=all(c['status'] in {'fixture_verified','host_accepted'} for c in criteria if c['required']),
                criteria=criteria,work_plan=contract['work_plan'],estimate=contract['estimate'],
                checkpoint_summary=checkpoint['summary'],research_report_digest=saved_report['content_digest'])
    (directory/'demo-report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def run_demo(output_directory=None):
    """Run in temporary storage by default, or explicitly create a new fixture directory."""
    if output_directory is None:
        with tempfile.TemporaryDirectory(prefix='dd-mvp-fixture-') as temp:
            return _run(Path(temp))
    directory=Path(output_directory).absolute()
    directory.mkdir(mode=0o700,parents=False,exist_ok=False)
    return _run(directory)


def main(argv=None):
    parser=argparse.ArgumentParser(description='Run an offline synthetic fixture and report current MVP gaps; this does not certify MVP completion.')
    parser.add_argument('--keep',metavar='NEW_DIRECTORY',help='Keep fixture files in a new directory; existing paths are never overwritten.')
    args=parser.parse_args(argv)
    try:
        report=run_demo(args.keep)
        print(json.dumps(report,indent=2))
        return 0
    except (OSError,ValueError,RuntimeError) as exc:
        print(json.dumps(dict(ok=False,error=str(exc))),file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
