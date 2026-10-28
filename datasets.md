# Datasets for “Right Answer, Wrong Reason”

**Checked:** 28 October 2026. **Unit of interest:** a chart, a question, a model answer, and a model explanation. An explanation is *unsupported* when at least one material claim contradicts the chart/source table or cannot be justified from the available evidence. A *right answer, wrong reason* case has a correct final answer and an unsupported explanation.

## Selection at a glance

| Dataset | Status | Best use | Main limitation |
| --- | --- | --- | --- |
| [ChartQA](#1-chartqa) | **READY** | Main chart question-answer pool; access to source tables and chart annotations | No explanation-faithfulness labels |
| [ChartQA-X](#2-chartqa-x) | **READY** | Reference explanation examples and prompt development | Explanations are selected model outputs, not verified claim labels |
| [ChartQAPro](#3-chartqapro) | **READY** | Hard, held-out chart QA evaluation | Test-only; no explanation labels |
| [CharXiv](#4-charxiv) | **READY** | Scientific-chart and unanswerable-question stress test | Evaluation-only; original charts retain authors' copyright |
| [ChartNet-Bench](#5-chartnet-bench) | **READY** | Chart grounding / hallucination benchmark pilot | Public record does not define its row-level label schema or class counts |
| [ChartNet `core_permissive`](#6-chartnet-core_permissive) | **READY** | Synthetic charts with source tables for controlled experiments | Default subset has no QA or hallucination labels |
| [ChartInsighter](#7-chartinsighter) | **READY** | Error taxonomy and auxiliary sentence classification | Chart summaries, not question-conditioned explanations |
| [ChartHal](#8-charthal) | **RESTRICTED** | Challenge set for false premises and abstention, if reuse is cleared | No explicit dataset licence found |
| [ChartNet original reasoning subsets](#9-chartnet-original-reasoning-subsets) | **RESTRICTED** | Possible source of chart reasoning examples | Explicit no-licence, reproducibility-only notice |
| [ChartFI-Bench](#10-chartfi-bench) | **RESTRICTED** | Future chart-description faithfulness comparison | Dataset release is still listed as a to-do |
| [FaithChart-1500](#11-faithchart-1500) | **RESTRICTED** | Future explanation-grounding comparison | Public download and licence not verified |
| [Project explanation set](#12-project-explanation-set) | **TO COLLECT** | **Primary outcome:** human labels for explanation support, including correct-answer/wrong-reason cases | Must be generated and annotated |

**What “class balance” means here:** For open-ended QA, the answer is a string or number, so there is no meaningful fixed positive/negative answer-class balance. Where a published dataset lacks explanation labels, the counts below describe its *available strata* (for example question type or chart source), not hallucination prevalence. Do not treat a model-selected explanation as “faithful” merely because it is present in a dataset.

## Dataset details

### 1. ChartQA

- **Size:** 32,719 question-answer (QA) records: 28,299 train, 1,920 validation, 2,500 test.
- **Label definition:** Ground-truth short/free-text answer to a question about a chart; `type` distinguishes human-written from augmented questions. The original release also supplies chart images and associated tables/annotations. **No explanation-support label.**
- **Class balance:** Train: 7,398 human / 20,901 augmented; validation: 960 / 960; test: 1,250 / 1,250. Overall: 9,608 human (29.4%) / 23,111 augmented (70.6%). There is no binary hallucination class.
- **Licence:** GPL-3.0 is declared on the official dataset card. Some chart imagery comes from external publishers; inspect source-chart rights before republishing images or a derived dataset.
- **How obtained:** Download the official image-bearing archive from the [ChartQA dataset repository](https://huggingface.co/datasets/ahmed-masry/ChartQA/tree/main) or the [authors' repository](https://github.com/vis-nlp/ChartQA); retain split and source-table IDs. The [dataset card](https://huggingface.co/datasets/ahmed-masry/ChartQA/blob/main/README.md) and [official split statistics](https://datasets-server.huggingface.co/statistics?dataset=ahmed-masry/ChartQA&config=default&split=train) support the counts. [Paper](https://aclanthology.org/2022.findings-acl.177/).

### 2. ChartQA-X

- **Size:** 30,799 chart–question–answer–explanation records: 28,299 train and 2,500 test; no validation split listed.
- **Label definition:** Ground-truth answer plus a **model-generated explanation selected using quality metrics**. The explanation is text to inspect, not a human-verified supported/unsupported label.
- **Class balance:** No supported/unsupported explanation counts reported. The answer is open-ended; no fixed answer-class balance.
- **Licence:** CC BY 4.0 is declared on the dataset card. It derives from ChartQA, so check the upstream ChartQA/chart-image terms before redistribution; the downstream licence tag alone does not settle those rights.
- **How obtained:** Download from the [official Hugging Face repository](https://huggingface.co/datasets/shamanthakhegde/ChartQA-X) and keep its train/test split. [Dataset card](https://huggingface.co/datasets/shamanthakhegde/ChartQA-X/blob/main/README.md); [published WACV 2026 paper](https://openaccess.thecvf.com/content/WACV2026/papers/Hegde_ChartQA-X_Generating_Explanations_for_Visual_Chart_Reasoning_WACV_2026_paper.pdf).

### 3. ChartQAPro

- **Size:** 1,341 charts and 1,948 QA records, released as a test set.
- **Label definition:** Reference answer(s) and question category: factoid, conversational, fact checking, multiple choice, or hypothetical. **No explanation-support label.**
- **Class balance:** Factoid 1,081 (55.5%); conversational 311 (16.0%); fact checking 244 (12.5%); multiple choice 214 (11.0%); hypothetical 98 (5.0%). These categories sum to 1,948. The fact-checking question type should not be mistaken for an explanation-hallucination label.
- **Licence:** MIT is declared on the dataset card; chart images may have third-party provenance and should be checked before redistribution.
- **How obtained:** Download the [official dataset](https://huggingface.co/datasets/ahmed-masry/ChartQAPro) or [authors' repository](https://github.com/vis-nlp/ChartQAPro). Reserve this test-only set for evaluation, rather than training or tuning prompts on its answers. [Dataset card](https://huggingface.co/datasets/ahmed-masry/ChartQAPro/blob/main/README.md); [official question-type statistics](https://datasets-server.huggingface.co/statistics?dataset=ahmed-masry/ChartQAPro&config=default&split=test); [published paper](https://aclanthology.org/2025.findings-acl.978/).

### 4. CharXiv

- **Size:** 2,323 scientific charts (1,000 validation; 1,323 test), with five questions per chart: 11,615 QA prompts in total. Public validation covers 5,000 prompts; test answers are withheld.
- **Label definition:** Reference answers to four descriptive questions (including one intentionally unanswerable question) and one reasoning question per chart. **No explanation-support label.**
- **Class balance:** Across all charts: 6,969 answerable descriptive (60%), 2,323 unanswerable descriptive (20%), and 2,323 reasoning prompts (20%). This is a **question-type** balance, not a hallucination balance. For scored local experiments, use the validation set because the test answers are hidden.
- **Licence:** CC BY-SA 4.0 is declared for the dataset annotations; the source arXiv chart images remain copyrighted by their original authors. The authors specify **evaluation-only** use.
- **How obtained:** Use the [official Hugging Face release](https://huggingface.co/datasets/princeton-nlp/CharXiv) or [authors' image archive and scripts](https://github.com/princeton-nlp/CharXiv). [Dataset card](https://huggingface.co/datasets/princeton-nlp/CharXiv/blob/main/README.md); [paper](https://arxiv.org/abs/2406.18521).

### 5. ChartNet-Bench

- **Size:** 3,807 human-verified chart images: 2,000 synthetic (52.5%) and 1,807 real-world (47.5%). The released ZIP is 612,755,017 bytes.
- **Label definition:** The public record says it supports chart-to-CSV extraction, chart summarization, hallucination detection/correction, and evidence-grounded evaluation. **Exact annotation fields and the definition of its hallucination labels are not documented in the public metadata examined here.** Verify these inside the archive before using it as a supervised set.
- **Class balance:** Synthetic/real chart balance above. Supported/unsupported explanation or claim counts are **not reported** in the public record; do not infer them from the chart count.
- **Licence:** CC0 1.0 is assigned to the Dataverse deposit. Check provenance of the real-world images before republishing those images; the deposit-level waiver does not establish ownership of every upstream image.
- **How obtained:** Download the unrestricted `0_ChartNetBench.zip` from the [official Harvard Dataverse record](https://doi.org/10.7910/DVN/3FH3VG) ([metadata API](https://dataverse.harvard.edu/api/datasets/:persistentId/?persistentId=doi:10.7910/DVN/3FH3VG)). Inspect the archive schema and count each task label before promoting it to a training source. **This is distinct from IBM's ChartNet.**

### 6. ChartNet `core_permissive`

- **Size:** 2,513,205 synthetic chart rows in the current default configuration.
- **Label definition:** Each row has a rendered chart, plotting code, source CSV/table, natural-language summary, chart type and plotting-library metadata. The default permissive subset does **not** supply the original release's QA reasoning traces or explanation-hallucination labels.
- **Class balance:** No supported/unsupported explanation classes exist in this subset. The full-release chart-type distribution is not reported in the card; dataset-viewer sample statistics should not be presented as population counts.
- **Licence:** CDLA-Permissive-2.0 for `core_permissive`, per the dataset card. This licence does **not** extend to the original restricted configurations below.
- **How obtained:** Select **only** `core_permissive` from the [official IBM dataset](https://huggingface.co/datasets/ibm-granite/ChartNet), ideally streaming or sampling rather than downloading its very large full release. The [dataset card and notice](https://huggingface.co/datasets/ibm-granite/ChartNet/blob/main/README.md) and [official size API](https://datasets-server.huggingface.co/size?dataset=ibm-granite/ChartNet) give the configuration terms and row count. [Published CVPR 2026 paper](https://openaccess.thecvf.com/content/CVPR2026/papers/Kondic_ChartNet_A_Million-Scale_High-Quality_Multimodal_Dataset_for_Robust_Chart_Understanding_CVPR_2026_paper.pdf).

### 7. ChartInsighter

- **Size:** 75 time-series line charts, balanced by chart complexity: 25 simple, 25 moderate, 25 complex. The study analyzes 2,693 sentences across human and model descriptions.
- **Label definition:** Sentence-level annotations of chart-description errors across ten categories, such as wrong values, trends or extrema and unsupported descriptive content. They are useful for an **error taxonomy**; these are not question-conditioned explanation labels.
- **Class balance:** Complexity 25/25/25. The paper reports error *rates per sentence*, which can exceed 1 because errors are multi-label; it does not report a clean binary supported/unsupported sentence distribution. Do not convert the reported rates into class counts without reprocessing and quality checks of the annotation workbooks.
- **Licence:** CC BY 4.0 is declared in the [authors' repository](https://github.com/wangfen01/ChartInsighter).
- **How obtained:** Clone/download the repository's chart images, generated descriptions and complexity-specific annotation workbooks. Confirm sentence alignment and reconcile workbook counts before training a classifier. [Paper](https://arxiv.org/abs/2501.09349).

### 8. ChartHal

- **Size:** 1,062 human-validated chart QA items.
- **Label definition:** Chart question plus reference answer, question type (descriptive, reasoning, open-ended) and relation to chart (irrelevant, inexistent element, contradictory premise, normal). The paper scores **a generated response** as hallucinated or not; the dataset is not a bank of human-labelled model explanations.
- **Class balance:** Descriptive 383 (36.1%); reasoning 322 (30.3%); open-ended 357 (33.6%). Relation: irrelevant 269 (25.3%), inexistent 344 (32.4%), contradictory 210 (19.8%), normal 239 (22.5%). No explanation-support prevalence is supplied.
- **Licence:** **No explicit reuse licence located** in the [authors' repository](https://github.com/ymcui/ChartHal) or [dataset page](https://huggingface.co/datasets/hfl/ChartHal) at the check date. Public download does not by itself grant redistribution or training rights; mark **RESTRICTED** until written terms are confirmed.
- **How obtained:** Files are publicly posted in the [GitHub `data` directory](https://github.com/ymcui/ChartHal/tree/main/data) and on [Hugging Face](https://huggingface.co/datasets/hfl/ChartHal). The HF viewer currently fails to infer features from the JSON, so use the source files. Seek author permission/clarification before using or releasing derivatives. [Paper](https://arxiv.org/abs/2509.17481).

### 9. ChartNet original reasoning subsets

- **Size:** In the [official size API](https://datasets-server.huggingface.co/size?dataset=ibm-granite/ChartNet), `reasoning` has 1,684,092 rows, `grounded_qa` 157,634; `human_verified` has 92,603 train and 2,000 test rows. These are **separate configurations**, not additions to `core_permissive`.
- **Label definition:** Chart QA and generated reasoning; `grounded_qa` includes grounding information, and `human_verified` contains verified cases. Neither is a ready-made binary wrong-reason benchmark.
- **Class balance:** No supported/unsupported explanation distribution reported in the dataset card.
- **Licence:** The [official data-availability notice](https://huggingface.co/datasets/ibm-granite/ChartNet/blob/main/README.md) says **no licence or other rights are granted** for the original release and limits it to verification/comparative evaluation of the ChartNet paper; commercial use is prohibited. Mark **RESTRICTED**.
- **How obtained:** The dataset card describes explicit retrieval steps for these configurations. Do not use them for this project's model training or redistributed examples without resolving the notice and upstream rights. [Published paper](https://openaccess.thecvf.com/content/CVPR2026/papers/Kondic_ChartNet_A_Million-Scale_High-Quality_Multimodal_Dataset_for_Robust_Chart_Understanding_CVPR_2026_paper.pdf).

### 10. ChartFI-Bench

- **Size:** 896 chart–description pairs drawn from arXiv charts; 80 samples were used for an expert-agreement comparison.
- **Label definition:** Reference descriptions and an evaluation framework for faithfulness, coverage, informativeness and acuity. The public README does not specify released row-level binary hallucination labels.
- **Class balance:** No supported/unsupported count reported.
- **Licence:** No released dataset licence verified; upstream arXiv figure rights must also be checked.
- **How obtained:** **Not yet obtainable as a public benchmark**: the [authors' repository](https://github.com/wangfen01/ChartFI) lists “open-source benchmark dataset” as a to-do. Track a release or contact the authors. [Paper](https://arxiv.org/abs/2605.23694).

### 11. FaithChart-1500

- **Size:** 1,498 human-verified chart-explanation samples, as stated in the paper abstract.
- **Label definition:** The work evaluates visual grounding of explanation traces with image-region sufficiency and comprehensiveness tests. It does not establish a publicly inspectable claim-level label schema for this project.
- **Class balance:** Not reported in the accessible abstract; no verified supported/unsupported counts.
- **Licence:** No dataset licence verified.
- **How obtained:** No public download verified from the [paper record](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7200053). Contact the authors if it becomes important; do not plan Phase 1 experiments around access.

### 12. Project explanation set

- **Size to collect:** **300 distinct model responses/explanations**, 50 per approach if six approaches are compared (or redistribute evenly across the final four to six approaches). With six approaches, use the **same 40 randomly selected chart questions** for all approaches (240 responses) and **10 additional questions selected to enrich likely correct-answer/wrong-reason cases** for all approaches (60 responses). Keep the two sampling frames separate in prevalence estimates.
- **Label definition:** For each response: (1) final answer correct / incorrect / ambiguous under a stated numerical tolerance; (2) explanation claims segmented into supported / contradicted / insufficient-evidence / non-factual; (3) error type (wrong value, wrong trend/comparison, invented chart element, unsupported premise, arithmetic/inference error, other); (4) chart/table evidence pointer; (5) derived `right_answer_wrong_reason = answer_correct AND any_material_claim_contradicted_or_insufficient`. Distinguish an unsupported explanation from an incorrect final answer.
- **Class balance:** **Unknown until annotation.** Do not force a 50/50 mix in the random sample. Report supported vs unsupported, answer correct vs incorrect, and their 2×2 cross-tab, separately for the random and enriched samples and for each method. If few wrong-reason positives occur, add another explicitly marked enrichment batch rather than silently changing prevalence.
- **Licence:** New human annotations and generated text can be released under a chosen project licence **only after** checking chart-source and model-output terms. Do not assume that annotating a GPL/third-party chart makes its image freely redistributable. Release IDs, annotations and permitted snippets first; link to source images when image rights are unclear.
- **How obtained, by when, by whom:** Generate outputs for the **same chart questions** under each method, saving model ID/version, prompt, seed/settings, image hash and source table. Finish the 300-item annotation by **end of project Week 5** (calendar date to set when kickoff is known), after a Week 2 pilot/codebook freeze. **Primary annotator:** project researcher (name to record in the project plan). **Second annotator:** an independent trained reviewer (name to confirm before the pilot) labels at least 60 items (20%), including all ambiguous cases where feasible; disagreements are adjudicated jointly and agreement is reported. These roles are proposed, **not confirmed personnel**.

## Recommended experimental use

1. **Main QA pool:** Sample chart questions from ChartQA's existing splits, retaining chart/source-table identifiers. Use ChartQA's test split only for final QA reporting if prompts or detectors are developed on train/validation. The source tables make numerical claims auditable.
2. **Hard external evaluation:** Use ChartQAPro and CharXiv validation without tuning on their final evaluation examples. CharXiv's unanswerable questions test whether a method invents explanations for missing evidence.
3. **Explanation audit:** Run every reasoning/verification strategy on the **same questions**. Compute answer accuracy on all generated outputs, then human explanation-support and right-answer/wrong-reason rates on the labelled sample. Report uncertainty intervals and the random/enriched samples separately.
4. **Auxiliary resources:** ChartQA-X supplies explanation examples, ChartInsighter supplies an error taxonomy, and ChartNet `core_permissive` supplies clean synthetic chart/table pairs. None replaces human labels for this project's central outcome.
5. **Pilot ChartNet-Bench:** Download and inspect its schema before treating it as a labelled hallucination benchmark. Report any discovered label definition and full class counts in a later data audit; its current public metadata does not justify those claims.

## Data statement

Data will come from the official dataset releases linked above and from model explanations generated for this project. Record source URL, version/revision, licence, retrieval date, split, chart ID and image hash for each included item. Some real-world charts may contain names, organisations or other incidental personal information; avoid collecting new personal data, screen examples before publication, and omit or redact sensitive content when found. Keep chart images and underlying data within their source terms; publish identifiers and annotations where image redistribution rights are unclear. Store annotation files without annotator names in the public release, and document model providers' retention/output terms before sending any charts to hosted services. Report licence uncertainty as a limitation rather than assuming that public availability permits all uses.
