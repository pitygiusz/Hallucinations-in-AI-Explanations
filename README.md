# Hallucinations-in-AI-Explanations

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
python Phase1/run_charxiv_pipeline.py
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
python Phase1/run_charxiv_prompt_strategies.py
```

The result is `outputs/prompt_strategies/charxiv_answers_v2.json`. The revised prompts ask the model to compare candidates over the same chart interval before abstaining; the earlier `charxiv_answers.json` run remains available. The JSON is atomically updated after each completed strategy. If a run stops, keep the same settings and resume it with:

```bash
python Phase1/run_charxiv_prompt_strategies.py --resume
```

The notebook [Experiments/charxiv_prompt_strategies.ipynb](Experiments/charxiv_prompt_strategies.ipynb) runs the same code with editable settings and a request progress bar. To evaluate another locally loaded model, pass its LM Studio model id with `--model` and use a different `--output` path.
