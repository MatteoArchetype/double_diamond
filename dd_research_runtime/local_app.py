"""Single-operator, loopback research interface. Optional public publication search."""
import argparse
import hmac
from datetime import datetime
import json
import mimetypes
import os
import tempfile
import secrets
import sqlite3
import threading
import uuid
import webbrowser
import shutil
import platform
import sys
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs,quote
from . import case_publish
from .persistent_ingestion import PersistentEvidenceStore,_encode
from .runtime import ResearchState,ResearchInvariantError
from .analysis_transactions import _keys,_text,_ids
from .double_diamond import PHASES,stage_currency,transition_action,reframing_action
from .gate_transactions import binding
from .research_agenda import inspect_agenda
from .source_search import search_publications
from .source_shortlist import SourceShortlist
from .source_draft import DefineDraft, DeliverDraft, DevelopDraft, DiscoverDraft, SourceDraft
from .document_library import DocumentLibrary
from .reporting import report_is_current,render_markdown

ACTOR='local-operator'
# Windows has no mime database, so guess_type falls back to octet-stream for files the
# app itself writes and serves. These names are fixed, so name them explicitly.
CONTENT_TYPES={'.css':'text/css; charset=utf-8','.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
               '.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.json':'application/json',
               '.md':'text/markdown; charset=utf-8','.pdf':'application/pdf','.png':'image/png','.svg':'image/svg+xml',
               '.txt':'text/plain; charset=utf-8','.zip':'application/zip'}
def content_type(name):
    """Serve a known file with its real type instead of asking the platform."""
    return CONTENT_TYPES.get(Path(name).suffix.lower()) or mimetypes.guess_type(name)[0] or 'application/octet-stream'
CAPABILITIES={'workflow_write','analysis_write','evidence_ingest','gate_propose','gate_decide'}
ASSETS=Path(__file__).parent/'webapp'
# Anchored to the application folder so cases do not seem to vanish when the app is launched from another directory.
DEFAULT_WORKSPACE=Path(__file__).resolve().parent.parent/'research-workspace'


def _authorize(actor,capability):return actor==ACTOR and capability in CAPABILITIES


def _id():return uuid.uuid4().hex


def _advisory_revision_allowed(claim):
    return (claim.get('analysis_status')=='advisory'
            and claim.get('status') in {'draft','unresolved','unknown','hypothesis'}
            and claim.get('disposition') in {'draft','unresolved','unknown','hypothesis'})


