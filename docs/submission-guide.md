# Samvaad360 participant submission guide

Prepared for **Glacier Queries**, leader **Arunvpp**, **team size 1**. Registration values were confirmed by the participant. The signed-in portal supplied a deadline of **6 October 2026, 11:59 PM IST**. No submission receipt has been recorded.

## 1. Submit the GitHub/Deployed Link module

| Portal field | Paste this value |
| --- | --- |
| Challenges | **Customer 360 and Next Best Action Engine** |
| GitHub Public Repository Link | https://github.com/Cherie05/samvaad360 |
| Prototype Deployed Link | https://samvaad360.streamlit.app/ |

Click **Submit** for this module and keep its confirmation. The repository is public and the website is accessible without the owner's Snowflake login. If the free host is asleep, wake it and check its displayed source label.

## 2. Fill the Prototype/MVP module

Select **Customer 360 and Next Best Action Engine** again.

### Prototype/MVP Brief

Copy only this paragraph (**871 characters**, under 1024):

Samvaad360 is a lending Customer 360 and Next Best Action prototype. It joins loan/payment facts with emails, chats and call transcripts, then recommends evidence-backed, reviewable interventions. Consent, hardship and opt-out checks prevent inappropriate outreach; a new job-loss reply stops an earlier growth proposal and routes human help. Six workspaces cover portfolio visualizations, customer journeys, cited answers, review queues, adaptive conversation rehearsal and onboarding/imports/servicing. A restricted Snowflake reader serves 20 fictional customers with shared snapshots and query budgets. Verified: 557 CI tests, 20 hosted-browser checks and 6 private local portal checks. Public changes are visit-only simulations; real calls and financial execution are disabled. The repository includes modular evidence, recommendation and approved-runner CoCo skills.

### Prototype deck upload

Upload **[Samvaad360_Official_Submission.pdf](../submission/Samvaad360_Official_Submission.pdf)**. It is **six pages / 3,113,451 bytes (3.12 MB)**, below the 5 MB limit. It follows the actual participant-provided organizer template. The cover includes Glacier Queries, Arunvpp and team size 1. All six slides and PDF pages were visually checked; template-plan and fidelity checks passed with zero issues. Sources/provenance are in the editable [PowerPoint](../submission/Samvaad360_Official_Submission.pptx) notes. Upload the PDF to the form.

The earlier ten-page custom deck is supplementary material; use the official PDF above for the template upload.

### Demo video link - requirement still pending

The [published product walkthrough](https://github.com/Cherie05/samvaad360/releases/download/hackathon-submission-2026/Samvaad360_Demo.mp4) is **4:12** and demonstrates the actual public Snowflake-backed website. **It does not yet include the required actual native CoCo CLI workflow.** Treat it as supplementary product footage, not proof that the CLI video requirement is complete.

The portal requires a **3-5 minute screen recording** showing **CoCo input -> actual tool processing -> actual output**, at least one completed workflow and **2-3 modular skills/capabilities**. Use evidence, generate and approved runner. The [exact private CoCo setup and prompt](coco-demo.md) are ready. Record only after private sign-in. Show citations, the actual action ID and returned COMPLETED/CALLBACK state; keep passwords, tokens and account-login screens out of the recording. Include a short live website segment showing Snowflake and the hardship change. Publish the final video with access available to judges, and test its link in an incognito browser.

CoCo runs in the separate terminal originally titled **Samvaad 360 - Private CoCo Submission Setup**. Find it with Alt+Tab or the Windows Terminal taskbar tabs. If it has been closed, open PowerShell in this project and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -NoExit -File scripts/start_submission_coco.ps1
```

Complete any login privately, then enter the prompt from [coco-demo.md](coco-demo.md). A skill listing, Python-only run or copied prompt does not establish a completed native workflow. The latest read-only check still finds the isolated action APPROVED, with only evidence/ask observations, not a completed callback. Obtain the real output before claiming completion.

## 3. Finish and keep the receipt

Check the correct challenge, both public links, brief, final video accessibility and PDF upload. Click **Submit** for the Prototype/MVP module before the portal deadline. Keep the successful confirmation and timestamp for **both** modules. A saved draft, GitHub release or filled form is not a completed submission.

## Verification and scope

- [GitHub run 37490270245](https://github.com/Cherie05/samvaad360/actions/runs/37490270245): 557 tests passed; deployment verified 20 fictional customers and live files. Source: `7e8cdc63805efde662bbc300dede0f33ce5cff07`.
- Hosted anonymous browser: 20 checks, genuine Snowflake source, six workspaces, onboarding/import/service and visit isolation at `2026-10-06T15:47:55.069776Z`.
- Private local relationship portal: six persistent SQLite staff/API/customer workflow checks at `2026-10-06T14:51:38.877300Z`.
- [Submission verification](../submission/verification.json) records package checks. [BUILD_STATUS.md](../BUILD_STATUS.md) preserves implementation evidence.

All demo customers are fictional. Public changes remain visit-only; private operational persistence is local SQLite. Real calls, SMS and financial execution are disabled. Private Snowflake relationship sync, managed identity/database and carrier acceptance remain production gates. This is a working lending prototype; it does not claim insurance claims implementation, measured business ROI, market exclusivity or production certification. See [production readiness](production-readiness.md).
