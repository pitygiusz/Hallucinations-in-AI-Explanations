# CharXiv: blinded OpenAI Batch judge, protocol v4

## What the judges output

These are **two separate requests to the same judge model**, each returning
strict, schema-validated JSON. Judge 1 checks answer correctness and strategy
adherence; Judge 2 checks grounding and does not receive the strategy prompt.
Use a new run directory for protocol v4; previously prepared requests retain
their original schemas.

Examples below are illustrative; the rows do not form a single judgment.

### Judge 1 — Answer correctness and strategy adherence

**Inputs:** question, reference answer, final response, and the exact saved
generation system prompt.

| Field | Meaning | Possible values | Example |
| --- | --- | --- | --- |
| `extracted_answer` | Exact answer text copied from the response. | String; may be empty for a missing or ambiguous answer. | `"1905"` |
| `verdict` | Whether the final answer matches the reference. | `correct`, `incorrect`, `missing`, `ambiguous` | `"correct"` |
| `justification` | Why the answer matches or differs from the reference. | String | `"The response and reference both give 1905."` |
| `strategy_followed` | Did the final response follow the saved prompt's observable strategy requirements? Independent of answer correctness. | `true` = followed; `false` = a required part is missing or violated, including partial compliance; `null` = cannot determine or saved prompt is missing. | `false` when the structured prompt requires a `Chart evidence:` section but it is missing. |
| `strategy_following_reason` | Short explanation of compliance, a missing requirement, or why it cannot be assessed. | Nonempty string | `"No Chart evidence section before the explanation."` |

The saved prompt determines the requirements: a brief explanation and
`Final answer:` line for direct prompts, evidence before explanation for
structured prompts, steps and relevant arithmetic for chain-of-thought, or
visible `Checks:` for verification. A wrong answer can follow its strategy and
a correct answer can violate it. This checks observable response behavior,
not factual grounding or internal verification. No extra API request is needed.
Python reports `strategy_following_rate` and `strategy_following_coverage`,
grouped by model and strategy; `null` judgments are excluded from the rate
denominator and remain visible in coverage.

### Judge 2 — Chart grounding

**Inputs:** chart, question, final explanation, returned reasoning, frozen
numerical tolerance, and optional verified source table. **No reference answer.**

| Field | Meaning | Possible values | Example |
| --- | --- | --- | --- |
| `chart_readability` | How clearly the chart can be read. | `readable`, `partly_readable`, `unreadable` | `"partly_readable"` |
| `chart_types` | Proposed chart-type labels for human checking; mixed figures can have several labels. | Array containing one or more of: `bar`, `line`, `scatter`, `area`, `pie`, `box`, `heatmap`, `histogram`, `other`, `unclear`. `other` means a recognizable type outside this list; `unclear` means the type cannot be confidently identified. | `["line", "scatter"]` |
| `final_explanation` | Assessment of the explanation shown to the user. | Object with the five fields in the next table. | An assessment finding a wrong value in “A has value 9.” |
| `returned_reasoning` | Separate assessment of the returned reasoning. | Object with the same five fields in the next table. | An assessment recording an exploratory mistake followed by a correction. |

**Inside each of Judge 2's two text assessments:**

| Field | Meaning | Possible values | Example |
| --- | --- | --- | --- |
| `applicable` | Does this text contain factual claims that can be checked? | Boolean: `true` / `false` | `true` for “A has value 9”; `false` for “Let me inspect the chart.” |
| `coverage_complete` | Were all distinct factual claims reviewed? | Boolean: `true` / `false` | `false` if the judge could review only part of a long explanation. |
| `requires_review` | Is there an ambiguity that could change the error label and needs human inspection? | Boolean: `true` / `false` | `true` if a blurry label could be either 5 or 9. A clearly wrong claim can have `false`. |
| `review_reason` | Explanation of why human review is needed. | String; empty when no review is needed. | `"The label is too blurry to distinguish 5 from 9."` |
| `claims` | Inventory of distinct factual claims, including supported claims. | Array of claim objects described below; empty if there are no auditable factual claims. | One entry for “A has value 9” and another for “B has value 3.” |

**Inside each claim:**

