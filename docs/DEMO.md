# Practice Assistant — demonstration guide

Open [the application](https://practice-assistant-demo.vercel.app). Each browser receives its own fictional workspace through Supabase anonymous sign-in. The application identifies itself as an independent demonstration. No employer login, private data, or access is required.

## A five-minute walkthrough

**1. Start with the office, not the chat.** Open Today, Calendar, Tasks, and Messages. Point out the fixed demonstration clock: September 8, 2026 at 08:15 Pacific. Maya's procedure is tomorrow at 09:00, so the fictional administrative paperwork deadline is 45 minutes away. The existing preparation task belongs to Alex. The patient appointments must remain fixed.

**2. Give the assistant an open request.** Ask: “Get tomorrow ready. Check paperwork, protect my clinic time, and prepare useful follow-up. Use existing tasks where possible.” Open the run inspector to show the actual model calls and selected tools. Read the proposed changes before approving them. Show the new records in their office views after execution.

**3. Change the situation.** Ask the assistant to move the engineering meeting to a suitable time. In Demo controls, occupy its proposed slot before approval. Approve the original plan and watch it reread current records and present a revised plan. The new meeting must fit both the calendar and the team's confirmed 11:00–12:00 or 14:00–15:00 availability.

**4. Show recovery.** Prepare a distinct task and a demo message. Enable the timeout-after-write scenario before approving. When the run reports partial completion, use “Resume remaining changes.” Show the same saved task and the remaining completed action. The receipt, mutation, and approval record explain why the operation does not duplicate work.

**5. Show the content boundary.** Ask for a short public video explaining why scar consultation pricing is individualized. The assistant retrieves public source notes, drafts a script and caption, proposes an assigned review, and finds a safe recording time. Switch to the content role: private preparation and engineering information should be unavailable. Review completion closes only the linked authorized review task.

## Additional evidence

- Save a preference through an approved plan, reload, and ask for it in another request. The memory view permits explicit edits and deletion.
- Open Reports and compare the counts with the current tasks. Counts come from database queries.
- Use Sources to inspect URLs, dated notes, and public-versus-fictional provenance. “Check source” records availability without replacing the reviewed note.
- Download a run's evidence from the inspector. Supabase stores the bundle privately and issues a ten-minute download link.
- Voice input produces an editable transcript. Sending the transcript is a separate action; recording a voice note does not approve office writes.
- Run the MCP server to demonstrate the same authenticated tools from an MCP client. The role restrictions still apply.

## Code walkthrough

The repository is [gemechutaye/practice-assistant-demo](https://github.com/gemechutaye/practice-assistant-demo).

| Question | Code to open |
| --- | --- |
| How does the model choose tools? | `services/assistant/agent.py` |
| Where are writes approved and validated? | `services/assistant/domain.py` |
| How does interrupted work resume? | `services/assistant/jobs.py`, `worker.py`, and PostgreSQL checkpoints |
| What can the content specialist see? | `services/assistant/public_content.py` |
| How are sources retrieved? | `services/assistant/knowledge.py` |
| How are users and workspaces separated? | `auth.py`, `store.py`, database policies |
| How can another application call tools? | `mcp_server.py`, `/api/integrations/handoff` |
| What is tested? | `tests/`, `scripts/verify_worker_crash.py`, `artifacts/verification/` |

## Explain the limits accurately

This is an AI-assisted engineering demonstration using fictional office records and short public-source notes. Demo inbox delivery is a stored office message; it is not real email. CRM/EMR handoffs demonstrate an authenticated, versioned contract against the fictional record adapter. The app does not connect to EmerGPT, diagnose, recommend treatment, or claim HIPAA compliance. Role switching demonstrates permissions inside one visitor's workspace; real staff provisioning is a separate integration.

Review the code and rehearse the walkthrough before an interview so that you can explain the design decisions, failure cases, and boundaries in your own words.
