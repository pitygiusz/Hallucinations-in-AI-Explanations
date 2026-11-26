# Chart-response judging — protocol v6

## TL;DR

The judge evaluates saved chart responses from Gemma, Qwen, or another generator.
It returns **labels and claim counts**, without copying responses, quoting claims,
or writing evidence explanations. Python calculates the statistics.

| Judge | Inputs | Output |
| --- | --- | --- |
| Answer | Question, reference answer, final response, saved generation prompt | Correctness verdict, strategy adherence, review flag |
| Grounding | Chart image, question, final explanation, returned reasoning, tolerance policy, optional verified table | Chart readability/type and separate compact claim counts for each text field |

Each generated response receives two independent API requests. Grounding sees
neither the reference answer nor the generator/strategy identity. It sees both
text fields but must assess them separately. The answer request has no image.
Requests are **not grouped across strategies or models**: each grounding request
includes its own copy of the image, even inside the same batch.

The main statistic is `correct_answer_final_explanation_unsupported`: among
reference-correct responses with usable explanation assessments, how many retain
at least one material contradicted or unsupported claim? Unknown assessments
are excluded, with coverage reported separately; they are never counted as clean.

Both providers use asynchronous Batch APIs. `prepare` is local; `submit` starts
paid work; `status` checks progress; `collect` downloads and validates outputs;
`report` calculates statistics locally. Use a **new run directory** for v6.
Existing runs retain their frozen schemas and results.

## Implementation

| File | Responsibility |
| --- | --- |
| [judge_schema.py](./judge_schema.py) | Current prompts, strict JSON schemas, semantic count validation, legacy dispatch |
| [judge_common.py](./judge_common.py) | Preparation, configuration, frozen protocols, human labels, statistics, reports |
| [judge_policy.py](./judge_policy.py) | Acceptance thresholds, chart metadata and tolerance rules; numerical checks for detailed legacy inventories |
| [openai_batch_judge.py](./openai_batch_judge.py) | OpenAI Responses API through Batch |
| [google_ai_studio_judge.py](./google_ai_studio_judge.py) | Google AI Studio Gemini Batch through `google-genai` |
| [judge_schema_legacy.py](./judge_schema_legacy.py) | Detailed claim-inventory schemas/validation for older runs and optional human annotations |
| [annotation_rulebook.md](./annotation_rulebook.md) | Four annotation rules for humans, matching the v6 judge prompts |

OpenAI uses strict JSON Schema Structured Outputs. Google requests
`responseMimeType: application/json` with `responseJsonSchema`. Collection applies
both JSON Schema validation and local semantic checks. Structured output does not
establish that the judge's factual judgments are correct.

## What the judges output

### Answer correctness and strategy adherence

| Field | Meaning | Possible values | Example |
| --- | --- | --- | --- |
| `verdict` | Does the candidate's final answer match the reference? | `correct`, `incorrect`, `missing`, `ambiguous` | `"correct"` |
| `strategy_followed` | Did the final response follow the saved prompt's observable requirements? Independent of correctness. | `true`, `false`, `null` | `false` for a missing required section |
| `review_required` | Is correctness ambiguous or adherence unassessable? | Boolean: `true` / `false` | `true` when the saved prompt is unavailable |

The judge compares the last explicit `Final answer:` line, or otherwise an
unambiguous stated conclusion. It must not infer an answer from separate reasoning
or solve the question itself. Equivalent notation, units and paraphrases are
accepted; additional incorrect alternatives are not. Abstention does not match
a substantive reference. No answer gives `missing`; unresolved conflicting
conclusions give `ambiguous`.

Adherence concerns observable sections, order, steps, relevant arithmetic and
answer format in the exact saved prompt. The judge must not invent requirements
or assess whether internal verification actually occurred. Missing prompts require
`strategy_followed: null`. Ambiguous correctness or null adherence requires
`review_required: true`.

The review flag does not automatically discard an otherwise resolved correctness
verdict: for example, a missing generation prompt can leave correctness resolved
while adherence is unknown. The report excludes null adherence from its adherence
rate and reports adherence coverage separately.

```json
{"verdict":"correct","strategy_followed":true,"review_required":false}
```

No extracted answer, correctness justification or adherence explanation is returned.

### Chart grounding