| Field | Meaning | Possible values | Example |
| --- | --- | --- | --- |
| `quote` | Exact text of the claim being checked. | Nonempty string copied verbatim from the assessed text. | `"A has value 9."` |
| `verdict` | Whether chart evidence or valid arithmetic supports the claim. | `supported`, `contradicted`, `insufficient_evidence` | `"contradicted"` when A is clearly labeled 5. |
| `categories` | Error types assigned to the claim. | Array using only `chart_reading`, `invented_information`, `unsupported_inference`, `calculation`. Supported claims require `[]`; other verdicts require one or more categories. | `["chart_reading", "calculation"]` |
| `material` | Could the claim affect the justification or substantive interpretation? Separate from whether it is correct. | Boolean: `true` / `false` | `true` for confusing which series is highest; `false` for harmless rounding. |
| `evidence` | Explanation of why the judge assigned its verdict, citing chart evidence or arithmetic. | Nonempty string | `"The response says 9, but A's bar is explicitly labeled 5."` |
| `resolution` | Whether the claim remains, was explicitly corrected later in the same field, or its correction status is unclear. | `retained`, `explicitly_corrected`, `uncertain` | `"retained"` if the model never corrects “A has value 9.” |
| `correction_quote` | Exact later retraction or correction in the same text field. | Nonempty verbatim string when `resolution` is `explicitly_corrected`; otherwise `""`. | `"Correction: A has value 5, not 9."` |
| `numeric_reference` | ID of a verified source-table cell directly comparable to the numerical claim. | A cell-ID string from the supplied verified table, or `""` when not applicable. | `"series_a_year_2020"` |
| `numeric_value` | The numerical value claimed for that referenced cell, in the same unit. | Number when mapped to a verified cell; otherwise `null`. | `9` |

**Python combines the answer and grounding judgments by response ID:** a correct final answer
plus a retained material error identifies a correct answer with flawed
explanation or reasoning.

- **Demonstrably wrong** means a claim is `contradicted`. The broader
  **unsupported** measure also includes `insufficient_evidence`.
- Python reports final-explanation errors, reasoning errors, and errors in either
  field separately, including their rates **among correct answers**. Explicitly
  corrected claims are counted separately; unresolved assessments remain missing.
- The primary metric is `correct_answer_final_explanation_unsupported`.
  The reasoning counterpart is `correct_answer_returned_reasoning_unsupported`.
  Judge outputs are saved in `judgments.jsonl`; Python calculates the rates and
  confidence intervals in `summary.json` and `metrics.csv`.

## Chosen prompting strategies

We compare four strategies on the same chart–question pairs for each model:

| Strategy | What the prompt requests | Purpose | Generation calls per response |
| --- | --- | --- | ---: |
| `direct` | A brief chart-based explanation and final answer. | Provides a baseline. | 1 |
| `structured` | List relevant chart evidence, then explain the answer. | Tests whether explicit evidence collection improves grounding. | 1 |
| `chain_of_thought` | Explain the chart-reading steps and show arithmetic. | Tests whether detailed explanations improve reliability or introduce additional unsupported claims. | 1 |
| `verification` | Generate a draft, then ask the same model to recheck its claims against the chart and revise it. | Tests whether self-verification removes errors or introduces new ones. | 2 |

All share the same chart-grounding rules and final-answer format. We compare
answer accuracy, explanation errors, claim-level rates and available token/time
usage without assuming that greater detail or self-verification improves results.
The grounding judge is not told which strategy generated a response; the answer
judge receives the saved prompt to assess adherence. Exact prompts are
defined in [the Gemma experiment](../eden/eden_charxiv_gemma.py) and
[the Qwen experiment](../eden/eden_charxiv_qwen.py).

## Workflow reference

[openai_batch_judge.py](./openai_batch_judge.py) evaluates saved experiment results.
The default judge is `gpt-6.2-sol`, with medium reasoning effort. It uses the
Responses API through Batch, not synchronous inference. There are two requests
per final generated response, plus a second grounding judgment on a seeded 5%
subset. Saved verification drafts receive two additional, separate requests:
answer correctness and grounding. Thus 1,000 final responses normally produce
about 2,550 requests when all 250 verification drafts are present. A 125-chart
run with two models and four strategies contains 1,000 final responses.

