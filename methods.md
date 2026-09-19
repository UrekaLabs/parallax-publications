# Public Methods

Edition label: `2026-10`

This repository publishes only reviewed, allowlisted, public-facing outputs.

Principles:

- Keep the private application isolated from the public delivery plane.
- Publish from a fixed approved release-output directory only.
- Preserve provenance, hashes, and review status in the public artifact set.

Non-goals:

- No private corpus mounting.
- No wiki indexing.
- No hidden editorial state.

## Legal and privacy review

Applies to Parallax Publications and the Parallax Research Atlas.

### 1. Why this exists rather than relying on removal

[The removals policy](corrections-removal.md#removals-policy) § 6 states the limit honestly: under CC BY 4.0, removal does not
retract copies. That makes pre-publication review the real protection, and the removal route
a backstop for what review misses. This policy is where the protection actually lives.

**No review, rights, privacy, provenance, or security gate is waived to meet a publication
date.** Where a date and this policy conflict, the component is descoped.

### 2. Mandatory review triggers

A candidate item may not enter a public edition until it has been reviewed against this
policy when **any** of the following applies:

1. It makes a factual claim about a **named living private individual**.
2. It makes an adverse factual claim about a **named living public figure** — meaning any
   claim of wrongdoing, misconduct, or criminal conduct.
3. It touches **sealed, grand-jury, or Rule 6(e)-adjacent material**, or analyses it.
4. It is **victim- or minor-adjacent** — drawn from a document, case file, or production
   known to contain such material.
5. It contains or derives from **recovered-redaction content**
   ([the redaction policy](privacy.md) § 4).
6. The **publication gate flagged it** — restricted path, missing sensitivity metadata, PII
   pattern, wrong destination, or non-allowlisted item.
7. It is **court-record-derived** and has not previously appeared in a published edition.

Where the review load cannot be carried before a release, the affected findings are descoped
rather than published unreviewed.

### 3. What review checks

- **Accuracy** — the claim is supported by the cited primary source, read directly rather
  than through a secondary characterisation.
- **Provenance** — the cited document resolves, its hash matches, and the citation points to
  the primary rather than to an aggregator.
- **Privacy** — the standing redactions in [the redaction policy](privacy.md) § 2 have been
  applied.
- **Characterisation** — allegations are described as allegations; charges as charges;
  findings as findings. A conflation here is the most likely source of a defensible-claim
  becoming an indefensible one.
- **Necessity** — where sensitive material is included, that its inclusion is necessary to
  the finding rather than incidental colour.

### 4. Recording review

Review state is not a memory or a conversation. Every registry item carries **review state,
accountable owner, provenance, and exact content hash**. The gate is fail-closed: an item with
no sensitivity or approval metadata is **refused, not admitted**.

Source material does not always carry sensitivity metadata. Fail-closed is what makes that
safe: absence of metadata is treated as "not cleared", never as "nothing to clear".

Because the hash is recorded, review attaches to an **exact version**. A reviewed item that
is subsequently edited is unreviewed again. There is no such thing as inheriting an approval
across a content change.

### 5. Who reviews

The publication owner. The single-approver posture is explicit: the person
who decides an item has cleared review is the same person who signs that the edition may
publish. There is no independent second reader.

**This is the weakest point in the first edition's controls and should be read as such.**
It is acceptable for a first edition only because the technical gates are fail-closed and
independently tested, so the human is not the only thing standing between restricted
material and a public URL. It should be revisited after the first edition.

### 6. Outside counsel

This policy is not a substitute for legal advice, and its author is not a lawyer. Four
matters warrant legal counsel: defamation exposure on
adverse claims about named living people; the Rule 6(e) line; whether EU or UK data
protection obligations attach to publishing personal data from US court records on a public
domain; and whether a DMCA designated agent is required.
