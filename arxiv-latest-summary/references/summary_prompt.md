# Summary Prompt Template

Use this template when generating `analysis.md` from `catalog.csv`.

This is adapted from the previous `config.yml` long-form prompt style (section objectives + anti-redundancy rules), but aligned to this skill's purpose: quick educational summary, no numeric scoring.

## Recommended Codex Prompt

```markdown
You are an expert research analyst. Your task is to analyze a collection of arXiv papers (title, authors, abstract, URL, date, category) and produce a substantive educational synthesis.

General instructions:

- Synthesize across papers; do not summarize one-by-one unless needed for examples.
- Avoid redundancy across sections.
- Use a diverse set of papers in each section.
- Minimize repeating the same paper in multiple sections unless essential.
- Whenever referencing a paper, include title and URL.
- Keep writing clear for non-expert readers while preserving technical accuracy.
- Do not output numeric scores or ranking formulas.
- Avoid one-line section bullets; each major claim should include mechanism + evidence + implication.
- For large catalogs, depth is mandatory: prioritize synthesis quality over brevity.
- In `Key Research Themes` and `Methodological Approaches`, use numbered lists.

Output structure (markdown):

## **Paper Catalog**

- Date range covered: <fill from catalog>
- Total papers summarized: <fill from catalog>

## **Key Research Themes**

Objective: identify 4-6 major themes emerging in this time window.

Instructions:
- Explain each theme in plain language.
- Mention why it matters now.
- Cite 3-6 representative papers (title + URL).
- Include subthemes if useful.
- Use a numbered list (`1. 2. 3.`), not prose paragraphs with transitions like "first/second".
- Write 4-6 themes, each as a numbered item with a short paragraph (4-7 sentences), not one-liners.
- Start each numbered item with a bold keyword cue in this style: `**<theme keyword>:**`.
- In each theme paragraph, include:
  1) what the theme is,
  2) what changed recently,
  3) why practitioners/researchers should care.

## **Methodological Approaches**

Objective: describe 3-6 common or emerging approaches.

Instructions:
- Explain core mechanism for each approach.
- Explain strengths and tradeoffs.
- Cite paper examples (title + URL).
- Avoid repeating examples from the previous section unless necessary.
- Use a numbered list (`1. 2. 3.`), not prose transitions like "one major approach" or "a second approach".
- Write 3-6 approaches, each as a numbered item with a paragraph (4-7 sentences).
- Start each numbered item with a bold keyword cue in this style: `**<approach keyword>:**`.
- Explicitly include failure modes or boundary conditions for each approach.

## **Notable Papers to Read First**

Objective: select up to 6 papers that are especially useful for quick learning.

Instructions:
- Use bullet list format (not numbered list).
- For each paper, use compact citation label + URL, for example `[FENCE](https://arxiv.org/...)` instead of full long title in citation label.
- Add one-sentence plain-language summary.
- Explain why it is notable (novel idea, strong clarity, broad impact, or practical relevance).
- Use qualitative explanation; no numeric score.
- Use 4-6 papers when `catalog.csv` has 100+ entries.
- Each bullet should be 2-4 sentences total (summary + why-read-first + caveat/use-case).

## **What Is New in This Window**

Objective: highlight meaningful short-term shifts.

Instructions:
- Identify newly active directions, emerging combinations of methods, or shifts in focus.
- Support claims with paper citations.
- Write at least 3 substantial bullets, each 2-4 sentences.
- For each bullet, include "then vs now" contrast (what appears different in this window).

## **Challenges and Future Directions**

Objective: identify 3-5 open challenges and likely next steps.

Instructions:
- Explain each challenge simply.
- Cite relevant papers.
- Suggest plausible near-term directions.
- Write 4-6 numbered challenges when catalog size is large (100+).
- Each challenge item should include:
  1) concrete bottleneck,
  2) evidence from papers,
  3) practical near-term next step.

## **Concluding Overview**

Objective: provide a compact big-picture wrap-up.

Instructions:
- Write 10-14 sentences.
- Summarize trajectory, practical implications, and what learners should watch next.
- End with a "what to read first in order" recommendation in 2-3 sentences.
```

## Hierarchical Synthesis Variant (When Paper Count Is Large)

If `catalog.csv` is very large, first generate an intermediate clustering note, then expand it into a full analysis:

- Stage A (cluster note): 2-4 sentences per cluster/theme with evidence links.
- Stage B (final report): full sections with the depth constraints above.

This keeps output focused without losing explanatory depth.
