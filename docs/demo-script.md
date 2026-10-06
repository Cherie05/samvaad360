# Samvaad 360 demo recording script

Target a **4–5 minute recording** for the participant portal. The [4:12 public website walkthrough](https://github.com/Cherie05/samvaad360/releases/download/hackathon-submission-2026/Samvaad360_Demo.mp4) is recorded with narration at 1.4× playback; it does not include the required native CoCo segment. The script below describes that remaining combined recording.

The required video must show **CoCo CLI Input → Processing → Output**, one complete working workflow and **2–3 modular capabilities**, according to the owner-provided submission form. The public browser walkthrough alone does not satisfy that requirement.

## Prepare the recording

Open the [public app](https://samvaad360.streamlit.app/), [CI run](https://github.com/Cherie05/samvaad360/actions/runs/37483107870) and private local staff UI at `http://127.0.0.1:8501`. The separate API is `http://127.0.0.1:8000/docs`. Work only with fictional fixtures. Keep private credentials, MFA, hosting secrets, capability tokens and personal records outside the recording.

For the CoCo segment, the installed executable reports 1.1.87; earlier native discovery verified the three original project skills. The submission package adds a separate read-only evidence skill. Actual account/model authentication, skill invocation and hook execution remain **unverified**. Establish those before recording a claimed CoCo workflow. A terminal listing demonstrates discovery, not execution. Refer to the [official CoCo CLI documentation](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-cli) and the installed version's help for its connection/login interface.

The prepared `scripts/start_submission_coco.ps1` helper uses a separate fictional database at `.local/submission-coco/samvaad.db`. The human approval must use that same store. The normal staff app at port8501 points to its own main database and cannot approve an action from another store. Use a separately launched staff view connected to the recording database, or an explicit human-operated approval command in a terminal whose `SAMVAAD_DB_PATH` points there. Keep that human step outside CoCo's generation/execution skills.

Prepared modular skills:

| Skill | Intended capability | Current evidence |
| --- | --- | --- |
| [samvaad-evidence](../.cortex/skills/samvaad-evidence/SKILL.md) | Answer a scoped customer question with returned evidence references. | Native discovery verified; complete workflow/recording still pending. |
| [samvaad-generate](../.cortex/skills/samvaad-generate/SKILL.md) | Inspect customer evidence and queue a governed recommendation. | Skill discovered; Python/domain contract tested. Actual native CoCo invocation pending. |
| [samvaad-approved-runner](../.cortex/skills/samvaad-approved-runner/SKILL.md) | Execute one separately approved action as the fixed automation principal, in simulation. | Skill discovered; approval/execution boundaries tested. Actual native CoCo invocation pending. |
| [samvaad-reset](../.cortex/skills/samvaad-reset/SKILL.md) | Explicitly requested synthetic fixture reset. | Discovered; optional setup capability. Do not reset current records merely to claim a third demonstration. |

Use evidence, recommendation generation and approved execution as three distinct capabilities if all are successfully invoked. Two invoked skills meet the form's minimum of two capabilities. Keep the human approval visible between generation and execution; never ask CoCo to approve its own financial proposal.

## Suggested sequence and narration

| Time | Screen/action | Narration and observable result |
| --- | --- | --- |
| 0:00–0:25 | Public Command center/source label | “Samvaad 360 is our lender Customer 360 and Next Best Action prototype. Loan/payment facts and customer conversations determine a reviewed next step. This public cohort is 20 fictional customers from a restricted Snowflake snapshot.” |
| 0:25–0:55 | Kabir Bose → Customer 360 timeline → A job loss → Compare interventions | “An overdue payment initially suggests a gentle reminder. Job-loss evidence changes the recommendation to supportive hardship contact. Here are the dated records and policy checks.” Show before/after cards. |
| 0:55–1:50 | Native CoCo: invoke samvaad-evidence, then samvaad-generate for `C0002` | Show actual prompts, tool processing and returned evidence/action. “The first capability explains the facts; the second queues the recommendation. The result states its action ID, terms, reviewer and status.” Preserve the actual returned ID. |
| 1:50–2:20 | Matching recording database: human approves the exact returned action as Arjun | “Approval is a separate operator decision. These local identities are demonstration personas; the automation cannot select the approver or change terms.” Show the saved approval in the same operational store. |
| 2:20–3:05 | Native CoCo: invoke samvaad-approved-runner with that approved ID | Show actual processing/output for simulated execution and its audit/outcome. “The runner rechecks policy, approval, permission and frozen terms. This is a recorded simulation, not delivered SMS, a new loan or a real call.” |
| 3:05–3:45 | Public Imran Shaikh → review simulation → Call studio → permission/identity → I lost my job | “The customer's own words stop the earlier top-up conversation. The evidence is visible and the policy changes; public state belongs to this visit.” Show the stopped growth proposal. |
| 3:45–4:20 | Public Customer hub: fictional application/import or customer request/withdrawal | “Customer hub covers intake and servicing. Public exercises are isolated. The private portal persists review, source linkage, imports and cases in SQLite; its optional private Snowflake writer is not yet configured.” |
| 4:20–4:45 | CI/browser evidence and live/repository links | “557 CI tests, 20 hosted-browser checks and 6 private local browser checks passed. Real calling, strong production identity and actual LMS integration remain rollout work.” End on the public links. |

If the CoCo flow takes longer, shorten the public Customer hub segment; keep the final recording between three and five minutes and preserve complete observable input/processing/output. Do not speed past required approval or hide a failed tool call.

## Concrete CoCo prompts and expected boundaries

Use natural-language requests in the actual native CoCo session; select the discovered skills through its supported interface.

**Evidence capability:** “Use samvaad-evidence for customer C0002. What evidence supports a retention review? Return the actual answer, evidence IDs and provider. Do not change records, approve or execute actions.”

**Recommendation capability:** “Use samvaad-generate for customer C0002. Inspect grounded evidence and generate the next-best-action recommendation. Show the returned action ID, required reviewer and current status. Do not approve or execute it.”

The skill's actual tool path inspects `tools.cli status`, evidence via `tools.cli ask`, then `tools.cli recommend C0002`. Record the real result. If a prior action is completed/blocked, prepare a new permitted fixture workflow deliberately; never edit approvals, consent or timestamps to force eligibility.

**Human step:** In the staff view or human-operated terminal connected to the same recording database, approve the exact action as its required reviewer, using a synthetic demo note. Public visit-local Review queue approvals and the normal staff store's approvals do not approve an action from the isolated recording store.

**Execution capability:** “Use samvaad-approved-runner to execute approved action ACTION_ID in simulation with outcome ACCEPT. Report the actual result and audit state. Do not change the approver, consent, caps or terms.” Replace `ACTION_ID` with the returned approved ID, never a fabricated identifier.

The fixed automation principal executes only a permitted action through `tools.cli execute`. A blocked attempt must remain visibly blocked. Hooks are supplemental; service rules are authoritative. Do not describe hook invocation as proven unless it is observed in that actual run.

## After recording

Verify duration, readable output, accurate backend labels and absence of secrets. Upload to an accessible video host and test anonymous playback. Put the actual video URL in the participant form and [submission guide](submission-guide.md). A locally saved video file is not an accessible submission link. Record the final portal confirmation separately; this script does not establish submission.
