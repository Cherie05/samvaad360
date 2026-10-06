// Edit duplicated organizer slides with artifact-tool. The source logo artwork,
// backgrounds, master/layouts, text-frame geometry and typography are retained.
import fs from 'node:fs/promises';
import path from 'node:path';
import { FileBlob, PresentationFile } from '@oai/artifact-tool';

const ROOT = path.resolve(process.argv[2]);
const SIZE = process.argv[3];
const STEM = process.argv[4] || 'Samvaad360_Official_Submission';
const NATIVE = process.argv[5] === 'verified-native';
if (!/^[A-Za-z0-9_-]+$/.test(STEM)) throw new Error('Invalid output basename.');
if (!SIZE || !/^\d+$/.test(SIZE) || Number(SIZE) < 1) throw new Error('Confirmed team size is required.');
const BUILD = path.join(ROOT,'output','organizer-template-build');
const QA = path.join(BUILD,'final-preview',STEM);
const LAYOUT = path.join(BUILD,'final-layout',STEM);
await fs.mkdir(QA,{recursive:true});
await fs.mkdir(LAYOUT,{recursive:true});
const p = await PresentationFile.importPptx(await FileBlob.load(path.join(BUILD,'template-starter.pptx')));
const slides = p.slides.items;
if (slides.length !== 6) throw new Error('Unexpected starter slide count.');
function field(slide,original,replacement){
 const target = slide.shapes.items.find(s=>String(s.text) === original);
 if (!target) throw new Error('Missing inherited cover field: '+original);
 target.text.replace(original,replacement);
}
field(slides[0],'Team Name :','Team Name : Glacier Queries');
field(slides[0],'Team Leader Name :','Team Leader Name : Arunvpp');
field(slides[0],'Team Size :','Team Size : '+SIZE);
field(slides[0],'Problem Statement :','Problem Statement : Customer 360 and Next Best Action Engine');

