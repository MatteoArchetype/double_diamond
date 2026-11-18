"""Synthetic criterion-to-research agenda example. No external work is performed."""
import argparse
import json
import tempfile
from pathlib import Path
from .criteria_demo import run_demo as run_criteria_example
from .persistent_ingestion import PersistentEvidenceStore
from .research_agenda import inspect_agenda,export_agenda
from .reporting import report_is_current
from .checkpoints import create_checkpoint,restore_checkpoint


def _run(folder):
    run_criteria_example(folder)
    store=PersistentEvidenceStore(folder/'research.sqlite');before,revision=store.load();report=before.outputs['after-iteration']
    items=[dict(item_id='context-observation',criterion_index=0,evidence_gap='Only synthetic context evidence exists',question='Does an independently reviewed contextual observation support this explanation?',method='desk_review',target_phase='discover',priority='high',priority_rationale='Ground the explanation before testing transfer',success_signal='A reviewed non-synthetic observation addresses the explanation in its context',effort='small',depends_on=[]),
           dict(item_id='transfer-test',criterion_index=1,evidence_gap='No transfer observation or test exists',question='Does the explanation hold in a second context?',method='experiment',target_phase='develop',priority='high',priority_rationale='The transfer criterion cannot be judged from one context',success_signal='A separately authorized bounded test provides evidence about transfer',effort='medium',depends_on=['context-observation'])]
    store.apply_workflow(dict(type='plan_research',agenda_id='follow-up-agenda',report_id='after-iteration',report_digest=report['content_digest'],items=items),
        operation_id='fixture-agenda',actor='fixture-planner',rationale='Synthetic proposed planning only',expected_state_revision=revision,authorize=lambda actor,permission:actor=='fixture-planner' and permission=='workflow_write')
    state,_=store.load();agenda=inspect_agenda(state,'follow-up-agenda')
    export_agenda(folder/'research.sqlite','follow-up-agenda',folder/'research-agenda.md')
    export_agenda(folder/'research.sqlite','follow-up-agenda',folder/'research-agenda.json',format='json')
    create_checkpoint(store,folder/'agenda-checkpoint.zip');restore_checkpoint(folder/'agenda-checkpoint.zip',folder/'agenda-restored.sqlite')
    checks=dict(all_gaps_planned={i['criterion_index'] for i in agenda['items']}=={0,1},
        dependency_order_preserved=agenda['proposed_order']==['context-observation','transfer-test'],
        proposal_current=agenda['current'] and agenda['status']=='proposed',
        no_execution_authorized=not agenda['execution_authorized'] and all(not i['execution_authorized'] for i in agenda['items']),
        experiment_requires_human_gate=agenda['items'][1]['required_gate_types']==['primary_research'],
        synthetic_and_missing_evidence_distinct=[i['evidence_origin'] for i in agenda['items']]==['synthetic_only','none'],
        basis_report_unchanged=report_is_current(state,'after-iteration') and state.outputs==before.outputs,
        existing_gates_unchanged=state.human_gates==before.human_gates,
        checkpoint_preserves_agenda=PersistentEvidenceStore(folder/'agenda-restored.sqlite').load()[0].snapshot()==state.snapshot())
    if not all(checks.values()):raise RuntimeError('agenda fixture invariant failed')
    result=dict(fixture_only=True,live_sources_used=False,identity='simulated fixture callback',mvp_ready=False,checks=checks,
                limitations=['No actual participant contact, external retrieval, experiment or human approval was performed.'])
    (folder/'agenda-demo-report.json').write_text(json.dumps(result,indent=2)+'\n');return result


def run_demo(destination=None):
    if destination is None:
        with tempfile.TemporaryDirectory(prefix='dd-agenda-example-') as temp:
            folder=Path(temp)/'case';return _run(folder)
    return _run(Path(destination).absolute())


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--keep');args=parser.parse_args(argv)
    print(json.dumps(run_demo(args.keep),indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