| Field | Meaning | Possible values | Example |
| --- | --- | --- | --- |
| `chart_readability` | Overall readability of the chart | `readable`, `partly_readable`, `unreadable` | `"readable"` |
| `chart_types` | Proposed visible-mark types for human checking; mixed figures allow several | One or more unique labels: `bar`, `line`, `scatter`, `area`, `pie`, `box`, `heatmap`, `histogram`, `other`, `unclear` | `["line", "scatter"]` |
| `final_explanation` | Assessment of the full saved `model_answer` text, including its final-answer line | Compact assessment below | See JSON example |
| `returned_reasoning` | Separate assessment of saved `model_reasoning` | Same compact assessment | `absent` when no reasoning was saved |

`other` means a recognizable type outside the list; `unclear` means the type
cannot be confidently identified. Proposed types do not become verified metadata.

Each text assessment contains exactly these fields:

| Field | Meaning | Possible values | Example |
| --- | --- | --- | --- |
| `status` | Whether the complete text could be assessed | `assessed`, `no_claims`, `absent`, `requires_review` | `"assessed"` |
| `total_claims` | All distinct atomic factual assertions, including later-corrected assertions | Nonnegative integer or `null` | `8` |
| `corrected_claims` | Assertions explicitly retracted and corrected later in the same field | Nonnegative integer or `null` | `1` |
| `contradicted_claims` | Retained assertions clearly conflicting with the chart or claimed arithmetic | Nonnegative integer or `null` | `2` |
| `unsupported_claims` | Retained assertions not established by chart evidence; excludes contradicted assertions | Nonnegative integer or `null` | `1` |
| `material_errors` | Retained contradicted or unsupported assertions affecting justification or substantive interpretation | Nonnegative integer or `null` | `2` |
| `material_contradictions` | Contradicted subset of material errors | Nonnegative integer or `null` | `1` |
| `error_categories` | Categories of retained material errors; multiple allowed, without duplicates | Array containing only the four categories below, or `null` | `["chart_reading", "calculation"]` |

| Status | When used | Counts and categories | Statistical treatment |
| --- | --- | --- | --- |
| `assessed` | At least one claim; every claim reviewed and material-error/correction judgments determinate | Integer counts; category array | Error rates usable if retained claims remain |
| `no_claims` | Present text without auditable factual assertions | All counts `0`; categories `[]` | Error-rate metrics null |
| `absent` | Empty or whitespace-only source text | All counts `0`; categories `[]` | Error-rate metrics null |
| `requires_review` | Incomplete review or ambiguity that could change material-error/correction labels | All counts and categories `null` | Unresolved, excluded from error rates |

A human review case might involve a blurry central value, an unclear retraction,
or a response too long to audit completely. A clearly unsupported causal claim
can receive a determinate error label without requiring review. An unreadable
chart cannot have an `assessed` field. No review-reason prose is returned.

Example of a complete grounding output:

```json
{
  "chart_readability": "readable",
  "chart_types": ["line"],
  "final_explanation": {
    "status": "assessed",
    "total_claims": 8,
    "corrected_claims": 1,
    "contradicted_claims": 2,
    "unsupported_claims": 1,
    "material_errors": 2,
    "material_contradictions": 1,
    "error_categories": ["chart_reading", "unsupported_inference"]
  },
  "returned_reasoning": {
    "status": "absent",
    "total_claims": 0,
    "corrected_claims": 0,
    "contradicted_claims": 0,
    "unsupported_claims": 0,
    "material_errors": 0,
    "material_contradictions": 0,
    "error_categories": []
  }
}
```

### Claim counting, corrections and categories

Count distinct atomic factual assertions about the chart, calculations and
supporting inferences, including supported claims. Repeated assertions count
once per field; split compound statements when their factual parts can have
different labels. Purely procedural self-talk is excluded. Missing endings are
not invented or automatically labeled false. Counts are judge estimates, not
human-established exhaustive claim segmentation.

An explicit correction requires a later clear retraction **and correction in the
same field**. For example, “A is 9. Correction: A is 5, not 9” contains two
assertions, one corrected and one retained. A different final answer alone is
not sufficient. The final explanation cannot retroactively repair the reasoning.

Python derives these quantities; the judge does not return them:

```text
retained claims = total_claims - corrected_claims
supported retained claims = retained claims - contradicted_claims - unsupported_claims
material unsupported claims = material_errors - material_contradictions
```

Contradicted and unsupported counts are disjoint. Material errors are a subset
of their sum; harmless rounding or style does not establish materiality. Local
validation rejects inconsistent counts, duplicate categories and categories
inconsistent with the presence of material errors.

| Category | Meaning | Example |
| --- | --- | --- |
| `chart_reading` | Wrong series, axis, value or comparison | Calling B highest when A is visibly higher |
| `invented_information` | Asserting absent labels, data or units | Claiming a printed unit that is missing |
| `unsupported_inference` | Conclusion beyond chart evidence | Claiming correlation proves causation |
| `calculation` | Wrong arithmetic or conclusion inconsistent with its steps | Reading 3 and 5, then stating their sum is 9 |