class Workspace:
    def __init__(self,path):
        self.path=Path(path).absolute();self.path.mkdir(mode=0o700,parents=True,exist_ok=True)
        if self.path.is_symlink():raise ValueError('workspace must not be a symbolic link')

    def diagnostics(self):
        """Return a bounded, operator-safe workspace health summary."""
        catalog=self.catalog()
        trash=self.trash_catalog()
        usable=False
        probe=None
        try:
            with tempfile.NamedTemporaryFile(prefix='.diagnostic-',dir=self.path,delete=False) as handle:
                probe=Path(handle.name)
                handle.write(b'')
                handle.flush()
                os.fsync(handle.fileno())
            probe.unlink()
            usable=True
        except (OSError,PermissionError):
            if probe is not None:
                try:probe.unlink()
                except OSError:pass
        total_bytes=0
        for folder in self.path.rglob('*'):
            try:
                if folder.is_symlink():continue
                if folder.is_file():total_bytes+=folder.stat().st_size
            except OSError:
                pass
        try:
            disk=shutil.disk_usage(self.path)
            disk_status=dict(total_bytes=disk.total,free_bytes=disk.free)
        except OSError:
            disk_status=dict(total_bytes=None,free_bytes=None)
        return dict(
            status='degraded' if not usable or catalog['unavailable_cases'] else 'healthy',
            workspace=dict(writable=usable,total_bytes=total_bytes),
            cases=dict(saved=len(catalog['cases']),unavailable=len(catalog['unavailable_cases']),
                       trashed=len(trash)),
            disk=disk_status,
            runtime=dict(platform=platform.platform(),python=sys.version.split()[0],
                         implementation=platform.python_implementation()),
        )

    def case_path(self,cid):
        if not isinstance(cid,str) or len(cid)!=32 or any(c not in '0123456789abcdef' for c in cid):raise ValueError('invalid case identifier')
        folder=self.path/cid
        if folder.is_symlink() or not folder.is_dir() or (folder/'research.sqlite').is_symlink() or not (folder/'research.sqlite').is_file():raise ValueError('unknown case')
        return folder

    def store(self,cid):return PersistentEvidenceStore(self.case_path(cid)/'research.sqlite')

    def shortlist(self,cid):
        return SourceShortlist(self.case_path(cid)/'source-shortlist.sqlite')

    def source_draft(self,cid):
        return SourceDraft(self.case_path(cid)/'source-draft.sqlite')

    def discover_draft(self,cid,visit):
        return self._visit_draft(cid,visit,'discover',DiscoverDraft)

    def define_draft(self,cid,visit):
        return self._visit_draft(cid,visit,'define',DefineDraft)

    def later_phase_draft(self,cid,visit,phase):
        draft_types={'develop':DevelopDraft,'deliver':DeliverDraft}
        if not isinstance(phase,str) or phase not in draft_types:
            raise ValueError('Choose Develop or Deliver.')
        return self._visit_draft(cid,visit,phase,draft_types[phase])

    def _visit_draft(self,cid,visit,phase,draft_type):
        from .interface_backups import _read_state
        folder=self.case_path(cid)
        state,_,_,_=_read_state(folder/'research.sqlite')
        workflow=state.workflow
        current=workflow['visits'][-1]
        if (workflow['status']!='active' or current['phase']!=phase or current['record'] is not None
                or visit!=current['visit_id']):
            raise RuntimeError(f'This {phase.title()} visit is no longer open. Refresh your research.')
        return draft_type(folder/(phase+'-draft-'+current['visit_id']+'.sqlite'))

    def documents(self,cid):
        return DocumentLibrary(self.case_path(cid)/'documents.sqlite')

    def case_storage(self,cid):
        """Report case file sizes without following links or opening research files."""
        folder=self.case_path(cid)
        sizes=dict(research_database_bytes=0,local_library_bytes=0,drafts_bytes=0,
                   shortlist_bytes=0,other_bytes=0)
        for item in folder.iterdir():
            if item.is_symlink() or not item.is_file():continue
            size=item.stat().st_size
            name=item.name
            if name=='research.sqlite' or name.startswith('research.sqlite-'):
                key='research_database_bytes'
            elif name=='documents.sqlite' or name.startswith('documents.sqlite-'):
                key='local_library_bytes'
            elif name=='source-draft.sqlite' or '-draft-' in name and name.endswith('.sqlite'):
                key='drafts_bytes'
            elif name=='source-shortlist.sqlite':
                key='shortlist_bytes'
            else:
                key='other_bytes'
            sizes[key]+=size
        sizes['total_bytes']=sum(sizes.values())
        return sizes

    def catalog(self):
        """Inspect candidate cases without constructors, adoption, migration or repair."""
        from .interface_backups import _read_state
        result=[];unavailable=[]
        for folder in sorted(self.path.iterdir()):
            if folder.is_symlink() or not folder.is_dir() or len(folder.name)!=32 or any(c not in '0123456789abcdef' for c in folder.name):continue
            meta_path=folder/'case-info.json';database=folder/'research.sqlite'
            # Empty crash reservations and private staging directories are not saved cases.
            if not meta_path.exists() and not meta_path.is_symlink() and not database.exists() and not database.is_symlink():continue
            title='Unnamed saved case'
            try:
                if meta_path.is_symlink():raise ValueError('unsupported metadata link')
                meta=json.loads(meta_path.read_text())
                if not isinstance(meta,dict) or not isinstance(meta.get('title'),str) or not meta['title'].strip() or type(meta.get('synthetic_example')) is not bool:raise ValueError('invalid case metadata')
                title=meta['title']
                state,revision,_,_=_read_state(self.case_path(folder.name)/'research.sqlite')
                if getattr(state,'workflow',{}).get('workflow_version') not in {2,3}:raise ValueError('unsupported browser workflow')
                result.append(dict(case_id=folder.name,title=title,synthetic_example=meta['synthetic_example'],phase=getattr(state,'workflow',{}).get('phase','brief'),status=getattr(state,'workflow',{}).get('status','active'),revision=revision,updated_at=int(database.stat().st_mtime)))
            except (OSError,ValueError,KeyError,TypeError,RuntimeError,sqlite3.Error,ResearchInvariantError):
                unavailable.append(dict(case_id=folder.name,title=title[:400],reason='case_unavailable'))
        # Most recently worked-on first: the identifier order is opaque to the operator.
        result.sort(key=lambda case:(case['updated_at'],case['title'].casefold()),reverse=True)
        return dict(cases=result,unavailable_cases=unavailable)

    def cases(self):return self.catalog()['cases']

    def _read_meta(self,folder):
        meta_path=folder/'case-info.json'
        if meta_path.is_symlink():raise ValueError('unsupported case metadata link')
        meta=json.loads(meta_path.read_text())
        if not isinstance(meta,dict) or not isinstance(meta.get('title'),str) or not meta['title'].strip() or type(meta.get('synthetic_example')) is not bool:raise ValueError('invalid case metadata')
        return meta_path,meta

    def _verified_trash_case(self,folder):
        _,meta=self._read_meta(folder)
        from .interface_backups import _read_state
        state,revision,ledger_revision,_=_read_state(folder/'research.sqlite')
        workflow=getattr(state,'workflow',{})
        if not isinstance(workflow,dict) or workflow.get('workflow_version') not in {2,3}:
            raise ValueError('unsupported trashed case workflow')
        return meta,state,revision,ledger_revision

    def rename(self,cid,title):
        """Change the display title only; the research record is untouched."""
        _text(title,'title');title=title.strip()
        if len(title)>200:raise ValueError('Choose a title of up to 200 characters.')
        folder=self.case_path(cid);meta_path,meta=self._read_meta(folder)
        meta['title']=title
        staged=folder/'.case-info.tmp'
        try:
            staged.write_text(_encode(meta));os.chmod(staged,0o600);os.replace(staged,meta_path)
        finally:
            if staged.exists():staged.unlink()
        return dict(case_id=cid,title=title)

    def delete(self,cid,confirm_title):
        """Move a case into the workspace trash so a mistake is still recoverable."""
        folder=self.case_path(cid);_,meta=self._read_meta(folder)
        if not isinstance(confirm_title,str) or confirm_title.strip()!=meta['title']:
            raise ValueError('Type the exact case title to confirm deletion.')
        trash=self.path/'.trash';trash.mkdir(mode=0o700,exist_ok=True)
        target=trash/(cid+'-'+datetime.now().strftime('%Y%m%dT%H%M%S'))
        os.replace(folder,target)
        return dict(case_id=cid,title=meta['title'],moved_to=target.name)

    def trash_catalog(self):
        """List restorable cases without constructing or repairing them."""
        trash=self.path/'.trash'
        if not trash.exists():return []
        result=[]
        for folder in sorted(trash.iterdir(),reverse=True):
            name=folder.name
            cid=name[:32] if len(name)>=33 else ''
            if (folder.is_symlink() or not folder.is_dir() or len(cid)!=32
                    or any(c not in '0123456789abcdef' for c in cid)):
                continue
            try:
                meta,state,revision,ledger_revision=self._verified_trash_case(folder)
                workflow=state.workflow
                result.append(dict(trash_id=name,case_id=cid,title=meta['title'],
                                   synthetic_example=meta['synthetic_example'],
                                   phase=workflow.get('phase','brief'),status=workflow.get('status','active'),
                                   revision=revision,ledger_revision=ledger_revision,
                                   deleted_at=int(folder.stat().st_mtime)))
            except (OSError,ValueError,KeyError,TypeError,RuntimeError,sqlite3.Error,ResearchInvariantError):
                try:
                    deleted_at=int(folder.stat().st_mtime)
                except FileNotFoundError:
                    continue
                result.append(dict(trash_id=name,case_id=cid,title='Unavailable trashed case',
                                   synthetic_example=False,phase='unknown',status='unavailable',
                                   revision=0,ledger_revision=0,deleted_at=deleted_at))
        return result

    def restore_trashed(self,trash_id):
        """Restore a trashed case to its original identifier."""
        if (not isinstance(trash_id,str) or len(trash_id)<34
                or trash_id[32]!='-' or any(c not in '0123456789abcdef' for c in trash_id[:32])):
            raise ValueError('Choose a case in the workspace trash.')
        cid=trash_id[:32]
        folder=self.path/'.trash'/trash_id
        if folder.is_symlink() or not folder.is_dir():raise ValueError('Choose a case in the workspace trash.')
        destination=self.path/cid
        if destination.exists() or destination.is_symlink():raise ValueError('A case already uses the original identifier.')
        try:
            meta,_,_,_=self._verified_trash_case(folder)
        except (OSError,ValueError,KeyError,TypeError,RuntimeError,sqlite3.Error,ResearchInvariantError) as exc:
            raise ValueError('This trashed case could not be verified and remains in Trash.') from exc
        os.replace(folder,destination)
        return dict(case_id=cid,title=meta['title'])

    def _publish_case(self,cid,folder,fault):
        """Expose an already verified staged case without replacing existing research."""
        fault('before_reservation')
        reservation=case_publish.reserve(self.path,cid)
        # An uncertain response after publication must retain the complete case.
        case_publish.publish(folder,self.path/cid,reservation,fault=fault)
        return cid

    def create(self,data,*,_fault=None):
        _keys(data,{'title','question','scope','max_visits','max_alternatives'})
        for name in ('title','question','scope'):_text(data[name],name)
        # Validate before staging; bootstrap is not a research approval.
        if type(data['max_visits']) is not int or not 4<=data['max_visits']<=20 or type(data['max_alternatives']) is not int or not 2<=data['max_alternatives']<=20:raise ValueError('Choose 4–20 visits and 2–20 alternatives.')
        def fault(name):
            if _fault is not None:_fault(name)
        cid=_id()
        with tempfile.TemporaryDirectory(prefix='.create-',dir=self.path) as temp:
            folder=Path(temp)/'case';folder.mkdir(mode=0o700)
            store=PersistentEvidenceStore(folder/'research.sqlite');store.initialize(ResearchState(research_id=data['title']))
            fault('after_initialize')
            store.apply_workflow(dict(type='start_criteria_research',workflow_id=cid,brief=data['question'],scope=data['scope'],questions=[data['question']],max_visits=data['max_visits'],max_alternatives=data['max_alternatives']),
                operation_id='ui-start',actor=ACTOR,rationale='Operator created a bounded research case in the local interface',expected_state_revision=0,authorize=_authorize)
            fault('after_workflow')
            meta=folder/'case-info.json';meta.write_text(_encode(dict(title=data['title'],synthetic_example=False)));os.chmod(meta,0o600)
            # Verify the complete staged case before exposing its identifier.
            state,sr,lr=store.load_with_revisions()
            if sr!=1 or lr!=0 or state.workflow['workflow_id']!=cid:raise ValueError('new case verification failed')
            return self._publish_case(cid,folder,fault)

    def demo(self,*,_fault=None):
        from .agenda_demo import run_demo
        def fault(name):
            if _fault is not None:_fault(name)
        cid=_id()
        with tempfile.TemporaryDirectory(prefix='.example-',dir=self.path) as temp:
            folder=Path(temp)/'case';result=run_demo(folder)
            fault('after_example')
            state,sr,lr=PersistentEvidenceStore(folder/'research.sqlite').load_with_revisions()
            if (result.get('fixture_only') is not True or result.get('live_sources_used') is not False
                or result.get('mvp_ready') is not False or not result.get('checks') or not all(result['checks'].values())
                or state.workflow.get('workflow_version')!=3 or not state.evidence
                or any(e.get('synthetic') is not True for e in state.evidence.values())):
                raise ValueError('learning example must remain a verified synthetic fixture')
            meta=folder/'case-info.json';meta.write_text(_encode(dict(title='Example: learn from an unresolved explanation',synthetic_example=True)));os.chmod(meta,0o600)
            return self._publish_case(cid,folder,fault)

    def view(self,cid):
        from .interface_backups import _read_state
        folder=self.case_path(cid);meta_path=folder/'case-info.json'
        if meta_path.is_symlink():raise ValueError('unsupported case metadata link')
        meta=json.loads(meta_path.read_text())
        if not isinstance(meta,dict) or not isinstance(meta.get('title'),str) or not meta['title'].strip() or type(meta.get('synthetic_example')) is not bool:raise ValueError('invalid case metadata')
        state,sr,lr,_=_read_state(folder/'research.sqlite')
        from .interface_guidance import build_guidance,research_gate_contexts
        from .analysis_transactions import assessment_is_current
        from assessment import DIMENSIONS
        return dict(case_id=cid,meta=meta,storage=self.case_storage(cid),gate_context_current=research_gate_contexts(state),guidance=build_guidance(state,synthetic_example=meta['synthetic_example']),revision=sr,ledger_revision=lr,state=state.snapshot(),currency=stage_currency(state),
                    reports=sorted([dict(report_id=rid,current=report_is_current(state,rid)) for rid in state.outputs if 'content_digest' in state.outputs[rid]],key=lambda r:(r['current'],state.outputs[r['report_id']].get('generated_at',''),r['report_id']),reverse=True),
                    agendas=[inspect_agenda(state,aid) for aid in getattr(state,'research_agendas',{})],
                    revisable_claim_ids=[key for key,claim in state.claims.items() if _advisory_revision_allowed(claim)],assessment_dimensions=list(DIMENSIONS),assessments=[dict(assessment=record,current=assessment_is_current(state,aid)) for aid,record in sorted(getattr(state,'assessments',{}).items())])

    def report(self,cid,report_id):
        from .interface_backups import _read_state
        state,_,_,_=_read_state(self.case_path(cid)/'research.sqlite')
        if report_id not in state.outputs:raise ValueError('unknown report')
        return render_markdown(state.outputs[report_id])

    def visit(self,cid,visit_id,expected_revision=None):
        from .visit_review import read_visit
        return read_visit(self.case_path(cid)/'research.sqlite',visit_id,expected_revision=expected_revision)

    def source_context(self,cid,evidence_id,expected_revision):
        from .source_review import read_source
        return read_source(self.case_path(cid)/'research.sqlite',evidence_id,expected_revision=expected_revision)

    def frame_draft(self,cid,visit_id,expected_revision):
        from .frame_revision import read_frame_draft
        return read_frame_draft(self.case_path(cid)/'research.sqlite',visit_id,expected_revision=expected_revision)

    def backup(self,cid,revision):
        from .interface_backups import download_checkpoint
        return download_checkpoint(self.case_path(cid)/'research.sqlite',expected_revision=revision)

    def inspect_backup(self,data):
        from .interface_backups import inspect_upload
        return inspect_upload(data)

    def restore_backup(self,data,digest):
        from .interface_backups import restore_upload
        return restore_upload(self.path,data,expected_digest=digest)

    def action(self,cid,body):
        _keys(body,{'action','data','expected_revision','expected_ledger_revision','request_id'})
        action=body['action'];data=body['data'];_text(body['request_id'],'request_id')
        if len(body['request_id'])>80:raise ValueError('request identifier too long')
        if not isinstance(data,dict):raise ValueError('action data must be an object')
        store=self.store(cid);state,sr,lr=store.load_with_revisions()
        if type(body['expected_revision']) is not int or type(body['expected_ledger_revision']) is not int:raise ValueError('invalid revision')
        # Do not silently refresh a stale browser tab or repeat an uncertain write.
        if sr!=body['expected_revision'] or lr!=body['expected_ledger_revision']:raise RuntimeError('This case changed. Refresh and review the latest research before trying again.')
        oid='ui-'+body['request_id']
        options=dict(operation_id=oid,actor=ACTOR,rationale=data.get('rationale','Local operator saved research through the interface'),expected_state_revision=sr,authorize=_authorize)
        provenance='operator_reviewed_source'
        metadata=dict(review_basis='Local operator confirmation; independent acquisition is a human assertion')
        if action=='document_source':
            _keys(data,{'document_id','paragraph','passage','title','publisher','group','confirmed','rationale','synthetic'},{'published_at'})
            if data['confirmed'] is not True:
                raise PermissionError('Check the saved document and explicitly approve the passage first.')
            if type(data['synthetic']) is not bool:raise ValueError('synthetic must be boolean')
            _text(data['document_id'],'document identifier')
            context=self.documents(cid).context(data['document_id'],data['paragraph'])
            matching=next(p['text'] for p in context['paragraphs'] if p['number']==context['number'])
            if matching!=data['passage']:
                raise ValueError('The passage does not match the saved paragraph. Reopen it and review again.')
            provenance='synthetic_local_document' if data['synthetic'] else 'operator_reviewed_local_document'
            metadata=dict(review_basis='Operator checked the original and approved the saved paragraph',
                          document_sha256=data['document_id'], transcript_sha256=context.get('transcript_sha256'))
            data=dict(title=data['title'],publisher=data['publisher'],group=data['group'],published_at=data.get('published_at'),
                      confirmed=True,rationale=data['rationale'],synthetic=data['synthetic'],
                      url='urn:sha256:'+data['document_id'],passage=matching,
                      location=f"{context['filename']} · {context['location']}",
                      snapshot='\n\n'.join(p['text'] for p in context['paragraphs']))
        if action in {'source','document_source'}:
            _keys(data,{'title','publisher','url','passage','location','snapshot','group','synthetic','confirmed','rationale'},{'published_at'})
            if data['confirmed'] is not True:raise PermissionError('Check the passage and location against your independently acquired source before approving.')
            if type(data['synthetic']) is not bool:raise ValueError('synthetic must be boolean')
            from .retrieval_validation import validate_retrieval_output
            from .evidence_review import review_retrieval
            from .state_journal import now
            sid=('synthetic-' if data['synthetic'] else 'source-')+body['request_id']
            doc=dict(source_id=sid,title=data['title'],publisher=data['publisher'],url=data['url'],retrieved_at=now(),published_at=data.get('published_at'),passage=data['passage'],content_location=data['location'],
                provenance='synthetic' if action=='source' and data['synthetic'] else provenance,synthetic=data['synthetic'],independence_cluster=data['group'],metadata=metadata)
            validation=validate_retrieval_output('retrieve',dict(status='completed',documents=[doc]))
            if validation.status!='ready_for_review':raise ValueError('; '.join(validation.errors))
            snapshots={sid:dict(text=data['snapshot'],location=data['location'])}
            review=review_retrieval(validation,snapshots=snapshots,reviewer=ACTOR,decision='approved',rationale=data['rationale'],state=state)
            result=store.ingest(validation,review,operation_id=oid,expected_state_revision=sr,expected_ledger_revision=lr,authorize=_authorize,source_snapshots=snapshots)
        elif action=='claim':
            _keys(data,{'claim','claim_type','evidence_ids','rationale'},{'uncertainty_ids'})
            record=dict(claim_id='claim-'+body['request_id'],claim=data['claim'],claim_type=data['claim_type'],disposition='unresolved',status='draft',evidence_ids=data['evidence_ids'])
            if 'uncertainty_ids' in data:record['material_uncertainties']=_ids(data['uncertainty_ids'],'uncertainty_ids')
            result=store.apply_analysis([dict(type='add_claim',record=record)],**options)
        elif action=='claim_revision':
            _keys(data,{'claim_id','claim','evidence_ids','uncertainty_ids','rationale'})
            for name in ('claim_id','claim','rationale'):_text(data[name],name)
            claim=state.claims.get(data['claim_id'])
            if claim is None:raise ValueError('Choose an existing interpretation to revise.')
            if not _advisory_revision_allowed(claim):raise PermissionError('This interpretation is outside the advisory draft revision form. Use its existing host review workflow.')
            patch=dict(claim=data['claim'],evidence_ids=_ids(data['evidence_ids'],'evidence_ids'),material_uncertainties=_ids(data['uncertainty_ids'],'uncertainty_ids'))
            result=store.apply_analysis([dict(type='update_claim',claim_id=data['claim_id'],patch=patch)],**options)
        elif action=='uncertainty':
            _keys(data,{'question','claim_ids','rationale'})
            _text(data['question'],'question');_text(data['rationale'],'rationale');_ids(data['claim_ids'],'claim_ids')
            if len(data['claim_ids'])>99:raise ValueError('Link at most 99 interpretations in one uncertainty transaction.')
            if any(cid not in state.claims for cid in data['claim_ids']):raise ValueError('Choose existing interpretations for this uncertainty.')
            uid='uncertainty-'+body['request_id']
            if uid in state.uncertainties:raise ValueError('This uncertainty identifier already exists; refresh and inspect saved research.')
            commands=[dict(type='put_uncertainty',record=dict(uncertainty_id=uid,question=data['question'],status='open'))]
            for claim_id in data['claim_ids']:
                linked=list(state.claims[claim_id].get('material_uncertainties',[]))
                commands.append(dict(type='update_claim',claim_id=claim_id,patch=dict(material_uncertainties=linked+[uid])))
            result=store.apply_analysis(commands,**options)
        elif action=='assessment':
            _keys(data,{'claim_id','evidence_id','dimensions','limitations','rationale'})
            _text(data['claim_id'],'claim_id');_text(data['evidence_id'],'evidence_id')
            command=dict(type='assess_evidence',assessment_id='assessment-'+body['request_id'],claim_id=data['claim_id'],evidence_id=data['evidence_id'],dimensions=data['dimensions'],limitations=data['limitations'],rationale=data['rationale'])
            result=store.apply_analysis([command],**options)
        elif action=='contradiction':
            _keys(data,{'claim_a','claim_b','issue','rationale'})
            for name in ('claim_a','claim_b','issue','rationale'):_text(data[name],name)
            if data['claim_a']==data['claim_b']:raise ValueError('Choose two distinct interpretations for a disagreement.')
            if any(data[name] not in state.claims for name in ('claim_a','claim_b')):raise ValueError('Choose existing interpretations for this disagreement.')
            record=dict(contradiction_id='contradiction-'+body['request_id'],claim_a=data['claim_a'],claim_b=data['claim_b'],issue=data['issue'],disposition='unresolved')
            result=store.apply_analysis([dict(type='add_contradiction',record=record)],**options)
        elif action=='phase_record':
            _keys(data,{'record','rationale'})
            phase=state.workflow['phase'];record=data['record']
            prior=[v for v in state.workflow['visits'][:-1] if v['phase']=='define' and v['record'] is not None]
            if phase=='define' and prior and prior[-1]['record']!=record:
                from .double_diamond import _validate
                _validate(state,phase,record)
                proposal=reframing_action(state,record)
                options['rationale']=_encode(dict(reason=data['rationale'],proposed_record=record))
                result=store.apply_gate(dict(type='propose',gate_id='gate-'+body['request_id'],action=proposal),**options)
                result['notice']='The revised frame is proposed. Review and approve its exact content before applying it.'
            else:result=store.apply_workflow(dict(type='record',phase=phase,record=record),**options)
        elif action=='propose_transition':
            _keys(data,{'target','rationale'})
            proposal=transition_action(state,data['target'],data['rationale'])
            result=store.apply_gate(dict(type='propose',gate_id='gate-'+body['request_id'],action=proposal),**options)
        elif action=='decide_gate':
            _keys(data,{'gate_id','decision','rationale'})
            gate=state.human_gates.get(data['gate_id'])
            if not gate or gate['gate_type'] not in {'phase_transition','material_reframing'}:raise PermissionError('This interface reviews research phase/framing gates only.')
            result=store.apply_gate(dict(type='decide',gate_id=data['gate_id'],decision=data['decision'],proposal_digest=binding(gate['action'])),**options)
        elif action=='apply_gate':
            _keys(data,{'gate_id','rationale'})
            gate=state.human_gates.get(data['gate_id'])
            if not gate or gate.get('status')!='approved':raise PermissionError('A current approved gate is required.')
            if gate['gate_type']=='phase_transition':
                target=gate['action']['payload']['to_phase'];current=state.workflow['phase']
                kind='reopen' if state.workflow['status']!='active' else ('advance' if PHASES.index(target)==PHASES.index(current)+1 else 'revisit')
                command=dict(type=kind,to_phase=target,reason=gate['action']['payload']['reason'],gate_id=data['gate_id'])
            elif gate['gate_type']=='material_reframing':
                proposed=json.loads(gate['proposal_rationale'])['proposed_record']
                command=dict(type='record',phase='define',record=proposed,gate_id=data['gate_id'])
            else:raise PermissionError('External actions and publication cannot be applied here.')
            result=store.apply_workflow(command,**options)
        elif action=='finish':
            _keys(data,{'outcome','rationale'})
            result=store.apply_workflow(dict(type='finish',outcome=data['outcome'],reason=data['rationale']),**options)
        elif action=='report':
            _keys(data,{'rationale'})
            result=store.apply_workflow(dict(type='report',report_id='report-'+body['request_id'],include_evaluation_evidence=True),**options)
        elif action=='agenda':
            _keys(data,{'report_id','items','rationale'})
            report=state.outputs.get(data['report_id'])
            if not report:raise ValueError('Choose a saved research report.')
            result=store.apply_workflow(dict(type='plan_research',agenda_id='agenda-'+body['request_id'],report_id=data['report_id'],report_digest=report['content_digest'],items=data['items']),**options)
        else:raise ValueError('unknown interface action')
        return result


class LocalServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,workspace,port=0):
        self.workspace=workspace;self.token=secrets.token_urlsafe(32);self.mutation_lock=threading.Lock()
        super().__init__(('127.0.0.1',port),Handler)
        self.origin='http://127.0.0.1:'+str(self.server_address[1])

    @property
    def url(self):return self.origin+'/#token='+self.token


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass

    def _reply(self,status,content,content_type='application/json; charset=utf-8',headers=None):
        if isinstance(content,(dict,list)):content=_encode(content)
        if isinstance(content,str):content=content.encode('utf-8')
        self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(content)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        for key,value in (headers or {}).items():self.send_header(key,value)
        self.end_headers();self.wfile.write(content)

    def _guard(self,api=False,write=False):
        if self.headers.get('Host')!=urlparse(self.server.origin).netloc:raise PermissionError('Unrecognized local host.')
        origin=self.headers.get('Origin')
        if (origin is not None and origin!=self.server.origin) or (write and origin!=self.server.origin):raise PermissionError('Open this action in the local research interface.')
        if api and not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+self.server.token):raise PermissionError('Open the current private launch link to access this workspace.')

    def do_GET(self):
        try:
            path=urlparse(self.path);api=path.path.startswith('/api/');self._guard(api=api)
            if path.path=='/api/checkpoint':
                query=parse_qs(path.query,keep_blank_values=True);revision=query.get('revision',[''])[0]
                if not revision.isascii() or not revision.isdecimal():raise ValueError('A current case revision is required.')
                data,_=self.server.workspace.backup(query.get('case',[''])[0],int(revision))
                return self._reply(200,data,'application/zip',{'Content-Disposition':'attachment; filename="research-checkpoint.zip"'})
            if path.path=='/api/document-original':
                query=parse_qs(path.query)
                library=self.server.workspace.documents(query.get('case',[''])[0])
                filename,data=library.original(query.get('document',[''])[0])
                disposition="attachment; filename=source; filename*=UTF-8''"+quote(filename,safe='')
                return self._reply(200,data,content_type(filename),
                                   {'Content-Disposition':disposition})
            if path.path=='/api/documents':
                query=parse_qs(path.query,keep_blank_values=True)
                library=self.server.workspace.documents(query.get('case',[''])[0])
                if 'paragraph' in query:
                    number=query['paragraph'][0]
                    if len(number)>4 or not number.isascii() or not number.isdecimal():
                        raise ValueError('Choose a valid paragraph number.')
                    return self._reply(200,library.context(query.get('document',[''])[0],int(number)))
                if 'document' in query:return self._reply(200,library.preview(query['document'][0]))
                return self._reply(200,dict(documents=library.list()))
            if path.path=='/api/later-phase-draft':
                query=parse_qs(path.query)
                draft=self.server.workspace.later_phase_draft(query.get('case',[''])[0],query.get('visit',[''])[0],
                                                            query.get('phase',[''])[0])
                return self._reply(200,draft.read())
            if path.path=='/api/define-draft':
                query=parse_qs(path.query)
                draft=self.server.workspace.define_draft(query.get('case',[''])[0],query.get('visit',[''])[0])
                return self._reply(200,draft.read())
            if path.path=='/api/discover-draft':
                query=parse_qs(path.query)
                draft=self.server.workspace.discover_draft(query.get('case',[''])[0],query.get('visit',[''])[0])
                return self._reply(200,draft.read())
            if path.path=='/api/source-draft':
                cid=parse_qs(path.query).get('case',[''])[0]
                return self._reply(200,self.server.workspace.source_draft(cid).read())
            if path.path=='/api/source-shortlist':
                cid=parse_qs(path.query).get('case',[''])[0]
                return self._reply(200,dict(leads=self.server.workspace.shortlist(cid).read()))
            if path.path=='/api/trash':return self._reply(200,dict(cases=self.server.workspace.trash_catalog()))
            if path.path=='/api/diagnostics':return self._reply(200,self.server.workspace.diagnostics())
            if path.path=='/api/catalog':return self._reply(200,self.server.workspace.catalog())
            if path.path=='/api/cases':return self._reply(200,self.server.workspace.cases())
            if path.path=='/api/state':return self._reply(200,self.server.workspace.view(parse_qs(path.query).get('case',[''])[0]))
            if path.path=='/api/frame-draft':
                query=parse_qs(path.query,keep_blank_values=True);revision=query.get('revision',[''])[0]
                if not revision.isascii() or not revision.isdecimal():raise ValueError('A current case revision is required.')
                return self._reply(200,self.server.workspace.frame_draft(query.get('case',[''])[0],query.get('visit',[''])[0],int(revision)))
            if path.path=='/api/source-context':
                query=parse_qs(path.query,keep_blank_values=True);revision=query.get('revision',[''])[0]
                if not revision.isascii() or not revision.isdecimal():raise ValueError('A current case revision is required.')
                return self._reply(200,self.server.workspace.source_context(query.get('case',[''])[0],query.get('evidence',[''])[0],int(revision)))
            if path.path=='/api/visit':
                query=parse_qs(path.query,keep_blank_values=True);revision=query.get('revision',[None])[0]
                if revision is not None and (not revision.isascii() or not revision.isdecimal()):raise ValueError('invalid expected revision')
                return self._reply(200,self.server.workspace.visit(query.get('case',[''])[0],query.get('visit',[''])[0],int(revision) if revision is not None else None))
            if path.path=='/api/report':
                query=parse_qs(path.query);cid=query.get('case',[''])[0];rid=query.get('report',[''])[0]
                return self._reply(200,self.server.workspace.report(cid,rid),'text/markdown; charset=utf-8')
            assets={'/':'index.html','/app.js':'app.js','/style.css':'style.css','/visit-panels.js':'visit-panels.js'}
            if path.path not in assets:return self._reply(404,dict(error='Not found'))
            asset=ASSETS/assets[path.path];return self._reply(200,asset.read_bytes(),content_type(asset.name))
        except (PermissionError,ValueError,KeyError,TypeError,OSError,RuntimeError,sqlite3.Error,ResearchInvariantError) as exc:self._reply(403 if isinstance(exc,PermissionError) else 409 if isinstance(exc,RuntimeError) else 400,dict(error=str(exc)))

    def do_POST(self):
        try:
            self._guard(api=True,write=True)
            path=urlparse(self.path).path
            if path in {'/api/document-preview','/api/documents','/api/document-transcript'}:
                from .file_preview import MAX_FILE_BYTES,preview_file
                from .document_preview import preview_word_document
                if self.headers.get('Content-Type','').split(';')[0]!='application/octet-stream':
                    raise ValueError('Choose a Word .docx file.')
                size=int(self.headers.get('Content-Length','-1'))
                if self.headers.get('Transfer-Encoding') or size>MAX_FILE_BYTES:
                    raise ValueError('Choose a supported file no larger than 64 MiB.')
                if size<1:raise ValueError('That file is empty. Choose a file with something in it.')
                payload=self.rfile.read(size)
                if len(payload)!=size:raise ValueError('Incomplete document upload.')
                if path=='/api/document-transcript':
                    query=parse_qs(urlparse(self.path).query)
                    library=self.server.workspace.documents(query.get('case',[''])[0])
                    return self._reply(200,library.attach_transcript(query.get('document',[''])[0],query.get('filename',[''])[0],payload))
                if path=='/api/documents':
                    query=parse_qs(urlparse(self.path).query)
                    library=self.server.workspace.documents(query.get('case',[''])[0])
                    return self._reply(200,library.save(query.get('filename',[''])[0],payload))
                query=parse_qs(urlparse(self.path).query)
                filename=query.get('filename',[''])[0]
                return self._reply(200,preview_file(filename,payload) if filename else preview_word_document(payload))
            if path in {'/api/checkpoint/inspect','/api/checkpoint/restore'}:
                from .interface_backups import MAX_TRANSFER_BYTES
                if self.headers.get('Content-Type','').split(';')[0]!='application/zip':raise ValueError('A checkpoint ZIP upload is required.')
                size=int(self.headers.get('Content-Length','-1'))
                if self.headers.get('Transfer-Encoding') or not 0<size<=MAX_TRANSFER_BYTES:raise ValueError('Choose a checkpoint ZIP no larger than 32 MiB.')
                payload=self.rfile.read(size)
                if len(payload)!=size:raise ValueError('Incomplete checkpoint upload.')
                with self.server.mutation_lock:
                    if path.endswith('/inspect'):return self._reply(200,self.server.workspace.inspect_backup(payload))
                    return self._reply(201,self.server.workspace.restore_backup(payload,self.headers.get('X-Checkpoint-SHA256','')))
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('JSON request required')
            size=int(self.headers.get('Content-Length','-1'))
            if self.headers.get('Transfer-Encoding') or not 0<=size<=2*1024*1024:raise ValueError('Request exceeds local interface limits.')
            try:body=json.loads(self.rfile.read(size))
            except json.JSONDecodeError:raise ValueError('The request could not be read. Refresh the page and try again.') from None
            if path=='/api/document-search':
                _keys(body,{'case_id','query'},{'mode'})
                return self._reply(200,self.server.workspace.documents(body['case_id']).search(body['query'],body.get('mode','phrase')))
            if path=='/api/later-phase-draft':
                _keys(body,{'case_id','visit','phase','expected_version','draft'})
                draft=self.server.workspace.later_phase_draft(body['case_id'],body['visit'],body['phase'])
                return self._reply(200,draft.write(body['expected_version'],body['draft']))
            if path=='/api/define-draft':
                _keys(body,{'case_id','visit','expected_version','draft'})
                draft=self.server.workspace.define_draft(body['case_id'],body['visit'])
                return self._reply(200,draft.write(body['expected_version'],body['draft']))
            if path=='/api/discover-draft':
                _keys(body,{'case_id','visit','expected_version','draft'})
                draft=self.server.workspace.discover_draft(body['case_id'],body['visit'])
                return self._reply(200,draft.write(body['expected_version'],body['draft']))
            if path=='/api/source-draft':
                _keys(body,{'case_id','expected_version','draft'})
                draft=self.server.workspace.source_draft(body['case_id'])
                return self._reply(200,draft.write(body['expected_version'],body['draft']))
            if path=='/api/source-search':
                _keys(body,{'query'},{'from_date','to_date','publication_type'})
                return self._reply(200,dict(results=search_publications(
                    body['query'],from_date=body.get('from_date',''),
                    to_date=body.get('to_date',''),
                    publication_type=body.get('publication_type',''))))
            if path=='/api/source-shortlist':
                _keys(body,{'case_id','action','lead'})
                leads=self.server.workspace.shortlist(body['case_id']).change(body['action'],body['lead'])
                return self._reply(200,dict(leads=leads))
            with self.server.mutation_lock:
                if path=='/api/example':
                    _keys(body,{'kind'})
                    if body['kind']!='synthetic_learning_example':raise ValueError('Only the clearly labelled synthetic learning example can be created here.')
                    return self._reply(201,dict(case_id=self.server.workspace.demo(),synthetic_example=True))
                if path=='/api/case/rename':
                    _keys(body,{'case_id','title'})
                    return self._reply(200,self.server.workspace.rename(body['case_id'],body['title']))
                if path=='/api/case/delete':
                    _keys(body,{'case_id','title'})
                    return self._reply(200,self.server.workspace.delete(body['case_id'],body['title']))
                if path=='/api/case/restore':
                    _keys(body,{'trash_id'})
                    return self._reply(200,self.server.workspace.restore_trashed(body['trash_id']))
                if path=='/api/cases':return self._reply(201,dict(case_id=self.server.workspace.create(body)))
                if path=='/api/action':
                    _keys(body,{'case_id','request'})
                    return self._reply(200,self.server.workspace.action(body['case_id'],body['request']))
            return self._reply(404,dict(error='Not found'))
        except (PermissionError,ValueError,KeyError,TypeError,OSError,RuntimeError,sqlite3.Error,ResearchInvariantError) as exc:
            self._reply(403 if isinstance(exc,PermissionError) else 409 if isinstance(exc,RuntimeError) else 400,dict(error=str(exc)))


def _parse_args(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',default=str(DEFAULT_WORKSPACE),
                        help='Folder for research cases. Defaults to a research-workspace folder beside the application, wherever you launch it from.')
    parser.add_argument('--port',type=int,default=0)
    parser.add_argument('--demo',action='store_true')
    parser.add_argument('--no-browser',action='store_true',help='Print the private link without opening it in your browser.')
    parser.add_argument('--diagnostics',action='store_true',
                        help='Print a local, operator-safe workspace health summary and exit.')
    return parser.parse_args(argv)


def _open_browser(url):
    """Best effort only: the printed link always works, so a failure here is not an error."""
    try:webbrowser.open(url)
    except Exception:pass


def main(argv=None):
    args=_parse_args(argv)
    workspace=Workspace(args.workspace)
    if args.diagnostics:
        print(_encode(workspace.diagnostics()))
        return
    if args.demo:workspace.demo()
    server=LocalServer(workspace,args.port)
    print('Open your private local research workspace: '+server.url,flush=True)
    print('Keep this process running while using the interface. Press Ctrl+C to stop.',flush=True)
    if not args.no_browser:_open_browser(server.url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()