The Q&A and Phase 1 feedback are inputs to this implementation; this workflow
does not revise those documents or claim that human validation has occurred.
The primary estimand is **material unsupported-or-contradicted final explanations
among reference-correct final answers**. Returned reasoning is a separate
generated-text outcome, not evidence of internal model decision-making.

There are three explicit stages. `development` is limited to 25 charts;
`validation` excludes development charts and freezes the acceptance rule before
judging; `evaluation` requires a passing held-out validation under exactly the
same model, prompts, schemas, output budgets and policy. Insufficient human
evidence is a validation failure, not permission to scale.

## Setup and first run

From the repository root, in your Python environment:

```bash
python -m pip install -r requirements-judge.txt
```

Set `OPENAI_API_KEY` in your environment using your preferred secret manager.
The script never saves the key and does not load `.env` automatically. API access
to the requested model and a funded API account are required.

First prepare a small development batch from two charts. This performs no API
calls. Source JSON files are never modified, and relative image paths are
resolved against each source JSON's directory.

```bash
python Experiments/batch_api/openai_batch_judge.py prepare \
  outputs/eden_gemma4_e4b/results.json \
  outputs/eden_qwen3_5_9b/results.json \
  --run outputs/judge/development --chart-limit 2
```

Inspect the frozen `manifest.json` and request JSONL files. To submit, check,
download and summarize:

```bash
python Experiments/batch_api/openai_batch_judge.py submit --run outputs/judge/development
python Experiments/batch_api/openai_batch_judge.py status --run outputs/judge/development
python Experiments/batch_api/openai_batch_judge.py collect --run outputs/judge/development
python Experiments/batch_api/openai_batch_judge.py report --run outputs/judge/development
```

`submit` sends paid requests. It submits all prepared shards; account queued-token
limits may require waiting and running `submit` again. `status` and `collect`
do not poll continuously. Use `collect` again once batches finish; an intermediate
report can contain missing results. Re-running `submit` skips saved batch IDs.
Shards default to at most 150 MB, below the 200 MB API limit, and contain at most
49,000 requests. Base64 chart data is included, so no public image hosting is needed.

Omit the Qwen input if unavailable. Next export the proposed policy and finalize
it **before** preparing validation. The defaults are design choices, not a
published universal standard or an empirical finding:

```bash
python Experiments/batch_api/openai_batch_judge.py policy --output outputs/judge/policy.json
```

| Acceptance criterion | Proposed default |
| --- | ---: |
| Final-explanation error detection precision / recall / F1 | Each ≥ 0.80 |
| Answer correctness agreement with adjudicated humans | Accuracy ≥ 0.95 |
| Human-labeled and judge-resolved coverage, each label | ≥ 95% of all validation responses |
| Resolved validation charts, each label | ≥ 10 |
| Resolved human-positive / human-negative explanation responses | Each ≥ 10 |
| Resolved human-correct / human-incorrect answer responses | Each ≥ 10 |
| Independently double-annotated overlap among adjudicated explanation labels | 100% |
| Independent human–human Cohen's κ for explanation labels | ≥ 0.60 for every annotator pair |

Thresholds use point estimates; the report also gives chart-clustered 95%
intervals. Passing is a limited operational gate, not proof of accurate
prevalence estimation. Ten positive examples can still leave substantial
uncertainty. Increase the human sample when intervals or class coverage are
inadequate; never lower the frozen threshold after observing held-out results.

For example, two development charts plus 23 held-out charts make a 25-chart,
200-response human sample when both models have all four strategies. Keep all
outputs from one chart in the same stage. Annotate both development and held-out
responses, but only held-out labels determine acceptance:

```bash
python Experiments/batch_api/openai_batch_judge.py prepare \
  outputs/eden_gemma4_e4b/results.json \
  outputs/eden_qwen3_5_9b/results.json \
  --run outputs/judge/validation_v4 --stage validation --chart-limit 23 \
  --exclude-run outputs/judge/development --policy outputs/judge/policy.json
```

