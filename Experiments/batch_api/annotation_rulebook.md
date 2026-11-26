# Human annotation rulebook — protocol v6

These four rules follow the [judge prompts](./judge_schema.py). Field formats and
templates are described in the [workflow guide](./judge_workflow.md#human-annotation-files).

1. **Judge the chart evidence independently.** Annotate grounding before opening
   the reference-answer/prompt packet or seeing other annotators' or judge labels.
   Use only the chart, valid arithmetic and any supplied verified source table.
   Assess the final explanation and returned reasoning separately; neither repairs
   the other. Do not reward confidence, verbosity or a plausible conclusion, and
   do not invent missing text. Follow the supplied tolerance: approximate readings
   allow half the smallest readable tick interval in axis space, including log
   space. Exact labels/table values use the supplied absolute/relative tolerances
   (zero by default).

2. **Count distinct factual assertions, including supported ones.** Split a
   compound statement when its parts could have different truth labels; count
   repetitions once per field and omit purely procedural self-talk.
   `total_claims` includes assertions later corrected. `corrected_claims` requires
   a later explicit retraction **and correction in the same field**; a changed
   final answer alone is insufficient. Count the replacement assertion too.
   Example: “A is 9. Correction: A is 5, not 9” gives two total claims, one
   corrected and one retained. Remaining error counts concern retained claims
   only: `total_claims − corrected_claims`.

3. **Separate errors, materiality and uncertainty.** A retained assertion is
   supported, contradicted by visible evidence/arithmetic, or unsupported because
   the chart does not establish it. `contradicted_claims` and `unsupported_claims`
   are disjoint. `material_errors` counts errors affecting justification or
   substantive interpretation; `material_contradictions` is its contradicted
   subset. Harmless rounding/style is not material. For retained material errors,
   select any applicable categories: `chart_reading` (wrong series/axis/value),
   `invented_information` (absent labels/data/units), `unsupported_inference`
   (beyond the evidence), `calculation` (wrong arithmetic/inconsistent steps).
   Use `assessed` only after complete review; `absent` for empty text and
   `no_claims` for present text without factual assertions (zero counts, `[]`).
   Incomplete review or ambiguity affecting materiality/correction gives
   `requires_review` (all counts/categories `null`). Never turn uncertainty into
   zero errors. Human response labels concern **material** errors: `contradicted`
   means at least one material contradiction; broader `unsupported` includes
   contradictions and insufficient evidence. Use `null` for unresolved,
   absent/nonfactual, or zero-retained-claim assessments.

4. **Score the answer and strategy separately, after grounding.** Compare the
   last explicit `Final answer:` line, or unambiguous conclusion, with the supplied
   reference; accept equivalent notation/units/paraphrases, but not additional
   wrong alternatives. Do not infer an answer from separate reasoning. Missing
   answers and abstention against a substantive reference are incorrect;
   conflicting/ambiguous answers are unresolved (`answer_correct: null`). Check
   `strategy_followed` against only the saved prompt's observable requirements:
   `true` for compliance, `false` for missing/violated requirements, `null` if
   unassessable or the prompt is missing. Correctness and adherence are independent.
   Preserve both independent annotations before recording a separate adjudication.
