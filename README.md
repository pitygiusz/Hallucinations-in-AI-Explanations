# Hallucinations-in-AI-Explanations

## OpenAI Batch judge evaluation

[Judge workflow and annotation codebook](Experiments/openai_batch_judge.md) describes
the blinded Batch API pipeline for saved experiment results. It produces
claim-level evidence labels, answer accuracy, correct-answer explanation error
rates, chart-clustered confidence intervals, paired comparisons, human agreement
metrics when labels are supplied, and token-usage records. Preparation is local;
only the explicit `submit` command sends paid requests. Install
[requirements-judge.txt](requirements-judge.txt) and follow the small development
batch example before scaling to all results. Protocol v2 separates development,
held-out human validation and evaluation; evaluation requires passing the frozen
acceptance policy. It also distinguishes corrected trace claims, measures saved
verification drafts, and reports truncation sensitivity and human-verified
chart-type subgroups.

## Quick CharXiv run

The starter pipeline samples 25 reasoning questions from the CharXiv **validation** split using seed `42`, sends each chart and question to a local vision-capable model through LM Studio, and writes the model response alongside the reference answer to JSON. The same seed and dataset ordering reproduce the same sample.

### Setup on a cloned repository

```bash
git clone <repository-url>
cd Hallucinations-in-AI-Explanations
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

In LM Studio, load a vision-capable model and start its local server. The default settings use the LM Studio native endpoint `http://localhost:1234/api/v1/chat` and model id `google/gemma-4-e4b`; set the model id to the identifier shown in your LM Studio installation if it differs.

Run the pipeline from the repository root:

```bash
python Experiments/run_charxiv_pipeline.py
```

By default, it writes `outputs/charxiv_lm_studio_answers.json` and copies each sampled chart into `outputs/images/`. Each JSON result stores its relative image path. 

The JSON records include the question, model answer, LM Studio reasoning item (when returned), CharXiv reference answer, saved image path, sample index, seed, model, and dataset split. It is initialized with an empty `results` list, then atomically updated after each completed chart; if a run is interrupted, completed records remain and `status` stays `in_progress`.

### Notebook

Open [Experiments/charxiv_lm_studio_pipeline.ipynb](Experiments/charxiv_lm_studio_pipeline.ipynb). The notebook locates the project root from its working directory, imports the pipeline from `Experiments/`, and saves results to the root `outputs/` directory. Install the root [`requirements.txt`](requirements.txt) in the notebook kernel first.

## Four prompt strategies

The separate experiment in [Experiments/charxiv_prompt_strategies.py](Experiments/charxiv_prompt_strategies.py) applies four strategies to **the same 25 seeded charts**. The system prompts are defined in that script and saved with the JSON output:

| Strategy | Prompt behavior | LM Studio calls per chart |
| --- | --- | ---: |
| Direct | Brief explanation and final answer | 1 |
| Structured | List relevant chart labels, values, and units before explaining | 1 |
| Chain-of-thought | Explain chart-reading and calculation steps | 1 |
| Verification | Draft an answer, then check it against the chart and revise | 2 |

With the defaults, this produces 100 result records and makes 125 LM Studio requests. Every record contains `prompt_strategy`, the system prompt, the same answer/reasoning/reference fields as the baseline, and a path to a chart copied under `outputs/prompt_strategies/images/`. The `outputs/` directory is ignored by Git.

Run from the repository root after the setup above:

```bash
python Experiments/run_charxiv_prompt_strategies.py
```

The default result is `outputs/prompt_strategies/charxiv_answers_v2.json`. The revised prompts ask the model to compare candidates over the same chart interval before abstaining. Existing five-chart pilot runs were saved as [`startegies_test_gemma.json`](outputs/prompt_strategies/startegies_test_gemma.json) and [`strategies_test_qwen.json`](outputs/prompt_strategies/strategies_test_qwen.json). The JSON is atomically updated after each completed strategy. If a run stops, keep the same settings and resume it with:

```bash
python Experiments/run_charxiv_prompt_strategies.py --resume
```

The notebook [Experiments/charxiv_prompt_strategies.ipynb](Experiments/charxiv_prompt_strategies.ipynb) runs the same code with editable settings and a request progress bar. To evaluate another locally loaded model, pass its LM Studio model id with `--model` and use a different `--output` path.

To export every chart referenced by an experiment JSON, including charts whose original image paths are missing, run:

```bash
python Experiments/export_charxiv_images.py outputs/prompt_strategies/charxiv_answers_qwen_25.json
```

The exporter validates each saved dataset index against the chart's `example_id`, writes one image per selected chart under `outputs/images/<result-name>/`, and creates a separate `<result-name>_with_images.json` with working relative image paths. The source JSON is unchanged. In names such as `001_idx0654_1524.jpg`, `001` is sample order, `654` is the dataset index, and `1524` is CharXiv's original figure filename.

## Eden cluster: standalone Gemma 4 run