Inspect, then explicitly `submit`, `status` and `collect` this run as above.
Have two humans label it independently, then adjudicate (see below). Concatenate
their completed JSONL files into one validation labels file, preserving each
annotator identity and the separate `adjudicated` records. Evaluate locally:

```bash
python Experiments/batch_api/openai_batch_judge.py validate \
  --run outputs/judge/validation_v4 \
  --human-labels outputs/judge/validation_labels.jsonl
```

`validation.json` records pass/failure reasons, thresholds, denominators,
class counts, human agreement and uncertainty. `validate` exits with status 2
when the judge does not pass. If any criterion fails or is
undefined, use a smaller human-annotated analysis. Refine the codebook/judge on
development data and validate on **fresh** charts. Exclude previous validation
runs too with repeated `--exclude-run` options. Software cannot establish that
annotators worked independently or that nobody previously inspected a chart;
the team must document those facts.

Only after validation passes, prepare the full comparison in a NEW run directory:

```bash
python Experiments/batch_api/openai_batch_judge.py prepare \
  outputs/eden_gemma4_e4b/results.json \
  outputs/eden_qwen3_5_9b/results.json \
  --run outputs/judge/comparison_v4 --stage evaluation \
  --validated-run outputs/judge/validation_v4 \
  --human-labels outputs/judge/validation_labels.jsonl \
  --policy outputs/judge/policy.json
python Experiments/batch_api/openai_batch_judge.py submit --run outputs/judge/comparison_v4
```

Model comparisons are produced when both are present. Evaluation preparation
recomputes the validation decision from labels and judgments; it does not trust
a hand-edited `validation.json`. Calibration charts and identical image bytes
are excluded, including inherited exclusions from earlier runs. Consequently,
holding out 25 of a 125-chart input leaves 100 evaluation charts (800 final
responses for two models × four strategies). Generate additional charts to
reach a genuinely independent 1,000-response evaluation. Counts always refer
explicitly to charts or responses. Do not include duplicate exports of an experiment.
Run from the repository root; `--run` and input CLI paths are relative to your
current directory. Use absolute paths from another working directory.

## Frozen judging protocol

The manifest contains exact prompts and JSON schemas, requested judge model,
reasoning effort, output budgets, source hashes and available dataset revisions,
request hashes, stable response/task IDs, acceptance/tolerance policy, stage,
excluded chart/image IDs, validation evidence hashes, and uploaded file/batch IDs. The returned
API model identifiers and raw response objects are retained during collection.
Use a dated model snapshot with `--model` if your account provides one; an alias
alone does not guarantee an unchanging checkpoint. Preserve the Python package
versions separately, for example with `python -m pip freeze` in the run directory.

### Answer judgment

Text-only inputs: question, reference answer, candidate final-answer/explanation
field, and saved generation system prompt. Labels: `correct`, `incorrect`,
`missing`, `ambiguous`. The extracted
answer must be a verbatim substring. No answer is inferred from the separate
returned reasoning. Equivalent notation/paraphrases are accepted; additional
incorrect alternatives are not. Missing answers count as accuracy failures;
ambiguous or failed judgments are unresolved. This is semantic judge scoring,
not an implementation of the official CharXiv scoring protocol.
The same response also returns `strategy_followed` and
`strategy_following_reason`; these do not change the correctness verdict.
Saved verification drafts use their own saved draft prompt, rather than the
final verification prompt. A missing prompt requires `strategy_followed: null`.

### Grounding judgment

Inputs: chart image, question, final explanation and returned reasoning. The
reference answer, model name, strategy name and original system prompt are
withheld. Both text fields are assessed separately in one request; the judge
can see both fields, so this is not an independent-call assessment of each field.

Each distinct factual claim has an exact source quote, evidence explanation,
materiality flag, retention/correction state and one evidence label:

| Label | Definition |
| --- | --- |
| `supported` | Visible chart evidence or valid arithmetic supports the claim. |
| `contradicted` | Clear conflict with the chart or its own arithmetic. |
| `insufficient_evidence` | Not established by the chart, or evidence too ambiguous. |

