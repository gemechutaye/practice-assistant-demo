# Practice Assistant — walkthrough guide

[Open the live application](https://practice-assistant-demo.vercel.app/) · [Inspect the public repository](https://github.com/gemechutaye/practice-assistant-demo)

Both recordings are silent screen captures from actual browser pages. They are not narrated as Gemechu and do not represent a connection to the employer’s private systems.

## Product walkthrough — 1 minute 48 seconds

Watch the [product walkthrough](https://practice-assistant-demo.vercel.app/materials/practice-assistant-demo.mp4). This recording reviews completed real model requests and persisted records in the local demonstration environment. The interface visibly identifies its local development identity. Public Supabase authentication and workspace isolation were verified separately on the live application.

Approximate positions:

| Time | What to inspect |
| --- | --- |
| 0:00 | The daily brief and assistant workspace. |
| 0:09 | Saved request history and a completed engineering request. |
| 0:21 | Recorded model/tool activity, cost, timing, and execution receipts. |
| 0:36 | Calendar readback: protected clinic appointments and the meeting rescheduled within confirmed team availability. |
| 0:48 | Completed paperwork and content-review tasks. |
| 0:54 | A public-source video draft and its supporting citation. |
| 1:09 | The separate public drafting model’s completed activity. |
| 1:18 | Persistent preferences. |
| 1:24 | Current workload reports and a saved report. |
| 1:30 | Public sources and their availability checks. |
| 1:38 | Role and change-of-situation controls. |

The fresh scheduling test first proposed 14:00–14:30. A new conflict made that approval stale. The assistant then requested fresh approval for 14:30–15:00 inside the confirmed 14:00–15:00 window, and the saved calendar was read back. The recording reviews that completed result.

The content request combined an administrative check with public drafting. Its separate drafting call received only approved public source IDs and the requested format/angle; approval created the draft and Jamie’s linked review task.

## Technical walkthrough — 3 minutes 22 seconds

Watch the [technical walkthrough](https://practice-assistant-demo.vercel.app/materials/technical-walkthrough.mp4). This recording opens the actual public GitHub repository and source files. It shows source inspection and saved verification evidence, not a fresh test-suite execution. The public `main` branch was verified at commit `808b66708a1f2b4e4310e548b1c13101abc3f4fb` during capture.

Approximate positions:

| Time | Source and question to inspect |
| --- | --- |
| 0:00 | Public repository and project context. |
| 0:14 | [agent.py](https://github.com/gemechutaye/practice-assistant-demo/blob/main/services/assistant/agent.py): how the model selects tools and the run stays bounded. |
| 0:37 | [domain.py](https://github.com/gemechutaye/practice-assistant-demo/blob/main/services/assistant/domain.py): how scheduling checks confirmed attendee windows and protected appointments. |
| 0:58 | Approval ownership, permission checks, and the exact saved plan. |
| 1:20 | Execution transactions and saved receipts used when work resumes. |
| 1:43 | [public_content.py](https://github.com/gemechutaye/practice-assistant-demo/blob/main/services/assistant/public_content.py): how the separate drafting model receives validated public sources. |
| 2:05 | [jobs.py](https://github.com/gemechutaye/practice-assistant-demo/blob/main/services/assistant/jobs.py): queue claims, leases, and stale-worker rejection. |
| 2:25 | [knowledge.py](https://github.com/gemechutaye/practice-assistant-demo/blob/main/services/assistant/knowledge.py): permission-scoped text and vector retrieval. |
| 2:44 | [pytest-summary.json](https://github.com/gemechutaye/practice-assistant-demo/blob/main/artifacts/verification/pytest-summary.json): 118 passing regression tests and the exact scope of that suite. |
| 3:00 | [worker-crash.json](https://github.com/gemechutaye/practice-assistant-demo/blob/main/artifacts/verification/worker-crash.json): physical process termination after a committed action, then successful recovery with one task and one message. |

The models can prepare proposed changes, but the approval API authorizes the saved plan. Execution checks current records again. The durable queue and per-action receipts preserve progress when a worker or response is interrupted. Public content drafting receives a deliberately narrower input than the office assistant.

The separate hosted-workflow verification used this test configuration: public Vercel frontend, Render API, and Supabase, with a temporary local worker during those recorded checks. The later deployment combines the API and a supervised worker on the free Render service; it can sleep after fifteen minutes of inactivity and take about a minute to wake. Consult the final deployment guide for its latest verification. The earlier tests are three verified functional examples, not a general accuracy benchmark.

Final release check: after the recordings, all 125 automated tests and three fresh workflows passed with the API and worker on Render and both laptop workers stopped. See the [cloud workflow evidence](https://github.com/gemechutaye/practice-assistant-demo/blob/main/artifacts/verification/cloud-workflows.json). The recordings retain their original capture-time provenance.

## Final public-release check

After the real Render restart, a fresh browser on the public application submitted one read-only request and received the correct stored task totals: Alex Kim 2, Sam Ortiz 1. Run `b95fb29f-47c1-4385-9a9d-fba90053aab1` completed with the local workers stopped, using the supervised cloud worker. It produced no action plan. All nine views opened through a Supabase anonymous identity. The service was already ready by the next browser observation; this visit does not claim to demonstrate a prolonged cold start.

Both public videos and the PDF returned HTTP 200. The product video was also played from its public URL, with a decoded duration of 108.208333 seconds. Full provenance, provider activity, and observed cost are recorded in the repository’s browser-verification report.