The standalone [Eden Python script](Experiments/eden_charxiv_gemma.py) downloads the official instruction-tuned Hugging Face checkpoint [`google/gemma-4-E4B-it`](https://huggingface.co/google/gemma-4-E4B-it) and the CharXiv validation dataset, then runs the same four revised prompt strategies without LM Studio. It saves the reference answer, final answer, returned thinking text when available, raw generation, prompt, chart image, and timing in `outputs/eden_gemma4_e4b/results.json`. The checkpoint weights are about **16 GB** on disk. The local LM Studio model may use different quantization, so its outputs are not directly interchangeable with this unquantized BF16/FP16 run.

The default is **125 new charts** (excluding the five prompt-development charts), producing **500 response records and 625 model generations**. The script pauses after 22 hours and can resume within Eden's 24-hour student-job limit. CharXiv validation has 1,000 charts, so even though the script enforces the requested cap of 1,250, fewer than 1,000 non-pilot validation charts with public answers are available.

On Eden, from a fresh clone in your shared home directory, create a Python 3.11+ environment and install [cluster dependencies](requirements-eden.txt):

```bash
python3 -m venv .venv-eden
source .venv-eden/bin/activate
python -m pip install -r requirements-eden.txt
```

The script normally downloads the model and dataset inside the GPU job. If compute nodes cannot reach Hugging Face, run the **same script** on the login host first with `--prepare-only`, then add `--offline` to the GPU job. This uses the shared home cache and writes a revision manifest next to the output JSON. Set `HF_TOKEN` in your environment only if Hugging Face requests authentication; the script does not save it.

The model loader uses eager attention for Gemma 4's audio component because some Transformers versions reject SDPA while constructing that component. Image and text attention retain the default SDPA. If an earlier job failed during model loading, copy the updated script to Eden and submit the command below again; cached downloads will be reused. No `--resume` flag is needed when the job failed before creating `results.json`.

Submit from the repository root after checking the current GPU GRES name with `sinfo -p student -o '%P %G'`:

```bash
sbatch -A 19-stud-2627-z -p student \
  --gres=gpu:rtx6000:1 --cpus-per-task=8 --mem=64G \
  --time=23:00:00 --signal=USR1@600 \
  --job-name=charxiv-gemma --output=eden-%j.out \
  --wrap='.venv-eden/bin/python Experiments/eden_charxiv_gemma.py --n 125'
```

If the job pauses or fails after some charts, submit the same command with `--resume` added inside `--wrap`. Each completed chart-strategy response is written atomically, and `--resume` checks the sampled indices, model and dataset revisions, prompts, and generation settings before continuing. To prefetch on the login host, run `.venv-eden/bin/python Experiments/eden_charxiv_gemma.py --prepare-only`, then include `--offline` in the job command. The code requests one GPU, below the two-GPU per-user limit stated in the Eden welcome instructions.

## Eden cluster: Qwen 3.5 9B run

The separate [Qwen script](Experiments/eden_charxiv_qwen.py) uses the same chart selection, four system prompts, and checkpoint format as the Gemma script. It downloads the official [`Qwen/Qwen3.5-9B`](https://huggingface.co/Qwen/Qwen3.5-9B) image-text checkpoint and writes to `outputs/eden_qwen3_5_9b/results.json`. Its checkpoint weights are about **19.3 GB** on disk. On the RTX PRO 6000 Blackwell Server Edition it loads unquantized BF16 weights; FP16 is the fallback when BF16 is unavailable. This is a different precision from the local LM Studio Q4 run, so differences cannot be attributed to model identity alone.

Qwen thinks by default. Each call has the same configurable `--max-new-tokens` cap as Gemma: 1,536 by default, including both thinking and final-answer tokens. This bounds a reasoning loop. If the cap is reached before `</think>`, the record keeps the raw text and reasoning, leaves `model_answer` empty, and marks `generation_truncated` and `answer_missing`. It does not invent a final answer. The two-call verification strategy applies the cap to each call separately.

To compare the same sampled charts as the current Gemma run, keep `--n 125` and the default seed, and pin the CharXiv revision to the Gemma log's revision:

```bash
cd ~/charxiv
sbatch -A 19-stud-2627-z -p student \
  --gres=gpu:rtx6000:1 --cpus-per-task=8 --mem=64G \
  --time=23:00:00 --signal=USR1@600 \
  --job-name=charxiv-qwen --output=eden-qwen-%j.out \
  --wrap='.venv-eden/bin/python Experiments/eden_charxiv_qwen.py --n 125 --dataset-revision f441eb632fc62f6f777830a0f47619e6e86459b0'
```

Use `--resume` with the same settings if the job pauses. The Gemma and Qwen results are saved separately, and every completed strategy is checkpointed. Compare `generation_truncated` and `answer_missing` between models: the same cap can still affect them differently if one spends more tokens thinking. Any later higher-cap comparison should rerun both models with the same explicit `--max-new-tokens` value rather than mixing caps within a resumed run.
