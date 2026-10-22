# Ingestion invariants

## Lemmas and exclusions

One main record per `(Language, Entry)`, regardless of part of speech. Keep contextual senses/parts of speech in the audit table without making duplicate main records.

Normalize inflections: English `is → be`, `problems → problem`, `minutes → minute`; French `est → être`, `fais → faire`, `laisse → laisser`, `suffit → suffire`. Normalize sentence-initial capitalization, preserving dictionary `I` in English.

Split French contractions and elisions: `n’est → ne + être`, `du → de + le`, `l’absence → le + absence`. Resolve ambiguous contractions from context. Keep integral words such as `aujourd’hui` intact. Review hyphens by meaning; `30-to-40-minute` contributes `to` and `minute`, while the numbers are excluded. French `30 à 40 minutes` contributes `à` and `minute`. Do not discard range connectors with their numbers.

Exclude numbers, punctuation, nonlexical fillers, personal/company/brand/publication names, and other proper names unless the user explicitly selects them for retention. Record exclusions. Include all other valid words, including grammatical/function words.

A full sentence is not an Expression merely because it was supplied whole. A multiword expression may be stored separately only when the user explicitly selected it OR it is a stable expression whose meaning cannot be conveyed by its component lemmas. Its extra record must not inflate the word-token totals; keep word and expression totals separate.

## Counting and idempotency

Seen Count is actual lemma-token occurrences over processed approved originals, not sources, documents, chats, or batches. Batch deduplication means one write per lemma, not one count per lemma. Expanded contractions contribute each resulting lemma token.

- New lemma: Seen Count = this batch's actual occurrences.
- Existing lemma, fresh batch: new Seen Count = prior Seen Count + this batch's occurrences.
- Retried/repaired batch: delta = target batch occurrences − proven already-applied batch occurrences; new Seen Count = current total + delta.
- A completed batch with unchanged source must have delta 0 on rerun. Do not create another ID merely to bypass that check.
- A negative repair delta requires evidence that this batch was overcounted; never subtract unrelated history.
- Old unstructured Source may prove batch membership but not its contribution. Require a prior snapshot, ledger, or explicit user-provided historical baseline before repairing counts. Preserve that evidence in the repair audit.

## Source and rich text

Each contribution records mode, date, stable batch ID, actual batch occurrence count, sentence IDs, and either the full corresponding original sentences or a durable link to a full batch record. Example:

`ChatGPT｜/ste-fr｜2026-10-22｜batch:ste-fr-chat-2026-10-22-v1｜occurrences:4｜原句:F01,F02,F05,F06｜原文:<full corresponding sentences or durable batch record link>`

Preserve all historical Source text and native references. Append a clearly marked authoritative correction for this batch instead of deleting old provenance. If a repair marker supersedes an old generic entry, state that the marker's occurrences are the TOTAL contribution for that batch, not an additional contribution. Record old total, old batch contribution, delta, target batch contribution, and new total. Read the latest authoritative marker on future retries, not the sum of old and corrective labels.

If only lossy SQL text is available, fetch the page or faithful rows before mutation. Preserve mentions, links, and rich-text semantics using a supported lossless write format; if the connector cannot do that, stop the affected update instead of flattening history.

## New and existing fields

- New single lemmas: Type = Word; contextual Part of speech and Chinese Meaning.
- Set First Seen only for new records, using the source date.
- If the user confirms understanding the whole source, new certain words use Recognized in context. Ingestion approval alone does not prove understanding; use Uncertain when comprehension is not established or source/transcription/lemma/meaning is uncertain.
- Preserve existing Status, especially Active. Upgrade to Active only with explicit evidence of active mastery, never from reading comprehension alone.
- For uncertain existing words, preserve Status and annotate the new uncertain evidence in the batch audit/Source rather than overwriting historical mastery.
- Do not overwrite existing meaning or part of speech merely to simplify an ingestion update. Store this batch's contextual interpretation in provenance; modify existing fields only when explicitly justified and authorized.