The four error categories are `chart_reading`, `invented_information`,
`unsupported_inference`, and `calculation`. They are multilabel: totals may
overlap. Supported claims must have no error categories. A nonsupported claim
needs at least one category. Materiality means it could alter the justification
or substantive interpretation, not minor rounding or prose style.

The inventory includes supported claims to enable an explanatory claim-rate
metric. It is generated by the judge, not a human-established exhaustive claim
segmentation. Duplicate identical claim quotes within one field are rejected.
The entire field must have been reviewed; incomplete coverage, unreadable
central evidence or a judgment-changing ambiguity requires human review.
Procedural self-talk is not automatically a factual claim. Truncated reasoning
is assessed only as observed text; missing text is not invented or labeled false.

The annotation unit is an atomic factual assertion. Split compound statements
when their factual parts could receive different labels; quote each part
verbatim, including enough context to identify the series or comparison. Label
claims before deriving response-level indicators. Repeated identical claims
within a field count once. Human annotators should independently build/check
the claim inventory before seeing judge labels; the generated inventory is
not ground truth.

| Category | Example of a material error |
| --- | --- |
| `chart_reading` | Calling series B the highest when the plotted series A is clearly higher. |
| `invented_information` | Claiming a chart explicitly labels a unit that is absent. |
| `unsupported_inference` | Claiming the plotted correlation proves a causal effect. |
| `calculation` | Reading values 3 and 5 correctly but stating their sum is 9. |

`insufficient_evidence` is distinct from a demonstrably false claim. An unreadable
value produces an uncertain assessment requiring review; an unsupported causal
claim can be a determinate unsupported label when the chart clearly provides
no causal evidence. These have different denominator consequences.

An `explicitly_corrected` claim must quote a later correction from the **same
field**. The original assertion retains its evidence verdict. Primary field
error rates and claim fractions use retained claims, while `observed_*` rates
include corrected assertions; counts of corrected and total claims are also
reported. A correction in the final text never retroactively repairs the trace.
Quote validation verifies location, not the semantic validity of a retraction;
humans must audit that interpretation. Uncertain correction states require review.

Saved verification drafts are judged in separate blinded requests. Their
errors and answers are compared with the final output to report answer recovery,
answer regression, error removal and error introduction, each with its own
eligible denominator and chart-clustered interval. Missing draft assessments
remain missing. These transitions do not establish why verification succeeded
or failed, and do not expose the draft/final relationship to the judge.

### Numerical tolerance and optional source tables

The frozen proposed visual rule allows half the smallest readable tick interval
for an approximate reading, measured in axis space (log space on log axes).
If the readable scale or resolution cannot establish that interval, flag
insufficient evidence and request human review. Exact printed labels and
human-verified numerical tables instead use `max(absolute, relative × |value|)`;
both tolerances default to zero and can be changed in the policy **before**
validation. Do not select a tolerance per claim after seeing a model's value.

CharXiv inputs in this pipeline have no source tables. To use verified tables
from another dataset, optionally pass `--chart-metadata path/to/metadata.json`
to `prepare`. The object is keyed by full chart ID or original `example_id`:

```json
{
  "example-figure-id": {
    "chart_types": ["line", "scatter"],
    "human_verified": true,
    "verified_table": {
      "provenance": "Source table checked by annotator; original source identifier",
      "values": [{"id": "series_a_year_2020", "value": 10, "unit": "count"}]
    }
  }
}
```

`verified_table` is optional; chart-type-only metadata uses the other two fields.
Unverified source tables are rejected. Source-table data are sent only to
grounding requests, not the answer scorer. A numerical claim mapped by the judge
to a directly comparable table cell is checked locally against the frozen
tolerance, overriding a conflicting judge verdict when it mismatches. Mappings,
units and extracted claim values still require auditing; this does not
deterministically validate arbitrary arithmetic, inferred aggregates or causal
claims. A table extracted by another vision model is not independent ground truth.

### Chart-type analysis

Grounding outputs propose chart-type labels. `chart_type_review.json` collects
them for human inspection. Only human-verified metadata supplied at preparation
defines chart-type metric groups; changing metadata requires a new prepared run.
Types are `bar`, `line`, `scatter`, `area`, `pie`, `box`, `heatmap`, `histogram`,
`other`, and `unclear`. Mixed charts may have several labels and appear in several
subgroups. Type associations are exploratory and may reflect question difficulty.

