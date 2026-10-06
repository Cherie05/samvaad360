# Samvaad 360 submission guide

Updated **6 October 2026, IST**. This guide separates prepared artifacts from an actually completed participant submission. **No successful portal submission is recorded.**

## Portal fields

| Field | Value |
| --- | --- |
| Challenge | **Customer 360 and Next Best Action Engine** |
| GitHub Public Repository Link | https://github.com/Cherie05/samvaad360 |
| Prototype Deployed Link | https://samvaad360.streamlit.app/ |
| Product walkthrough link | https://github.com/Cherie05/samvaad360/releases/download/hackathon-submission-2026/Samvaad360_Demo.mp4 — **4:12**, actual website; native CoCo segment still required. |
| Prototype deck upload | [Samvaad360_Prototype_Deck.pdf](../submission/Samvaad360_Prototype_Deck.pdf), **625 KB**, ten pages, visually verified; custom format pending organizer-template validation. |
| Editable deck source | [Samvaad360_Prototype_Deck.pptx](../submission/Samvaad360_Prototype_Deck.pptx) |

The official challenge asks for structured/unstructured customer touchpoints, including transcripts, and next-best-action recommendations. The implemented lender scope fits that challenge; it does not claim implemented insurance claims processing. [Official challenge and rubric](https://hack2skill.com/event/cococlihack-gccedition/).

The owner-provided participant form lists **6 October 2026, 11:59 PM IST**. The public event page lists **13 September–4 October** for the prototype window. Use the signed-in participant portal's actual deadline; the later deadline is participant-supplied evidence, not an independently verified general extension. [Public timeline](https://hack2skill.com/event/cococlihack-gccedition/).

## Copy-ready Prototype/MVP brief

Copy only the following paragraph. It is **928 characters**, below the 1024-character field limit:

Samvaad 360 is a lender Customer 360 and Next Best Action prototype joining loan/payment facts with emails, chats and call transcripts. Six public workspaces explain portfolio priorities, customer journeys, policy contributions and cited recommendations. Review-gated conversations adapt to hardship and opt-out, stopping stale growth proposals. Customer hub rehearses onboarding, imports and servicing; the private SQLite portal persists intake/review, source links, versioned imports, cases and preference withdrawals. A restricted Snowflake reader serves 20 seeded fictional customers through shared budgeted snapshots; public changes remain visit-only. Verified: 557 CI tests, 20 hosted-browser checks and 6 private local workflow checks. Real calling is disabled, private Snowflake sync is unconfigured, and production identity is pending. A product walkthrough is published; native CoCo workflow recording remains pending.

If actual CoCo execution/video evidence is completed, update the final sentence to the verified result and recount the paragraph before submitting. A Python CLI trace, skill listing or successful Cortex SQL model request alone is not evidence of a CoCo-executed workflow.

## Judge quick start

1. Open the public prototype in a fresh browser. Wake the free-host app if needed and inspect its source label. The verified release read a real Snowflake snapshot; a displayed offline backup must be described as offline.
2. Select **Kabir Bose** in Customer 360. Compare **A job loss**: the actual policy changes his reminder to a supportive hardship callback. Inspect the conversation/repayment timeline and evidence IDs.
3. Select **Imran Shaikh**, add the proposal to Review queue, approve in simulation, open Call studio, grant transcript permission and confirm the fictional account holder. Choose **I lost my job** and show growth stops.
4. Visit Customer hub: submit/review a fictional application, preview/apply fictional source data, then demonstrate a customer request and opt-out. State that these public exercises belong to the visit.

The private local Relationship hub/API has a separate durable workflow: applicant intake → staff attestation/review → source linkage → validated import → Customer 360 → service cases/preferences. Local operators are demonstration identities. The private local browser verified this path; it is not an externally hosted production borrower portal.

## Evidence to include

| Evidence | Verified scope |
| --- | --- |
| [GitHub run 37490270245](https://github.com/Cherie05/samvaad360/actions/runs/37490270245) | **557 tests / 75.62 seconds**, source `7e8cdc63805efde662bbc300dede0f33ce5cff07`; deployment job `112362108238` verified 20 customers and `LIVE_VERSION_READY`. |
| Hosted public browser | **20 checks** at `2026-10-06T15:47:55.069776Z`; genuine Snowflake source, seeded 20-customer cohort, six workspaces and new relationship exercises. Hosting does not directly expose its commit. |
| Local public browser | **20 checks** at `2026-10-06T14:59:04.862553Z`. |
| Private local relationship browser | **6 checks** at `2026-10-06T14:51:38.877300Z`; persistent SQLite staff/API/customer forms. |
| Local automated validation | Full **555 / 78.18 seconds**, followed by **14 targeted tests** including two new engine fact cases. CI covers the complete 557-test suite. |

Technical records are described in [BUILD_STATUS.md](../BUILD_STATUS.md). The product verification above covers runtime source `7a619e7`; documentation release `42fabba` follows it. Submission packaging adds a judge's guide to the sidebar, deck, recorded product walkthrough, docs and a read-only CoCo evidence skill; its later source/checks are recorded in [verification.json](../submission/verification.json).

## Exact outstanding submission items

| Item | Current state | Completion evidence needed |
| --- | --- | --- |
| Public repository and prototype links | Available and verified | Reopen both anonymously before final submission. |
| Deck | **Complete:** ten-page PDF, 625,215 bytes; ten-slide editable PowerPoint. All pages/slides visually inspected; bounds, notes, credential patterns and link checks passed. | Organizer-template validation remains required. |
| Organizer submission template | **Not provided in this session** | Download/access the actual template linked in the participant portal; inspect it and adapt the deck. An original deck is not proof of template compliance. |
| Actual CoCo workflow | **Pending** | Recorded native CoCo input → processing/tool execution → output, with at least one complete working flow and 2–3 modular capabilities. |
| 3–5 minute product walkthrough | **Recorded:** actual Snowflake-backed website, 251.51 seconds, narrated at 1.4× playback. Public release link above. | This covers the website; add actual native CoCo input/tool processing/output before claiming the required workflow video is complete. |
| Participant form submission | **Not recorded** | Uploaded PDF, completed required fields, successful confirmation/receipt and its timestamp. A saved draft or prepared artifact does not establish submission. |

The project has no measured real-world ROI/churn improvement, proven market exclusivity or guaranteed contest outcome. Its observable result is an evidence-backed, policy-controlled lender workflow on synthetic data. Real calls/SMS/financial changes were not performed. Production remains **NO-GO**; private Snowflake relationship sync, strong identity, actual lender-source connection and operational cloud rollout remain pending. See [production readiness](production-readiness.md).