## Prompt strategies under evaluation

| Strategy | Requested response | Generator calls |
| --- | --- | ---: |
| `direct` | Brief chart-based explanation and final answer | 1 |
| `structured` | Relevant chart evidence before explanation and final answer | 1 |
| `chain_of_thought` | Chart-reading steps and relevant arithmetic | 1 |
| `verification` | Draft, followed by a chart-based check and revision | 2 |

Saved prompts, rather than strategy names, determine adherence requirements.
See [the Gemma runner](../eden/eden_charxiv_gemma.py) and
[the Qwen runner](../eden/eden_charxiv_qwen.py). Returned reasoning is observable
generated text, not evidence of a model's internal causal decision process.

Saved verification drafts receive their own answer and grounding requests using
the draft prompt. Grounding is not told which responses are drafts. Draft-to-final
metrics measure answer recovery/regression and material-error recovery/introduction;
missing assessments remain missing. A seeded fraction of final grounding tasks
is repeated to measure stability; repeats never replace or vote on primary labels.

With `N` final responses, `D` saved drafts and `R` repeated grounding tasks,
request count is `2N + 2D + R`. Ten charts with four strategies from one model
normally give 40 final responses, 10 drafts and about two repeats: about 102
requests. The repeat count is seeded, not guaranteed to equal exactly 5%.

## Setup and input format

Run commands from the repository root in your Python environment:

```bash
python -m pip install -r requirements-judge.txt
```

Copy [.env.example](../../.env.example) to `.env` and fill in the needed provider:

| Setting | Use |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI authentication |
| `OPENAI_MODEL_ID` | OpenAI judge; fallback in code is `gpt-6.2-sol` |
| `GOOGLE_API_KEY` | Google AI Studio authentication |
| `GEMINI_API_KEY` | Alternative Google key; `GOOGLE_API_KEY` takes precedence |
| `GOOGLE_MODEL_ID` | Required Google model default unless supplied with `--model` |

Shell variables override `.env`; `--model` overrides model settings. Values are
loaded without variable interpolation. Keys are not put in manifests or requests.
The selected Google model must support image input, schema output and Batch.

Each positional input is a saved experiment JSON with `dataset`, `split` and
`results`. Each result supplies `example_id`, `question`, `correct_answer` and
`image_path`; `model_answer`, `model_reasoning`, `prompt_strategy`, saved prompts,
truncation and usage/configuration metadata are retained when available.
Relative image paths resolve against the source JSON's directory. Generator
identity comes from a result's `model`, falling back to document `model`.
Supply each experiment once: duplicate model/strategy/chart cells are rejected.

Chart identity uses dataset, split and example ID. Matched responses must have
the same question and identical image bytes. Missing model/strategy cells are
allowed; coverage must be checked. `--chart-limit` selects the first eligible
chart IDs in input order, retaining their available responses across inputs.
Preparation shuffles requests using the seed, not the chart selection.

## Run a development batch

Always choose a directory that does not yet exist. The commands below create a
new v6 run and do not reuse the earlier `gemini_batch_10` pilot.

### Gemini / Google AI Studio

```bash
python Experiments/batch_api/google_ai_studio_judge.py prepare \
  outputs/eden_gemma4_e4b/results.json \
  --run outputs/judge/gemini_development_v6 --chart-limit 10
python Experiments/batch_api/google_ai_studio_judge.py submit --run outputs/judge/gemini_development_v6
python Experiments/batch_api/google_ai_studio_judge.py status --run outputs/judge/gemini_development_v6
python Experiments/batch_api/google_ai_studio_judge.py collect --run outputs/judge/gemini_development_v6
python Experiments/batch_api/google_ai_studio_judge.py report --run outputs/judge/gemini_development_v6
```

### OpenAI

```bash
python Experiments/batch_api/openai_batch_judge.py prepare \
  outputs/eden_gemma4_e4b/results.json \
  --run outputs/judge/openai_development_v6 --chart-limit 10
python Experiments/batch_api/openai_batch_judge.py submit --run outputs/judge/openai_development_v6
python Experiments/batch_api/openai_batch_judge.py status --run outputs/judge/openai_development_v6
python Experiments/batch_api/openai_batch_judge.py collect --run outputs/judge/openai_development_v6
python Experiments/batch_api/openai_batch_judge.py report --run outputs/judge/openai_development_v6
```

