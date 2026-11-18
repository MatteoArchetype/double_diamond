import copy
import json
from pathlib import Path
import pytest
from dd_research_runtime.public_case import read_packet,prepare_public_case
from dd_research_runtime.persistent_ingestion import PersistentEvidenceStore,_encode,_checksum
from dd_research_runtime.pending_retrieval import PendingRetrievalQueue


def test_real_public_source_candidates_are_unapproved(tmp_path):
    packet=read_packet();status=prepare_public_case(tmp_path/'review')
    assert packet['independent_human_acquisition_confirmed'] is False
    assert len(packet['documents'])==2 and all(doc['synthetic'] is False for doc in packet['documents'])
    assert {doc['independence_cluster'] for doc in packet['documents']}=={'sqlite.org'}
    assert status['human_acceptance']=='pending' and status['mvp_ready'] is False
    assert status['state_revision']==status['ledger_revision']==status['approved_evidence_count']==0
    store=PersistentEvidenceStore(tmp_path/'review'/'research.sqlite')
    state,_=store.load()
    assert not state.evidence and not state.sources and not getattr(state,'acceptance_records',{})
    assert state.human_gates['publication']['status']=='pending_review'
    assert PendingRetrievalQueue(store).load('public-source-candidate').status=='pending'
    assert json.loads((tmp_path/'review'/'source-review-packet.json').read_text())==packet


def test_prepare_never_overwrites_user_directory(tmp_path):
    target=tmp_path/'existing';target.mkdir();(target/'sentinel').write_text('preserve')
    with pytest.raises(FileExistsError):prepare_public_case(target)
    assert [p.name for p in target.iterdir()]==['sentinel']
    link=tmp_path/'link';link.symlink_to(target)
    with pytest.raises(FileExistsError):prepare_public_case(link)


@pytest.mark.parametrize('change',['digest','approval','snapshot','synthetic'])
def test_packet_changes_require_integrity_and_cannot_bypass_review(tmp_path,change):
    packet=read_packet()
    if change=='digest':packet['question']='changed'
    elif change=='approval':packet['human_acceptance']='approved'
    elif change=='snapshot':packet['source_snapshots'][packet['documents'][0]['source_id']]['text']='different'
    else:packet['documents'][0]['synthetic']=True
    if change!='digest':packet['packet_digest']=_checksum(_encode({k:v for k,v in packet.items() if k!='packet_digest'}))
    path=tmp_path/'packet.json';path.write_text(json.dumps(packet))
    with pytest.raises((ValueError,TypeError)):read_packet(path)
