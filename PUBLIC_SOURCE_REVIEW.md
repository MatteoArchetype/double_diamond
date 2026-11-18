# Public-source example for your review

**Review status: pending. No source intake, phase progression or final acceptance has been approved.**

Question: Does saving a SQLite transaction guarantee that it survives sudden power loss?

The proposed answer is conditional. The official documentation describes assumptions
about the operating system and storage, and discusses circumstances in which a power
failure can lose previously committed work. Recovering a consistent database and
preserving every committed transaction are different properties.

Please check the source context:

- [SQLite: Atomic Commit, Section 2 — Hardware Assumptions](https://www.sqlite.org/atomiccommit.html).
- [SQLite: How To Corrupt a Database, Section 3 — Failure to sync](https://www.sqlite.org/howtocorrupt.html).

The interpretation to review is: an unconditional survival claim is too strong;
SQLite's documented guarantees depend on the storage stack meeting its assumptions.
This is a reading of documentation, not a test of this computer or a recommendation
to change its settings. Both pages come from SQLite and count as one publisher,
not two independent confirmations. No real power-loss experiment was run.

The machine-readable packet retains short source excerpts, page URLs, section locators,
acquisition time, source metadata and a packet digest. The pages were opened directly
with the web tool before assembling the candidate; an authenticated human still needs
to check the context and independence of acquisition. The excerpts are not full pages.
They are real public-source candidates, explicitly separate from synthetic test data.

The candidate is kept outside the approved evidence state until that review. The next
human step is to approve or reject this source selection and bounded interpretation,
or request corrections. This does not authorize publication or waive subsequent
phase and acceptance decisions. Authenticated intake and the actual workflow run
must precede final MVP-08 acceptance; this document alone does not complete it.

See ACCEPTANCE_GUIDE.md for the durable decision path and PUBLIC_SOURCE_CASE.json
for the exact candidate content.