Add `outputs/eden_qwen3_5_9b/results.json` as a second positional input to judge
both generators. This adds independent requests; it does not combine responses
into a shared image assessment. Omit that input if unavailable.

`prepare` makes no API requests and never changes source JSON. Inspect the
manifest and request shards before `submit`. Submission saves job IDs and returns;
the terminal need not remain open. Use one process per run directory. `status`
and `collect` do not poll continuously: rerun them when convenient. `report` can
run before completion, but its results are provisional.

| Completion state | Next step |
| --- | --- |
| Gemini `JOB_STATE_PENDING` / `JOB_STATE_RUNNING` | Check again later |
| Gemini `JOB_STATE_SUCCEEDED` | Collect, then report |
| Gemini `JOB_STATE_FAILED` / `JOB_STATE_CANCELLED` / `JOB_STATE_EXPIRED` | Inspect snapshot; collect available results before retrying |
| OpenAI `completed` | Collect, then report |
| OpenAI `failed` / `cancelled` / `expired` | Inspect snapshot; collect available results before retrying |

A successful batch is not a guarantee of valid judgments. Collection records
`valid`, `invalid` and `missing` tasks, joins results by request ID/key, preserves
raw downloads and retains usage from retrieved attempts. Gemini requires a single
completed candidate with finish reason `STOP`; `MAX_TOKENS` output is invalid.

## Commands and defaults

Both runners expose the same command names:

| Command | Purpose | API access |
| --- | --- | --- |
| `policy --output PATH` | Export proposed acceptance/tolerance policy | No |
| `prepare INPUT... --run DIR` | Freeze inputs and build request shards | No |
| `submit --run DIR` | Upload unsubmitted shards and create batch jobs | Yes; paid work |
| `status --run DIR` | Refresh job snapshots | Yes |
| `collect --run DIR` | Download and validate available results | Yes |
| `retry --run DIR` | Prepare unsuccessful request keys after all jobs are terminal and collected | No; submit separately |
| `attach --run DIR --chunk INDEX --batch-id ID` | Reconcile an existing job after an uncertain creation outcome | Yes |
| `report --run DIR` | Calculate metrics, optional human agreement and cost estimate | No |
| `validate --run DIR --human-labels PATH` | Apply held-out acceptance gate | No |

| `prepare` option | Default / behavior |
| --- | --- |
| `--model` | Environment/default as above; frozen at preparation |
| `--effort` | OpenAI: `medium`, choices `low`, `medium`, `high`; Google: `default`, additionally allowing those three levels |
| `--answer-tokens` | `2048` |
| `--grounding-tokens` | `12000` |
| `--repeat-fraction` | `0.05` |
| `--seed` | `42` |
| `--max-shard-mb` | `150`; parser accepts values greater than zero and at most `190` |
| `--chart-limit` | No limit, subject to development's 25-chart maximum |
| `--stage` | `development`; alternatives `validation`, `evaluation` |
| `--policy PATH` | Optional JSON; otherwise proposed defaults below |
| `--chart-metadata PATH` | Optional human-checked chart types/source tables |
| `--exclude-run DIR` | Repeatable chart/image exclusions, including inherited exclusions |
| `--validated-run DIR` | Required for evaluation |
| `--human-labels PATH` | Required for evaluation preparation |

Google's `default` omits an explicit thinking configuration. Other Google effort
values become `thinkingLevel`; OpenAI uses reasoning effort. Supported levels
depend on the selected model. **v6 has not changed effort or token defaults.**

Token limits are hard ceilings including thinking, not graceful completion
instructions. Compact JSON reduces visible output but does not guarantee short
thinking or eliminate truncation. Test effort/budget changes on development data
and prepare a new run; do not edit frozen requests. The generator's own token
limit is separate and is recorded when available.

Shards contain at most 49,000 requests, with inline/base64 images. The Google
runner also rejects individual request envelopes larger than its 19 MB guard.
No public image hosting is needed. `report` and `validate` accept `--bootstrap`
(default `2000`, minimum `100`) and `--seed` (default `42`).

## Human annotation

Use the four rules in [annotation_rulebook.md](./annotation_rulebook.md).
Annotate independently before seeing judge labels. Review the grounding packet
first, then the answer/reference packet.

### Human annotation files

Preparation creates `human_grounding_packets.jsonl`, `human_answer_packets.jsonl`,
chart copies in `human_images/`, and templates for two annotators plus a separate
adjudication. Fill labels with `true`, `false` or `null` (unknown/unassessed), keeping
`response_id` and actual annotator identities. Keep the independent labels as well
as the `adjudicated` records.

