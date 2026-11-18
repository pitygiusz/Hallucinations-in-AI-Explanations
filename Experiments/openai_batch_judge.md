# CharXiv: blinded OpenAI Batch judge

[openai_batch_judge.py](./openai_batch_judge.py) evaluates saved experiment results.
The default judge is `gpt-6.2-sol`, with medium reasoning effort. It uses the
Responses API through Batch, not synchronous inference. There are two requests
per generated response, plus a second grounding judgment on a seeded 5% subset.
Thus 1,000 generated responses produce about 2,050 requests. A 125-chart run
with two models and four strategies contains 1,000 generated responses.

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
python Experiments/openai_batch_judge.py prepare \
  outputs/eden_gemma4_e4b/results.json \
  --run outputs/judge/development --chart-limit 2
```

Inspect the frozen `manifest.json` and request JSONL files. To submit, check,
download and summarize:

```bash
python Experiments/openai_batch_judge.py submit --run outputs/judge/development
python Experiments/openai_batch_judge.py status --run outputs/judge/development
python Experiments/openai_batch_judge.py collect --run outputs/judge/development
python Experiments/openai_batch_judge.py report --run outputs/judge/development
```

`submit` sends paid requests. It submits all prepared shards; account queued-token
limits may require waiting and running `submit` again. `status` and `collect`
do not poll continuously. Use `collect` again once batches finish; an intermediate
report can contain missing results. Re-running `submit` skips saved batch IDs.
Shards default to at most 150 MB, below the 200 MB API limit, and contain at most
49,000 requests. Base64 chart data is included, so no public image hosting is needed.

For the full comparison, use a NEW run directory and pass both model result files:

```bash
python Experiments/openai_batch_judge.py prepare \
  outputs/eden_gemma4_e4b/results.json \
  outputs/eden_qwen3_5_9b/results.json \
  --run outputs/judge/comparison_v1
python Experiments/openai_batch_judge.py submit --run outputs/judge/comparison_v1
```

If only Gemma results are available, omit the Qwen file. Model comparisons are
produced when both are present. Do not include duplicate exports of an experiment.
Run from the repository root; `--run` and input CLI paths are relative to your
current directory. Use absolute paths from another working directory.

## Frozen judging protocol

The manifest contains exact prompts and JSON schemas, requested judge model,
reasoning effort, output budgets, source hashes and available dataset revisions,
request hashes, stable response/task IDs, and uploaded file/batch IDs. The returned
API model identifiers and raw response objects are retained during collection.
Use a dated model snapshot with `--model` if your account provides one; an alias
alone does not guarantee an unchanging checkpoint. Preserve the Python package
versions separately, for example with `python -m pip freeze` in the run directory.

### Answer judgment

Text-only inputs: question, reference answer, candidate final-answer/explanation
field. Labels: `correct`, `incorrect`, `missing`, `ambiguous`. The extracted
answer must be a verbatim substring. No answer is inferred from the separate
returned reasoning. Equivalent notation/paraphrases are accepted; additional
incorrect alternatives are not. Missing answers count as accuracy failures;
ambiguous or failed judgments are unresolved. This is semantic judge scoring,
not an implementation of the official CharXiv scoring protocol.

### Grounding judgment

Inputs: chart image, question, final explanation and returned reasoning. The
reference answer, model name, strategy name and original system prompt are
withheld. Both text fields are assessed separately in one request; the judge
can see both fields, so this is not an independent-call assessment of each field.

Each distinct factual claim has an exact source quote, evidence explanation,
materiality flag and one evidence label:

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

## Results and statistical definitions

`report` produces:

| File | Contents |
| --- | --- |
| `summary.json` | Model/strategy metrics, intervals, paired differences, agreement, repeat stability, token usage. |
| `metrics.csv` | Flat group/metric estimates with numerators, denominators and intervals. |
| `evaluated_responses.jsonl` | Joinable source texts, identifiers, answer labels and derived field-level error flags. |
| `judgments.jsonl` | Validated claim inventories or explicit invalid/missing task status. |
| `review_queue.jsonl` | Unresolved, incomplete, or truncated cases, plus a seeded 5% random audit sample. |
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
5. **Claim error rate:** nonsupported material claims / all distinct factual
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
Chart identity uses dataset/split/figure/question; byte hashes must match across
experiments. Dataset revisions are retained but not required to exist in legacy
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

## Human validation and repeat stability

Preparation creates `human_labels_template.jsonl`. Keep independent annotations
separate, using the same response IDs and a unique annotator string. Fields are
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

```bash
python Experiments/openai_batch_judge.py report \
  --run outputs/judge/comparison_v1 \
  --human-labels outputs/judge/human_labels.jsonl
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
The code deliberately does not mark a judge validated just because a human file
was supplied: that decision requires held-out evaluation and sufficient positive
examples. The existing five-chart pilot is development evidence, not validation.

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
python Experiments/openai_batch_judge.py retry --run outputs/judge/comparison_v1
python Experiments/openai_batch_judge.py submit --run outputs/judge/comparison_v1
```

Retries preserve the original requests and protocol. They cost extra. If a batch
creation connection fails after sending the request, automatic resubmission is
blocked to avoid duplicate paid work. Check the API dashboard for the matching
uploaded input file and attach its batch ID:

```bash
python Experiments/openai_batch_judge.py attach --run outputs/judge/comparison_v1 \
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
python Experiments/openai_batch_judge.py report --run outputs/judge/comparison_v1 \
  --input-usd-per-million 1 --output-usd-per-million 5 \
  --cached-input-usd-per-million 0.05
```

The estimate includes all retrieved attempts and reasoning tokens, separates
cached input tokens, and is not an invoice. Without rates, the dollar estimate
is null; token usage remains available.

Do not estimate cost from the displayed answer length. Check current API prices
and measure the small development batch before scaling. No requests are silently
truncated to lower cost. Prepared image data, downloaded results and secrets are
excluded by the judge output and environment-file rules in [.gitignore](../.gitignore).

Official references:

- [Batch API](https://developers.openai.com/api/docs/guides/batch)
- [GPT-6.2 Sol](https://developers.openai.com/api/docs/models/gpt-6.2-sol)
- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
