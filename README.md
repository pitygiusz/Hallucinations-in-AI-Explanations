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

The JSON records include the question, model answer, LM Studio reasoning item (when returned), CharXiv reference answer, saved image path, sample index, seed, model, and dataset split. 

### Notebook

Open [Experiments/charxiv_lm_studio_pipeline.ipynb](Experiments/charxiv_lm_studio_pipeline.ipynb). The notebook locates the project root from its working directory, imports the pipeline from `Experiments/`, and saves results to the root `outputs/` directory. Install the root [`requirements.txt`](requirements.txt) in the notebook kernel first.