## Results and statistical definitions

`report` produces:

| File | Contents |
| --- | --- |
| `summary.json` | Model/strategy metrics, intervals, paired differences, agreement, repeat stability, token usage. |
| `metrics.csv` | Flat group/metric estimates with numerators, denominators and intervals. |
| `evaluated_responses.jsonl` | Joinable source texts, identifiers, answer labels and derived field-level error flags. |
| `judgments.jsonl` | Validated claim inventories or explicit invalid/missing task status. |
| `review_queue.jsonl` | Unresolved, incomplete, or truncated cases, plus a seeded 5% random audit sample. |
| `chart_type_review.json` | Per-chart proposed labels, provenance and human verification status. |
| `raw/` | Unmodified downloaded API output/error files. |
| `usage.jsonl` | Token usage and returned model for each attempt, including retries/repeats. |

For each model and strategy, the report separates these estimands:

1. **Answer accuracy:** reference-correct / resolved answer judgments, counting
   missing final answers as incorrect. Failed/ambiguous answer judgments remain
   missing and must be reported with coverage.
2. **Material contradiction rate:** responses with at least one material
   contradicted claim / responses with a determinate grounding assessment.
3. **Material unsupported-or-contradicted rate:** same, additionally including
   `insufficient_evidence`. This broader measure is not called factual falsity.
4. **Correct answer, flawed explanation:** material-error cases among
   reference-correct responses with a determinate grounding assessment. Both
   narrow and broad definitions are reported.
5. **Claim error rate:** nonsupported material retained claims / all distinct retained factual
   claims, computed per response, then macro averaged. Long explanations do not
   automatically receive more weight. Claim extraction itself can be imperfect.
6. **Per-category response rates:** at least one material nonsupported claim
   in the category / determinate response assessments.

Final explanation, returned reasoning, and their union have separate response
rates. A union positive needs one determinate positive field; a union negative
requires all present fields to be determinate negatives. Absent/nonfactual fields
are not certified as grounded; their field metrics are null. Never interpret
an unresolved or absent assessment as a clean explanation.

Rate estimates include denominator, contributing chart count and group record
count. Conditional metrics intentionally exclude incorrect answers. Numerators
for macro claim rates are sums of per-response fractions, not integer error counts.
Metrics computed before all tasks finish are provisional complete-case estimates;
missingness and manual-review coverage can be nonrandom. A large judge-labeled
set does not repair a biased judge or make its labels human ground truth.

Confidence intervals are seeded **95% percentile cluster bootstrap** intervals
(2,000 replicates by default), resampling chart IDs and retaining their responses.
Chart identity uses dataset/split/figure, so changing question text cannot put
the same figure into development and validation. The input format currently
supports one question per chart per model/strategy; duplicates are rejected.
Image byte hashes must match across experiments. Dataset revisions are retained but not required to exist in legacy
files: verify provenance manually if a revision is missing. The script does not
require every strategy/model cell to be present; compare coverage and matched
chart counts. Fewer than two contributing charts yields no interval. Degenerate
samples can yield zero-width intervals; these are not proof of certainty.

Pairwise strategy differences within model, and model differences within strategy,
use only matched charts with resolved labels on both sides. Conditional paired
differences use only charts answered correctly on BOTH sides, a different
population from each model's unconditional conditional rate. Differences are
right minus left. Intervals are exploratory, unadjusted for multiple comparisons;
no confirmatory p-values or automatic superiority claims are produced.

Paired comparisons include final explanation, trace and claim rates separately;
conditional pairs require both final answers to be correct. Reports warn when
the primary conditional metric has fewer than the frozen
`min_conditional_charts` (default 10), rather than assuming a larger run must
contain enough correct answers. They also include missing-answer and grounding
coverage, character/claim counts, generation configuration, available generator
usage, and a sensitivity analysis restricted to known untruncated responses.
Unknown truncation status is excluded from that sensitivity analysis explicitly.
Quantization, model revisions and token budgets remain potential confounders;
different precision runs are not interpreted as a clean model-size comparison.

