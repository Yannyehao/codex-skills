# Highlight synchronization

Use this alongside the shared ingestion rules for approved intensive-study Corpus ingestion. Keep one Lexicon: all eligible words/expressions are counted, while only explicit user-marked unfamiliar items join the highlighted review subset.

## Evidence and mapping

- Read the original Corpus annotations and notes before flattening them. The current Corpus convention is the user's active yellow highlighting. Accept only highlights identified as the user's unfamiliar-word marks, or the user's explicit designation of the exact item. Assistant emphasis, guessed difficulty, generic formatting, Status=Uncertain, or a word merely appearing in Corpus are not highlight evidence.
- Capture the exact marked surface/span, original full sentence, stable source URL and sentence ID (Corpus S-number where available), and the evidence identifying it as the user's mark.
- Normalize the marked item to the same Language + Type + normalized Entry key used for ingestion. A highlighted inflection maps to its lemma. An explicitly selected expression maps to Expression; do not automatically mark every component word unfamiliar. A whole highlighted sentence with unclear target is unresolved, not an Expression.
- Missing annotations, truncated retrieval, or ambiguous span/lemma mapping: retain the exact gap in the ledger. Continue independently verified token ingestion when authorized, but do not claim highlight synchronization complete.

## Mutation boundaries

| Field | Ingestion behavior |
| --- | --- |
| Highlighted | Set true only with explicit evidence. For an existing row, preserve true even when this source is unmarked. Never reset it during ingestion. A new unmarked row stays false/default, which does not imply mastery. |
| Review Context | Append missing exact original context plus source link and sentence ID for the marked item. Preserve previous contexts and native links/formatting. Never replace with a generated example. |
| Recall | Preserve existing values. A new highlighted row may use Not reviewed; do not overwrite a prior real review or infer Forgotten/Remembered from highlighting or comprehension. |
| Last Reviewed / Next Review | Preserve existing values; leave blank on new rows. Ingestion is not a review and must not invent review dates. |
| Status / Seen Count | Apply the existing independent ingestion rules. Highlighting is not a Status change and review activity is not another token occurrence. |

Use faithful before snapshots, re-read before mutation and send only intended changed properties. Existing empty Recall can remain empty; do not rewrite it to manufacture a review.

## Ledger and retries

Alongside the existing occurrence ledger, record a stable highlight evidence key (source identity + sentence ID + exact marked span + normalized entry key), evidence details, before snapshot, intended metadata patch, and applied/verified checkpoint. Keep context deduplication by that key, not by batch ID alone. Repeated copies of the same source annotation are one context.

A previously imported source can acquire a newly available highlight: reconcile its original token contribution first, then apply only the missing Highlighted/context metadata. Its already-applied occurrence delta remains zero; do not replay counts or invent a new source batch to bypass reconciliation. Unknown prior counts block count changes, not a separately provable, authorized metadata-only patch to an unambiguous existing row. Do not create a new counted row from a highlight-only backfill without the ordinary source/count reconciliation.

Historical bulk backfill is separate work, not automatically authorized by a skill update. Do not modify Corpus completion, database schemas/views, or review results while adapting the ingestion skill.

## Verification

Read back every affected row. Verify the intended flag/context, no duplicate context on retry, unchanged existing Recall/review dates/Status/First Seen and historical content, and the independently planned occurrence delta. If an outcome is unknown, read back before retry; keep unresolved metadata checkpoints pending. Report token ingestion and highlight synchronization separately.

Dry-run cases (no live writes): new highlighted inflection; unmarked source matching an already-highlighted row; new ordinary unmarked lemma; an already-ingested source acquiring its first highlight; duplicate highlight retry; expression versus component words; ambiguous whole-sentence mark; missing annotations; existing real recall result/dates.