// Match the source's Manrope run styles and paragraph spacing; shorter content
// fits the same frame without font reduction or new slide objects.
const font = {typeface:'Manrope',fontSize:'17pt',color:'#202729'};
const title = run=>({runs:[{run,textStyle:{...font,bold:true}}],spaceBefore:0,spaceAfter:0});
const subtitle = run=>({runs:[{run,textStyle:{...font,fontSize:'14.42pt',bold:true,italic:true}}],spaceBefore:0,spaceAfter:0});
const section = run=>({runs:[{run,textStyle:{...font,bold:true}}],spaceBefore:16,spaceAfter:0});
const line = run=>({runs:[{run,textStyle:font}],spaceBefore:0,spaceAfter:0});
const bullet = run=>({...line(run),bulletCharacter:'\u25cf',marginLeft:32,indent:-24});
const url = value=>({runs:[{run:value,textStyle:{...font,underline:'sng'},link:{uri:value,isExternal:true}}],spaceBefore:0,spaceAfter:0});
function content(slide,paragraphs){
 const target = slide.shapes.items.find(s=>s.name==='Google Shape;64;p14');
 if (!target) throw new Error('Missing inherited guidelines frame.');
 target.text = paragraphs;
 // Source leading is 115%; all other shape formatting remains inherited.
 target.text.lineSpacing = 1.15;
}
content(slides[1],[
 title('Samvaad360 | Problem Brief'),
 subtitle('Customer 360 and Next Best Action Engine | Lending'),
 section('Target user and business pain'),
 bullet('Relationship and support officers work across fragmented records.'),
 bullet('Repayment facts alone can miss job loss, disputes and opt-out.'),
 section('Why the next conversation matters'),
 bullet('A growth offer can become inappropriate after a hardship reply.'),
 bullet('Officers need the reason, cited evidence and a reviewable action.'),
 section('Implemented response'),
 bullet('Join loans, payments, emails and call transcripts in Customer 360.'),
 bullet('Apply consent, hardship and approval gates before next actions.'),
 bullet('Re-evaluate new context; stop stale offers and route human help.'),
 line('Domain: synthetic lender servicing; no insurance claims demo.')
]);
content(slides[2],[
 title('Samvaad360 | Architecture Diagram'),
 subtitle('Structured and unstructured data to a guarded next action'),
 section('Loan / repayment facts + email / call transcript + preferences'),
 line('                         \u2193'),
 line('Snowflake fictional snapshot  \u2192  fixed, read-only reader'),
 line('                         \u2193'),
 line('Python evidence + deterministic policy engine + approval gates'),
 line('                         \u2193'),
 line('Streamlit: Customer 360  \u2192  Review queue  \u2192  Conversation'),
 section('Private operational path: FastAPI + persistent SQLite'),
 line('Reviewed intake / versioned imports / servicing / audit records'),
 section('CoCo skills: evidence  \u2192  generate  \u2192  approved runner'),
 line(NATIVE ? 'Native CoCo verified with local CLI + isolated fictional data.' : 'Local CLI + isolated data; native execution proof is pending.'),
 line('Public changes stay visit-only. Private Snowflake sync is pending.')
]);
content(slides[3],[
 title('Samvaad360 | Impact Statement'),
 subtitle('Measured prototype verification; business uplift not yet measured'),
 section('Verified today'),
 bullet('557 CI tests; 20 hosted browser checks; 6 private portal checks.'),
 bullet('20 fictional customers; six public workspaces; Snowflake reader.'),
 section('Observable workflow outcome'),
 bullet('A new hardship reply removes an eligible growth proposal.'),
 bullet('The journey, evidence and officer handoff remain explainable.'),
 section('Scalability and use beyond the demo'),
 bullet('Shared snapshots and query reservations bound app query usage.'),
 bullet('Reviewed source imports and outbox projection support integration.'),
 bullet('Next: managed database, SSO, private sync and carrier validation.'),
 line('No proven ROI, churn reduction or production readiness claimed.')
]);
content(slides[4],[
 title('Samvaad360 | Demonstration and Public Links'),
 subtitle('Glacier Queries | Arunvpp | Fictional customer journey'),
 section('Try the working journey'),
 bullet('Customer 360: Kabir Bose \u2192 compare a job loss \u2192 cited action.'),
 bullet('Imran Shaikh \u2192 demo review \u2192 conversation \u2192 hardship reply.'),
 bullet('Show growth stopping, human handoff and revised evidence.'),
 bullet('Customer hub: onboarding, source preview/import and servicing.'),
 section('Deployed prototype'),
 url('https://samvaad360.streamlit.app/'),
 section('Public source, checks and modular CoCo skills'),
 url('https://github.com/Cherie05/samvaad360'),
 line('Public reviews/conversations are simulations; real calls disabled.'),
 line(NATIVE ? 'Native CoCo result: COMPLETED / CALLBACK / simulate.' : 'A separate actual CoCo CLI screen recording remains required.')
]);
const sharedSource='Participant-provided Prototype Submission Template _ CoCo CLI Hackathon GCC Edition.pptx; organizer branding retained.';
const notes=[
 'Team name Glacier Queries and leader Arunvpp supplied by the participant. Team size '+SIZE+' confirmed separately. Track matches the participant portal.\n'+sharedSource,
 'The implemented scope is lending customer context and policy-aware recommendations. All demonstrated people and records are fictional. No measured churn/ROI improvement or market exclusivity claimed.\n'+sharedSource+'\nhttps://github.com/Cherie05/samvaad360/blob/main/samvaad/engine.py\nhttps://samvaad360.streamlit.app/',
 'Public frontend is Python Streamlit. The dedicated Snowflake reader issues fixed read-only synthetic snapshot queries. Private FastAPI/SQLite flows persist locally; private Snowflake writer/outbox activation remains unconfigured. CoCo definitions are samvaad-evidence, samvaad-generate and samvaad-approved-runner. '+(NATIVE ? 'Native 1.1.87 executed all three in the owner terminal; returned trace matches isolated SQLite COMPLETED/CALLBACK/simulate, one attempt, completed 2026-10-06T16:23:35.422079Z. App-service controls remain authoritative; no native shell sandbox claim.' : 'Native full-workflow proof remains pending.')+'\n'+sharedSource+'\nhttps://github.com/Cherie05/samvaad360/blob/main/public_app/repository.py\nhttps://github.com/Cherie05/samvaad360/blob/main/.cortex/skills/samvaad-evidence/SKILL.md\nhttps://github.com/Cherie05/samvaad360/blob/main/.cortex/skills/samvaad-generate/SKILL.md\nhttps://github.com/Cherie05/samvaad360/blob/main/.cortex/skills/samvaad-approved-runner/SKILL.md',
 '557 tests passed in GitHub run 37490270245. Hosted browser report: 20 checks at 2026-10-06T15:47:55.069776Z. Private local browser: 6 checks at 2026-10-06T14:51:38.877300Z. These are functional prototype checks, not production certification. Shared budgets are application controls, not an account-wide credit cap or proof of Community Cloud per-IP enforcement. No real telephone call or loan change was performed.\n'+sharedSource+'\nhttps://github.com/Cherie05/samvaad360/actions/runs/37490270245\nhttps://github.com/Cherie05/samvaad360/blob/main/docs/production-readiness.md\nLocal evidence: output/cloud/public-browser/hosted/result.json; output/cloud/relationship-browser/result.json',
 'Links point to the public deployed prototype and source. '+(NATIVE ? 'Owner supplied the actual native input, three SKILL loads, three POWERSHELL tool results and final callback summary. The stored action ID e2e19413-c7b0-4583-af6b-f52199122e66 and completion timestamp match the read-only database verification. This establishes native workflow execution separately from the required recording. No telephone call or financial change occurred.' : 'The published product walkthrough currently lacks the required verified actual CoCo CLI segment.')+' Participant portal receipt is pending.\n'+sharedSource+'\nhttps://samvaad360.streamlit.app/\nhttps://github.com/Cherie05/samvaad360\nhttps://github.com/Cherie05/samvaad360/releases/tag/hackathon-submission-2026',
 'Original closing artwork preserved without edits.\n'+sharedSource
];
for (let i=0;i<slides.length;i++){
 const s=slides[i];
 s.speakerNotes.textFrame.setText('[Sources]\n'+notes[i]+'\n[/Sources]');
 const png=await p.export({slide:s,format:'png',scale:1.5});
 await fs.writeFile(path.join(QA,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await png.arrayBuffer()));
 const layout=await s.export({format:'layout'});
 await fs.writeFile(path.join(LAYOUT,`slide-${String(i+1).padStart(2,'0')}.layout.json`),await layout.text());
}
const pptx=await PresentationFile.exportPptx(p);
await pptx.save(path.join(ROOT,'submission',STEM+'.pptx'));
console.log('Six organizer-template slides exported; original editable frames retained.');
