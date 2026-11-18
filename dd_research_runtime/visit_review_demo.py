"""Offline original-context inspection example; all evidence and reviews are fixtures."""
import json
import tempfile
from pathlib import Path
from hashlib import sha256
from .agenda_demo import run_demo as agenda_demo
from .visit_review import read_visit


def run_demo():
    with tempfile.TemporaryDirectory(prefix='dd-visit-review-') as temp:
        case=Path(temp)/'case';agenda_demo(case);database=case/'research.sqlite'
        before=sha256(database.read_bytes()).hexdigest()
        earlier=read_visit(database,'V2');later=read_visit(database,'V5');delivery=read_visit(database,'V7')
        checks=dict(original_context_verified=all(v['context_status']=='verified_original' for v in (earlier,later,delivery)),
            original_frame_preserved=earlier['visit']['record']['problem']=='Explain the example',
            revised_frame_inspectable=later['visit']['record']['problem']=='Identify what remains unknown about the example',
            exact_comparison=later['changed_fields']==['problem'] and later['previous_record']==earlier['visit']['record'],
            old_visit_not_current=not earlier['is_current_record'] and later['is_current_record'],
            synthetic_passage_retained=all(e['synthetic'] for e in earlier['context']['evidence'].values()),
            criterion_context_from_original_snapshot=delivery['context']['defined_problem']==later['visit']['record'],
            original_evaluation_visible=bool(delivery['visit']['record']['evaluations']),
            read_only_bytes_preserved=sha256(database.read_bytes()).hexdigest()==before)
        if not all(checks.values()):raise RuntimeError('visit review fixture invariant failed')
        return dict(fixture_only=True,live_sources_used=False,mvp_ready=False,checks=checks,
            limitations=['All evidence and approvals are synthetic/simulated. Inspection is not an approval or independent identity/source verification.'])


def main():print(json.dumps(run_demo(),indent=2))


if __name__=='__main__':main()
