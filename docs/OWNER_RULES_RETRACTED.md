# OWNER_RULES.md - RETRACTED 2026-07-16 (owner directive)

`docs/OWNER_RULES.md` was deleted on 2026-07-16 at the owner's explicit instruction:

> "IGNORE or do not take as fact the OWNER_RULES.md file. I am a human, we make mistakes, we are
> not good at math, AND I know NOTHING about trading. […] That file was the literal
> interpretation of my complaints about the bot/system architecture that was incorrectly
> deemed gospel."

## What this means for the codebase

- The file is **no longer an authority**. Nothing may be justified "because OWNER_RULES says so."
- Constants and behaviors previously labeled *owner-verbatim* keep that provenance label - it
  records where they **came from** - but the label no longer confers correctness. Each such
  behavior must stand on its own mathematical/EV merits under the normal evidence discipline
  (sweep-ledger registration, WORST-ledger N-graded validation).
- Design questions previously closed by quotation (e.g. "no fixed-price-point exits ever",
  risk-neutral EV-max with no variance/ruin consideration, the overnight evidence rule's exact
  gates) are **open engineering questions**, to be settled by evidence.
- The standing **end goal** (owner, 2026-07-16, supersedes the retracted file): *an autonomous
  options trader that plays with the edge the house gives it, making informed decisions, while
  remaining in a slightly 'casino' posture to attempt to maximize profit taking.*

## Historical copies

- git: committed at `cf7ffc9` (`docs/OWNER_RULES.md`), SHA-256 first-12 `d25e74fe6658`.
  That file is archived with the equity system and is not part of this public copy.

Rule-number citations in `atlas/options/exit_engine.py` / `exit_engine_legacy.py` docstrings
refer to the retracted file's numbering and remain as historical mapping documentation only.
