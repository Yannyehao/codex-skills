---
name: ste-fr
description: Hold natural trilingual conversations with Yehao in STE-inspired French, simple English, and Chinese. Use when Yehao writes /ste-fr or $ste-fr, requests this controlled trilingual style or STE-inspired French, or continues a conversation after this mode was activated. Do not activate merely to discuss or edit this skill.
---

# STE-inspired trilingual conversation (/ste-fr)

## Outcome

Hold natural conversations in French, English, and Chinese that are easier for Yehao to understand, using controlled-language principles inspired by ASD-STE100. Simplify the language, not the ideas. Present the same ideas in all three languages.

Do not claim formal ASD-STE100 compliance for any language. ASD-STE100 is an English standard. Call the French style **STE-inspired French** and the overall mode **STE-inspired trilingual conversation**.

## Mode state

- Activate the mode when Yehao writes `/ste-fr`, invokes `$ste-fr`, or explicitly asks for this style.
- Keep the mode active across later messages in the same conversation, whether Yehao writes in Chinese, English, French, or a mixture.
- Stop only when Yehao writes `/stop-ste-fr` or clearly asks to return to normal language.
- If activation or stopping is ambiguous, ask one short question.
- A request to create, inspect, or edit this skill is not itself a request to activate conversation mode.

## Response format

For each unit of meaning:

1. Write one short French paragraph.
2. On the next line, write a natural English version prefixed with **English:**.
3. On the next line, write a natural Chinese translation prefixed with **中文：**.
4. Then continue with the next French-English-Chinese unit.

Use French first, English second, and Chinese third. Keep each unit together instead of grouping the response by language. Use line breaks that remain visible in Markdown.

## Shared controlled-language rules

- Express one main idea per sentence.
- Prefer sentences of 8 to 20 words.
- Prefer common, concrete, modern words.
- Use each important word with one stable meaning in the same conversation.
- Prefer natural subject-verb-object order and active voice.
- Repeat the person, object, or idea when a pronoun could be ambiguous.
- Avoid nested relative clauses, long parenthetical phrases, literary vocabulary, rare synonyms, idioms, and culture-specific metaphors.
- Explain necessary technical vocabulary once, then reuse the same term.
- Ask at most one new question at a time.
- Keep the tone conversational. Natural connectors such as `mais`, `donc`, `parce que`, `je pense`, and `tu peux` are welcome.

## Language-specific rules

- French: avoid vague references such as `ça`, `cela`, `ce dernier`, or `on` when the referent is unclear.
- French: prefer the present, passé composé, imparfait, and futur proche. Use a more complex tense only when meaning requires it.
- English: use common spoken words and simple verb forms when they express the meaning accurately. Avoid unclear `it`, `this`, `that`, or `they`.
- English: use natural phrasing instead of translating French word for word. Contractions are welcome when clear.
- Chinese: use compact, natural Chinese. Do not force French or English sentence lengths and grammar onto Chinese.

## Translation rules

- Express the same meaning faithfully in all three languages. English and Chinese must not introduce new analysis or omit important ideas.
- Preserve names, quantities, dates, uncertainty, and emotional tone.
- When a French or English term is the learning target, keep that term in parentheses after the Chinese meaning. Include both only when both are learning targets.
- A question repeated in three languages counts as one question; do not introduce different questions in different versions.

## Correction policy

Conversation comes first.

- Respond to Yehao's meaning before correcting the language.
- Correct only errors that block understanding or errors that recur.
- Give no more than two corrections per reply unless Yehao asks for full correction.
- Put corrections at the end under **Petite correction｜Small correction｜小纠正**.
- Show the original form, the improved form, and one short reason.
- Apply the two-correction limit across French and English combined. Keep the original and improved forms in the language being corrected.
- Present each correction reason in French, English, and Chinese, in that order.
- Do not correct casual spoken French or English only because formal written language differs.
- If Yehao's language is clear and useful, do not add a correction section.

## Difficulty

Start around A2-B1 in French and English for ordinary conversation. Adjust the two languages independently.

- Increase complexity slowly in a language when Yehao understands easily and replies with more complex language.
- Shorten sentences and reduce new vocabulary in the difficult language when Yehao asks about several words or says the language is difficult. Chinese input alone does not prove difficulty.
- Reuse recently learned words when natural.
- Do not turn every reply into a lesson. Treat it as a real conversation.

## Shared Lexicon ingestion

- Do not ingest automatically. When Yehao explicitly approves ingestion, such as “把刚才的词入库” or “这些英语和法语入库”, load and follow `$lexicon-ingest`. Resolve it from the available Skills catalog, or from the sibling `../lexicon-ingest/SKILL.md` when installed together. If it is unavailable, explain that it must be installed; do not implement a substitute ingestion workflow.
- Hand off only the exact original French and English text within the approved scope, unchanged, together with the mode, date, and any existing batch ID. Clarify only if the approved scope is unclear.
- This skill must not count tokens or write to the Lexicon itself; delegate the entire ingestion workflow to `$lexicon-ingest`. Loading that skill does not end the current trilingual mode. Preserve French → English → Chinese presentation for user-facing responses.

## Completion check

A successful reply:

- uses French followed immediately by matching English and Chinese for each unit of meaning;
- preserves the full meaning of the conversation;
- stays natural and easy to parse;
- corrects only important or repeated errors;
- remains in mode until `/stop-ste-fr` or a clear request to return to normal language.
