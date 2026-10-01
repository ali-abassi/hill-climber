# Hill Climber workbench

## Product and visual thesis

A local experiment desk for people improving code, instructions, writing,
interfaces and configuration in Git. Its first job is to turn a broad ambition
into a bounded, externally measurable experiment; its second is to show what
the evidence actually supports.

For builders about to spend model capacity on uncertain work, this interface
feels like a quiet field notebook so the goal and proof remain visible. It
prioritizes a legible experiment over dashboard density, expressed through a
serif question, precise native controls, open margins and restrained green.
It succeeds when someone can prepare a meaningful command and distinguish a
development gain from a private promotion at both 1280 and 390 pixels.

## Reference ledger

Rendered reference inspected in a real headed Chrome session on 2026-10-01:

| Exact URL | Observed | Use and departure |
| --- | --- | --- |
| https://gepa-ai.github.io/gepa/workbench/ | The published product screenshots put score history above diagnostics, with a narrow candidate list. The light surfaces and thin boundaries keep experiment evidence legible. The starter offers distinct submit, configure and inspect actions. | Use the evidence hierarchy and separation of setup from inspection. Depart with a single editable planning form and contextual recipes rather than starter cards; distinguish development selection from final private promotion rather than treating every score gain as accepted. No agent chat or self-grading. |

Screenshot evidence is local at `/tmp/hill-ui-reference-gepa.png`; it is not a
repository asset. Color and spacing are authored here, rather than inferred
from the reference's implementation.

## Composition and typography

The 1104px usable desktop canvas has a compact brand header and three section
tabs. A left-aligned question leads into a six-recipe selector, then a 760px
form beside a contextual route guide. The mobile form becomes one column;
recipes become two rows, context moves into the Field guide, and actions become
full-width. Never require horizontal scrolling to prepare a climb.

Three typography directions considered:

- All system sans: coherent native utility, but the goal looks like another
  settings label; rejected for the primary question.
- Monospace instrument: accurate for evidence, but overemphasizes machinery
  and makes writing/design users decode a developer interface; rejected.
- Georgia display plus system sans controls: chosen. The large open question
  supplies editorial focus while compact, familiar controls remain precise.

Georgia is a local system font with Times New Roman/serif fallbacks. Body uses
the native platform stack. The display is 60px desktop, 47px mobile, normal
weight with tight tracking. Body is 15px; labels and help are 12px/11px. Mono
appears only in commands, evidence IDs and file surfaces. No font downloads.

## Ten system levers

1. Product register, balanced form density; quiet surroundings.
2. Left-aligned question → work family → objective → evaluator → prepared
   command. Results put verdict before chart and chart before raw evidence.
3. Serif for questions and outcome numbers; system sans for decisions; mono
   for text that will be executed or matched exactly.
4. Canvas `#f6f7f3`, white inputs, ink `#202a23`, secondary `#657067`, line
   `#dce2da`. Green `#275d3b` only for actions, selected recipe and evidence.
   Warm red is errors; ochre marks a retained baseline.
5. A 4px base with intentional 8/12/16/20/24/32/48px relationships.
6. 6px control radii, 9–12px grouped surfaces, a circle only for a stage
   marker or measured point.
7. Thin boundaries and material contrast provide separation; no shadows.
8. A simple inline mountain mark and six stroke icons; no stock imagery or
   decorative charts. The result chart uses verified numerical data.
9. One primary action per section. Native labels, controls, disclosure,
   keyboard focus, real errors and observable waiting states.
10. No gradients, glass, pseudo-live activity, model success claims, excessive
    badges or decorative code terminals. Commands only appear after a real
    plan response. Demo results are labelled explicitly.

## Interaction and evidence

Changing a field invalidates its prepared command. Recipe selection updates
evaluation guidance and untouched repeat defaults; custom goals and budgets
stay intact, and selecting the current recipe is a no-op. Suggested defaults
remain visible as advice. The Field guide includes the selected recipe's gates
at mobile widths. The
server prepares safely quoted commands; the browser never executes them.
Inspection only renders a controller-verified response, escapes dynamic text
through DOM text nodes, and draws its own SVG instead of executing artifact
markup. Changing an experiment path invalidates pending results. Every result
shows its verified source directory, the final kept score separately from its
development best, and a chart sized only after the result is visible. The
local deterministic demo uses an explicit POST action and makes no model calls.

Required rendered proof: Plan at 1280 and 390; preparation with custom input;
Results with real deterministic evidence; failed inspection; Guide; keyboard
focus and no page overflow. Record resulting captures in the QA handoff,
not as fabricated proof in this design document.
