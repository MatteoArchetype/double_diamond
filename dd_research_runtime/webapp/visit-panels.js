'use strict';
// Render retained research as text only. Historical references never use live state.
function retainedEvidence(ids,context,{expanded=false}={}){
  const box=node('div');
  for(const id of ids||[]){
    const e=context?.evidence?.[id];
    if(!e){box.append(text('p','The original context for this reference is unavailable.','muted small'));continue;}
    const s=context.sources?.[e.source_id]||e.metadata||{};
    box.append(node('details',expanded?{class:'details',open:''}:{class:'details'},node('summary',{},(e.synthetic?'[Synthetic] ':'')+(e.metadata?.title||s.title||'Retained source passage')),
      node('blockquote',{},e.finding),value('Exact location',e.exact_location),value('Publisher or author',e.metadata?.publisher||s.publisher),
      value(e.metadata?.document_sha256?'Saved file reference':'Source URL',e.metadata?.url||s.url),value('Retrieved at',e.metadata?.retrieved_at||s.retrieved_at),value('Shared origin group',e.independence_cluster),
      text('p',e.synthetic?'Invented material; this is not real-world evidence.':'Retained source material. Review and traceability do not establish that a claim is true.','muted small')));
  }
  if(!(ids||[]).length)box.append(text('p','No evidence linked in this record.','muted small'));
  return box;
}
function retainedClaims(ids,context){
  const box=node('div');
  for(const id of ids||[]){
    const claim=context?.claims?.[id];
    if(!claim){box.append(text('p','The original interpretation context is unavailable.','muted small'));continue;}
    box.append(node('details',{class:'details'},node('summary',{},claim.claim),tag('Advisory interpretation'),value('Type',readable(claim.claim_type)),
      value('Recorded status',readable(claim.status||claim.disposition)),text('h3','Evidence linked at the time'),retainedEvidence(claim.evidence_ids,context)));
  }
  if(!(ids||[]).length)box.append(text('p','No interpretations linked.','muted small'));
  return box;
}
function retainedUncertainties(ids,context){
  const box=node('div');
  for(const id of ids||[]){const u=context?.uncertainties?.[id];box.append(u?node('div',{class:'card subtle'},value('Question',u.question),value('Recorded status',u.status),value('Resolution basis',u.resolution_basis)):text('p','The original uncertainty context is unavailable.','muted small'));}
  if(!(ids||[]).length)box.append(text('p','No uncertainties linked in this frame. This does not establish that none exist.','muted small'));
  return box;
}
function retainedRecord(phase,record,context){
  const box=node('div');if(!record){box.append(text('p','This visit has no saved findings yet.','muted'));return box;}
  if(phase==='discover')box.append(value('Observations',record.notes),value('Perspectives and gaps',record.perspectives.join('\n')),value('Discovery limits',record.limitations),text('h3','Evidence explored'),retainedEvidence(record.evidence_ids,context));
  if(phase==='define')box.append(value('Problem frame',record.problem),value('Success criteria',record.success_criteria.map((c,i)=>(i+1)+'. '+c).join('\n')),text('h3','Interpretations informing the frame'),retainedClaims(record.claim_ids,context),text('h3','Linked uncertainties'),retainedUncertainties(record.uncertainty_ids,context));
  if(phase==='develop')for(const a of record.alternatives)box.append(node('section',{class:'card subtle'},text('h3',a.hypothesis),value('Proposed test',a.test),text('p','This records a proposed test; it is not proof that the test happened.','muted small'),value('Limits and assumptions',a.limitations),text('h3','Interpretations to test'),retainedClaims(a.claim_ids,context),text('h3','Evidence linked to this alternative'),retainedEvidence(a.evidence_ids,context)));
  if(phase==='deliver'){
    const alternatives=context?.developed_alternatives?.alternatives||[];
    const alternative=id=>alternatives.find(a=>a.alternative_id===id)?.hypothesis||'Original alternative context unavailable';
    box.append(value('Research decision',readable(record.decision)),value('Conclusion',record.summary),value('Selected alternative',alternative(record.selected_alternative_id)),value('Conclusion limits',record.limitations));
    for(const evaluation of record.evaluations)box.append(node('section',{class:'card subtle'},text('h3','Recorded evaluation: '+alternative(evaluation.alternative_id)),value('Method actually recorded',evaluation.method),value('Outcome',readable(evaluation.outcome)),value('Evaluation limits',evaluation.limitations),retainedEvidence(evaluation.evidence_ids,context)));
    for(const criterion of record.criterion_assessments||[]){const evaluations=record.evaluations.filter(e=>criterion.evaluation_ids.includes(e.evaluation_id));box.append(node('section',{class:'card subtle'},text('h3',context?.defined_problem?.success_criteria?.[criterion.criterion_index]||'Original criterion context unavailable'),tag(readable(criterion.outcome),criterion.outcome!=='met'),value('Assessment reason',criterion.rationale),value('Linked evaluation methods',evaluations.map(e=>e.method).join('\n')||'No evaluation linked'),retainedEvidence([...new Set(evaluations.flatMap(e=>e.evidence_ids))],context),value('Next research',criterion.next_research)));}
    box.append(text('h3','Interpretations included in this result'),retainedClaims(record.claim_ids,context));
  }
  return box;
}
function visitPanel(review){
  const visit=review.visit;
  const panel=card(phaseNames[visit.phase]+' · saved visit '+visit.visit_id,tag('Inspection only · no phase change'),value('Why this visit',visit.reason));
  if(!visit.record){panel.append(text('p','This visit is open and has no saved findings yet. Inspecting it has not changed the research phase.'));return panel;}
  panel.append(tag(review.current_binding_matches?'Current saved finding':review.is_current_record?'Current record needs review':'Earlier research finding',!review.current_binding_matches));
  if(review.context_status==='verified_original')panel.append(text('p','Sources and interpretations below are the retained versions from when this finding was saved. They are not silently replaced by later edits.','muted small'),value('Saved at',new Date(review.recorded_at).toLocaleString()),value('Recording reason',review.recording_reason));
  else panel.append(text('div','The original recording context is unavailable in the verified journal. The saved record is shown, but current source or interpretation text will not be substituted.','notice'));
  if(review.context)panel.append(node('details',{class:'details'},node('summary',{},'Question and scope when this was saved'),value('Research question',review.context.brief?.text),value('What this research covered',review.context.scope?.text),value('Questions recorded',review.context.questions.map(q=>q.question).join('\n'))));
  panel.append(retainedRecord(visit.phase,visit.record,review.context));
  if(review.previous_record){
    panel.append(node('details',{class:'details'},node('summary',{},'Compare with previous '+phaseNames[visit.phase]+' visit '+review.previous_visit_id),value('Changed record sections',review.changed_fields.length?review.changed_fields.map(readable).join(', '):'No record fields changed'),text('p','Comparison uses the immutable visit records. Inspect the earlier visit separately for its original evidence and interpretation context.','muted small'),
      visit.phase==='define'?node('div',{},value('Previous problem frame',review.previous_record.problem),value('Previous success criteria',review.previous_record.success_criteria.join('\n'))):value('Previous finding',review.previous_record.summary||review.previous_record.notes||(visit.phase==='develop'?review.previous_record.alternatives.map(a=>a.hypothesis).join('\n'):'Saved record'))));
  }
  return panel;
}