## Human validation and repeat stability

Preparation creates `human_labels_template.jsonl` and separate
`human_annotator_1_template.jsonl`, `human_annotator_2_template.jsonl` and
`human_adjudicated_template.jsonl`. These cover all responses so independent
overlap is explicit. The four team members can divide the workload into two
independent annotators per response; use actual unique annotator names and
preserve their individual files. Do not expose judge labels before annotation.
Use the shuffled `human_grounding_packets.jsonl` with chart copies under
`human_images/` for grounding, and `human_answer_packets.jsonl` for the separate
reference comparison. These omit model and strategy metadata; the grounding
packet also withholds the reference answer. Image paths are relative to the run
directory and use opaque chart filenames to avoid revealing the generating
model through source-directory names. Keep the answer packet hidden until the
grounding annotation is complete.

The answer annotation packet includes the saved prompt for adherence checks.
Review it after grounding so strategy instructions do not bias the grounding
labels. The optional human label `strategy_followed` is `true` when all applicable observable requirements are
met, `false` for partial or failed adherence, and `null` when unassessable. Human
agreement for this label is reported separately; it does not extend the primary
answer/grounding acceptance gate to certify adherence labels.

Response-label fields are
`true`, `false`, or `null` (not assessed/uncertain). Copy the template before editing.

```json
{"response_id":"r...","annotator":"reviewer_1","answer_correct":true,"final_explanation_contradicted":false,"final_explanation_unsupported":true,"returned_reasoning_contradicted":null,"returned_reasoning_unsupported":null}
```

`unsupported` includes material contradictions AND insufficient evidence; it must
not be false when `contradicted` is true. Optionally add per-category labels such
as `final_explanation_calculation` or `returned_reasoning_chart_reading`, where a
true label means at least one material nonsupported claim in that category.
Add adjudicated labels as another annotator called `adjudicated`; they do not
replace the original independent annotations.

An optional `claim_annotations` object can hold a full grounding assessment in
the frozen `schemas.grounding` format from the manifest, independently authored
by the human. It defaults to null. The importer validates exact quotes,
corrections and evidence labels, derives response labels from the inventory, and
rejects supplied response labels that contradict it. This supports reproducible
claim annotation without pretending that automated claim segmentation itself
has been validated. Keep the inventories alongside the original human labels.

```bash
python Experiments/batch_api/openai_batch_judge.py report \
  --run outputs/judge/validation_v4 \
  --human-labels outputs/judge/validation_labels.jsonl
```

The report computes confusion matrices, precision, recall, F1, accuracy and
Cohen's kappa per annotator and field/label, plus pairwise human–human agreement
on overlapping responses. Intervals resample charts. Undefined precision/recall,
F1 or kappa remain null. Repeat stability uses the extra grounding requests and
the same binary comparisons; repeats are never majority-voted into primary labels.
Repeatability is not validity. These repeated requests may also be affected by
server-side determinism/caching.

Split human development/validation sets by chart BEFORE prompt development.
Declare judge acceptance thresholds before inspecting held-out annotations.
Supplying a human file alone never marks a judge validated. The frozen gate
requires held-out evaluation, coverage, human agreement and enough positive and
negative cases. Only answer correctness and the primary final-explanation
unsupported response label are covered by this acceptance decision; claim
segmentation, trace labels and individual categories need separate validation
before claims of validated performance. The existing five-chart pilot is
development evidence, not validation.

`annotation_dataset.json` records TO_COLLECT status, units, sizes, sources,
unknown class balance and planned overlap. Assign actual annotators, a deadline
and an annotation-release licence in the study's dataset statement; these fields
remain explicitly null until the team decides them. Do not infer that annotation
rights permit redistribution of chart images. Reports supply observed class
counts by annotator and label rather than inventing an expected balanced set.

This software addresses the judge, annotation, metric, uncertainty and study
design feedback. Literature-table corrections, bibliography, supervisor/LLM-use
declarations and dataset legal statements in the report still require a report
revision; the script cannot establish them.

## Feedback coverage

