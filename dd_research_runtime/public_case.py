"""Prepare an unapproved public-source candidate; never invent a human decision."""
import copy
import json
from pathlib import Path
from .persistent_ingestion import PersistentEvidenceStore,_encode,_checksum
from .retrieval_validation import validate_retrieval_output
from .source_snapshots import verify_source_snapshots
from .runtime import ResearchState
from .cycle import ResearchCycle
from .persistent_controller import run_persistent_controller_step
from .pending_retrieval import PendingRetrievalQueue


def read_packet(path=None):
    path=Path(path) if path is not None else Path(__file__).resolve().parents[1]/'PUBLIC_SOURCE_CASE.json'
    if path.stat().st_size>2*1024*1024:raise ValueError('public packet exceeds byte limit')
    packet=json.loads(path.read_text())
    if packet.get('packet_version')!=1 or packet.get('status')!='pending_human_source_review':raise ValueError('unapproved public case packet required')
    if _checksum(_encode({k:v for k,v in packet.items() if k!='packet_digest'}))!=packet.get('packet_digest'):raise ValueError('public packet digest mismatch')
    validation=validate_retrieval_output('retrieve',dict(status='completed',documents=packet['documents']))
    if validation.status!='ready_for_review' or any(doc.synthetic for doc in validation.documents):raise ValueError('real-source candidate documents required')
    # Validate snapshots structurally without creating a review or asserting independence.
    from .evidence_review import _digest
    documents=[d.to_evidence_payload() for d in validation.documents]
    snapshots=packet['source_snapshots']
    review=dict(snapshot_digests=[_digest(dict(source_id=d['source_id'],text=snapshots[d['source_id']]['text'],location=snapshots[d['source_id']]['location'])) for d in documents])
    verify_source_snapshots(documents,review,snapshots)
    if any(packet.get(key)!='pending' for key in ('human_source_review','human_transition_decisions','human_acceptance')) or packet.get('independent_human_acquisition_confirmed') is not False:
        raise ValueError('public packet must preserve human review requirements')
    return copy.deepcopy(packet)


def prepare_public_case(destination):
    packet=read_packet();destination=Path(destination).absolute()
    destination.mkdir(mode=0o700,exist_ok=False)
    state=ResearchState(research_id=packet['case_id'])
    state.create_gate('publication','publication','Any external publication','Explicit human approval required','Approve exact publication content')
    store=PersistentEvidenceStore(destination/'research.sqlite');store.initialize(state)
    candidate=run_persistent_controller_step(store,ResearchCycle('public-source-review',packet['question']),
        step_fn=lambda state,cycle,**context:dict(highest_value_action='retrieve'),step_context={},
        executors={'retrieve':lambda **context:dict(status='completed',documents=packet['documents'],summary='Public-source candidate; human review pending')})
    queue=PendingRetrievalQueue(store);queue.save('public-source-candidate',candidate)
    (destination/'source-review-packet.json').write_text(json.dumps(packet,indent=2)+'\n')
    (destination/'REVIEW.md').write_text((Path(__file__).resolve().parents[1]/'PUBLIC_SOURCE_REVIEW.md').read_text())
    status=dict(case_id=packet['case_id'],packet_digest=packet['packet_digest'],candidate_id='public-source-candidate',
        candidate_status=queue.load('public-source-candidate').status,state_revision=store.load()[1],ledger_revision=store.ledger.revision(),
        approved_evidence_count=len(store.load()[0].evidence),human_acceptance='pending',mvp_ready=False)
    (destination/'handoff-status.json').write_text(json.dumps(status,indent=2)+'\n')
    return status
