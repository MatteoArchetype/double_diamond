'use strict';
const app=document.getElementById('app');
const params=new URLSearchParams(location.hash.slice(1));
if(params.has('token')){sessionStorage.setItem('dd-token',params.get('token'));history.replaceState(null,'',location.pathname+location.search);}
const token=sessionStorage.getItem('dd-token')||'';
let unavailableCases=[];
let cases=[],view=null,tab='Research',message='',error='',busy=false,creating=false,selectedReport=null;
const drafts=new Map();
const assessmentDrafts=new Map();let renderedKey=null;
let frameSeed=null;
let sourceContext=null,sourceContextId=null,sourceContextPending=false,sourceContextGeneration=0;
let claimRevision=null;
let deliverDraftReader=null;
let developDraftReader=null;
let restoring=false,restoreFile=null,restorePreview=null,restoreConfirmed=false;
let inspectingVisit=null,visitReview=null,reviewPending=false,reviewGeneration=0;
const draftKey=()=>restoring?'restore':creating?'new-case':(view?view.case_id+'/'+view.revision+'/'+tab+'/'+(tab==='Next research'?(agendaBasis()?.report_id||'work'):(inspectingVisit||'work')):'home');
const phases=['discover','define','develop','deliver'];
const readable=v=>({stop_unresolved:'Stopped with uncertainty',recommend:'Recommend the selected alternative',revise:'Revise and return to research',synthetic_only:'Synthetic evidence only',real_only:'Reviewed source evidence',non_synthetic_only:'Reviewed source evidence',mixed:'Mixed evidence origins',none:'No linked evidence',not_met:'Not met',pending_review:'Awaiting review',desk_review:'Desk review'}[v]||String(v).replaceAll('_',' '));
const phaseNames={discover:'Discover',define:'Define',develop:'Develop',deliver:'Deliver'};
const names={discover:'Explore evidence and perspectives',define:'Frame the problem and success criteria',develop:'Explore alternatives and tests',deliver:'Evaluate and decide what comes next'};
const node=(tag,attrs={},...children)=>{const e=document.createElement(tag);for(const [k,v] of Object.entries(attrs)){if(k==='class')e.className=v;else if(k.startsWith('on'))e.addEventListener(k.slice(2).toLowerCase(),v);else if(k==='checked')e.checked=v;else if(k==='value')e.value=v;else e.setAttribute(k,v);}for(const c of children.flat()){if(c!==null&&c!==undefined)e.append(c instanceof Node?c:document.createTextNode(String(c)));}return e;};
const text=(tag,value,cls)=>node(tag,cls?{class:cls}:{},value);
const button=(label,fn,kind='')=>node('button',{type:'button',class:kind,onClick:fn,disabled:busy?'disabled':undefined},label);
// Remove false optional attributes rather than passing executable research content into HTML.
const btn=(label,fn,kind='')=>{const b=button(label,fn,kind);if(!busy)b.removeAttribute('disabled');return b;};
const card=(title,...content)=>node('section',{class:'card'},title?text('h2',title):null,...content);
const tag=(label,warn=false)=>text('span',label,'tag'+(warn?' warn':''));
const value=(label,content)=>node('div',{class:'label-value'},text('span',label),text('div',content||'Not recorded'));
const lines=s=>s.split('\n').map(x=>x.trim()).filter(Boolean);
function field(label,{type='text',value='',hint='',options=[],required=true,rows}={}){let input;if(type==='textarea')input=node('textarea',{rows:rows||3});else if(type==='select'){input=node('select',{},...options.map(o=>node('option',{value:typeof o==='string'?o:o[0]},typeof o==='string'?o:o[1])));}else input=node('input',{type});if(type!=='select'||value!=='')input.value=value;if(required)input.required=true;const wrap=node('label',{class:'field'},label,input,hint?text('small',hint):null);return {wrap,input,get:()=>input.value};}
function choices(title,items,empty='Nothing to choose yet. Add reviewed sources or interpretations first.',selected=[]){const box=node('fieldset',{},node('legend',{},title));const entries=items.map(([id,label])=>{const input=node('input',{type:'checkbox',value:id,checked:selected.includes(id)});box.append(node('label',{class:'check'},input,label));return input;});if(!items.length)box.append(text('p',empty,'muted small'));return {wrap:box,get:()=>entries.filter(e=>e.checked).map(e=>e.value)};}
function form(fields,submit,label='Save research'){const f=node('form',{},...fields.map(x=>x.wrap||x));f.append(node('button',{type:'submit',class:'primary'},label));f.addEventListener('submit',e=>{e.preventDefault();submit();});return f;}
async function api(path,body){const response=await fetch(path,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined,cache:'no-store'});const data=await response.json();if(!response.ok)throw Error(data.error||'The action could not be completed.');return data;}
function resetInspection(){inspectingVisit=null;visitReview=null;reviewPending=false;reviewGeneration++;}
async function openVisit(id){if(busy)return;const generation=++reviewGeneration,cid=view.case_id,revision=view.revision;inspectingVisit=id;visitReview=null;reviewPending=true;tab='Research';error='';render();try{const result=await api('/api/visit?case='+cid+'&visit='+encodeURIComponent(id)+'&revision='+revision);if(generation===reviewGeneration&&view.case_id===cid&&view.revision===revision)visitReview=result;}catch(e){if(generation===reviewGeneration)error=e.message;}finally{if(generation===reviewGeneration){reviewPending=false;render();}}}
async function load(cid){resetSourceContext();resetInspection();view=await api('/api/state?case='+encodeURIComponent(cid));if(frameSeed&&(frameSeed.case_id!==view.case_id||frameSeed.based_on_state_revision!==view.revision))frameSeed=null;if(!view.reports.some(r=>r.report_id===selectedReport))selectedReport=view.reports[0]?.report_id||null;}
async function loadCatalog(){const catalog=await api('/api/catalog');cases=catalog.cases;unavailableCases=catalog.unavailable_cases;}
async function refresh(){await loadCatalog();if(view)await load(view.case_id);render();}
async function perform(action,data){
 if(busy)return;
 const phaseChange=action==='apply_gate'&&view.state.human_gates[data.gate_id]?.gate_type==='phase_transition';
 let applied=false;
 busy=true;error='';message='';render();
 try{
  const result=await api('/api/action',{case_id:view.case_id,request:{action,data,
   expected_revision:view.revision,expected_ledger_revision:view.ledger_revision,request_id:crypto.randomUUID()}});
  message=result.notice||'Saved to this research case.';
  if(action==='propose_transition'||(action==='phase_record'&&result.notice))tab='Approvals';
  await refresh();
  if(phaseChange){
   tab='Research';
   message='Phase change applied. Now in '+phaseNames[view.state.workflow.phase]+'.';
   applied=true;
  }
  return result;
 }catch(e){
  error=e.message;
  try{await refresh();}catch(_){}
  return null;
 }finally{
  busy=false;render();
  if(applied){
   const heading=app.querySelector('#research-work h2');
   if(heading){
    const disclosure=heading.closest('details');
    if(disclosure)disclosure.open=true;
    heading.tabIndex=-1;
    heading.focus();
   }
  }
  document.getElementById('announcer').textContent=error||message;
 }
}
async function copyReviewedFrame(){
if(busy||!visitReview)return;const cid=view.case_id,revision=view.revision,source=visitReview.visit.visit_id;busy=true;error='';render();
try{const draft=await api('/api/frame-draft?case='+cid+'&visit='+encodeURIComponent(source)+'&revision='+revision);if(view.case_id!==cid||view.revision!==revision)throw Error('This case changed. Refresh before preparing a draft.');frameSeed={...draft,case_id:cid};drafts.delete(cid+'/'+revision+'/Research/work');resetInspection();tab='Research';message='The earlier frame is copied into an unsaved draft. Review it and enter a fresh saving reason.';}
catch(e){error=e.message;}finally{busy=false;render();}}
async function choose(cid){busy=true;error='';message='';creating=false;restoring=false;render();try{await load(cid);tab='Research';history.replaceState(null,'','/?case='+cid);}catch(e){error=e.message;}finally{busy=false;render();}}
async function createLearningExample(){
if(busy)return;busy=true;error='';message='';render();
try{const result=await api('/api/example',{kind:'synthetic_learning_example'});await loadCatalog();creating=false;await load(result.case_id);tab='Research';history.replaceState(null,'','/?case='+result.case_id);message='Synthetic learning case created. Its evidence and historical approvals are invented demonstrations, not real findings or human acceptance.';}
catch(e){error=e.message+' Check Your research before trying again; an uncertain response is not retried automatically.';try{await loadCatalog();}catch(_){} }
finally{busy=false;render();}}
function discoverBriefPanel(){
 const p=view.meta.discover_brief;if(!p||typeof p!=='object'||typeof p.summary!=='string'||!Array.isArray(p.sources)||!Array.isArray(p.interpretations)||!Array.isArray(p.gaps))return null;
 const list=items=>node('ul',{},...items.filter(x=>typeof x==='string').map(x=>node('li',{},x)));
 const sourceBlocks=p.sources.filter(x=>x&&typeof x.title==='string'&&typeof x.url==='string').map(x=>{let link=text('span',x.title);try{const u=new URL(x.url);if(['https:','http:'].includes(u.protocol))link=node('a',{href:u.href,target:'_blank',rel:'noopener noreferrer'},x.title);}catch(_){}return node('details',{class:'details'},node('summary',{},x.publisher+' · '+x.title),link,value('Date and section',x.date+' · '+x.location),value('What the source says',x.observation),value('What it does not establish',x.limit));});
 return card('Your question · initial Discover notes',tag('Real public sources · notes for review'),text('p','These are initial notes from real sources, not final findings. They are ready for your review. No source approval or move to the next stage has been recorded.','notice'),text('h3','What the first sources suggest'),text('p',p.summary),text('h3','Working ideas to test'),list(p.interpretations),text('h3','What we still need to learn'),list(p.gaps),text('h3','Sources to review'),text('p','Open each source to see what it supports and its limits. These are real publications, not made-up examples.','muted small'),...sourceBlocks,text('p','Next decision: review these source selections and the limits of this initial interpretation before we save a Discover finding or propose a problem frame.','muted small'));
}
function guidancePanel(){const g=view.guidance;if(!g)return null;return card('Where you are · '+phaseNames[g.phase],tag('Guidance · no action authorized'),text('h3',g.title),text('p',g.detail),g.outdated_research_reviews?text('p',String(g.outdated_research_reviews)+' outdated research review(s) remain in Approvals as history. They do not authorize changed research.','notice'):null,btn(g.navigation.label,()=>{resetInspection();if(g.navigation.tab==='Sources'){openSources();return;}tab=g.navigation.tab;render();if(tab==='Research')document.getElementById('research-work')?.scrollIntoView({block:'start'});},'primary'),node('details',{class:'details'},node('summary',{},'Saved progress and remaining visits'),...g.phases.map(p=>value(phaseNames[p.phase],p.status==='needs_review'?'Needs review':p.status==='saved'?'Saved finding':'Not recorded')),value('Phase visits remaining',String(g.visits_remaining)),text('p',g.budget_note,'muted small')),text('p',g.boundary,'muted small'));}
const fullGuidancePanel=guidancePanel;
guidancePanel=()=>startingDiscover()?null:fullGuidancePanel();
function sourceChoices(){return Object.entries(view.state.evidence).map(([id,e])=>[id,(e.synthetic?'[Synthetic] ':'')+(e.metadata?.title||e.finding.slice(0,70))]);}
function claimChoices(){return Object.entries(view.state.claims).map(([id,c])=>[id,c.claim]);}
function focusHeading(id){
 const heading=document.getElementById(id);
 if(!heading)return;
 heading.tabIndex=-1;
 heading.focus();
}
function focusField(id){
 const control=document.getElementById(id);
 if(!control)return;
 control.scrollIntoView({block:'center'});
 control.focus();
}
function openDetails(id){
 const details=document.getElementById(id);
 if(!details)return;
 details.open=true;
 details.scrollIntoView({block:'start'});
 details.querySelector('input, textarea, select')?.focus();
}
function startingDiscover(){
 const workflow=view?.state?.workflow;
 return workflow?.status==='active'&&workflow.phase==='discover'&&!workflow.records.discover
  &&!Object.keys(view.state.evidence).length;
}
function firstDiscoverPanel(){
 return card('Your first step',
  text('p','Find one source that can help you explore your question. Save one short passage from it, with enough context to understand what the author meant.'),
  node('ol',{class:'onboarding-steps'},
   text('li','Find a publication, add a source link, or upload a file.'),
   text('li','Review one passage with its page number, section, or timestamp.'),
   text('li','Return here to record what you learned and what remains open.')),
  text('p','You can build from there. You do not need to plan every phase before beginning.','muted small'));
}
function firstSourcePanel(){
 return card('Choose how to add your first source',
  text('p','Choose the route that matches the material you have. You will review a specific passage before it becomes evidence in this case.','muted'),
  text('p','Use original, real-world material for your own research. Invented passages belong only in the practice example and remain visibly marked as synthetic.','notice'),
  node('div',{class:'choice-grid'},
   node('div',{class:'choice'},text('h3','Search publications'),text('p','Search Crossref for registered research publications.'),btn('Search publications',()=>focusField('public-search-terms'))),
   node('div',{class:'choice'},text('h3','Add a link'),text('p','Keep a web source you already found for later review.'),btn('Add a source link',()=>openDetails('source-link'))),
   node('div',{class:'choice'},text('h3','Upload a file'),text('p','Work from a PDF, document, transcript, recording, or video saved on this computer.'),btn('Upload a research file',()=>focusHeading('source-upload')))));
}
function exampleGuidePanel(){
 const go=next=>{resetInspection();tab=next;render();app.querySelector('[data-current-research-section]')?.focus();};
 return card('How to explore this example',
  text('p','This is a completed, invented practice case. It is here to show how the workspace keeps evidence, choices and limits connected — not to provide real findings or a template answer.','muted'),
  node('ol',{class:'onboarding-steps'},
   text('li','Read the research trail to see what was recorded in each Double Diamond phase.'),
   text('li','Inspect the passages to see how evidence is marked as synthetic and retained with context.'),
   text('li','Read the saved draft to see the final decision, its limits and what further research would be needed.')),
  node('div',{class:'button-row'},
   btn('Open research trail',()=>go('Research'),'primary'),
   btn('Inspect example evidence',()=>go('Sources')),
   btn('Read saved draft',()=>go('Reports'))));
}
function openSources(){
 tab='Sources';
 render();
 focusHeading('sources-find');
}
function openHome(){
 creating=false;
 restoring=false;
 view=null;
 message='';
 error='';
 resetInspection();
 resetSourceContext();
 history.replaceState(null,'','/');
 render();
 focusHeading('workspace-home-title');
}
function openCreateForm(){
 creating=true;
 restoring=false;
 message='';
 error='';
 render();
 document.getElementById('new-research-question')?.focus();
}
function createForm(){
 const question=field('What do you want to understand?',{type:'textarea'});
 question.input.id='new-research-question';
 const title=field('Case name',{required:false,hint:'Leave blank to use the research question.'});
 const scope=field('What should this research cover?',{type:'textarea',required:false,
  hint:'Describe what to include or leave out. Leave blank to start broad.'});
 const editor=form([question,title,scope],async()=>{
  if(busy)return;
  const prompt=question.get().trim();
  if(!prompt){question.input.value='';question.input.reportValidity();return;}
  const data={
   title:title.get().trim()||prompt,
   question:prompt,
   scope:scope.get().trim()||'Explore evidence and perspectives relevant to the question. Refine the problem and success criteria in Define.',
   max_visits:8,max_alternatives:4
  };
  busy=true;
  error='';
  render();
  let opened=false;
  try{
   const result=await api('/api/cases',data);
   creating=false;
   await loadCatalog();
   await load(result.case_id);
   tab='Research';
   history.replaceState(null,'','/?case='+result.case_id);
   opened=true;
  }catch(e){error=e.message;}
  finally{
   busy=false;
   render();
   if(opened)focusHeading('research-case-title');
   else document.getElementById('new-research-question')?.focus();
  }
 },'Start research');
 return card('Start with a question',text('p','Start exploring in Discover. You can narrow the problem as you learn.','muted'),editor);
}
function sourceLeadCard(lead,prepare,action){
 return node('div',{class:'card subtle'},
  node('a',{href:lead.url,target:'_blank',rel:'noopener noreferrer'},lead.title),
  text('p',lead.publisher,'muted small'),
  btn('Prepare for review',()=>prepare(lead)),action);
}
function sourceSearchPanel(prepareSource){
 const caseId=view.case_id;
 const saved=node('div');
 const savedStatus=node('p',{role:'status',class:'muted small'},'Opening saved sources…');
 let changing=false, changed=false;
 const prepare=lead=>{
  savedStatus.textContent=prepareSource(lead)
   ?'Source details copied into the review form. Check the original and complete the review before saving.'
   :'The review form already contains a draft. Save or clear that draft before preparing another source.';
 };
 const showSaved=leads=>{
  saved.replaceChildren(...leads.map(lead=>sourceLeadCard(lead,prepare,
   btn('Remove saved source',()=>change('remove',{url:lead.url})))));
  if(!leads.length)saved.append(text('p','No sources saved for later yet.','muted small'));
 };
 const change=async(action,lead)=>{
  if(changing)return false;
  changing=true;
  changed=true;
  savedStatus.textContent='Updating saved sources…';
  try{
   const response=await api('/api/source-shortlist',{case_id:caseId,action,lead});
   showSaved(response.leads);
   savedStatus.textContent=action==='keep'?'Source saved for later review.':'Saved source removed.';
   return true;
  }catch(e){savedStatus.textContent=e.message;return false;}
  finally{changing=false;}
 };
 api('/api/source-shortlist?case='+encodeURIComponent(caseId)).then(response=>{
  if(!changed){showSaved(response.leads);savedStatus.textContent='';}
 }).catch(e=>{if(!changed)savedStatus.textContent=e.message;});

 const title=field('Source title');
 const url=field('Source link',{type:'url'});
 const publisher=field('Publisher or author',{required:false});
 title.input.maxLength=500;
 url.input.maxLength=4096;
 publisher.input.maxLength=300;
 const manual=form([title,url,publisher],async()=>{
  const submit=manual.querySelector('button');
  if(submit.disabled)return;
  submit.disabled=true;
  const lead={title:title.get(),url:url.get(),publisher:publisher.get()};
  try{
   if(await change('keep',lead)){
    for(const [name,item] of Object.entries({title,url,publisher})){
     if(item.get()===lead[name])item.input.value='';
    }
   }
  }finally{submit.disabled=false;}
 },'Save source for later');
 const query=field('Public search terms',{hint:'Try a few words from your question. Only the terms you enter here are sent to Crossref.'});
 query.input.id='public-search-terms';
 query.input.maxLength=300;
 const status=node('p',{role:'status',class:'muted small'});
 const results=node('div');
 const search=form([query],async()=>{
  const submit=search.querySelector('button');
  if(submit.disabled)return;
  submit.disabled=true;
  results.replaceChildren();
  status.textContent='Searching Crossref…';
  try{
   const response=await api('/api/source-search',{query:query.get()});
   status.textContent=response.results.length?'Publication leads. Open an original to check its relevance and context.':'No publications found. Try different terms or add a source you already have.';
   for(const lead of response.results){
    results.append(sourceLeadCard(lead,prepare,
     btn('Save for later',()=>change('keep',lead))));
   }
  }catch(e){status.textContent=e.message;}
  finally{submit.disabled=false;}
 },'Search publications');
 return node('div',{},
  node('section',{id:'source-search'},card('Find public research sources',text('p','This tool uses Crossref to search registered research publications, including articles, books and reports. Enter search terms below to find publications, then open the originals to review them.','muted'),search,status,results)),
  card('Sources saved for later',text('p','Save links from search results or add a source you already found. Entering details here saves the source in this case for later review. To find a paper, use Search publications above. Review and approve a passage before using it as evidence. Case checkpoint downloads exclude these saved links.','muted small'),savedStatus,saved,node('details',{class:'details',id:'source-link'},node('summary',{},'Save a source you already found'),text('p','Enter the title and link of a source you want to remember.','muted small'),manual)));
}
function documentPassageSearch(paragraphs,notice,usePassage){
 const query=field('Words or phrase to find');
 query.input.maxLength=200;
 const matches=node('div',{role:'status'});
 const search=form([query],()=>{
  const term=query.get().trim().toLocaleLowerCase();
  if(!term){matches.replaceChildren(text('p','Enter words to search for.'));return;}
  const hits=paragraphs.filter(item=>item.text.toLocaleLowerCase().includes(term));
  matches.replaceChildren(text('p',hits.length
   ?'Showing '+Math.min(hits.length,10)+' of '+hits.length+' matching paragraphs.'
   :'No matching paragraphs. Try a different word or phrase.','muted small'));
  for(const item of hits.slice(0,10))matches.append(card(item.location||'Paragraph '+item.number,
   node('blockquote',{},item.text),btn('Use passage and details',()=>usePassage(item))));
 },'Find passages');
 return node('div',{},text('h3','Search this document'),
  notice?text('p',notice,'muted small'):null,
  paragraphs.length?search:text('p','No searchable passages were found.','muted small'),
  matches);
}
function savedDocumentReview(item,context){
 const title=field('Source title',{value:item.metadata.title||context.filename});
 const publisher=field('Publisher or author',{value:item.metadata.publisher});
 const date=field('Publication date',{value:item.metadata.date,required:false});
 const group=field('Shared source group',{hint:'Use the same group for sources with a shared origin.'});
 const rationale=field('Why keep this passage?',{type:'textarea'});
 const confirmed=node('input',{type:'checkbox',required:'required'});
 const synthetic=node('input',{type:'checkbox'});
 const editor=form([title,publisher,date,group,rationale,
  node('label',{class:'check'},synthetic,'This document is a synthetic example.'),node('label',{class:'check'},confirmed,
  'I checked this passage in the original file or recording and approve it as evidence.')],
  ()=>perform('document_source',{document_id:item.id,paragraph:item.number,passage:item.text,
   title:title.get(),publisher:publisher.get(),published_at:date.get().trim()||null,
   group:group.get(),rationale:rationale.get(),synthetic:synthetic.checked,confirmed:confirmed.checked}),'Approve saved passage');
 return node('details',{class:'details','data-local-document-review':''},
  node('summary',{},'Review as evidence from this file'),
  text('p','The app retains the matching passage, nearby text and a fingerprint of the saved file. No public link is needed.','muted small'),editor);
}
function savedPassageContext(caseId,item){
 const content=node('div');
 const details=node('details',{class:'details'},node('summary',{},'See surrounding paragraphs'),content);
 let loading=false,loaded=false;
 details.addEventListener('toggle',async()=>{
  if(!details.open||loading||loaded)return;
  loading=true;
  content.replaceChildren(text('p','Opening source context…','muted small'));
  try{
   const query=new URLSearchParams({case:caseId,document:item.id,paragraph:item.number});
   const context=await api('/api/documents?'+query);
   const paragraphs=context.paragraphs.map(paragraph=>{
    const match=paragraph.number===context.number;
    return node('div',{class:match?'card subtle':'label-value'},
     text('h4',(match?'Matching passage · ':'')+(paragraph.location||'Paragraph '+paragraph.number)),
     node('blockquote',{},paragraph.text));
   });
   content.replaceChildren(
    text('p','Nearby extracted text from '+context.filename+'. Check its location against the original file.','muted small'),
    context.passage_notice?text('p',context.passage_notice,'notice'):null,
    ...paragraphs,savedDocumentReview(item,context));
   loaded=true;
  }catch(e){
   content.replaceChildren(text('p',e.message+' Close and reopen this section to retry.','notice'));
  }finally{loading=false;}
 });
 return details;
}
function caseDocumentSearch(caseId,openDocument,prepareSource){
 const query=field('Words or phrase across saved documents');
 const mode=field('Search mode',{type:'select',options:[
  ['phrase','Exact phrase'],['keywords','Keywords ranked by match']
 ]});
 query.input.maxLength=200;
 const status=node('p',{role:'status',class:'muted small'});
 const results=node('div');
 const search=form([query,mode],async()=>{
  const submit=search.querySelector('button');
  if(submit.disabled)return;
  submit.disabled=true;
  results.replaceChildren();
  status.textContent='Searching saved documents…';
  try{
   const found=await api('/api/document-search',{case_id:caseId,query:query.get(),mode:mode.get()});
   status.textContent=!found.document_count?'Save a document or transcript in this case to search it.'
    :found.total?'Showing '+found.matches.length+' of '+found.total+' matching paragraphs.'
    :'No matching paragraphs. Try another word or phrase.';
   if(found.incomplete.length)results.append(text('p',
    'Search could not cover all text in: '+found.incomplete.join(', ')+'.','notice'));
   for(const item of found.matches){
    const location=item.filename+' · '+(item.location||'Main-body paragraph '+item.number);
    results.append(card(location,item.matched_keywords
     ?text('p','Matched keywords: '+item.matched_keywords.join(', '),'muted small'):null,
     node('blockquote',{},item.text),
     savedPassageContext(caseId,item),
     btn('Open saved document',()=>openDocument(item)),
     btn('Use passage and details',()=>{
      const draft={...item.metadata,passage:item.text,location};
      status.textContent=prepareSource(draft)
       ?'Passage copied for review. Check the original and add its context before approving.'
       :'The review form already contains a draft. Save or clear it before copying a passage.';
     })));
   }
  }catch(e){status.textContent=e.message;}
  finally{submit.disabled=false;}
 },'Search saved documents');
 return node('div',{},search,status,results);
}
function originalDocumentDownload(caseId,digest){
 const status=node('p',{role:'status',class:'muted small'});
 const download=btn('Download original file',async()=>{
  if(download.disabled)return;
  download.disabled=true;
  status.textContent='Checking the saved file…';
  try{
   const query=new URLSearchParams({case:caseId,document:digest});
   const response=await fetch('/api/document-original?'+query,{headers:{Authorization:'Bearer '+token}});
   if(!response.ok){
    const failure=await response.json();
    throw Error(failure.error||'The original file could not be opened.');
   }
   const encoded=response.headers.get('Content-Disposition')?.split("filename*=UTF-8''")[1];
   const filename=encoded?decodeURIComponent(encoded):'source.docx';
   const url=URL.createObjectURL(await response.blob());
   node('a',{href:url,download:filename}).click();
   setTimeout(()=>URL.revokeObjectURL(url),1000);
   status.textContent='Original file sent to browser downloads.';
  }catch(e){status.textContent=e.message+' Approved text remains in its evidence record.';}
  finally{download.disabled=false;}
 });
 return node('div',{},download,status);
}
function documentPreviewPanel(prepareSource){
 const endpoint='/api/documents?case='+encodeURIComponent(view.case_id);
 const file=node('input',{type:'file',accept:'.docx,.pdf,.txt,.md,.vtt,.srt,.mp4,.mov,.webm,.mp3,.m4a,.wav,.ogg',required:'required'});
 const keep=node('input',{type:'checkbox','data-document-keep':''});
 const status=node('p',{role:'status',class:'muted small'});
 const libraryStatus=node('p',{role:'status',class:'muted small'});
 const preview=node('div'),library=node('div');
 let reading=false;
 file.addEventListener('change',()=>{preview.replaceChildren();status.textContent='';});
 const showPreview=(result,filename)=>{
  const details=result.metadata;
  preview.replaceChildren(text('h3',filename),value('Title',details.title),
   value('Author',details.publisher),value('Publication date',details.date),value('Original link',details.url));
  if(Object.values(details).some(Boolean))preview.append(btn('Use these details',()=>{
   status.textContent=prepareSource(details)
    ?'Details copied to the review form. Check the original before approving.'
    :'The review form already contains a draft. Save or clear it before copying these details.';
  }));
  preview.append(documentPassageSearch(result.paragraphs,result.passage_notice,item=>{
   const draft={...details,passage:item.text,location:filename+' · '+(item.location||'Main-body paragraph '+item.number)};
   status.textContent=prepareSource(draft)
    ?'Passage and details copied. Check the original and add its context before approving.'
    :'The review form already contains a draft. Save or clear it before copying a passage.';
  }));
 };
 const openDocument=async item=>{
  if(reading)return;
  reading=true;
  status.textContent='Opening saved document…';
  preview.replaceChildren();
  try{
   const result=await api(endpoint+'&document='+encodeURIComponent(item.id));
   showPreview(result,result.filename);
   preview.append(originalDocumentDownload(view.case_id,result.id));
   if(result.media&&!result.transcript_sha256){
    const transcript=node('input',{type:'file',accept:'.vtt,.srt',required:'required'});
    const transcriptStatus=node('p',{role:'status'});
    const attach=form([node('label',{class:'field'},'Timestamped transcript (.vtt or .srt)',transcript)],async()=>{
     const selected=transcript.files[0];
     if(!selected)return;
     if(selected.size>2*1024*1024){transcriptStatus.textContent='Transcripts support up to 2 MiB.';return;}
     const submit=attach.querySelector('button');
     submit.disabled=true;
     try{
      const response=await fetch('/api/document-transcript?'+new URLSearchParams({case:view.case_id,document:result.id,filename:selected.name}),
       {method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/octet-stream'},body:selected});
      const attached=await response.json();
      if(!response.ok)throw Error(attached.error);
      await openDocument(item);
     }catch(e){transcriptStatus.textContent=e.message;}
     finally{submit.disabled=false;}
    },'Attach transcript');
    preview.append(text('p','Check transcript words and timestamps against the original recording before approving evidence. The saved transcript is retained with this recording.'),attach,transcriptStatus);
   }
   status.textContent='Saved document opened.';
   preview.scrollIntoView({block:'start'});
  }catch(e){status.textContent=e.message;}
  finally{reading=false;}
 };
 let listRequest=0;
 const refreshLibrary=async()=>{
  const request=++listRequest;
  try{
   const result=await api(endpoint);
   if(request!==listRequest)return;
   libraryStatus.textContent=result.documents.length?'':'No saved documents in this case.';
   library.replaceChildren(...result.documents.map(item=>btn('Open '+item.filename,()=>openDocument(item))));
  }catch(e){if(request===listRequest)libraryStatus.textContent=e.message;}
 };
 refreshLibrary();
 const upload=form([node('label',{class:'field'},'Research file',file),
  node('label',{class:'check'},keep,'Keep a local copy in this case')],async()=>{
  if(reading)return;
  const selected=file.files[0];
  if(!selected)return;
  const save=keep.checked;
  reading=true;
  file.disabled=true;
  keep.disabled=true;
  const submit=upload.querySelector('button');
  submit.disabled=true;
  preview.replaceChildren();
  status.textContent=save?'Saving and reading document…':'Reading document details…';
  try{
   if(selected.size>64*1024*1024)throw Error('Choose a file no larger than 64 MiB. Word files support up to 8 MiB.');
   const response=await fetch(save?endpoint+'&filename='+encodeURIComponent(selected.name):'/api/document-preview?filename='+encodeURIComponent(selected.name),{
    method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/octet-stream'},body:selected
   });
   const result=await response.json();
   if(!response.ok)throw Error(result.error);
   showPreview(result,result.filename||selected.name);
   if(save){reading=false;await openDocument({id:result.id});reading=true;}
   status.textContent=save?'Document saved in this case.':'Check the details and fill in anything missing.';
   if(save)await refreshLibrary();
  }catch(e){status.textContent=e.message;}
  finally{reading=false;file.disabled=false;keep.disabled=false;submit.disabled=false;}
 },'Read document details');
 return node('section',{id:'source-upload'},card('Upload research files',
  text('p','Upload PDF, Word (.docx), text (.txt), Markdown (.md), transcripts (.vtt, .srt), video (.mp4, .mov, .webm) or audio (.mp3, .m4a, .wav, .ogg). Files stay on this computer and are excluded from case checkpoints. Maximum 64 MiB per file, 8 MiB for Word and 2 MiB for text.','muted'),
  text('p','PDF search uses embedded text. Scanned PDFs need OCR first. Save a recording, then attach its WebVTT or SRT transcript to search timestamped passages. Automatic transcription is unavailable.' ,'muted small'),
  upload,text('h3','Saved research files'),libraryStatus,library,
  caseDocumentSearch(view.case_id,openDocument,prepareSource),status,preview));
}
function draftControls(route,context,editor,readForm,writeForm,heading,description,hasDraft){
 const encode=value=>JSON.stringify(value,(_,item)=>
  item&&typeof item==='object'&&!Array.isArray(item)
   ?Object.fromEntries(Object.keys(item).sort().map(key=>[key,item[key]])):item);
 const {case_id,...query}=context;
 const endpoint=route+'?'+new URLSearchParams({case:case_id,...query});
 const status=node('p',{role:'status',class:'muted small'},'Checking for a saved draft…');
 let saved=null,working=false;
 const update=()=>{
  const current=readForm();
  const hasText=hasDraft?hasDraft(current):Object.values(current).some(value=>typeof value==='string'?value.trim():Array.isArray(value)?value.length:value);
  const matches=saved?.draft&&encode(current)===encode(saved.draft);
  save.disabled=busy||working||!saved||!hasText||!!matches;
  reopen.disabled=busy||working||!saved?.draft||!!matches;
  remove.disabled=busy||working||!saved?.draft;
  refresh.disabled=busy||working;
  save.textContent=saved?.draft?'Replace saved draft':'Save draft for later';
  reopen.textContent=hasText?'Replace form with saved draft':'Open saved draft';
  if(!working&&saved)status.textContent=matches?'Draft saved on this computer.'
   :hasText?'Unsaved draft. Save it to reopen after a reload.'
   :saved.draft?'A saved draft is available for this case.':'No saved draft for this case.';
 };
 const run=async operation=>{
  if(working)return;
  working=true;
  update();
  let failure;
  try{saved=await operation();}
  catch(e){failure=e.message;}
  finally{working=false;update();if(failure)status.textContent=failure;}
 };
 const store=draft=>run(()=>api(route,{...context,expected_version:saved.version,draft}));
 const save=btn('Save draft for later',()=>store(readForm()));
 const reopen=btn('Open saved draft',()=>{writeForm(saved.draft);update();});
 const remove=btn('Remove saved draft',()=>store(null));
 const refresh=btn('Refresh saved draft',()=>run(()=>api(endpoint)));
 editor.addEventListener('input',update);
 editor.addEventListener('change',update);
 editor.addEventListener('click',update);
 run(()=>api(endpoint));
 return node('div',{},text('h3',heading),text('p',description,'muted small'),
  save,reopen,remove,refresh,status);
}
function sourceReviewAids(fields,synthetic){
 const groupSuggestion=node('div');
 const original=node('div');
 const updateGroup=()=>{
  groupSuggestion.replaceChildren();
  const publisher=fields.publisher.get().trim().toLowerCase();
  if(!publisher||fields.group.get().trim())return;
  const groups=new Set(Object.values(view.state.evidence).filter(record=>
   record.synthetic===synthetic.checked&&record.metadata?.publisher?.trim().toLowerCase()===publisher
   &&record.independence_cluster).map(record=>record.independence_cluster));
  if(groups.size!==1)return;
  const [group]=groups;
  groupSuggestion.append(text('p','This publisher already has a source group in this case. Reuse it if the sources share an origin.','muted small'),
   btn('Use group '+group,()=>{
    fields.group.input.value=group;
    fields.group.input.dispatchEvent(new Event('input',{bubbles:true}));
    fields.group.input.focus();
   }));
 };
 const updateLink=()=>{
  original.replaceChildren();
  try{
   const url=new URL(fields.url.get());
   if(['https:','http:'].includes(url.protocol)&&!url.username&&!url.password)
    original.append(node('a',{href:url.href,target:'_blank',rel:'noopener noreferrer'},'Open original source in a new tab'));
  }catch(_){}
 };
 fields.publisher.input.setAttribute('data-source-aids','');
 fields.publisher.input.addEventListener('input',updateGroup);
 fields.publisher.input.addEventListener('change',()=>{updateGroup();updateLink();});
 fields.group.input.addEventListener('input',updateGroup);
 synthetic.addEventListener('change',updateGroup);
 fields.url.input.addEventListener('input',updateLink);
 return {groupSuggestion,original};
}
function sourceForm(){
 const fields={
  title:field('Source title'),publisher:field('Publisher or author'),url:field('Source URL',{type:'url'}),
  published_at:field('Publication date',{required:false}),
  group:field('Shared source group',{hint:'Give sources with the same origin the same label, such as “Company A annual report”. This helps you recognise when several passages come from one underlying source.'}),
  passage:field('Exact passage you want to retain',{type:'textarea',hint:'Copy a short excerpt word for word from the source or transcript.'}),
  location:field('Exact location',{hint:'Tell yourself where to find the excerpt again, such as page 12, section 3 or 00:04:20–00:04:45 in a recording.'}),
  snapshot:field('Paste the surrounding text from the original source',{type:'textarea',
   hint:'Include the passage and the text around it so you can check what the author meant in context.'}),
  rationale:field('Why is this source suitable for the case?',{type:'textarea',hint:'Explain how the passage helps explore your research question. Mention any limitations you noticed.'})
 };
 const synthetic=node('input',{type:'checkbox'});
 const confirmed=node('input',{type:'checkbox',required:'required','data-reset-on-render':''});
 const aids=sourceReviewAids(fields,synthetic);
 const readForm=()=>({
  ...Object.fromEntries(Object.entries(fields).map(([key,item])=>[key,item.get()])),
  synthetic:synthetic.checked
 });
 const writeForm=draft=>{
  for(const [key,item] of Object.entries(fields))item.input.value=draft[key];
  synthetic.checked=draft.synthetic;
  confirmed.checked=false;
  fields.publisher.input.dispatchEvent(new Event('change'));
 };
 const editor=form([fields.title,fields.publisher,fields.url,aids.original,fields.published_at,
  fields.group,aids.groupSuggestion,fields.passage,fields.location,fields.snapshot,fields.rationale,
  node('label',{class:'check'},synthetic,'This is a synthetic example, not real-world evidence.'),
  text('p','Use this only for an invented practice passage. Synthetic evidence stays distinct from reviewed sources and cannot establish a real-world finding.','muted small'),
  node('label',{class:'check'},confirmed,'I opened the original, checked the excerpt and its location, and approve saving this passage as evidence.')
 ],()=>{
  const {published_at,...draft}=readForm();
  perform('source',{...draft,...(published_at.trim()?{published_at:published_at.trim()}:{}),confirmed:confirmed.checked});
 },'Approve and save source');
 const review=card(null,editor,draftControls('/api/source-draft',{case_id:view.case_id},editor,readForm,writeForm,
  'Keep an unfinished review','One draft per case, stored on this computer and excluded from case backups. Saving a draft does not approve evidence.'));
 const prepareSource=lead=>{
  if(Object.values(fields).some(item=>item.get().trim())||synthetic.checked||confirmed.checked)return false;
  writeForm({title:lead.title,publisher:lead.publisher,url:lead.url,published_at:lead.date||'',
   group:'',passage:lead.passage||'',location:lead.location||'',snapshot:'',rationale:'',synthetic:false});
  editor.dispatchEvent(new Event('change'));
  review.scrollIntoView({block:'start'});
  fields.passage.input.focus();
  return true;
 };
 return {find:node('div',{},sourceSearchPanel(prepareSource),documentPreviewPanel(prepareSource)),review};
}
function uncertaintyChoices(){return Object.entries(view.state.uncertainties).map(([id,u])=>[id,u.question+' · '+readable(u.status)]);}
function claimForm(){
 const claim=field('Your working interpretation',{type:'textarea'});
 const kind=field('Interpretation type',{type:'select',options:[
  ['descriptive','Description'],['causal','Possible cause'],['generalisation','Possible generalisation']
 ]});
 const evidence=choices('Evidence informing this interpretation',sourceChoices());
 evidence.wrap.setAttribute('data-interpretation-evidence','');
 const comparison=node('section',{},text('h3','Compare selected passages'));
 const passages=node('div');
 comparison.append(passages);
 const updateComparison=()=>{
  const selected=evidence.get();
  if(!selected.length){
   passages.replaceChildren(text('p','Select evidence above to see its wording and source details here.','muted small'));
   return;
  }
  const groups=new Map();
  let syntheticCount=0;
  for(const id of selected){
   const record=view.state.evidence[id];
   if(record.synthetic)syntheticCount++;
   const group=record.independence_cluster;
   if(group)groups.set(group,(groups.get(group)||0)+1);
  }
  const shared=[...groups].filter(([,count])=>count>1).map(([group,count])=>group+' ('+count+')');
  passages.replaceChildren(
   text('p',selected.length+' selected · '+(selected.length-syntheticCount)+' reviewed source · '+syntheticCount+' synthetic','muted small'),
   shared.length?text('p','Shared source groups: '+shared.join(', ')+'. Check whether passages come from the same underlying source.','notice'):null,
   retainedEvidence(selected,view.state,{expanded:true}));
 };
 evidence.wrap.addEventListener('change',updateComparison);
 updateComparison();
 const uncertainties=choices('Uncertainties affecting this interpretation',uncertaintyChoices(),
  'No uncertainties are recorded. Record an open question below; none will be inferred.');
 const reason=field('Why record this interpretation?',{type:'textarea'});
 const editor=form([claim,kind,evidence,comparison,uncertainties,reason],()=>perform('claim',{
  claim:claim.get(),claim_type:kind.get(),evidence_ids:evidence.get(),
  uncertainty_ids:uncertainties.get(),rationale:reason.get()
 }),'Save advisory interpretation');
 editor.setAttribute('data-interpretation-form','');
 return card('Add a working interpretation',
  text('p','Interpretations remain advisory. A source link or uncertainty link does not confirm an explanation.','muted'),editor);
}
function uncertaintyForm(){const question=field('What remains unknown?',{type:'textarea'}),claims=choices('Interpretations affected by this question',claimChoices(),'No interpretations yet. The open question can be saved on its own.'),reason=field('Why does this uncertainty matter?',{type:'textarea'});return card('Record an open research question',text('p','This saves an uncertainty, not evidence or a conclusion. Links are explicit and advisory. Saving does not resolve it, change the phase or approve research. Up to 99 interpretations may be linked.','muted'),form([question,claims,reason],()=>perform('uncertainty',{question:question.get(),claim_ids:claims.get(),rationale:reason.get()}),'Save open uncertainty'));}
function uncertaintyPanel(){const entries=Object.entries(view.state.uncertainties);return card('Questions still requiring judgment',text('p','Uncertainties and their saved statuses are research records. They are not source evidence or proof that a question has been answered. Choose relevant questions explicitly when framing Define.','muted'),...entries.map(([id,u])=>{const linked=Object.values(view.state.claims).filter(c=>(c.material_uncertainties||[]).includes(id));return node('div',{class:'card subtle'},text('h3',u.question),tag(readable(u.status),['open','unresolved'].includes(u.status)),value('Interpretations linked to this uncertainty',linked.map(c=>c.claim).join('\n')||'None explicitly linked'),u.resolution_basis?value('Recorded basis',u.resolution_basis):null);}),entries.length?null:text('p','No uncertainties have been recorded.','muted'));}

function developFrameReference(frame){
 if(!frame)return null;
 return card('Define frame for these alternatives',
  view.currency.define===false?text('p','The saved frame is stale. Review the changes before relying on it.','notice'):null,
  value('Problem to address',frame.problem),
  text('h3','Saved success criteria'),
  node('ol',{},...frame.success_criteria.map(criterion=>node('li',{},criterion))),
  text('p','Use the criteria to plan how you would compare alternatives. Completed evaluations are recorded in Deliver.','muted small'));
}
function developEditor(w){
 const seed=drafts.get(draftKey())?.develop,rows=[],container=node('div');
 const summary=node('div');
 const comparison=node('details',{class:'details'},node('summary',{},'Compare alternative drafts'),summary);
 const refreshComparison=()=>{
  if(!comparison.open)return;
  summary.replaceChildren(...rows.map((row,index)=>node('section',{class:'card subtle'},
   text('h3','Alternative '+(index+1)),value('Explanation or option',row.hypothesis.get()),
   value('Proposed test',row.test.get()),value('Limits and assumptions',row.limits.get()),
   text('p',row.claims.get().length+' linked interpretations · '+row.evidence.get().length+' linked passages','muted small'))));
 };
 comparison.addEventListener('toggle',refreshComparison);
 container.addEventListener('input',refreshComparison);
 container.addEventListener('change',refreshComparison);
 const add=(initial)=>{if(rows.length>=w.max_alternatives)return;const number=rows.length+1,label='Alternative '+number;
  const hypothesis=field('Explanation or option for '+label,{type:'textarea',value:initial?.hypothesis||''});
  const claims=choices('Interpretations informing '+label,claimChoices(),'Record a working interpretation first. Select at least one explicitly.',initial?.claim_ids||[]);
  const evidence=choices('Evidence linked to '+label,sourceChoices(),'No reviewed evidence is available. No passage will be inferred.',initial?.evidence_ids||[]);
  const test=field('Proposed test for '+label,{type:'textarea',value:initial?.test||'',hint:'Describe what you would investigate. This does not record a completed test or authorize external work.'});
  const limits=field('Limits and assumptions for '+label,{type:'textarea',value:initial?.limitations||''});
  const wrap=node('fieldset',{'data-alternative-row':'true'},node('legend',{},label),hypothesis.wrap,claims.wrap,evidence.wrap,test.wrap,limits.wrap);
  rows.push({hypothesis,claims,evidence,test,limits,wrap});container.append(wrap);updateButtons();refreshComparison();
 };
 const addButton=btn('Add another alternative',()=>add()),removeButton=btn('Remove last alternative',()=>{if(rows.length<=2)return;rows.pop().wrap.remove();updateButtons();refreshComparison();});
 const updateButtons=()=>{addButton.disabled=busy||rows.length>=w.max_alternatives;removeButton.disabled=busy||rows.length<=2;};
 for(const initial of seed?.alternatives||[null,null])add(initial);
 const get=()=>({alternatives:rows.map((r,i)=>({alternative_id:'option-'+(i+1),hypothesis:r.hypothesis.get(),claim_ids:r.claims.get(),evidence_ids:r.evidence.get(),test:r.test.get(),limitations:r.limits.get()}))});
 developDraftReader=get;
 return {wrap:node('div',{'data-develop-editor':'true'},developFrameReference(w.records.define),text('p','Keep the basis of each competing alternative distinct. Select interpretations and passages separately for each one. Selecting an interpretation does not automatically select its evidence. Proposed tests are plans, not completed evaluations or permission to act.','notice'),container,addButton,removeButton,comparison,text('p','At least two alternatives; this case permits up to '+w.max_alternatives+'. New rows start empty. Removing the last unsaved row does not change earlier rows.','muted small')),get};
}

function deliverCriteriaCheck(record,criteria){
 const byId=new Map(record.evaluations.map(item=>[item.evaluation_id,item]));
 const issues=[];
 for(const criterion of record.criterion_assessments){
  const label='Criterion '+(criterion.criterion_index+1)+' · '+criteria[criterion.criterion_index];
  if(!criterion.rationale.trim())issues.push(label+': explain the outcome.');
  if(criterion.outcome!=='met'&&!criterion.next_research.trim())issues.push(label+': add a next research step.');
  if(criterion.outcome==='unknown')continue;
  const required=criterion.outcome==='met'?'supported':'unsupported';
  const matching=criterion.evaluation_ids.some(id=>{
   const evaluation=byId.get(id);
   return evaluation?.alternative_id===record.selected_alternative_id
    &&evaluation.outcome===required&&evaluation.evidence_ids.length>0;
  });
  if(!matching)issues.push(label+': link an evaluation marked '+required+' with at least one evidence passage.');
 }
 if(record.decision==='recommend'){
  if(record.criterion_assessments.some(item=>item.outcome!=='met'))
   issues.push('A recommendation requires all success criteria to be met.');
  if(!record.evaluations.some(item=>item.alternative_id===record.selected_alternative_id&&item.outcome==='supported'))
   issues.push('A recommendation requires an evaluation marked supported for the selected alternative.');
 }
 return issues;
}
function deliverEditor(w){
 const seed=drafts.get(draftKey())?.deliver;
 const alternatives=w.records.develop?.alternatives||[];
 const byId=new Map(alternatives.map(alternative=>[alternative.alternative_id,alternative]));
 const options=alternatives.map(a=>[a.alternative_id,a.hypothesis]);
 const selected=field('Alternative selected for the research decision',{type:'select',options,value:seed?.selected_alternative_id||''});
 const rows=[],container=node('div'),criterionRows=[];
 const coverage=node('div');
 const refreshCoverage=()=>{
  const counts=new Map();
  for(const row of rows){
   const id=row.alternative.get();
   if(row.method.get().trim())counts.set(id,(counts.get(id)||0)+1);
  }
  coverage.replaceChildren(...alternatives.map(alternative=>{
   const count=counts.get(alternative.alternative_id)||0;
   return value(alternative.hypothesis,count?count+' draft '+(count===1?'evaluation has':'evaluations have')+' a method entered':'No evaluation method entered');
  }));
 };
 container.addEventListener('input',refreshCoverage);
 const refreshLinks=()=>{for(const c of criterionRows){const chosen=c.links?.get()||c.initial||[];c.links=choices('Evaluations informing this criterion',rows.filter(r=>r.alternative.get()===selected.get()).map(r=>[r.id,r.label]),'No evaluation currently tests the selected alternative. Add one or change an evaluation alternative.',chosen);c.initial=null;c.slot.replaceChildren(c.links.wrap);}};
 const add=(initial)=>{if(rows.length>=20)return;const number=rows.length+1,id='evaluation-'+number,label='Evaluation '+number;
  const alternative=field('Alternative tested in '+label,{type:'select',options,value:initial?.alternative_id||selected.get()});
  const method=field('Method used in '+label,{type:'textarea',value:initial?.method||'',hint:'Record an evaluation actually carried out. A proposed test is not a completed experiment.'});
  const evidence=choices('Evidence for '+label,sourceChoices(),undefined,initial?.evidence_ids||[]);
  const outcome=field('Outcome of '+label,{type:'select',options:['inconclusive','supported','unsupported'],value:initial?.outcome||'inconclusive'});
  const limits=field('Limits of '+label,{type:'textarea',value:initial?.limitations||''});
  const plan=node('div');
  const refreshPlan=()=>{
   const saved=byId.get(alternative.get());
   plan.replaceChildren(...(saved?[
    value('Proposed test in Develop',saved.test),
    value('Assumptions and limits in Develop',saved.limitations)
   ]:[]));
  };
  refreshPlan();
  const reference=node('details',{class:'details'},node('summary',{},'See what was planned in Develop'),plan);
  const wrap=node('fieldset',{'data-evaluation-row':'true'},node('legend',{},label),alternative.wrap,reference,method.wrap,evidence.wrap,outcome.wrap,limits.wrap);
  rows.push({id,label,alternative,method,evidence,outcome,limits,wrap});container.append(wrap);
  alternative.input.addEventListener('change',()=>{refreshPlan();refreshLinks();refreshCoverage();});
  refreshLinks();updateButtons();refreshCoverage();
 };
 const addButton=btn('Add another evaluation',()=>add()),removeButton=btn('Remove last evaluation',()=>{if(rows.length<=1)return;rows.pop().wrap.remove();refreshLinks();updateButtons();refreshCoverage();});
 const updateButtons=()=>{addButton.disabled=busy||rows.length>=20;removeButton.disabled=busy||rows.length<=1;};
 for(const initial of seed?.evaluations||[null])add(initial);
 const criteriaNames=w.records.define?.success_criteria||[];
 const criteria=criteriaNames.map((criterion,i)=>{const previous=seed?.criterion_assessments?.find(c=>c.criterion_index===i);
  const status=field('Outcome for criterion '+(i+1),{type:'select',options:['unknown','met','not_met'].map(v=>[v,readable(v)]),value:previous?.outcome||'unknown'});
  const rationale=field('Reason for criterion '+(i+1),{type:'textarea',value:previous?.rationale||''});
  const next=field('Next research for criterion '+(i+1),{type:'textarea',required:false,value:previous?.next_research||'',hint:'Required when this criterion is not met or unknown.'});
  const slot=node('div');const c={i,status,rationale,next,slot,initial:previous?.evaluation_ids||[]};criterionRows.push(c);
  return node('fieldset',{},node('legend',{},criterion),status.wrap,rationale.wrap,slot,next.wrap);
 });
 selected.input.addEventListener('change',refreshLinks);refreshLinks();
 const decision=field('Research decision',{type:'select',options:[['stop_unresolved','Stop this pass with uncertainty'],['revise','Revise and return to earlier research'],['recommend','Recommend the selected alternative']],value:seed?.decision||'stop_unresolved'});
 const summary=field('What does the research support?',{type:'textarea',value:seed?.summary||''});
 const claims=choices('Interpretations included in the result',claimChoices(),undefined,seed?.claim_ids||[]);
 const limits=field('Limits of the conclusion',{type:'textarea',value:seed?.limitations||''});
 const get=()=>({selected_alternative_id:selected.get(),evaluations:rows.map(r=>({evaluation_id:r.id,alternative_id:r.alternative.get(),method:r.method.get(),evidence_ids:r.evidence.get(),outcome:r.outcome.get(),limitations:r.limits.get()})),decision:decision.get(),summary:summary.get(),claim_ids:claims.get(),limitations:limits.get(),criterion_assessments:criterionRows.map(c=>({criterion_index:c.i,outcome:c.status.get(),evaluation_ids:c.links.get(),rationale:c.rationale.get(),next_research:c.next.get()}))});
 deliverDraftReader=get;
 const checks=node('div',{role:'status'});
 const refreshChecks=()=>{
  const issues=deliverCriteriaCheck(get(),criteriaNames);
  checks.replaceChildren(issues.length
   ?node('ul',{},...issues.map(issue=>node('li',{},issue)))
   :text('p','No missing items in these checks. Review the evidence and remaining Deliver fields before saving.','muted small'));
 };
 const wrap=node('div',{'data-deliver-editor':'true'},selected.wrap,
  node('details',{class:'details'},node('summary',{},'Review evaluation draft coverage'),
   view.currency.develop===false?text('p','The Develop record is stale. Review changes before relying on its test plans.','notice'):null,
   text('p','Counts show where a draft method has been entered. Check what was actually done before saving.','muted small'),coverage),
  text('p','Keep each evaluation separate. Link a criterion only to evaluations of the selected alternative. Added rows do not run tests or approve research.','notice'),container,addButton,removeButton,text('p','Up to 20 recorded evaluations. Removing the last row also clears its criterion links.','muted small'),...criteria,decision.wrap,
  card('Check criteria and recommendation',
   text('p','This checks draft entries and evidence links. It does not assess evidence quality or save a decision.','muted small'),checks),
  summary.wrap,claims.wrap,limits.wrap);
 wrap.addEventListener('input',refreshChecks);
 wrap.addEventListener('change',refreshChecks);
 addButton.addEventListener('click',refreshChecks);
 removeButton.addEventListener('click',refreshChecks);
 refreshChecks();
 return {wrap,get};
}

function defineEvidenceContext(claims){
 const context=view.state;
 const pairs=assessmentPairs();
 const content=node('div');
 const update=()=>{
  const selected=claims.get();
  if(!selected.length){
   content.replaceChildren(text('p','Select an interpretation above to see its linked evidence and uncertainties.','muted small'));
   return;
  }
  content.replaceChildren(...selected.map(id=>{
   const claim=context.claims[id];
   const linked=pairs.filter(pair=>pair.claim.claim_id===id);
   const uncertainties=(claim.material_uncertainties||[]).map(key=>context.uncertainties[key]).filter(Boolean);
   return node('section',{class:'card subtle'},
    text('h4',claim.claim),
    retainedEvidence(claim.evidence_ids,context),
    linkedPassageAssessments(linked),
    text('h4','Uncertainties linked to this interpretation'),
    uncertainties.length?node('ul',{},...uncertainties.map(item=>node('li',{},
     item.question+' · '+readable(item.status)))):text('p','No uncertainties are linked.','muted small'));
  }));
 };
 claims.wrap.setAttribute('data-define-claims','');
 claims.wrap.addEventListener('change',update);
 update();
 return node('section',{},text('h3','Evidence behind the selected interpretations'),
  text('p','Use this context to frame the problem. Select uncertainties separately if they belong in the frame.','muted small'),content);
}
function phaseForm(){const w=view.state.workflow,phase=w.phase;const seed=frameSeed&&frameSeed.case_id===view.case_id&&frameSeed.based_on_state_revision===view.revision&&frameSeed.target_visit_id===w.visits.at(-1).visit_id?frameSeed.record:null;const reason=field('Reason for saving this research',{type:'textarea'});let fields=[],build,visitDraft;
if(phase==='discover'){
 const evidence=choices('Reviewed evidence to explore',sourceChoices());
 const notes=field('What have you observed?',{type:'textarea'});
 const perspectives=field('Perspectives and gaps — one per line',{type:'textarea',
  hint:'Name at least two. Be explicit about people or perspectives you have not studied.'});
 const limits=field('Limits of this discovery',{type:'textarea'});
 fields=[evidence,notes,perspectives,limits];
 const textFields={notes,perspectives,limitations:limits,rationale:reason};
 const read=()=>({evidence_ids:evidence.get(),...Object.fromEntries(
  Object.entries(textFields).map(([key,item])=>[key,item.get()]))});
 const restore=draft=>{
  for(const [key,item] of Object.entries(textFields))item.input.value=draft[key];
  const selected=new Set(draft.evidence_ids);
  for(const input of evidence.wrap.querySelectorAll('input'))input.checked=selected.has(input.value);
 };
 visitDraft=editor=>draftControls('/api/discover-draft',{case_id:view.case_id,visit:w.visits.at(-1).visit_id},
  editor,read,restore,'Keep unfinished Discover notes',
  'Drafts are saved on this computer for this Discover visit and excluded from case backups. Saving a draft does not record a finding.');
 build=()=>({evidence_ids:evidence.get(),notes:notes.get(),perspectives:lines(perspectives.get()),limitations:limits.get()});
}
if(phase==='define'){
 const problem=field('What problem should this research focus on?',{type:'textarea',value:seed?.problem||''});
 const claims=choices('Interpretations informing the frame',claimChoices(),undefined,seed?.claim_ids||[]);
 const criteria=field('What would count as success? One criterion per line',{type:'textarea',value:seed?.success_criteria.join('\n')||''});
 const uncertainties=choices('Uncertainties to include explicitly',Object.entries(view.state.uncertainties).map(([id,u])=>[id,u.question]),
  'No uncertainties are recorded. None will be added automatically.',seed?.uncertainty_ids||[]);
 fields=[problem,claims,defineEvidenceContext(claims),criteria,uncertainties];
 const read=()=>({problem:problem.get(),criteria:criteria.get(),rationale:reason.get(),
  claim_ids:claims.get(),uncertainty_ids:uncertainties.get()});
 const restore=draft=>{
  problem.input.value=draft.problem;
  criteria.input.value=draft.criteria;
  reason.input.value=draft.rationale;
  for(const [field,ids] of [[claims,draft.claim_ids],[uncertainties,draft.uncertainty_ids]]){
   const selected=new Set(ids);
   for(const input of field.wrap.querySelectorAll('input'))input.checked=selected.has(input.value);
   field.wrap.dispatchEvent(new Event('change'));
  }
 };
 visitDraft=editor=>draftControls('/api/define-draft',{case_id:view.case_id,visit:w.visits.at(-1).visit_id},
  editor,read,restore,'Keep an unfinished problem frame',
  'Drafts stay on this computer for this Define visit and are excluded from case backups. Check restored selections against the current research before recording a frame.');
 build=()=>({problem:problem.get(),claim_ids:claims.get(),uncertainty_ids:uncertainties.get(),
  success_criteria:lines(criteria.get())});
}
if(phase==='develop'||phase==='deliver'){
 const phaseEditor=phase==='develop'?developEditor(w):deliverEditor(w);
 fields=[phaseEditor];
 build=phaseEditor.get;
 reason.input.id='phase-draft-reason';
 const read=()=>({record:build(),rationale:reason.get()});
 const restore=draft=>{
  render({[phase]:draft.record});
  const input=document.getElementById('phase-draft-reason');
  input.value=draft.rationale;
  input.dispatchEvent(new Event('input',{bubbles:true}));
  input.focus();
 };
 const hasDraft=({record,rationale})=>{
  if(rationale.trim())return true;
  if(phase==='develop')return record.alternatives.length>2||record.alternatives.some(item=>
   item.hypothesis.trim()||item.test.trim()||item.limitations.trim()||item.claim_ids.length||item.evidence_ids.length);
  const first=w.records.develop?.alternatives?.[0]?.alternative_id||'';
  return record.selected_alternative_id!==first||record.decision!=='stop_unresolved'
   ||record.summary.trim()||record.limitations.trim()||record.claim_ids.length||record.evaluations.length>1
   ||record.evaluations.some(item=>item.alternative_id!==first||item.method.trim()||item.limitations.trim()
    ||item.outcome!=='inconclusive'||item.evidence_ids.length)
   ||record.criterion_assessments.some(item=>item.outcome!=='unknown'||item.rationale.trim()
    ||item.next_research.trim()||item.evaluation_ids.length);
 };
 visitDraft=editor=>draftControls('/api/later-phase-draft',
  {case_id:view.case_id,visit:w.visits.at(-1).visit_id,phase},editor,read,restore,
  'Keep unfinished '+phaseNames[phase]+' work',
  'Drafts stay on this computer for this visit and are excluded from case backups. Saving a draft does not record a finding or decision.',hasDraft);
}
const prior=phase==='define'?[...w.visits].reverse().find(v=>v.phase==='define'&&v.record):null;const pendingFrame=phase==='define'?Object.values(view.state.human_gates).find(g=>g.gate_type==='material_reframing'&&['pending_review','approved'].includes(g.status)&&g.action?.payload?.visit_id===w.visits.at(-1).visit_id&&view.gate_context_current?.[g.gate_id]===true):null;
const editor=form([...fields,reason],()=>{const record=build();if(phase==='develop'){const missing=record.alternatives.findIndex(a=>!a.claim_ids.length);if(missing>=0){error='Choose at least one interpretation for Alternative '+(missing+1)+'.';render();return;}}perform('phase_record',{record,rationale:reason.get()});},'Save '+phaseNames[phase]+' record');
return card(names[phase],pendingFrame?node('div',{class:'notice'},text('p',pendingFrame.status==='approved'?'An approved frame is saved and awaiting application.':'A revised frame is saved and awaiting review.'),btn('Continue saved frame review',()=>{tab='Approvals';render();})):null,seed?text('div','Unsaved draft copied from '+frameSeed.source_visit_id+'. Check the current interpretations and uncertainties. No approval was copied.','notice'):null,prior?btn('Review previous saved frame',()=>openVisit(prior.visit_id)):null,text('p','Save one record for this visit. To revise it later, request a return to this phase.','muted small'),editor,visitDraft?visitDraft(editor):null);}
function reviewCard(gid,g){const a=g.action?.payload||{},isFrame=g.gate_type==='material_reframing',current=view.gate_context_current?.[gid]===true;let proposed=null,why=g.proposal_rationale;try{const parsed=JSON.parse(why);if(parsed.proposed_record){proposed=parsed.proposed_record;why=parsed.reason;}}catch(_){}const c=card(isFrame?'Review revised problem frame':'Review phase change',node('div',{class:'tags'},tag(readable(g.status),g.status==='pending_review')),value('Reason',why));if(!current)c.append(tag('Outdated research context',true),text('p','Research has changed since this proposal. Its recorded decision is retained, but it cannot authorize the current research. Review the saved findings and request a new change.','notice'),btn('Review current research',()=>{tab='Research';render();}));if(isFrame&&proposed){const prior=[...view.state.workflow.visits].reverse().find(v=>v.phase==='define'&&v.record);if(prior&&current)c.append(value('Previous problem',prior.record.problem),value('Previous success criteria',prior.record.success_criteria.join('\n')),value('Changed sections',['problem','success_criteria','claim_ids','uncertainty_ids'].filter(k=>JSON.stringify(prior.record[k])!==JSON.stringify(proposed[k])).map(readable).join(', ')),btn('Inspect preceding saved frame',()=>openVisit(prior.visit_id)));c.append(value('Proposed problem',proposed.problem),value('Success criteria',proposed.success_criteria.join('\n')),value(current?'Interpretations informing this frame':'Interpretation references in the original proposal',proposed.claim_ids.map(id=>current?(view.state.claims[id]?.claim||id):id).join('\n')),value(current?'Uncertainties included':'Uncertainty references in the original proposal',proposed.uncertainty_ids.map(id=>current?(view.state.uncertainties[id]?.question||id):id).join('\n')||'None recorded'));}else c.append(value('From',phaseNames[a.from_phase]||a.from_phase),value('To',phaseNames[a.to_phase]||a.to_phase),value('Why return or progress',a.reason));if(g.status==='pending_review'){const reason=field(current?'Your approval or rejection reason':'Your rejection reason',{type:'textarea'});if(current)c.append(form([reason],()=>perform('decide_gate',{gate_id:gid,decision:'approve',rationale:reason.get()}),'Approve this exact change'));c.append(...(current?[]:[reason.wrap]),btn('Reject this proposal',()=>{if(!reason.get().trim()){reason.input.focus();return;}perform('decide_gate',{gate_id:gid,decision:'reject',rationale:reason.get()});},'danger'));}if(g.status==='approved'&&current)c.append(text('p','Approval is saved. Applying it will change this case; stale or changed content will be refused.','muted small'),btn('Apply approved change',()=>perform('apply_gate',{gate_id:gid,rationale:'Operator explicitly applied the reviewed change'}),'primary'));return c;}
function fullResearchView(){const w=view.state.workflow;const left=node('div');if(inspectingVisit){left.append(btn('Return to current research',()=>{resetInspection();render();}));if(reviewPending)left.append(card('Opening original saved context',text('p','Checking this visit against its retained research history…','muted')));else if(visitReview){left.append(visitPanel(visitReview));if(visitReview.visit.phase==='define'&&visitReview.visit.record&&w.status==='active'&&w.phase==='define'&&!w.records.define){left.append(card('Prepare a revised frame',text('p','Copying replaces any unsaved Define form. It does not save a finding or copy an approval. Changed frames still require separate human review.','muted small'),visitReview.context_status==='verified_original'?btn('Replace current Define form with this frame',()=>copyReviewedFrame(),'primary'):text('p','Original context is unavailable. Write a fresh draft instead.','notice')));}}else left.append(card('Saved context could not be opened',text('p','Refresh saved research and inspect the visit again.','muted')));}else if(w.status==='active'&&!w.records[w.phase])left.append(phaseForm());else{const current=w.records[w.phase];left.append(card(w.status==='active'?'This phase is saved':'This research pass is '+w.status,value('Current phase',phaseNames[w.phase]),current?value('Recorded finding',current.summary||current.problem||current.notes||'Competing alternatives are recorded.'):null,text('p','Earlier findings and their review history are retained.','muted small'),btn('Inspect full saved finding',()=>openVisit(w.visits.at(-1).visit_id))));}
const right=node('div');const next=phases[phases.indexOf(w.phase)+1];const targets=w.status!=='active'?phases.slice(0,phases.indexOf(w.phase)+1):[...(next&&w.records[w.phase]?[next]:[]),...phases.slice(0,phases.indexOf(w.phase)+1)];const target=field('Where should you work next?',{type:'select',options:targets.map(p=>[p,phaseNames[p]])}),reason=field('Why is this the right next step?',{type:'textarea',hint:'Explain what you learned, what remains uncertain, or why an earlier phase needs another visit.'});const reopening=w.status!=='active';right.append(card(reopening?'Reopen research carefully':'Choose the next research step',text('p',reopening?'Returning keeps the completed history intact and proposes a new visit in an earlier phase. It does not reopen the case automatically.':'Move forward after saving the current phase, or return to an earlier phase when new evidence changes the picture. Saved findings remain in the history.','muted'),form([target,reason],()=>perform('propose_transition',{target:target.get(),rationale:reason.get()}),'Request review of this change'),text('p','A named reviewer must approve the exact request, and it must then be applied separately in Approvals.','muted small')));
const stop=field('Why pause, finish, or escalate?',{type:'textarea',hint:'Describe the limit, unresolved question, or reason further review is needed.'});if(w.status==='active'){const canFinish=w.phase==='deliver'&&!!w.records.deliver;right.append(card('Pause or finish this research pass',text('p','Finishing preserves the research as it is and allows a draft to be prepared. It does not approve publication or turn a finding into a final fact.','muted'),canFinish?form([stop],()=>perform('finish',{outcome:'stopped',rationale:stop.get()}),'Finish this research pass'):node('div',{class:'notice'},text('p','Finishing becomes available after you save a Deliver record. You can still escalate incomplete research for further review.')),canFinish?btn('Escalate for further review',()=>{if(stop.get().trim())perform('finish',{outcome:'escalated',rationale:stop.get()});else stop.input.focus();}):node('div',{},stop.wrap,btn('Escalate for further review',()=>{if(stop.get().trim())perform('finish',{outcome:'escalated',rationale:stop.get()});else stop.input.focus();}),text('p','Escalation preserves incomplete work without claiming a conclusion.','muted small'))));}
const visits=node('div');for(const v of w.visits)visits.append(node('details',{class:'details'},node('summary',{},v.visit_id+' · '+phaseNames[v.phase]+(v.record?' · saved':' · open')),value('Why this visit',v.reason),v.record?value('Original finding',v.record.summary||v.record.problem||v.record.notes||'Competing alternatives recorded'):null,btn('Inspect '+phaseNames[v.phase]+' visit '+v.visit_id,()=>openVisit(v.visit_id))));right.append(card('Research history',visits));return node('div',{class:'grid',id:'research-work'},left,right);}
function researchView(){
 if(!startingDiscover())return fullResearchView();
 return node('div',{id:'research-work'},firstDiscoverPanel(),node('details',{class:'details'},node('summary',{},'Research controls and saved history'),guidancePanel(),fullResearchView()));
}
function resetSourceContext(){sourceContext=null;sourceContextId=null;sourceContextPending=false;sourceContextGeneration++;}
async function openSourceContext(id){if(busy)return;const generation=++sourceContextGeneration,cid=view.case_id,revision=view.revision;sourceContextId=id;sourceContext=null;sourceContextPending=true;error='';render();try{const result=await api('/api/source-context?case='+cid+'&evidence='+encodeURIComponent(id)+'&revision='+revision);if(generation===sourceContextGeneration&&view.case_id===cid&&view.revision===revision)sourceContext=result;}catch(e){if(generation===sourceContextGeneration)error=e.message;}finally{if(generation===sourceContextGeneration){sourceContextPending=false;render();focusHeading('source-context-title');}}}
function sourceContextPanel(){if(!sourceContextId)return null;const panel=card(null,node('h2',{id:'source-context-title'},'Retained source context'),btn('Close source context',()=>{resetSourceContext();render();focusHeading('sources-approved');}));if(sourceContextPending){panel.append(text('p','Checking the retained intake records…'));return panel;}if(!sourceContext){panel.append(text('p','Context could not be opened. Refresh saved research and try again.','notice'));return panel;}const c=sourceContext;const digest=c.evidence.metadata?.document_sha256;if(digest)panel.append(originalDocumentDownload(view.case_id,digest));panel.append(tag(c.evidence.synthetic?'Synthetic example':'Source record',c.evidence.synthetic),text('p',c.boundary,'notice'),value('Retained passage',c.evidence.finding),value('Exact location',c.evidence.exact_location));if(c.snapshot)panel.append(value('Source text retained at intake',c.snapshot.text),value('Retained snapshot location',c.snapshot.location));else panel.append(text('p','No source text snapshot was retained for this evidence. The passage alone is not a substitute for its original context.','notice'));if(c.review)panel.append(value('Recorded intake reviewer',c.review.reviewer),value('Recorded intake decision',c.review.decision),value('Recorded reason',c.review.rationale));else panel.append(text('p','No original intake review payload is available for this historical evidence.','notice'));return panel;}
function prepareInterpretationWithEvidence(selected){
 if(busy)return;
 resetSourceContext();
 tab='Interpretations';
 error='';
 message='Selected passages added to the interpretation draft. Review the links before saving.';
 render();
 const editor=app.querySelector('[data-interpretation-form]');
 const evidence=editor.querySelector('[data-interpretation-evidence]');
 for(const input of evidence.querySelectorAll('input')){
  if(selected.has(input.value))input.checked=true;
 }
 evidence.dispatchEvent(new Event('change'));
 editor.scrollIntoView({block:'start'});
 editor.querySelector('textarea').focus();
}
function reviewedEvidenceSearch(evidence){
 const query=field('Keywords in reviewed passages');
 query.input.maxLength=200;
 const includeSynthetic=node('input',{type:'checkbox','data-reset-on-render':''});
 const status=node('p',{role:'status',class:'muted small'});
 const results=node('div');
 const words=value=>value.toLowerCase().match(/[\p{L}\p{N}]+/gu)||[];
 const search=form([query,node('label',{class:'check'},includeSynthetic,'Include synthetic practice evidence')],()=>{
  results.replaceChildren();
  const phrase=query.get().trim().toLowerCase();
  const terms=[...new Set(words(phrase))];
  if(!terms.length){status.textContent='Enter at least one word or number.';return;}
  const matches=[];
  for(const record of evidence){
   if(record.synthetic!==false&&!(includeSynthetic.checked&&record.synthetic===true))continue;
   const tokens=new Set(words(record.finding));
   const matched=terms.filter(term=>tokens.has(term));
   if(matched.length)matches.push({record,matched,phraseMatch:record.finding.toLowerCase().includes(phrase)});
  }
  matches.sort((a,b)=>b.matched.length-a.matched.length||Number(b.phraseMatch)-Number(a.phraseMatch));
  status.textContent=matches.length?'Showing '+Math.min(matches.length,10)+' of '+matches.length+' matching passages.'
   :'No matching reviewed passages. Try different keywords.';
  if(!matches.length)return;
  const selected=new Set();
  const prepare=btn('Use selected passages in an interpretation',()=>prepareInterpretationWithEvidence(selected));
  prepare.disabled=true;
  for(const {record,matched} of matches.slice(0,10)){
   const title=record.metadata?.title||'Reviewed passage';
   const pick=node('input',{type:'checkbox','data-reset-on-render':''});
   pick.addEventListener('change',()=>{
    if(pick.checked)selected.add(record.evidence_id);
    else selected.delete(record.evidence_id);
    prepare.disabled=!selected.size;
   });
   results.append(card(title,tag(record.synthetic?'Synthetic practice evidence':'Reviewed source',record.synthetic),
    text('p','Matched keywords: '+matched.join(', '),'muted small'),node('blockquote',{},record.finding),
    value('Exact location',record.exact_location),
    node('label',{class:'check'},pick,'Select passage from '+title),
    btn('Inspect context for '+(record.metadata?.title||record.evidence_id),()=>openSourceContext(record.evidence_id))
   ));
  }
  results.append(prepare);
 },'Search reviewed evidence');
 includeSynthetic.addEventListener('change',()=>{
  results.replaceChildren();
  status.textContent='Run the search again to apply this setting.';
 });
 return card('Find reviewed evidence',text('p','Search approved passages in this case. Results show the original wording and its location.','muted'),search,status,results);
}
function sourcesView(){
 const evidence=Object.values(view.state.evidence);
 const {find,review}=sourceForm();
 const firstSource=!evidence.length;
 const readyForDiscover=evidence.length&&view.state.workflow.phase==='discover'&&!view.state.workflow.records.discover;
 const continueDiscover=readyForDiscover?card('Your reviewed evidence is ready',
  text('p','You can now record what this evidence helps you explore in Discover, or use it to create clearly labelled working interpretations. Neither action treats the passage as proof or moves the research forward automatically.','muted'),
  node('div',{class:'button-row'},
   btn('Record what you learned in Discover',()=>{tab='Research';render();document.getElementById('research-work')?.scrollIntoView({block:'start'});},'primary'),
   btn('Create working interpretations',()=>{tab='Interpretations';render();app.querySelector('[data-current-research-section]')?.focus();}))) : null;
 const approved=node('section',{},node('h2',{id:'sources-approved'},'3. Approved evidence'),sourceContextPanel(),
  evidence.length?reviewedEvidenceSearch(evidence):card('No reviewed evidence yet',
   text('p','A passage appears here after you check its original context and approve it.','muted')),
  ...evidence.map(e=>card(e.metadata?.title||'Retained evidence',
   tag(e.synthetic?'Synthetic example':'Source record',e.synthetic),node('blockquote',{},e.finding),
   value('Exact location',e.exact_location),value('Publisher',e.metadata?.publisher),
   value(e.metadata?.document_sha256?'Saved file reference':'Source URL',e.metadata?.url),
   value('Shared source group',e.independence_cluster),
   btn('Inspect saved context for '+(e.metadata?.title||e.evidence_id),()=>openSourceContext(e.evidence_id)))));
 return node('div',{},firstSource?firstSourcePanel():null,node('nav',{'aria-label':'Source steps',class:'tabs'},
  btn('Find a source',()=>focusHeading('sources-find')),
  btn('Review a passage',()=>focusHeading('sources-review')),
  btn('Approved evidence',()=>focusHeading('sources-approved'))),
  continueDiscover,
  node('div',{class:'grid'},
   node('section',{},node('h2',{id:'sources-find'},'1. Find a source'),find),
   node('section',{},node('h2',{id:'sources-review'},'2. Review a passage'),
    text('p','Save a passage or short excerpt from a document or transcript. Use this section to check an excerpt and save it as evidence for your research.','muted'),
    node('ol',{},
     text('li','Open the original source and choose an excerpt relevant to your research question.'),
     text('li','Add the source details, copy the exact words, and record the page or timestamp. Include nearby text to preserve the author’s meaning.'),
     text('li','Explain why the excerpt is useful. After checking it against the original, confirm your review and select Approve and save source.')),
    node('details',{class:'details'},node('summary',{},'See an example'),
     text('p','Invented example for illustration: if a report discusses AI and insurance managers, you might retain a sentence about time spent checking automated decisions. Record its page number, include the paragraph around it, and explain how it helps you explore changes in managers’ work. Mark invented material as synthetic if you save it.','muted small')),
    text('p','Approved passages appear in Approved evidence, ready to inform your interpretations. You can save an unfinished review as a draft and return to it later.','muted small'),review)),
  approved);
}

function contradictionForm(){
 const options=[['','Choose an interpretation'],...claimChoices()];
 const first=field('First interpretation in this disagreement',{type:'select',options});
 const second=field('Second interpretation in this disagreement',{type:'select',options});
 const issue=field('Where do these interpretations disagree?',{type:'textarea'}),reason=field('Why retain this disagreement?',{type:'textarea'});
 const f=form([first,second,issue,reason],()=>{if(first.get()===second.get()){error='Choose two distinct interpretations for a disagreement.';render();return;}perform('contradiction',{claim_a:first.get(),claim_b:second.get(),issue:issue.get(),rationale:reason.get()});},'Save unresolved disagreement');
 if(Object.keys(view.state.claims).length<2)f.querySelector('button[type=submit]').disabled=true;
 return card('Keep a disagreement visible',text('p','Choose two existing interpretations and describe the tension. This records an unresolved advisory disagreement. It does not choose a winner, change either interpretation or create evidence.','muted'),Object.keys(view.state.claims).length<2?text('p','Record at least two working interpretations first.','notice'):null,f);
}
function disagreementOrigin(claim,context){const ids=claim?.evidence_ids||[];if(!ids.length)return 'No linked evidence';if(ids.some(id=>!context.evidence?.[id]))return 'Evidence context incomplete';const flags=ids.map(id=>context.evidence[id].synthetic===true);return flags.every(Boolean)?'Synthetic evidence only':flags.some(Boolean)?'Mixed evidence origins':'Reviewed source evidence';}
function contradictionsPanel(records,context,historical=false){
 const box=card(historical?'Disagreements at report creation':'Recorded disagreements',text('p',historical?'These interpretations and source passages are the versions retained in this report. Current edits are not substituted. Saved statuses are not independent validation.':'These are recorded tensions, not proof that one explanation is correct. Current interpretations and their linked evidence are shown here; saved reports retain their own versions. Resolution is not offered by this form.','muted'));
 for(const r of Object.values(records||{})){
  const section=card(r.issue,tag('Advisory disagreement'),tag(readable(r.disposition||'unresolved'),['open','unresolved'].includes(r.disposition||'unresolved')));
  for(const [label,id] of [['First interpretation',r.claim_a],['Second interpretation',r.claim_b]]){
   const claim=context.claims?.[id];section.append(value(label,claim?.claim||'Retained interpretation context is unavailable.'),claim?tag(disagreementOrigin(claim,context),disagreementOrigin(claim,context)==='Synthetic evidence only'):null,claim?value('Recorded interpretation status',readable(claim.status||claim.disposition)):null,claim?retainedEvidence(claim.evidence_ids,context):null);
  }
  if(r.resolution_basis)section.append(value('Saved resolution basis',r.resolution_basis));box.append(section);
 }
 if(!Object.keys(records||{}).length)box.append(text('p','No disagreements have been recorded. This does not establish agreement.','muted'));
 return box;
}
function reportEvidenceContext(report){
 const context={claims:{},evidence:{},sources:{}};
 for(const packed of report.claims||[]){context.claims[packed.claim_id]=packed.interpretation;for(const item of packed.evidence||[]){context.evidence[item.evidence_id]=item.evidence;if(item.source)context.sources[item.evidence.source_id]=item.source;}}
 for(const item of report.evaluation_evidence||[]){
  context.evidence[item.evidence_id]=item.evidence;
  if(item.source)context.sources[item.evidence.source_id]=item.source;
 }
 return context;
}
function startClaimRevision(id){const c=view.state.claims[id];if(!view.revisable_claim_ids.includes(id))return;claimRevision={case_id:view.case_id,revision:view.revision,claim_id:id,draft:{claim:c.claim,evidence_ids:[...(c.evidence_ids||[])],uncertainty_ids:[...(c.material_uncertainties||[])]},rationale:''};message='Unsaved advisory revision. Review the wording and links before saving.';error='';render();}
function claimHistory(c){const history=c.belief_history||[];return node('details',{class:'details'},node('summary',{},'Previous recorded versions ('+history.length+')'),text('p','Earlier wording and evidence links are retained. These versions are not new findings or approvals. Uncertainty references remain in the audit; current question text is not substituted here.','muted small'),...history.map(h=>{const previous=h.previous||{};return node('section',{class:'card subtle'},value('Earlier interpretation',previous.claim),value('Reason for the subsequent change',h.reason),value('Earlier type',readable(previous.claim_type)),value('Earlier recorded status',readable(previous.status||previous.disposition)),value('Uncertainty links then',String((previous.material_uncertainties||[]).length)),retainedEvidence(previous.evidence_ids,view.state));}));}
function claimRevisionPanel(){
 const m=claimRevision;if(!m||m.case_id!==view.case_id)return null;
 const cancel=()=>{claimRevision=null;message='Unsaved revision closed. Check saved research for any completed changes.';render();};
 if(m.revision!==view.revision)return card('Revision draft needs a fresh review',text('p','This unsaved draft targets an earlier case revision and has not been reapplied. Inspect the latest saved interpretation before preparing a new revision. An uncertain response must not be retried automatically.','notice'),value('Unsaved wording retained for reference',m.draft.claim),retainedEvidence(m.draft.evidence_ids,view.state),value('Uncertainty links selected in this draft',String(m.draft.uncertainty_ids.length)),value('Unsaved revision reason',m.rationale),btn('Close unsaved revision',cancel));
 if(!view.revisable_claim_ids.includes(m.claim_id))return card('This interpretation uses its host review workflow',btn('Close unsaved revision',cancel));
 const before=view.state.claims[m.claim_id],wording=field('Revised advisory interpretation',{type:'textarea',value:m.draft.claim}),evidence=choices('Evidence explicitly linked after this revision',sourceChoices(),undefined,m.draft.evidence_ids),uncertainties=choices('Uncertainties explicitly linked after this revision',uncertaintyChoices(),'No uncertainties are recorded.',m.draft.uncertainty_ids),reason=field('Why revise this interpretation?',{type:'textarea',value:m.rationale});
 const editor=node('div',{'data-claim-revision-editor':'true'},value('Current saved interpretation',before.claim),value('Fixed interpretation type',readable(before.claim_type)),value('Fixed recorded status',readable(before.status)),text('p','This revises advisory wording and explicit links only. Prior versions remain. It cannot accept a claim, change its type or decision status, approve a frame or move a phase. Existing assessments and saved findings may become stale.','notice'),form([wording,evidence,uncertainties,reason],async()=>{const payload={claim_id:m.claim_id,claim:wording.get(),evidence_ids:evidence.get(),uncertainty_ids:uncertainties.get(),rationale:reason.get()};const saved=await perform('claim_revision',payload);if(saved&&claimRevision===m){claimRevision=null;message='Advisory revision saved. Earlier versions remain; review any stale assessments or findings.';render();}},'Save advisory revision'),btn('Close unsaved revision',cancel));
 const sync=()=>{m.draft={claim:wording.get(),evidence_ids:evidence.get(),uncertainty_ids:uncertainties.get()};m.rationale=reason.get();};editor.addEventListener('input',sync);editor.addEventListener('change',sync);
 return card('Revise an advisory draft',editor);
}
function assessLinkedPassage(claimId,evidenceId){
 if(busy)return;
 tab='Evidence fit';
 error='';
 message='';
 render();
 const pair=app.querySelector('[data-assessment-pair]');
 pair.value=JSON.stringify([claimId,evidenceId]);
 pair.dispatchEvent(new Event('change'));
 pair.scrollIntoView({block:'center'});
 pair.focus();
}
const assessmentStatusLabels={
 current:'Current assessment recorded',stale:'Earlier assessment is stale',missing:'Awaiting assessment'
};
function assessmentPairs(){
 const statuses=new Map();
 for(const {assessment,current} of view.assessments){
  const key=JSON.stringify([assessment.claim_id,assessment.evidence_id]);
  if(current||!statuses.has(key))statuses.set(key,current?'current':'stale');
 }
 const pairs=[];
 for(const claim of Object.values(view.state.claims)){
  for(const id of claim.evidence_ids||[]){
   const record=view.state.evidence[id];
   if(!record)continue;
   const key=JSON.stringify([claim.claim_id,id]);
   const title=(record.synthetic?'[Synthetic] ':'')+(record.metadata?.title||'Retained passage');
   pairs.push({claim,id,key,title,status:statuses.get(key)||'missing'});
  }
 }
 return pairs;
}
function linkedPassageAssessments(pairs){
 const actions=pairs.map(({claim,id,title,status})=>node('div',{class:'label-value'},
  value(title,assessmentStatusLabels[status]),
  btn('Assess passage from '+title,()=>assessLinkedPassage(claim.claim_id,id))));
 return actions.length?node('div',{},text('h3','Evidence fit for linked passages'),...actions):null;
}
function claimsView(){
 const byClaim=new Map();
 for(const pair of assessmentPairs()){
  if(!byClaim.has(pair.claim.claim_id))byClaim.set(pair.claim.claim_id,[]);
  byClaim.get(pair.claim.claim_id).push(pair);
 }
 const readyForDiscover=Object.keys(view.state.claims).length&&view.state.workflow.phase==='discover'&&!view.state.workflow.records.discover;
 const continueDiscover=readyForDiscover?card('Bring these ideas back to Discover',
  text('p','Working interpretations help you compare possible explanations. Record what the current evidence supports, what remains uncertain and which ideas still need testing before asking to move beyond Discover.','muted'),
  btn('Record the Discover finding',()=>{tab='Research';render();document.getElementById('research-work')?.scrollIntoView({block:'start'});},'primary')):null;
 return node('div',{},continueDiscover,node('div',{class:'grid'},node('div',{},text('p','Preparing a revision replaces any other unsaved interpretation revision in this page. Saved versions remain unchanged.','muted small'),...Object.values(view.state.claims).map(c=>card('Working interpretation',text('p',c.claim),node('div',{class:'tags'},tag('Advisory'),tag((c.evidence_ids||[]).length?((c.evidence_ids||[]).every(id=>view.state.evidence[id]?.synthetic)?'Synthetic evidence only':(c.evidence_ids||[]).some(id=>view.state.evidence[id]?.synthetic)?'Mixed evidence origins':'Reviewed source evidence'):'No linked evidence',(c.evidence_ids||[]).length>0&&(c.evidence_ids||[]).every(id=>view.state.evidence[id]?.synthetic))),value('Status',c.status),value('Explicitly linked uncertainties',(c.material_uncertainties||[]).map(id=>view.state.uncertainties[id]?.question||id).join('\n')||'None explicitly linked'),text('h3','Linked evidence in current research'),retainedEvidence(c.evidence_ids,view.state),linkedPassageAssessments(byClaim.get(c.claim_id)||[]),claimHistory(c),view.revisable_claim_ids.includes(c.claim_id)?btn('Prepare revision of '+c.claim,()=>startClaimRevision(c.claim_id)):text('p','This record uses its existing host review workflow.','muted small'))),uncertaintyPanel(),contradictionsPanel(view.state.contradictions,view.state)),node('div',{},claimRevisionPanel(),claimForm(),uncertaintyForm(),contradictionForm())));}

const assessmentLabels={strength:'Strength of the evidence',directness:'Directness for this interpretation',causal_attribution:'Support for attributing a cause',transferability:'Transferability to this context',independence:'Independence from other evidence',recency:'Recency for this question',context_completeness:'Completeness of the retained context',claim_fitness:'Fit to the wording of this interpretation',selection_risk:'Risk of selection bias',baseline_quality:'Quality of the comparison or baseline',outcome_validity:'Validity of the recorded outcome',systemic_relevance:'Relevance to the wider system'};
function assessmentForm(linked){
 const pairs=linked.map(({claim,key,title})=>[key,claim.claim+' · '+title]);
 const pair=field('Interpretation and linked source passage',{type:'select',options:[['','Choose an interpretation and linked passage'],...pairs]});pair.input.setAttribute('data-assessment-pair','true');const preview=node('div');
 const ratings=view.assessment_dimensions.map(key=>({key,...field(assessmentLabels[key]||readable(key),{type:'select',value:'unknown',options:[['unknown','Unknown'],['low','Low'],['medium','Medium'],['high','High'],['not_applicable','Not applicable']]})}));
 const limits=field('Known limits — one per line',{type:'textarea',required:false,hint:'No recorded limits does not establish that none exist.'});
 const reason=field('Why do these ratings fit this passage and interpretation?',{type:'textarea'});
 const answers=[...ratings,limits,reason];
 const answerFields=node('div',{'data-assessment-answers':''},...answers.map(answer=>answer.wrap));
 const draftPrefix=view.case_id+'/'+view.revision+'/';
 const refreshPreview=()=>{
  preview.replaceChildren();
  const values=assessmentDrafts.get(draftPrefix+pair.get());
  for(const [index,answer] of answers.entries()){
   answer.input.disabled=!pair.get();
   answer.input.value=values?.[index]??(answer.key?'unknown':'');
  }
  f.querySelector('button[type=submit]').disabled=!pair.get();
  if(!pair.get())return;
  const [cid,eid]=JSON.parse(pair.get());
  preview.append(value('Interpretation being assessed',view.state.claims[cid]?.claim),
   retainedEvidence([eid],view.state,{expanded:true}));
 };
 pair.input.addEventListener('change',refreshPreview);
 const remember=()=>{
  if(pair.get())assessmentDrafts.set(draftPrefix+pair.get(),answers.map(answer=>answer.get()));
 };
 answerFields.addEventListener('input',remember);
 answerFields.addEventListener('change',remember);
 const f=form([pair,preview,answerFields],()=>{
  if(!pair.get()){pair.input.focus();return;}
  const [cid,eid]=JSON.parse(pair.get());
  perform('assessment',{claim_id:cid,evidence_id:eid,
   dimensions:Object.fromEntries(ratings.map(r=>[r.key,r.get()])),
   limitations:lines(limits.get()),rationale:reason.get()});
 },'Save advisory evidence assessment');
 if(!pairs.length)f.querySelector('button[type=submit]').disabled=true;
 return card('Assess how a passage fits an interpretation',text('p','Choose an explicit interpretation/passage pair. Ratings start Unknown and describe the named dimension, not a combined score. High selection-bias risk means high risk. Nothing here validates a method, accepts a claim or approves research.','notice'),node('details',{class:'details'},node('summary',{},'How to use these checks'),text('p','Rate one dimension at a time. Leave a rating as Unknown when the passage does not let you judge it, and record any important caveats under Known limits. The result is a transparent review note, not a verdict on whether an interpretation is true.','muted small')),!pairs.length?text('p','First attach reviewed evidence to a working interpretation. An assessment cannot create the link.','muted'):null,f);
}
function assessmentsPanel(entries,context,historical=false){
 const box=card(historical?'Evidence assessments at report creation':'Saved evidence assessments',text('p',historical?'Ratings and freshness are retained as recorded at report creation. They are not recomputed against current research.':'An assessment belongs to exact saved versions of an interpretation and passage. If the interpretation changes, the old assessment remains visible and is labelled stale.','muted'));
 for(const entry of entries||[]){const a=entry.assessment,c=context.claims?.[a.claim_id];const section=card('Advisory evidence assessment',tag('Advisory'),tag(historical?(entry.current?'Matched at report creation':'Already stale at report creation'):(entry.current?'Matches current versions':'Stale · interpretation or passage changed'),!entry.current),value(historical?'Interpretation at report creation':entry.current?'Assessed interpretation':'Current interpretation · earlier assessed version is different',c?.claim||'Retained context unavailable'),value('Evidence origin when assessed',a.evidence_origin==='synthetic_only'?'Synthetic evidence only':a.evidence_origin==='non_synthetic'?'Source record · not a truth guarantee':readable(a.evidence_origin||'unknown')),retainedEvidence([a.evidence_id],context));
  if(!entry.current)section.append(text('p','Do not treat these ratings as an assessment of the displayed interpretation version. Record a new assessment after reviewing the changed research.','notice'));
  for(const [key,rating] of Object.entries(a.dimensions||{}))section.append(value(assessmentLabels[key]||readable(key),readable(rating)));
  section.append(value('Recorded limits',(a.limitations||[]).join('\n')||'None recorded · not proof of no limitations'),value('Assessment reason',a.rationale));box.append(section);
 }
 if(!(entries||[]).length)box.append(text('p','No evidence-fit assessments have been recorded. Attaching a passage alone is not an assessment.','muted'));return box;
}
function assessmentQueue(pairs){
 const pending=pairs.filter(pair=>pair.status!=='current');
 const stale=pending.filter(pair=>pair.status==='stale');
 const missing=pending.filter(pair=>pair.status==='missing');
 return card('Passages to assess',
  text('p',stale.length+' need reassessment · '+missing.length+' awaiting a first assessment','muted small'),
  !pairs.length?text('p','Link a passage to a working interpretation to add it here.','muted small'):null,
  pairs.length&&!pending.length?text('p','All currently linked passages have a current assessment.','muted small'):null,
  ...[...stale,...missing].map(({claim,id,title,status})=>node('div',{class:'label-value'},
   tag(assessmentStatusLabels[status],status==='stale'),
   value('Interpretation',claim.claim),value('Linked passage',title),
   value('Exact location',view.state.evidence[id].exact_location),
   btn('Assess passage from '+title,()=>assessLinkedPassage(claim.claim_id,id)))));
}
function evidenceFitView(){
 const pairs=assessmentPairs();
 return node('div',{class:'grid'},
  node('div',{},assessmentQueue(pairs),assessmentsPanel(view.assessments,view.state)),assessmentForm(pairs));
}
function planFromReport(reportId,index){
 if(busy)return;
 selectedReport=reportId;
 tab='Next research';
 error='';
 message='';
 render();
 const row=app.querySelector('[data-agenda-criterion="'+index+'"]');
 row?.scrollIntoView({block:'start'});
 row?.querySelector('textarea')?.focus();
}
function reportCriterionCard(criterion,report,context,evaluations,current){
 const linked=criterion.evaluation_ids||[];
 const trace=node('details',{class:'details'},node('summary',{},'Inspect evaluations and evidence ('+linked.length+')'));
 if(!linked.length)trace.append(text('p','No evaluation was linked to this criterion in the report.','muted small'));
 for(const id of linked){
  const evaluation=evaluations.get(id);
  if(!evaluation){
   trace.append(value('Evaluation reference',id),text('p','This evaluation is unavailable in the saved report.','muted small'));
   continue;
  }
  trace.append(node('section',{class:'card subtle'},text('h4','Recorded evaluation'),
   value('Method used',evaluation.method),value('Recorded outcome',readable(evaluation.outcome)),
   value('Limits',evaluation.limitations),
   value('Evidence origin',readable(report.evaluation_origins?.[id]||'unknown')),
   retainedEvidence(evaluation.evidence_ids,context)));
 }
 return node('div',{class:'card subtle'},text('h3',criterion.criterion),tag(readable(criterion.outcome),criterion.outcome!=='met'),
  value('Reason',criterion.rationale),value('Evidence basis',readable(criterion.evidence_origin)),
  value('Next research',criterion.next_research),trace,
  current&&criterion.outcome!=='met'?btn('Plan follow-up for this criterion',
   ()=>planFromReport(report.report_id,criterion.criterion_index)):null);
}
function reportsView(){const main=node('div');if(view.state.workflow.status!=='active')main.append(card('Save a research draft',text('p','A report communicates the current findings, limits and decisions. It does not authorize publication.','muted'),btn('Create current draft',()=>perform('report',{rationale:'Operator requested a saved draft of this stopped research pass'}),'primary')));else main.append(card('Research is in progress',text('p','Stop or escalate this pass to create a saved report. Your evidence and phase records are already retained.','muted')));for(const r of view.reports){const report=view.state.outputs[r.report_id];const section=card('Research draft',node('div',{class:'tags'},tag(r.current?'Current research snapshot':'Historical / stale',!r.current)),value('Summary',report.workflow.records?.deliver?.summary||report.workflow.stopping_reason));if(report.decision_trace){const context=reportEvidenceContext(report);const evaluations=new Map((report.workflow.records?.deliver?.evaluations||[]).map(item=>[item.evaluation_id,item]));section.append(value('Selected alternative',report.workflow.records?.develop?.alternatives?.find(a=>a.alternative_id===report.decision_trace.selected_alternative_id)?.hypothesis||report.decision_trace.selected_alternative_id),value('Decision',readable(report.decision_trace.decision)));for(const criterion of report.decision_trace.criteria)section.append(reportCriterionCard(criterion,report,context,evaluations,r.current));}if(report.assessments?.length)section.append(assessmentsPanel(report.assessments,reportEvidenceContext(report),true));if(Object.keys(report.contradictions||{}).length)section.append(contradictionsPanel(report.contradictions,reportEvidenceContext(report),true));section.append(btn('Download readable draft',async()=>{try{const response=await fetch('/api/report?case='+view.case_id+'&report='+encodeURIComponent(r.report_id),{headers:{Authorization:'Bearer '+token}});if(!response.ok)throw Error('Report download failed');const url=URL.createObjectURL(await response.blob()),a=node('a',{href:url,download:'research-draft.md'});a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){error=e.message;render();}}));main.append(section);}return main;}
async function downloadBackup(){if(busy)return;busy=true;error='';message='';render();try{const response=await fetch('/api/checkpoint?case='+view.case_id+'&revision='+view.revision,{headers:{Authorization:'Bearer '+token}});if(!response.ok){const result=await response.json();throw Error(result.error||'Backup download failed');}const url=URL.createObjectURL(await response.blob()),link=node('a',{href:url,download:'research-checkpoint.zip'});link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);message='Checkpoint downloaded. It contains plaintext research data; keep it somewhere private.';}catch(e){error=e.message;}finally{busy=false;render();}}
function backupPanel(){return card('Back up this saved case',text('p','Download a verified checkpoint containing the saved research, source records, history and pending decisions. Unsaved form fields and other cases are not included.','muted'),text('p','The ZIP contains plaintext research data. Store it privately; a code release ZIP is not a research backup. Browser transfers are limited to 32 MiB.','notice'),btn('Download case checkpoint',()=>downloadBackup(),'primary'),btn('Restore a checkpoint as a separate case',()=>{restoring=true;creating=false;restoreFile=null;restorePreview=null;restoreConfirmed=false;render();}),text('p','Restoring creates a separate case and preserves historical records. It does not overwrite this case or approve anything new.','muted small'));}
async function uploadCheckpoint(path,digest){if(!restoreFile||!restoreFile.size||restoreFile.size>32*1024*1024)throw Error('Choose a checkpoint ZIP no larger than 32 MiB.');const response=await fetch(path,{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/zip',...(digest?{'X-Checkpoint-SHA256':digest}:{})},body:await restoreFile.arrayBuffer()});const result=await response.json();if(!response.ok)throw Error(result.error||'Checkpoint request failed');return result;}
async function inspectBackup(){if(busy)return;busy=true;error='';restorePreview=null;restoreConfirmed=false;render();try{restorePreview=await uploadCheckpoint('/api/checkpoint/inspect');}catch(e){error=e.message;}finally{busy=false;render();}}
async function restoreBackup(){if(busy)return;if(!restorePreview||!restoreConfirmed){error='Inspect the checkpoint and confirm a separate restored copy first.';render();return;}busy=true;error='';render();try{const result=await uploadCheckpoint('/api/checkpoint/restore',restorePreview.checkpoint_digest);await loadCatalog();restoring=false;restoreFile=null;restorePreview=null;restoreConfirmed=false;await load(result.case_id);tab='Research';history.replaceState(null,'','/?case='+result.case_id);message='Restored as a separate case. No earlier approval was renewed and existing cases were not overwritten.';}catch(e){error=e.message+' Check Your research before trying again; an uncertain response is not retried automatically.';try{await loadCatalog();}catch(_){} }finally{busy=false;render();}}
function restorePanel(){const file=node('input',{type:'file',accept:'.zip,application/zip',onChange:e=>{restoreFile=e.target.files?.[0]||null;restorePreview=null;restoreConfirmed=false;error='';render();}});const inspect=btn('Inspect selected checkpoint',()=>inspectBackup(),'primary');inspect.disabled=busy||!restoreFile;const panel=card('Restore a saved checkpoint',text('p','Choose a trusted personal checkpoint ZIP. The browser supports criterion-linked Double Diamond cases up to 32 MiB. It will inspect the contents before you confirm a separate restored case.','muted'),node('label',{class:'field'},'Choose checkpoint ZIP',file),value('Selected file',restoreFile?.name||'None selected'),inspect,btn('Cancel restore',()=>{restoring=false;restoreFile=null;restorePreview=null;restoreConfirmed=false;render();}));if(restorePreview){const p=restorePreview,confirm=node('input',{type:'checkbox',checked:restoreConfirmed,required:'required',onChange:e=>{restoreConfirmed=e.target.checked;}});panel.append(card('Checkpoint inspection',value('Saved case',p.title),value('Saved phase',phaseNames[p.phase]+' · '+readable(p.status)),value('Retained evidence',p.evidence_counts.synthetic+' synthetic; '+p.evidence_counts.source_records+' source records'),value('Historical gate statuses',Object.entries(p.historical_gate_counts).map(([status,count])=>readable(status)+': '+count).join('\n')||'No gates recorded'),value('Historical acceptance entries',String(p.historical_acceptance_entries)),text('p','Integrity checks detect damage; they do not authenticate sources, identities or earlier approvals. Restoration preserves history and creates no new approval.','notice'),form([node('label',{class:'check'},confirm,'I inspected this checkpoint and want a separate restored copy. Existing cases must remain unchanged.')],()=>restoreBackup(),'Restore as separate case')));}return panel;}
function agendaBasis(){
 const candidates=view.reports.filter(r=>r.current&&view.state.outputs[r.report_id].decision_trace);
 return candidates.find(r=>r.report_id===selectedReport)||candidates[0];
}
function agendaView(){const box=node('div');for(const agenda of view.agendas){const c=card('Proposed research agenda',tag(agenda.status,!agenda.current),text('p','Planning only. No interview, source retrieval or experiment is authorized.','muted small'));const items=Object.fromEntries(agenda.items.map(i=>[i.item_id,i]));for(const id of agenda.proposed_order){const i=items[id];c.append(node('div',{class:'card subtle'},text('h3',i.question),value('Criterion and gap',i.criterion+' — '+i.evidence_gap),value('Method and return phase',readable(i.method)+' · '+phaseNames[i.target_phase]),value('Priority',i.priority+' — '+i.priority_rationale),value('What would count as progress',i.success_signal),value('Depends on',i.depends_on.join(', ')||'No prerequisite'),tag('Proposed · not authorized')));}box.append(c);}const basis=agendaBasis();if(basis){const report=view.state.outputs[basis.report_id],gaps=report.decision_trace.criteria.filter(c=>c.outcome!=='met');if(gaps.length){const rows=gaps.map((g,i)=>{const question=field('Question to investigate',{type:'textarea',value:g.next_research}),gap=field('Evidence gap',{type:'textarea',value:g.rationale}),method=field('Proposed method',{type:'select',options:['desk_review','analysis','interview','survey','experiment'].map(v=>[v,readable(v)])}),target=field('Return phase',{type:'select',options:phases.slice(0,3).map(p=>[p,phaseNames[p]])}),priority=field('Priority',{type:'select',options:['high','medium','low']}),why=field('Why this priority?',{type:'textarea'}),signal=field('What new evidence would count as progress?',{type:'textarea'}),effort=field('Estimated effort',{type:'select',options:['small','medium','large']}),depends=choices('Depends on an earlier item',gaps.slice(0,i).map((x,j)=>['research-'+j,x.criterion]),'No earlier items; this item has no prerequisite.');return {wrap:node('fieldset',{'data-agenda-criterion':g.criterion_index},node('legend',{},g.criterion),...[question,gap,method,target,priority,why,signal,effort,depends].map(x=>x.wrap)),get:()=>({item_id:'research-'+i,criterion_index:g.criterion_index,evidence_gap:gap.get(),question:question.get(),method:method.get(),target_phase:target.get(),priority:priority.get(),priority_rationale:why.get(),success_signal:signal.get(),effort:effort.get(),depends_on:depends.get()})};});box.append(card('Plan the next evidence to gather',
 value('Based on the saved report',report.generated_at),
 text('p','Plan one item for each unmet or unknown criterion. Saving records a proposal for human review.','muted small'),
 form(rows,()=>perform('agenda',{report_id:basis.report_id,items:rows.map(r=>r.get()),rationale:'Operator proposed follow-up research from unmet criteria'}),'Save proposed research agenda')));}}if(!box.childNodes.length)box.append(card('Research follows the evidence gaps',text('p','Save a current criterion-linked report to turn its failed or unknown criteria into proposed next research.','muted')));return box;}
function render(restoredEditor){if(renderedKey&&renderedKey!=='restore'&&document.querySelector('main'))drafts.set(renderedKey,{values:[...document.querySelectorAll('main input:not([type=file]):not([data-document-keep]):not([data-reset-on-render]),main textarea,main select')].filter(e=>!e.closest('[data-deliver-editor],[data-develop-editor],[data-claim-revision-editor],[data-local-document-review],[data-assessment-answers]')).map(e=>({value:e.value,checked:e.checked})),deliver:deliverDraftReader?.(),develop:developDraftReader?.()});deliverDraftReader=null;developDraftReader=null;renderedKey=draftKey();
 if(restoredEditor)drafts.set(renderedKey,{...drafts.get(renderedKey),...restoredEditor});
 app.replaceChildren();const side=node('aside',{class:'sidebar'},node('div',{class:'brand'},text('span','◇◇','diamonds'),node('div',{},'Double Diamond',text('div','Research workspace','muted small'))),btn('Workspace home',openHome),btn('+ New research case',openCreateForm,'primary'));const list=node('div',{class:'case-list'},text('div','Your research','eyebrow'));for(const c of cases)list.append(btn(c.title,()=>choose(c.case_id),'case-button'+(view?.case_id===c.case_id?' active':'')));side.append(btn('Restore a backup',()=>{restoring=true;creating=false;error='';message='';render();}),list,text('p','Local workspace. Your research is saved on this computer. Final host acceptance and external actions remain separate.','foot'));const main=node('main');main.append(node('div',{class:'topbar'},'A question → evidence → a research decision',btn('Refresh saved research',()=>refresh().catch(e=>{error=e.message;render();}))));if(error)main.append(text('div',error,'notice error'));if(message)main.append(text('div',message,'notice good'));if(unavailableCases.length)main.append(card('Some saved research could not be opened',text('p','The files for '+String(unavailableCases.length)+(unavailableCases.length===1?' saved case':' saved cases')+' could not be verified and were left unchanged. Your other cases remain available.','notice'),...unavailableCases.map(c=>value('Unavailable case',c.title)),text('p','Keep the original files for inspection. If you have a trusted checkpoint, use Restore a backup to create a separate copy. Nothing is repaired or deleted automatically.','muted small')));if(busy)main.append(text('div','Saving or opening verified research…','notice'));
if(restoring)main.append(restorePanel());else if(creating)main.append(createForm());else if(!view){
 main.append(
  node('div',{class:'hero'},node('div','A guided research workspace','eyebrow'),node('h1',{id:'workspace-home-title'},'Turn a question into a traceable research decision.'),
   text('p','Gather evidence, understand what it supports, compare possible directions, and make your reasoning visible from start to finish.')),
  card('How it works',node('div',{class:'choice-grid'},
   node('div',{class:'choice'},text('h3','1. Ask a question'),text('p','Start with something you want to understand. You can narrow the scope as you learn.')),
   node('div',{class:'choice'},text('h3','2. Review evidence'),text('p','Save exact passages from sources and check their original context before using them.')),
   node('div',{class:'choice'},text('h3','3. Decide carefully'),text('p','Use the Double Diamond phases to frame the problem, compare alternatives, and record the limits of your decision.')))),
  card('How the Double Diamond guides the work',text('p','Discover and Define help you explore widely before framing the problem. Develop and Deliver help you compare possible directions before deciding what to do next. If new evidence changes the picture, you can request a reviewed return to an earlier phase.','muted')),
  node('div',{class:'phase-strip'},...phases.map(p=>node('div',{class:'card subtle'},text('h3',phaseNames[p]),text('p',names[p],'small')))),
  card('Start your research',text('p','Create a case around your own question. Your first task will be to add one source and review a passage from it.','muted'),btn('Start a research case',openCreateForm,'primary')),
  card('Explore a completed example',text('p','Open a local practice copy to inspect how evidence, choices, and limits are recorded across the four phases. It uses invented evidence and simulated decisions.','muted'),
   btn('Open practice example',createLearningExample))
 );
}else{const w=view.state.workflow;main.append(node('div',{class:'hero'},node('div',{class:'tags'},tag(view.meta.restored_checkpoint?'Restored copy':view.meta.synthetic_example?'Synthetic learning example':'Your research',view.meta.synthetic_example),view.meta.synthetic_only?tag('Synthetic evidence only',true):null,tag(w.status),tag('Visit '+w.visits.length+' of '+w.max_visits)),node('h1',{id:'research-case-title'},view.meta.title),text('p',view.state.brief.text),node('details',{class:'details'},node('summary',{},'What this research covers'),text('p',view.state.scope?.text||'Not recorded','small'))));if(view.meta.restored_checkpoint)main.append(text('div','Restored as a separate case. Source labels and historical decisions were retained. Restoration does not authenticate or renew earlier approvals.','notice'));if(view.meta.synthetic_example)main.append(text('div','This example uses synthetic evidence and simulated historical approvals. It does not establish real findings or actual human acceptance.','notice'),exampleGuidePanel());if(Object.values(view.currency).some(current=>!current))main.append(text('div','Some saved phase findings are stale. Review the new evidence and request a return before drawing a new conclusion.','notice'));main.append(node('div',{class:'phase-strip'},...phases.map(p=>{const b=btn(phaseNames[p],()=>{const visit=[...w.visits].reverse().find(v=>v.phase===p);if(visit)openVisit(visit.visit_id);else{resetInspection();tab='Research';message=phaseNames[p]+' has no visit yet. Inspecting phases does not move the research.';render();}},p===w.phase?'current':'');b.append(text('small',(p===w.phase?'Current · ':'')+(w.records[p]?'Saved':view.meta.discover_brief&&p==='discover'?'Notes for review':'Not recorded')));return b;})));const tabs=['Research','Sources','Interpretations','Evidence fit','Approvals','Reports','Next research','Backups'];const isFirstDiscover=startingDiscover(),visibleTabs=isFirstDiscover?['Research','Sources']:tabs;const tabControl=t=>{
 const labels={Research:'Research',Sources:'Sources',Interpretations:'Working ideas','Evidence fit':'Check evidence',Approvals:'Review changes',Reports:'Research drafts','Next research':'Plan next research',Backups:'Save a copy'},label=labels[t]||t;
 const control=btn(label+(t==='Approvals'?' ('+Object.values(view.state.human_gates).filter(g=>g.status==='pending_review'&&view.gate_context_current?.[g.gate_id]===true&&['phase_transition','material_reframing'].includes(g.gate_type)).length+')':''),()=>{
  if(t==='Sources'){openSources();return;}
  tab=t;
  render();
  app.querySelector('[data-current-research-section]')?.focus();
 },tab===t?'active':'');
 if(tab===t){control.setAttribute('aria-current','page');control.setAttribute('data-current-research-section','');}
 return control;
};const navigation=node('nav',{class:'tabs','aria-label':'Research sections'},...visibleTabs.map(tabControl));if(isFirstDiscover)navigation.append(node('details',{class:'section-menu'},node('summary',{},'More research tools'),node('div',{class:'section-menu-items'},...tabs.filter(t=>!visibleTabs.includes(t)).map(tabControl))));main.append(navigation);if(tab==='Research'){if(w.phase==='discover')main.append(card('Start with sources',text('p','Search for publications related to your question, or add a source you already have.'),btn('Find and review sources',openSources,'primary')));const brief=discoverBriefPanel();if(brief)main.append(brief,node('details',{class:'details'},node('summary',{},'Research controls and saved history'),guidancePanel(),researchView()));else main.append(guidancePanel(),researchView());}if(tab==='Sources')main.append(sourcesView());if(tab==='Interpretations')main.append(claimsView());if(tab==='Evidence fit')main.append(evidenceFitView());if(tab==='Reports')main.append(reportsView());if(tab==='Next research')main.append(agendaView());if(tab==='Backups')main.append(backupPanel());if(tab==='Approvals'){const gates=Object.entries(view.state.human_gates).filter(([,g])=>['phase_transition','material_reframing'].includes(g.gate_type)&&['pending_review','approved'].includes(g.status));main.append(...(gates.length?gates.map(([id,g])=>reviewCard(id,g)):[card('No research changes awaiting review',text('p','Request a phase change from Research when you are ready. Publication is never approved by this interface.','muted'))]));}}
app.append(node('div',{class:'shell'},side,main));const saved=restoring?null:drafts.get(renderedKey);if(saved)[...main.querySelectorAll('input:not([type=file]):not([data-document-keep]):not([data-reset-on-render]),textarea,select')].filter(e=>!e.closest('[data-deliver-editor],[data-develop-editor],[data-claim-revision-editor],[data-local-document-review],[data-assessment-answers]')).forEach((e,i)=>{if(saved.values[i]){e.value=saved.values[i].value;if(e.type==='checkbox')e.checked=saved.values[i].checked;}});for(const pair of main.querySelectorAll('[data-assessment-pair],[data-interpretation-evidence],[data-define-claims],[data-source-aids]'))pair.dispatchEvent(new Event('change'));if(busy)for(const e of main.querySelectorAll('input,textarea,select,button'))e.disabled=true;}
(async()=>{try{await loadCatalog();const requested=new URLSearchParams(location.search).get('case');if(requested)await load(requested);}catch(e){error=e.message;}render();})();
