# RepoLens — Interview Notes

Format per topic: **30-second answer → why → alternatives → trade-offs → how it scales/breaks.**
Add one entry per feature. Be honest about limitations; that is what makes the answers credible.

---

## Why store source code in its own table? (ADR-023)

**30-second answer:** "The audit has to report exact line numbers, so it needs the original source. I first rebuilt files from embedding chunks, but chunks contain injected headers, overlapping windows and duplicated nested symbols, so findings pointed to wrong lines. I now store the source in a separate table, which keeps file listings fast and lets me re-run audits when rules change without re-cloning."

- **Alternatives:** scan during ingestion (couples rules to ingestion, no re-runs); re-clone per audit (slow, repo may have moved); keep reconstructing from chunks (lossy).
- **Trade-offs:** extra storage; large files make large rows.
- **Scaling / failure:** cap file size at ingestion; later, move to object storage keyed by `sha256_hash` for dedup across versions.

## Bug I found in my own system (good story)

"I audited my own codebase and found the analyzer produced unreliable results: line numbers were wrong, route metadata was dropped before it reached the rules (so one rule could never fire), and one rule's AST path was dead code. I traced it to a single design flaw: the audit rebuilt source from chunks. Fixing the data flow and adding tests that assert exact line numbers on a real cloned fixture repo fixed all three at once."

## Why persist symbol metadata as JSON? (ADR-024)

**30-second answer:** "Routes are derived statically from decorator text, never by running the repo. I store them as JSON on the symbol so the schema doesn't change per framework; if I need to query by route I'd promote it to indexed columns."

- **Alternatives:** typed columns; JSONB; re-parse at audit time only.
- **Trade-offs:** not queryable in SQL; text JSON for SQLite portability.
- **Limitation to admit:** only Python routes are detected so far; Express/Next handlers aren't marked yet.

## Why did you change the CORS config? (ADR-025)

"My own scanner flagged the wildcard-origin-with-credentials pattern in my API. I replaced it with an env-driven allow-list and added a test that an unlisted origin gets no CORS headers."

## Testing approach

"Tests build a throwaway local git repository and run the real ingestion and audit pipelines against it, so they cover persistence, parsing and analysis together rather than mocking each layer." (Gotcha I hit: on Windows, git checks out CRLF, so the test normalises newlines.)

## How do you keep secrets out of your database and LLM prompts? (ADR-026)

**30-second answer:** "Redaction is enforced at one choke point, the rule registry, so no individual rule can forget it. Evidence is redacted before it's persisted or sent to the AI advisor. I also test it by checking that a token inside a non-secret rule's finding comes out masked."

- **Alternatives:** per-rule redaction (easy to forget), redact at the API layer (raw secrets already in the DB).
- **Trade-offs:** pattern-based, so unknown secret formats can leak; mitigation is a dedicated secret scanner later.
- **Honest limitation:** raw chunks are still embedded and used for RAG without redaction (known gap, planned fix).

## A failing rule shouldn't look like a clean scan (ADR-026)

"The original registry swallowed exceptions, so a crashing rule looked like zero findings. In a security tool that's dangerous. Now failures are logged and surfaced in the audit summary, and a test proves one broken rule doesn't stop the others."

## How do your rules handle multi-line code? (ADR-027)

"Regexes ran per physical line and missed multi-line calls. I join lines into bounded logical lines by bracket balance. The cap stops unbalanced brackets from swallowing a file. The real fix is AST queries, which is the next step for the highest-value rules."

## Why did you relabel rules from AST_ANALYSIS to STATIC_RULE?

"Most rules are pattern matches. Labelling them as AST analysis overstated what they do. Honest labels matter when findings feed a health score and an AI advisor."