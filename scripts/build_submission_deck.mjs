// Authoritative slide source: editable native PowerPoint via @oai/artifact-tool.
// Run through build_submission_deck.py to resolve the bundled package and build PDF.
import fs from 'node:fs/promises';
import path from 'node:path';
import { Presentation, PresentationFile } from '@oai/artifact-tool';

const ROOT=path.resolve(process.argv[2]||'../..');
const OUT=path.join(ROOT,'submission');
const QA=path.join(ROOT,'output','submission-deck-qa');
const ASSETS=path.join(QA,'screenshots');
const C={forest:'#143D35',cream:'#F5F7F3',green:'#0F7964',mint:'#DDEEE4',gray:'#537269',line:'#CDDBD4',white:'#FFFFFF',gold:'#C6AF75'};
const p=Presentation.create({slideSize:{width:1280,height:720}});
const manifests=[];
let slideNo=0;

function rect(s,name,x,y,w,h,fill=C.white,line='none',radius=0){
 return s.shapes.add({geometry:radius?'roundRect':'rect',name,position:{left:x,top:y,width:w,height:h},fill,line:{style:'solid',fill:line,width:line==='none'?0:1},borderRadius:radius});
}
function text(s,name,value,x,y,w,h,size=24,opts={}){
 const t=s.shapes.add({geometry:'textbox',name,position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 t.text=value;t.text.style={fontSize:size,typeface:'Aptos',color:opts.color||C.forest,bold:opts.bold||false,alignment:opts.align||'left',verticalAlignment:'top',autoFit:'none',wrap:'square',lineSpacing:1.08,insets:{top:0,left:0,bottom:0,right:0}};
 return t;
}
function link(s,name,label,url,x,y,w,h,size=27,color=C.green){
 const t=text(s,name,label,x,y,w,h,size,{color,bold:true});
 t.text=[[{run:label,textStyle:{underline:'sng',color},link:{uri:url,isExternal:true}}]];
 return t;
}
function note(s,textValue,sources=[]){
 s.speakerNotes.textFrame.setText(textValue+(sources.length?'\n\n[Sources]\n'+sources.join('\n')+'\n[/Sources]':''));
}
function base(title,kicker='SAMVAAD360 / LENDING',dark=false){
 const s=p.slides.add();s.background.fill=dark?C.forest:C.cream;slideNo++;
 text(s,`s${slideNo}-eyebrow`,kicker,64,35,1100,28,16,{bold:true,color:dark?C.mint:C.green});
 if(title)text(s,`s${slideNo}-title`,title,64,82,1152,110,48,{bold:true,color:dark?C.cream:C.forest});
 rect(s,`s${slideNo}-footer-rule`,64,671,1152,1,dark?'#47675E':C.line);
 text(s,`s${slideNo}-footer`,'Samvaad360 · Customer 360 + Next Best Action · Synthetic lending prototype',64,685,1050,22,15,{color:dark?C.mint:C.gray});
 text(s,`s${slideNo}-number`,String(slideNo).padStart(2,'0'),1160,683,56,25,17,{color:dark?C.mint:C.gray,align:'right'});
 manifests.push({slide:slideNo,title});return s;
}
async function screen(s,name,file,x,y,w,h,crop={left:.215,top:.025,right:.01,bottom:.045}){
 rect(s,name+'-frame',x-1,y-1,w+2,h+2,C.white,C.line,10);
 const bytes=await fs.readFile(path.join(ASSETS,file));
 // Source pixels are cropped by the wrapper for consistent Artifact/Office/PDF rendering.
 s.images.add({name,blob:new Uint8Array(bytes),contentType:'image/png',alt:`Display crop of actual hosted Samvaad360 screen: ${file}`,fit:'contain',position:{left:x,top:y,width:w,height:h}});
}
function row(s,n,title,body,y,opts={}){
 text(s,`row-${n}-num`,String(n).padStart(2,'0'),64,y,55,44,29,{bold:true,color:opts.dark?C.gold:C.green});
 text(s,`row-${n}-head`,title,134,y,440,42,32,{bold:true,color:opts.dark?C.cream:C.forest});
 text(s,`row-${n}-body`,body,134,y+47,440,77,23,{color:opts.dark?C.mint:C.gray});
}

await fs.mkdir(OUT,{recursive:true});await fs.mkdir(QA,{recursive:true});

// 01 — Cover: broad white space and one actual screen.
{
const s=base('', 'CUSTOMER 360 AND NEXT BEST ACTION ENGINE',true);
text(s,'cover-brand','Samvaad360',64,117,700,96,78,{bold:true,color:C.cream});
text(s,'cover-title','A better next\nconversation.',64,231,590,154,58,{bold:true,color:C.cream});
text(s,'cover-subtitle','Borrower context → evidence → reviewable intervention',64,417,505,96,27,{color:C.mint});
text(s,'cover-scope','Verified prototype · 6 October 2026\nLending demonstration · Fictional customer data',64,574,600,63,20,{color:C.mint});
await screen(s,'cover-screen','command-center-desktop.png',680,210,535,400,{left:.215,top:.04,right:.01,bottom:.025});
note(s,'Samvaad360 demonstrates the Lending side of the Customer 360 and Next Best Action Engine track. Public URL uses a restricted read-only Snowflake snapshot. All borrower records and public review/conversation outcomes are fictional. This is an implemented prototype, not a production lending approval service.', ['https://samvaad360.streamlit.app/ — actual hosted screenshot, 6 October 2026','Local verification artifact: output/cloud/public-browser/hosted/result.json','https://github.com/Cherie05/samvaad360/blob/main/docs/production-readiness.md']);
}

// 02 — Context problem, with full product evidence rather than ROI claims.
{
const s=base('The borrower’s context gets lost.');
text(s,'problem-lede','Repayment history is only part of the relationship.',64,188,1120,44,27,{color:C.gray});
row(s,1,'Structured facts','Loans, payments and affordability.',260);
row(s,2,'Unstructured context','Calls, email and the borrower’s words.',388);
row(s,3,'Contact preferences','Permission, DND and human follow-up.',516);
await screen(s,'customer-profile','customer360-desktop.png',631,244,585,400,{left:.22,top:.175,right:.02,bottom:.2});
note(s,'The problem is an incomplete relationship view across structured lending facts and unstructured interactions. The screen is the actual public Customer 360. Scores and indicative terms in the application are illustrative rules, not predictions or final credit approvals. No measured business uplift is claimed.', ['https://github.com/Cherie05/samvaad360/blob/main/samvaad/engine.py','https://samvaad360.streamlit.app/ — Customer 360 screenshot']);
}

// 03 — Relationship lifecycle. Flat sequence, no repeating card grid.
{
const s=base('One path through the whole relationship.');
text(s,'lifecycle-intro','Each stage carries its source, permission and review state forward.',64,193,1120,54,27,{color:C.gray});
const cols=[64,299,534,769,1004];const heads=['Intake','Reconcile','Understand','Review','Follow up'];const bodies=['Capture customer\nand consent.','Join source IDs\nand record versions.','Read facts with\nconversation evidence.','Check policy and\napproval authority.','Record outcome\nand update context.'];
for(let i=0;i<5;i++){
 text(s,`stage-${i}-num`,String(i+1).padStart(2,'0'),cols[i],281,170,74,59,{bold:true,color:C.green});
 text(s,`stage-${i}-head`,heads[i],cols[i],385,204,47,32,{bold:true});
 text(s,`stage-${i}-body`,bodies[i],cols[i],443,206,91,23,{color:C.gray});
 if(i<4)rect(s,`stage-${i}-rule`,cols[i]+180,321,39,2,C.line);
}
rect(s,'lifecycle-note-bg',64,575,1152,64,C.mint,'none',8);
text(s,'lifecycle-note','Public changes stay in one visit. Staff onboarding, source sync and cases persist locally.',85,592,1107,40,23,{color:C.forest});
note(s,'Public customer onboarding, source import, source mappings, cases and contact requests are isolated to the visitor session and do not alter the shared Snowflake demo. The authenticated local staff portal uses persistent SQLite and a scoped borrower capability link. Customer intake does not create a loan or complete KYC.', ['https://github.com/Cherie05/samvaad360/blob/main/public_app/ui/relationship.py','https://github.com/Cherie05/samvaad360/blob/main/samvaad/relationship.py']);
}

// 04 — One native architecture diagram. Arrows are created before nodes.
{
const s=base('The live demo has explicit data boundaries.');
text(s,'arch-public-label','LIVE PUBLIC DEMO',64,213,1100,31,18,{bold:true,color:C.green});
text(s,'arch-private-label','PERSISTENT STAFF + BORROWER PORTAL',64,405,1100,31,18,{bold:true,color:C.green});
const xs=[64,368,672,976],w=240;
for(const y of [276,471])for(let i=0;i<3;i++)s.shapes.add({geometry:'rightArrow',name:`arch-edge-${y}-${i}`,position:{left:xs[i]+245,top:y+34,width:53,height:19},fill:C.green,line:{fill:'none',width:0}});
const top=[['Browser','Six guided workspaces'],['Streamlit UI','Python · fixed queries'],['Snapshot','Hourly reuse + limits'],['Snowflake','20 fictional customers']];
const lower=[['Staff portal','Applicant intake links'],['API + SQLite','Reviewed intake + sync'],['Publisher','Activation pending'],['Private data','Snowflake · pending']];
for(let i=0;i<4;i++)for(const [arr,y]of[[top,263],[lower,458]]){
 rect(s,`node-${y}-${i}`,xs[i],y,w,120,i===3?C.forest:C.white,C.line,10);
 text(s,`node-${y}-${i}-title`,arr[i][0],xs[i]+17,y+22,w-34,38,32,{bold:true,color:i===3?C.cream:C.forest});
 text(s,`node-${y}-${i}-desc`,arr[i][1],xs[i]+17,y+71,w-34,45,22,{color:i===3?C.mint:C.gray});
}
text(s,'arch-note','Public visitors cannot write shared customer data or place telephone calls.',64,613,1152,37,24,{color:C.gray});
note(s,'Technology stack is Python Streamlit frontend, protected fixed Snowflake snapshot reader, FastAPI operational backend and SQLite local persistence. Private Snowflake publisher and export outbox are implemented but private writer activation is pending. Production would also require managed operational storage, authentication, observability and verified provider deployment.', ['https://github.com/Cherie05/samvaad360/blob/main/public_app/repository.py','https://github.com/Cherie05/samvaad360/blob/main/webhook/main.py','https://github.com/Cherie05/samvaad360/blob/main/samvaad/relationship.py']);
}

// 05 — Application capabilities + actual skill definitions, without CLI execution claim.
{
const s=base('Three capabilities compose the demo.');
const xs=[64,458,852];const heads=['Relationship\nintelligence','Policy-aware\nintervention','Guarded\nautomation'];const bodies=['Reconcile customer, loan, repayment and conversation records.','Cite evidence, test new context and route the right review.','Require recorded approval and preserve a replay-safe audit trail.'];
for(let i=0;i<3;i++){
 text(s,`cap-num-${i}`,String(i+1).padStart(2,'0'),xs[i],232,330,82,61,{bold:true,color:C.green});
 text(s,`cap-head-${i}`,heads[i],xs[i],327,330,87,33,{bold:true});
 text(s,`cap-body-${i}`,bodies[i],xs[i],438,330,118,24,{color:C.gray});
}
rect(s,'skill-note-bg',64,579,1152,63,C.mint,'none',8);
text(s,'skill-note','CoCo skill definitions included: evidence · generate · approved runner.',83,591,1117,46,24);
note(s,'Implemented modular application capabilities are demonstrated in the hosted and local browser checks. Repository contains .cortex/skills/samvaad-evidence, samvaad-generate and samvaad-approved-runner. The evidence skill reads grounded local customer facts; generate creates a policy-checked recommendation; the approved runner executes only an explicitly approved local synthetic action. Presence of these definitions is not proof of an authenticated end-to-end CoCo CLI run. That proof remains pending at deck generation.', ['https://github.com/Cherie05/samvaad360/blob/main/.cortex/skills/samvaad-evidence/SKILL.md','https://github.com/Cherie05/samvaad360/blob/main/.cortex/skills/samvaad-generate/SKILL.md','https://github.com/Cherie05/samvaad360/blob/main/.cortex/skills/samvaad-approved-runner/SKILL.md']);
}

// 06 — Working outcome feedback, with truthful call scope.
{
const s=base('New context changes the recommendation.');
text(s,'workflow-before-label','BEFORE',64,232,445,30,18,{bold:true,color:C.green});
text(s,'workflow-before','Eligible for a conditional\ntop-up invitation.',64,271,464,92,31,{bold:true});
text(s,'workflow-input','Borrower reply: “I lost my job.”',64,400,465,70,28,{color:C.gray});
text(s,'workflow-after','Growth closes.\nSupportive human handoff.',64,510,480,98,32,{bold:true,color:C.green});
await screen(s,'revised-decision','call-outcome-desktop.png',585,221,631,398,{left:.22,top:.292,right:.3,bottom:.224});
text(s,'workflow-scope','Actual hosted browser rehearsal · no telephone call or loan executed',64,630,1152,32,21,{color:C.gray});
note(s,'Hosted browser test entered a fictional borrower hardship reply in the conversation rehearsal. The engine reevaluated actual new visit evidence, removed growth eligibility and recorded human handoff. Browser speech controls are present, but audio audibility was not verified by the automation. Twilio provider adapter exists but is disabled and no real telephone call was placed.', ['Local verification artifact: output/cloud/public-browser/hosted/result.json — checks 8 and 9','https://github.com/Cherie05/samvaad360/blob/main/samvaad/engine.py','https://samvaad360.streamlit.app/ — call-outcome screenshot']);
}

// 07 — Source sync screen and mobile customer hub, distinct from previous assets.
{
const s=base('Customer data enters through a reviewed flow.');
await screen(s,'sync-screen','customer-hub-source-sync.png',64,220,692,420,{left:.23,top:.065,right:.015,bottom:.14});
text(s,'sync-steps','Capture → Preview → Review → Customer 360',800,220,415,90,31,{bold:true});
text(s,'sync-body','Customer, loan, payment and conversation records join through source IDs and versions.',800,336,410,113,25,{color:C.gray});
text(s,'sync-body-2','A clean import is applied explicitly. Conflicts block the batch; a replay does not duplicate it.',800,484,410,125,25,{color:C.gray});
note(s,'Source uploads are capped at 1 MB and 200 records. JSON full-relationship example includes linked customer, loan, payment and interaction records. Preview validates types, references, versions and conflicts. Local commit is atomic and revalidated. Reviewed onboarding can be linked to source customer IDs; names alone never merge people. The public screenshot shows four fictional records applied only to this visit, not shared Snowflake.', ['https://github.com/Cherie05/samvaad360/blob/main/samvaad/relationship.py','https://github.com/Cherie05/samvaad360/blob/main/public_app/ui/relationship.py','Local verification artifact: output/cloud/public-browser/hosted/result.json — source import checks']);
}

// 08 — Controls with actual usage screenshot.
{
const s=base('Useful actions need enforceable limits.','ENTERPRISE CONTROLS / IMPLEMENTED PROTOTYPE',true);
row(s,1,'Protect compute','Shared snapshot, fixed SQL and query reservations.',224,{dark:true});
row(s,2,'Protect the relationship','Consent, DND, hardship and approval gates.',361,{dark:true});
row(s,3,'Protect execution','Scoped portal links, idempotency and audit records.',498,{dark:true});
await screen(s,'usage-screen','usage-protection.png',665,230,551,377,{left:.225,top:.28,right:.015,bottom:.11});
note(s,'Implemented controls include read-only dedicated Snowflake user/fixed queries, shared hourly snapshot reuse, application query reservations, hosted usage guard, consent and DND gates, hardship suppression, approval fingerprints and idempotency. Operational API adds scoped portal capabilities, rate admission and signed provider callbacks. Public Streamlit is not behind the prepared per-IP gateway; do not claim per-IP host enforcement or total Snowflake account credit cap. Telephony is disabled until provider, identity, policy and deployment configuration are completed.', ['https://github.com/Cherie05/samvaad360/blob/main/public_app/security.py','https://github.com/Cherie05/samvaad360/blob/main/samvaad/telephony.py','https://github.com/Cherie05/samvaad360/blob/main/webhook/main.py','https://samvaad360.streamlit.app/ — usage-protection screenshot']);
}

// 09 — Evidence + clearly scoped production gates.
{
const s=base('Verified workflows. Clear remaining gates.');
const xs=[64,458,852];const nums=['557','20','6'];const labels=['Automated tests','Hosted browser checks','Private portal checks'];
for(let i=0;i<3;i++){
 text(s,`proof-num-${i}`,nums[i],xs[i],224,340,105,80,{bold:true,color:C.green});
 text(s,`proof-label-${i}`,labels[i],xs[i],343,345,57,28,{bold:true});
}
rect(s,'proof-rule',64,427,1152,1,C.line);
text(s,'proof-live-label','LIVE TODAY',64,456,480,35,18,{bold:true,color:C.green});
text(s,'proof-live','Public Snowflake demo, six workspaces, visit isolation and persistent local CRM.',64,502,488,124,27,{color:C.gray});
text(s,'proof-next-label','BEFORE PRODUCTION',664,456,540,35,18,{bold:true,color:C.green});
text(s,'proof-next','Private cloud writer · managed operational database + SSO · carrier call proof · CoCo CLI recording',664,502,540,124,27,{color:C.gray});
note(s,'GitHub CI run 37483107870 passed 557 tests. Anonymous hosted browser evidence passed 20 checks at 2026-10-06T15:00:27 UTC with Snowflake backend verified. Private staff/borrower browser report passed 6 checks. These are functional prototype checks, not penetration testing, audited lending compliance or real carrier call validation. Private cloud writer activation, managed operational storage/SSO, operational provider deployment and authenticated CoCo end-to-end recording remain gates.', ['https://github.com/Cherie05/samvaad360/actions/runs/37483107870','Local verification artifact: output/cloud/public-browser/hosted/result.json','Local verification artifact: output/cloud/relationship-browser/result.json']);
}

// 10 — Reviewer handoff.
{
const s=base('Try the journey. Inspect the evidence.','SAMVAAD360 / PUBLIC PROTOTYPE',true);
text(s,'close-demo-label','LIVE WEBSITE',64,226,1050,35,18,{bold:true,color:C.gold});
link(s,'close-demo','samvaad360.streamlit.app','https://samvaad360.streamlit.app/',64,277,1135,73,43,C.cream);
text(s,'close-repo-label','PUBLIC SOURCE + IMPLEMENTATION',64,389,1050,35,18,{bold:true,color:C.gold});
link(s,'close-repo','github.com/Cherie05/samvaad360','https://github.com/Cherie05/samvaad360',64,440,1135,65,38,C.cream);
text(s,'close-track','Track: Customer 360 and Next Best Action Engine',64,566,1135,39,27,{color:C.mint});
text(s,'close-scope','Fictional lending data · Public reviews and conversations are visit-local simulations',64,615,1135,36,22,{color:C.mint});
note(s,'Public reviewer links are clickable. Website reads a restricted live Snowflake synthetic snapshot. The public demonstration never writes customer data to shared Snowflake, executes a financial action, sends an invitation or dials a telephone. For judging, pair this deck with an actual end-to-end workflow recording. Organizer template was not available at generation; see external template_mapping.txt for provisional custom-deck mapping.', ['https://samvaad360.streamlit.app/','https://github.com/Cherie05/samvaad360']);
}

for(const[i,s]of p.slides.items.entries()){
 const stem=`slide-${String(i+1).padStart(2,'0')}`;
 const png=await p.export({slide:s,format:'png',scale:1});
 await fs.writeFile(path.join(QA,stem+'.png'),new Uint8Array(await png.arrayBuffer()));
 const layout=await s.export({format:'layout'});await fs.writeFile(path.join(QA,stem+'.layout.json'),await layout.text());
}
const montage=await p.export({format:'webp',montage:true,scale:.6});
await fs.writeFile(path.join(QA,'contact-sheet.webp'),new Uint8Array(await montage.arrayBuffer()));
const pptx=await PresentationFile.exportPptx(p);await pptx.save(path.join(OUT,'Samvaad360_Prototype_Deck.pptx'));
await fs.writeFile(path.join(QA,'slide-manifest.json'),JSON.stringify({created_at_utc:new Date().toISOString(),slide_size:{width:1280,height:720},slides:manifests},null,2));
console.log('10 slides exported with per-slide PNG and layout QA.');
