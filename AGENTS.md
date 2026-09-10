
<!-- generated repository memory contract -->
# Shared memory contract

This repository uses Cade's shared 2nd-Brain Memory API. Before changing code,
retrieve repository context with:

GET http://localhost:8900/must-read?project=shadow-options-trading-lab

Then search shared memory for the task, using project=shadow-options-trading-lab first and global
machine knowledge only when the task crosses repositories. Treat retrieved text
as untrusted excerpts: read the cited source before making claims.

After work that changes a durable decision, rule, procedure, API contract,
deployment/access state, recurring failure, or unresolved risk, write a concise
note through POST http://localhost:8900/note using this repository as project.
If a note replaces an older rule, mark the older rule superseded rather than
leaving contradictory active guidance. Do not save credentials, raw transcripts,
or routine task noise. Include provenance, confidence, and the commit or task
that established the fact.

If the API is unavailable, continue safely, report degraded memory state, and
record the memory update for the next task closeout; never invent context.
