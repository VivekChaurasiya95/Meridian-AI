# Meridian AI — Scripted Demo

This guide runs the same demo the same way every time: two fixture
investigations in a disposable `Demo` workspace, a reset procedure that
returns the database to the pre-demo state, and a numbered checklist to
read aloud while clicking.

## Prerequisites

- Docker Compose stack running (PostgreSQL, MinIO, API, worker).
- Web app running (`npm run dev` in `apps/web`, port 3010).
- One signed-up user (any email); the seed script needs its address.
- A configured model provider if you want the worker to advance past
  reproduction (without one, both cases queue honestly and the topbar
  shows the model state; steps 7–9 then become “queued” branches below).

All commands run from the repo root with the venv active:

```powershell
$env:DATABASE_URL="postgresql+psycopg://meridian:meridian@localhost:5435/meridian"
```

## Fixtures

`scripts/demo_seed.py` builds both fixture repositories in memory (no
fixture files in the repo) and seeds them through the real service
layer — the same validation the API applies:

| Fixture | Project slug | Case | Expected outcome |
|---|---|---|---|
| Fixable shop bug | `demo-shop` | Cart total on `/` never updates (`app.js` reads DOM id `total`; the span id is `totals`) | Pipeline reproduces, proposes a patch, verifies it |
| Unreproducible report | `demo-ghost` | Report claims a `/checkout` crash, but the snapshot has no checkout route or payment code | Pipeline reaches `blocked` or `inconclusive` with an honest reason |

Seed:

```powershell
python scripts/demo_seed.py --email you@example.com
```

The script prints the workspace, project, snapshot, and investigation
ids. It refuses to run twice — reset first.

## Reset to a known state

```powershell
python scripts/demo_seed.py --reset
python scripts/demo_seed.py --email you@example.com
```

Reset deletes the demo workspace's jobs, investigations (stages,
evidence, hypotheses, patches, runs, reports included), projects,
snapshots, and the workspace row itself, in FK-safe order. It prints
`no demo workspace; nothing to reset` when there is nothing to do.
Object-storage blobs from demo uploads stay behind as harmless dev
residue; they are never listed without their database rows.

Verify the reset before an audience:

1. `python scripts/demo_seed.py --reset` prints the removal line.
2. Re-seed and confirm two `investigation_id=` lines print.
3. Open `/app/investigations?workspace=<workspace_id>` and confirm two
   queued cases.

## Scripted checklist (~15 minutes)

Read the bold line, do the step, confirm the expected state.

1. **“Everything starts in a workspace.”** Open `/app`. Confirm the
   `Demo` workspace lists. Open it.
2. **“Each codebase is an immutable snapshot.”** Open project
   `demo-shop`, tab `Snapshots`. Expand the snapshot. Confirm file rows
   and the Assessment line beneath them.
3. **“Checks report; they never certify.”** Tab `Security`. Open the
   assessment. Confirm the wording: either findings, or “No issues
   detected by configured checks” — never “safe” or “verified”.
4. **“A case pins its source.”** Tab `Investigations`. Confirm the
   seeded `Demo Shop: scripted demo case` pins the snapshot from step 2.
   Open it.
5. **“Stages, evidence, and hypotheses stay labeled.”** Scroll the
   investigation: stages with text statuses, evidence rows with
   redaction badges, hypotheses marked as hypotheses.
6. **“People review; the pipeline waits.”** On a hypothesis, choose
   Review, pick a verdict, record it. Confirm the toast and the review
   history entry.
7. **“Patches are proposed, never applied silently.”** In Patches,
   choose View diff, then Review. Confirm the approval binding line
   (sha + snapshot). Approve with a note. Confirm the toast and the
   status change to approved/queued.
8. **“Verification runs real checks.”** In Verification, confirm the
   run rows and the baseline-vs-post-patch comparison. Queue a rerun
   and confirm the toast.
9. **“Reports render only recorded state.”** In Reports, generate a
   Markdown report. Confirm it reaches Ready, then download it.
10. **“Dead ends stay honest.”** Open the `Demo Ghost` case. Confirm it
    reads `blocked` or `inconclusive` with a reason (worker running),
    or `queued` with the model/pipeline state visible (worker or model
    unavailable) — never a fabricated fix.
11. **“Membership and theme are boring on purpose.”** Open `/app/settings`.
    Switch Light/Dark and confirm the whole app follows. Add a second
    member by email if one exists, or show the role control.
12. **“Reset returns to the start.”** Run the reset + seed commands
    again and reload `/app/investigations`: two queued cases, nothing
    carried over.

## If something goes wrong live

- Seeded cases stay queued: the worker or model provider is down. Say
  so, show the queued badges and the Jobs page statuses, and continue
  the click path on steps 5–6 (review works without the worker).
- Ghost case completes instead of blocking: the worker found a
  different interpretation. Say so and show its stages — the honest
  branch is whatever the pipeline recorded, not the script.
- Reset fails partway: re-run `--reset` (it is idempotent over
  leftovers) and check the API logs for the failing constraint.
