# Hallucinations-in-AI-Explanations

## Project introduction

**Right Answer, Wrong Reason** investigates whether AI models can give a correct
answer while supporting it with an incorrect or unsupported explanation. We
focus on chart-based question answering, where explanations can misread a
series, invent a value or label, make an unsupported inference, or contain an
arithmetic error. Answer accuracy alone does not reveal these problems.

Our experiments use chart–question pairs from the CharXiv validation split and
compare Gemma 4 E4B and Qwen 3.5 9B under four prompting strategies: direct,
structured, chain-of-thought, and verification. Each model receives the same
chart–question pairs across strategies. We assess the final answer, the
explanation shown to the user, and any separately returned reasoning text.

## Research goals

1. **Detect unreliable explanations.** Develop a claim-level annotation protocol
   and evaluate an automated judge against independent human annotations.
2. **Measure “correct answer, flawed explanation.”** Estimate how often a correct
   final answer is accompanied by material contradicted or unsupported claims,
   reporting final explanations and returned reasoning separately.
3. **Compare prompting strategies.** Test whether structured evidence, detailed
   reasoning, or self-verification reduce errors, and whether extra reasoning
   introduces additional unsupported claims. Also check whether responses follow
   their assigned strategy instructions.
4. **Understand error patterns and costs.** Examine error categories, chart types,
   explanation length, corrections, truncation, and available token/time usage.
5. **Make the comparison reproducible.** Preserve prompts, sampling seeds,
   generation settings and source evidence, and report uncertainty clustered by
   chart, including paired comparisons on questions both strategies answer correctly.

## Planned outcomes and scope

The intended deliverables are a human-annotated set of chart explanations, a
reproducible comparison of the four strategies, and an analysis of explanation
errors and computational costs. 

We evaluate the text models produce. Returned reasoning is not treated as
evidence of how a model internally reaches its answer. We distinguish clear
contradictions from insufficient evidence and do not assume that longer
explanations or verification necessarily improve reliability. 

## Repository layout

| Location | Contents |
| --- | --- |
| [Experiments/local/](Experiments/local/) | LM Studio pipelines, local notebooks, and the chart-image exporter. |
| [Experiments/eden/](Experiments/eden/) | Standalone Gemma and Qwen generation scripts for Eden / CUDA. |
| [Experiments/batch_api/](Experiments/batch_api/) | Shared judge schema, OpenAI Batch and Google AI Studio runners, workflow guide, and offline tests. |
| [Phase1/](Phase1/) | Project brief, literature and dataset notes, requirements, feedback, and Q&A. |
| [Phase2/](Phase2/) | Presentation PDFs, presentation scripts, and the pilot-analysis PDF. |
| [rules/](rules/) | Course rules, assessment criteria, reproducibility checklist, and editorial guidance. |
| [Code/](Code/) | Initial exploratory notebook. |
| [outputs/](outputs/) | Saved experiment JSON, chart images, and generated evaluation artifacts. |

## Choose a setup

Run the commands below from the repository root. The scripts run directly;
there is no package-install step such as `pip install -e .`.

| Workflow | Dependencies | Additional requirements | Entry point |
| --- | --- | --- | --- |
| Local chart generation | [requirements.txt](requirements.txt) | A vision-capable model loaded in LM Studio and its local server running. | [run_charxiv_pipeline.py](Experiments/local/run_charxiv_pipeline.py) or [run_charxiv_prompt_strategies.py](Experiments/local/run_charxiv_prompt_strategies.py) |
| Eden / CUDA generation | [requirements-eden.txt](requirements-eden.txt), which includes the base requirements | A CUDA GPU for inference; Hugging Face access or a prepared shared cache. | [eden_charxiv_gemma.py](Experiments/eden/eden_charxiv_gemma.py) or [eden_charxiv_qwen.py](Experiments/eden/eden_charxiv_qwen.py) |
| Batch judging and offline analysis | [requirements-judge.txt](requirements-judge.txt) | Saved result JSON and chart images; the matching provider's API key for network commands. | [OpenAI Batch](Experiments/batch_api/openai_batch_judge.py) or [Gemini Batch](Experiments/batch_api/google_ai_studio_judge.py), both using [judge_schema.py](Experiments/batch_api/judge_schema.py) |

The judge dependencies are separate from the generation dependencies; install
both requirement files if using both workflows in one environment. The notebooks
need a Jupyter-capable environment with the generation dependencies installed.

| Default | Local pipelines | Eden scripts |
| --- | --- | --- |
| Dataset split | CharXiv `validation` | CharXiv `validation` |
| Charts per model | 25 | 125, excluding the five development charts |
| Sampling seed | `42` | `20261117` |
| Four-strategy output per model | 100 final responses / 125 generation calls | 500 final responses / 625 generation calls |

All generation entry points accept `--n`, `--seed`, and `--output`. Local
pipelines also accept `--model`; Eden uses a separate script for each model.
Matching the seed across different sampling procedures is not enough:
the Eden scripts exclude the development charts, while the local pipelines do
not. Compare saved chart IDs and dataset revisions when matching runs.

## Run instructions

Run from the repository root. Create and activate an environment once:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

### Local generation with LM Studio

