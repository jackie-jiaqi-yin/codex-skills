# Narrative Grounding

Use the language model for interpretation, not for inventing evidence.

## Grounding rules

- Do not claim causality from observational patterns.
- Do not state that a feature is "important" without tying it to a computed ranking or chart.
- Mention exact columns and quantitative evidence when possible.
- Separate data quality issues from behavioral or business interpretation.
- If a pattern may be an artifact of missingness, leakage, imbalance, or small sample size, say so.

## Tone rules

- Sound like an analyst reviewing real evidence.
- Avoid boilerplate praise such as "valuable insight" or "useful visualization".
- Prefer concise interpretation plus a concrete next check.

## Good narrative moves

- explain why a skew or outlier pattern matters,
- connect missingness to downstream modeling or reporting risk,
- compare several candidate features instead of discussing them in isolation,
- point out when a visually strong pattern may still need validation.
- for health or life-science datasets, distinguish baseline variables from follow-up or censoring variables,
- call out multicollinearity when several biologically related measures move together,
- mention when target labels are only observed for a subset and explain why that changes interpretation.
