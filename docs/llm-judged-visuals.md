# Hill-climbing logos and other visual artifacts

Visual quality is not mechanically measurable in the same way as test pass
rate. It can still be optimized responsibly when deterministic asset checks are
combined with a calibrated, versioned LLM judge. The judge supplies evidence;
it is not ground truth.

## Frozen evaluation contract

Every candidate must receive the same brand brief, source references, rendered
preview matrix, rubric, judge model and settings. The judge must not see the
generator, candidate name, prior scores, conversation history, or sibling
scores.

Run deterministic gates before model scoring:

- expected format and dimensions;
- real alpha transparency when required;
- complete crop with no edge collision;
- required 32 px, 48 px, and 144 px renders;
- white and GitHub-dark surface composites;
- no accidental text, watermark, or unrelated elements.

A failed deterministic gate makes the candidate ineligible regardless of its
model-judged score.

## Logo judge v1

Score five non-overlapping dimensions. A critical dimension below bar fails the
candidate; otherwise compute the weighted average and round to the nearest
half-point.

| Dimension | Weight | Type | Observable question |
| --- | ---: | --- | --- |
| Subject clarity | 0.30 | critical | Does the mark immediately depict the requested subject without reading as letters or an unrelated symbol? |
| Small-size legibility | 0.25 | critical | Is the defining silhouette recognizable at every supplied target size? |
| Brand specificity | 0.20 | quality | Does the mark express this product's identity rather than generic stock iconography? |
| Surface integration | 0.15 | quality | Do edges, contrast, and color remain intentional on every supplied background? |
| Craft and distinctiveness | 0.10 | quality | Are proportion, negative space, detail, and finish coherent and memorable? |

Use these relational anchors exactly:

- **Below bar (<7):** a deterministic gate or critical dimension fails, the
  subject is ambiguous, or a required context cannot be judged.
- **7.0:** usable minimum; recognizable and technically valid, with material
  weaknesses in specificity, proportion, or polish.
- **7.5:** delta from 7.0: one material clarity or integration weakness is
  resolved without introducing a new failure.
- **8.0:** delta from 7.5: all required sizes and surfaces are consistently
  usable; remaining issues are minor rather than functional.
- **8.5:** delta from 8.0: the silhouette and visual decisions become clearly
  product-specific instead of merely competent.
- **9.0:** delta from 8.5: an expert reviewer finds no material weakness across
  the supplied contexts; only optional polish remains.
- **9.5:** delta from 9.0: the mark adds memorable, defensible differentiation
  while preserving the same clarity and technical reliability.
- **10.0:** delta from 9.5: reference-quality in every supplied context, with no
  actionable change from the calibrated human review panel. Reserve this score.

Each verdict must quote visible evidence for every dimension, explain the
anchor it clears, name the gap to the next anchor, and return structured JSON.

## Consistency and promotion

Run each judgment in clean context. For routine climbing, use three identical
independent judgments and take the median half-point. For pairwise tie-breaking,
judge both A→B and B→A; treat an order-sensitive result as a tie. Pin the judge
prompt and model version where the provider permits it.

Before the score controls promotion, calibrate `logo-judge-v1` against 50–100
human-labeled examples, including adjacent-anchor cases. Measure within-0.5
agreement, Spearman rank correlation, and binarized Cohen's kappa. Tune anchors
on a development split and verify agreement on an untouched calibration
holdout. Recalibrate after any rubric, prompt, or model change.

Use ordinary preview cases for candidate selection. Run the selected contender
once on a private promotion panel containing fresh sizes, surfaces, or crops.
Hill Climber promotes only a strict median gain that passes every deterministic
and critical gate. Preserve all judge outputs with the candidate receipt so the
decision remains inspectable.

This protocol makes a visual climb repeatable and falsifiable. It does not make
subjective taste perfectly objective or an uncalibrated model judge reliable.
