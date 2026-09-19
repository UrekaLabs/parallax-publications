# Privacy

Edition label: `2026-10`

Publications are screened for privacy risk before release.

We do not publish:

- private corpus content
- unreleased personal data
- contact details beyond the public security route
- unresolved PII-risk material

If a correction or removal is needed, use the corrections/removal route and the published safety contact.

Pre-publication legal and privacy review is described on the [Public Methods](methods.md) page.

## Redaction policy

Applies to Parallax Publications and the Parallax Research Atlas.

### 1. What redaction is for

Redaction removes specific sensitive content while leaving the surrounding record intact and
citable. It is preferred over [removal](corrections-removal.md#removals-policy) wherever it is sufficient, because it
protects the person without destroying the evidence.

Every redaction is visible. We mark that something was redacted and what category it fell
into. A silent excision is indistinguishable from a document that never contained the
material, and it makes the record untrustworthy in exactly the way this project criticises
elsewhere.

### 2. Standing redactions — applied before publication, without a request

These are applied by default to everything we publish, in both products:

1. **Names and identifying details of victims and survivors of sexual abuse**, including
   where those names appear unredacted in the underlying public record.
2. **Identities of people who were minors** at the time of the events described.
3. **Government identity numbers** — Social Security numbers, passport numbers, driver
   licence numbers.
4. **Financial account identifiers** — account numbers, routing numbers, card numbers.
5. **Medical information** about identifiable individuals.
6. **Personal contact details** of private individuals — home addresses, personal phone
   numbers, personal email addresses.
7. **Dates of birth** of private individuals.

Names and conduct of **public officials and public figures acting in a public capacity** are
not redacted. That material is the point of the publication.

### 3. Redaction must be irreversible

A redaction in anything we publish must remove the underlying data, not merely conceal it.

- No black boxes drawn over live text.
- No CSS, layer, or overlay concealment in HTML.
- No metadata, alt text, or embedded original retaining the redacted content.
- In the Atlas, no redacted value surviving in a sibling field, an index, an embedding, or a
  checksum input from which it could be recovered.

**Every redaction is verified after rendering, in the published artifact, not in the source.**
A redaction that is correct in the source and recoverable in the PDF is a failed redaction.

This project has documented at scale what happens when this is done badly — redactions in
the source corpus were recoverable. We are not entitled to make the same mistake in our own
output.

### 4. Recovered redactions — the hardest rule here

Our research has recovered text from failed redactions in government-produced documents. The
existence of those failures is a legitimate and important finding about the disclosure
process, and we publish that finding.

**We do not publish the recovered content itself.**

We publish: that a redaction failed, where, in which production, of what category, and what
that says about the disclosure process and its review. We do not publish the underlying text
that the redaction was intended to withhold, and we do not paraphrase it closely enough to
reconstruct it.

The reasoning: the government's redaction may have been improper, but that is a question for
a court or an oversight committee, not something we resolve unilaterally by republishing.
And where the redaction was *proper* — a victim's name, a minor's identity — republishing it
because the government fumbled the tooling would harm exactly the person the redaction
existed to protect.

Where we believe a redaction was improper and the material should be public, the remedy is
to say so and to route it to the body with authority to order release — not to release it
ourselves and call that oversight.

### 5. Requesting a redaction

Use the route in [the removals policy](corrections-removal.md#removals-policy) § 4. Redaction requests are handled on the same
timeline and under the same grounds; the difference is only in the remedy applied.

### 6. Publishing a redaction

Redactions ship as a patch release of the affected edition, exactly as corrections do
([the corrections policy](corrections-removal.md#corrections-policy) § 5). The correction notice records that a redaction was
made and its category, and does not restate the redacted material.