| Concern from the Q&A / review | Implementation |
| --- | --- |
| Difficult pilot charts and uncertain causes | Four evidence categories, human review and exploratory type analysis; no automatic causal attribution. |
| Chart counts versus response counts | Frozen run counts, annotation dataset description and chart-level exclusions. |
| Sparse correct answers / pooled model differences | Model/strategy denominators, conditional chart-count warnings and model-specific estimates. |
| Trace errors later corrected | Separate fields, verbatim correction evidence, observed versus retained error rates. |
| Longer traces create more error opportunities | Per-response claim fractions, claim/character counts and corrected-claim counts. |
| Frozen judge acceptance / fallback | Policy export, independent overlap, adjudication, held-out gate and human-only fallback. |
| Different strategies solve different questions | Paired shared-success comparisons with matching question checks. |
| Verification sometimes fails | Separately blinded saved drafts and draft-to-final transition metrics. |
| Numerical approximations / source tables | Frozen visual/table tolerances, ambiguity review and optional verified-cell checks. |
| Low-resolution images and unreliable judges | Explicit unresolved labels, coverage, human review and validation before evaluation. |
| Token caps differ in effect | Truncation/missing-answer reporting, saved generation settings and untruncated sensitivity. |
| Correlated outputs / reproducibility | Chart-clustered intervals, immutable request hashes and recorded versions/provenance. |

Run the offline regression suite from the project root:

```bash
python -m unittest discover -s Experiments/batch_api -p test_openai_batch_judge.py
```

Tests use synthetic local judgments and mocked API clients. Passing tests means
the implementation behaves as specified; it does not validate an actual judge.

## Failures, retries and cost

API refusals, invalid JSON, non-verbatim quotes, schema inconsistencies and
incomplete output are invalid judgments and excluded from resolved denominators.
They are retained for review. Generation truncation and judge-output truncation
are different: the former describes the model under evaluation, the latter means
the judge's labels are unusable. Default judge budgets are 2,048 output tokens
for answer checks and 12,000 for grounding, including judge reasoning tokens.
They differ from the 1,536-token generation cap used in the experiment.

After terminal batches have been collected:

```bash
python Experiments/batch_api/openai_batch_judge.py retry --run outputs/judge/comparison_v4
python Experiments/batch_api/openai_batch_judge.py submit --run outputs/judge/comparison_v4
```

Retries preserve the original requests and protocol. They cost extra. If a batch
creation connection fails after sending the request, automatic resubmission is
blocked to avoid duplicate paid work. Check the API dashboard for the matching
uploaded input file and attach its batch ID:

```bash
python Experiments/batch_api/openai_batch_judge.py attach --run outputs/judge/comparison_v4 \
  --chunk 0 --batch-id batch_REPLACE_WITH_ACTUAL_ID
```

This command checks the batch's uploaded file ID. If no batch was created, verify
that fact in the dashboard before clearing that chunk's `submission_started`
field in the manifest; it is not included in the frozen protocol hash.

The actual token usage (including judge reasoning and retries) and available
batch elapsed wall times are retained. Batch elapsed time includes queueing and
must not be called model inference time. Source-model token counts and timings
are retained when present. The package and Python versions used for preparation
are recorded automatically in the manifest.

To also report an estimated USD cost, supply CURRENT Batch rates explicitly;
these example rates correspond to the Sol documentation checked on 18 November
2026 and must be rechecked before use:

```bash
python Experiments/batch_api/openai_batch_judge.py report --run outputs/judge/comparison_v4 \
  --input-usd-per-million 1 --output-usd-per-million 5 \
  --cached-input-usd-per-million 0.05
```

The estimate includes all retrieved attempts and reasoning tokens, separates
cached input tokens, and is not an invoice. Without rates, the dollar estimate
is null; token usage remains available.

Do not estimate cost from the displayed answer length. Check current API prices
and measure the small development batch before scaling. No requests are silently
truncated to lower cost. Prepared image data, downloaded results and secrets are
excluded by the judge output and environment-file rules in [.gitignore](../../.gitignore).

Official references:

- [Batch API](https://developers.openai.com/api/docs/guides/batch)
- [GPT-6.2 Sol](https://developers.openai.com/api/docs/models/gpt-6.2-sol)
- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