To compare human and judge labels, pass `--human-labels PATH` to `report`.
The report includes agreement, precision, recall and F1. Human checking of claim
counts and materiality remains necessary; valid JSON alone does not establish
judge accuracy.

**Current code restriction:** `development` is limited to 25 charts. A
`validation` run needs `--exclude-run` pointing to development data; `evaluation`
requires a passing held-out validation via `--validated-run` and `--human-labels`,
with the same judge settings. Acceptance defaults live in
[judge_policy.py](./judge_policy.py); `policy` exports them and `validate` checks
them. These restrictions remain in the code even though this guide omits the
extended study-design procedure.

## Reading the results

| File | What to use it for |
| --- | --- |
| `summary.json` | Overall and model/strategy statistics, coverage, comparisons and token usage |
| `metrics.csv` | Flat table of the same metric estimates |
| `evaluated_responses.jsonl` | Inspect each original response, its labels and derived counts |
| `judgments.jsonl` | Raw compact judge labels/counts, or invalid/missing status |
| `review_queue.jsonl` | Cases needing inspection plus a seeded random audit sample |
| `usage.jsonl` | Token usage for retrieved attempts, including thinking, repeats and retries |
| `manifest.json` | Saved inputs, settings and batch IDs |

### Main metrics

| Metric | Meaning |
| --- | --- |
| `answer_accuracy` | Correct / resolved answers; missing answers count as incorrect, ambiguous/failed judgments are excluded |
| `strategy_following_rate` | Compliant / assessed responses with a saved prompt |
| `final_explanation_unsupported` | Fraction of assessed explanations containing at least one retained material error |
| `correct_answer_final_explanation_unsupported` | Same error fraction, restricted to correct answers |
| `final_explanation_claim_count` | Mean total claims per assessed explanation |
| `final_explanation_material_error_count` | Mean retained material errors per assessed explanation |
| `final_explanation_claim_error_rate` | Mean of each explanation's `material_errors / retained_claims` |

Corresponding `returned_reasoning_` metrics assess reasoning separately.
`unsupported` includes both contradictions and insufficient evidence;
`contradicted` counts only material contradictions. Raw `contradicted_claim_count`
and `unsupported_claim_count` include nonmaterial errors too. Retained claims
are total claims minus explicitly corrected claims. Verification recovery/
regression metrics compare saved drafts with final responses.

**How to read `metrics.csv`:** `group` identifies the model/strategy and `metric`
identifies the statistic. `value = numerator / denominator`. For binary rates,
`numerator` is the number of positives; for mean claim counts it is the summed
count; for macro claim rates it is the sum of per-response fractions. Therefore
not every numerator is an integer error count. `group_records` gives the full
group size, while `denominator` gives the eligible/resolved responses.
`contributing_charts` is the number of charts contributing to the estimate.

`ci95_low` / `ci95_high` are 95% chart-cluster bootstrap bounds, using 2,000
replicates by default. Few charts give unstable estimates; a zero-width interval
is not proof of certainty. Paired comparisons use matched charts; conditional
comparisons require both answers to be correct. Differences are right minus left.

Always report coverage and denominators. Absent, nonfactual and unresolved fields
are not counted as clean. Claim rates use material errors and macro averaging,
so they need not equal the pooled error count divided by pooled claim count.
Proposed chart types become report groups only when supplied as human-verified
metadata. Numerical mismatch metrics are unavailable in compact v6 outputs.

## Failures, retries and token usage

After all jobs are terminal and collected, prepare failed/missing requests again,
then submit them separately. Example for the OpenAI pilot:

```bash
python Experiments/batch_api/openai_batch_judge.py retry --run outputs/judge/openai_batch_10_v6
python Experiments/batch_api/openai_batch_judge.py submit --run outputs/judge/openai_batch_10_v6
```

Use the Google runner for a Google run. Retries preserve the frozen requests;
changing prompts, schema, effort or budgets requires a new run directory.
If creation had an unknown outcome, use `attach` to reconcile the existing job
before resubmitting. For Google's explicit `400 FAILED_PRECONDITION`, check the
API-key project's billing/model/Batch access, fix prerequisites, then retry submit.

Usage includes internal thinking and all retrieved attempts, not just visible
JSON. An optional cost estimate requires all three current Batch rates on
`report`: `--input-usd-per-million`, `--output-usd-per-million`, and
`--cached-input-usd-per-million`. Without rates, cost is null. Batch elapsed time
includes queueing. Existing v5 results remain readable with their frozen schema;
do not combine them with v6 as one validated protocol.

Offline regression checks:

```bash
python -m unittest discover -s Experiments/batch_api -p 'test_*judge.py'
```