Load a vision-capable model and start LM Studio's server at
`http://localhost:1234`. The default model ID is `google/gemma-4-e4b`;
change it with `--model` if needed.

```bash
python -m pip install -r requirements.txt
python Experiments/local/run_charxiv_pipeline.py
python Experiments/local/run_charxiv_prompt_strategies.py
```

The baseline writes `outputs/charxiv_lm_studio_answers.json`; the four-strategy
run writes `outputs/prompt_strategies/charxiv_answers_v2.json`. Resume the latter
with `--resume`, keeping the original settings. Use `--output` for separate runs.
Notebook alternatives: [baseline](Experiments/local/charxiv_lm_studio_pipeline.ipynb)
and [four strategies](Experiments/local/charxiv_prompt_strategies.ipynb).

### Eden / CUDA generation

Use Python 3.11+ and install `requirements-eden.txt` in your GPU environment.
For example, with the activated `.venv` above:

```bash
python -m pip install -r requirements-eden.txt
sbatch -A 19-stud-2627-z -p student \
  --gres=gpu:rtx6000:1 --cpus-per-task=8 --mem=64G \
  --time=23:00:00 --signal=USR1@600 --output=eden-%j.out \
  --wrap='.venv/bin/python Experiments/eden/eden_charxiv_gemma.py --n 125'
```

Adjust the allocation to your account. For Qwen, replace the script with
[eden_charxiv_qwen.py](Experiments/eden/eden_charxiv_qwen.py). Both scripts save
`outputs/<model-run>/results.json` and support `--resume`, `--max-new-tokens`,
and pinned `--dataset-revision` / `--model-revision`. Match chart IDs, dataset
revision, seed and generation settings when comparing runs. If compute nodes
lack internet access, run `--prepare-only` on the login host first, then add
`--offline` to the GPU job. Set `HF_TOKEN` if model access requires it.

To generate a fresh batch without repeating previously generated charts, add
`--exclude-from` pointing to an earlier Eden results JSON and choose a new output:

```bash
python Experiments/eden/eden_charxiv_gemma.py --n 125 --seed 20261126 \
  --exclude-from outputs/eden_gemma4_e4b/results.json \
  --output outputs/eden_gemma4_e4b_batch2/results.json
```

Use this command inside your GPU allocation or as the Slurm `--wrap` command.
For Qwen, use its script and a separate Qwen output directory, keeping the same
seed, sample size, dataset revision and exclusion files to select matching charts.
Repeat `--exclude-from` for multiple earlier batches. Both scripts exclude chart
IDs present in the source files' `results` entries, including any partially
completed chart, but not charts with no saved response yet. Exclusions are saved
in the new checkpoint; `--resume` restores them without needing the source files.
Supplying exclusion files again on resume must produce the same excluded IDs.
Without `--exclude-from`, sampling is unchanged.

### API judging

Fill in the repository-root `.env` with your API keys and model IDs. For a fresh
clone, copy [.env.example](.env.example) to `.env` first. Both runners load it
automatically; shell environment variables take precedence, and `--model`
overrides the configured model ID. The local `.env` is excluded from Git.

```bash
python -m pip install -r requirements-judge.txt
python Experiments/batch_api/openai_batch_judge.py prepare \
  outputs/eden_gemma4_e4b/results.json \
  --run outputs/judge/openai_development_v6 --chart-limit 2
```

Preparation is local. OpenAI uses `OPENAI_API_KEY`; `submit` sends paid Batch
requests. For Gemini Batch, configure `GOOGLE_API_KEY` and `GOOGLE_MODEL_ID`,
install the updated requirements (including `google-genai`), then run:

```bash
python Experiments/batch_api/google_ai_studio_judge.py prepare \
  outputs/eden_gemma4_e4b/results.json \
  --run outputs/judge/gemini_batch_10 --chart-limit 10
python Experiments/batch_api/google_ai_studio_judge.py submit --run outputs/judge/gemini_batch_10
python Experiments/batch_api/google_ai_studio_judge.py status --run outputs/judge/gemini_batch_10
python Experiments/batch_api/google_ai_studio_judge.py collect --run outputs/judge/gemini_batch_10
python Experiments/batch_api/google_ai_studio_judge.py report --run outputs/judge/gemini_batch_10
```

Google also accepts `GEMINI_API_KEY`. `submit` starts asynchronous jobs; the
terminal can then be closed. Check `status` later and run `collect` once all jobs
show `JOB_STATE_SUCCEEDED`. Use a fresh directory: old sequential-run request
files cannot be submitted as batches. See the
[shared schemas and provider workflows](Experiments/batch_api/judge_workflow.md)
for execution, human validation and evaluation.

Offline regression tests:

```bash
python -m unittest discover -s Experiments/batch_api -p 'test_*judge.py'
```

### Restore missing chart images

Some image directories and all judge outputs are excluded by
[.gitignore](.gitignore); generation result JSON is not generally excluded.
With the base dependencies installed, restore images using:

```bash
python Experiments/local/export_charxiv_images.py outputs/eden_gemma4_e4b/results.json
```

This creates `results_with_images.json` and exports images under
`outputs/images/`. Use the new JSON for judging; the source is unchanged.
