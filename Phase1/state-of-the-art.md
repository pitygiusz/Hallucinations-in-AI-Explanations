# State of the art: hallucinations in AI explanations of charts

**Research snapshot:** 28 October 2026  
**Project brief:** [project-topic.md](./project-topic.md)  
**Question:** When a model answers a chart question correctly, can its explanation still contain false or unsupported claims, and which generation or verification methods reduce that problem?

## Executive assessment

Chart question answering (CQA) has advanced beyond simple benchmark accuracy, but **answer correctness is an inadequate measure of explanation reliability**. Recent work supplies realistic chart questions (CharXiv, ChartQAPro), answer–explanation pairs (ChartQA-X), chart-specific hallucination probes (ChartHal), and an emerging visual-grounding benchmark (FaithChart) [3–7]. These are close precedents, so the project should **not** claim to be the first study of faithful chart explanations. Its sharper contribution would be a reproducible, *claim-level* analysis of explanations **given correct answers**, with error localization, evidence checks, and a controlled comparison of reasoning versus verification strategies.

There is no single defensible “best model” for this topic: leaderboards measure different chart types, questions, answer formats, and access to source data. The strongest methodological direction is to **separate chart extraction, arithmetic, and explanation checking**, then evaluate each stage. Structured chart-to-table conversion and executable computation have shown gains in chart/numerical tasks [2, 16, 20–21], while independent verification and step-level checks offer ways to detect errors that answer voting alone may miss [17–18]. These gains do not by themselves establish that the final natural-language explanation is fully supported by the chart.

## What exactly should be measured?

For a chart image or source table (E), question (Q), generated answer (A), and explanation (X):

- **Answer correctness:** Does (A) match the reference answer, with appropriate numeric tolerance and units?
- **Evidence grounding:** Does each factual claim in (X) follow from the chart, its source table, and any allowed question context? A claim can be false, unsupported, or unverifiable from the available evidence.
- **Step validity:** Do operations in (X) use the stated values and yield the stated intermediate and final results?
- **Answer–explanation consistency:** If the steps in (X) are followed, do they actually support (A)?
- **Causal faithfulness:** Did the model *internally use* the reasons it states? This is a different, much harder question. Chain-of-thought text can rationalize a prediction [11–12]. The project brief explicitly excludes claims about internal reasoning, so use “evidence-grounded” or “supported explanation” for the primary outcome. FaithChart's image-perturbation tests address a related causal-grounding question, but their metric is not interchangeable with claim-level factual support [7].

The target failure is **(A) correct, (X) flawed**. For example, a model might answer “2019” correctly while claiming a bar has value 62 when it is 52, or while using a subtraction that does not yield the stated difference. Report this cell separately rather than hiding it in overall accuracy.

## Closest prior work

| Strand | Main contribution | Relevance and limitation for this project |
| --- | --- | --- |
| **Chart QA and realistic tests** | ChartQA contains human-written and summary-derived questions requiring visual and logical reasoning [1]. CharXiv uses 2,323 curated charts from scientific papers; ChartQAPro adds 1,341 charts and 1,948 diverse questions, including unanswerable ones [3–4]. | Good sources of questions and difficulty variation. Reference answers alone usually do not identify which explanation claims are wrong. ChartQA's source tables can act as stronger evidence than pixels alone where available. |
| **Explanations for CQA** | ChartQA-X supplies 30,799 chart samples with questions, answers, and explanations; it evaluates explanation quality and fine-tuning [5]. | The closest explanation dataset. Its generated/selected explanations are useful as a baseline, but quality scores should not be treated as ground truth that every atomic claim is supported. |
| **Chart hallucination evaluation** | ChartHal provides a human-validated 1,062-sample, fine-grained chart hallucination benchmark, with difficult absent/contradictory-information cases [6]. ChartNet-Bench adds chart-to-CSV, summarization, and hallucination-detection tasks [22]. | Valuable stress tests and taxonomy ideas. They are broader than the specific conditional event “correct answer, flawed explanation.” Check data access and licensing before adoption. |
| **Visual grounding of explanations** | FaithChart (2026 preprint) proposes image-region perturbation metrics and 1,498 human-verified examples; its abstract reports that accuracy ranking and grounding ranking differ across models [7]. | Directly adjacent work. A new project should compare or complement its sufficiency/comprehensiveness measures with human-checked claim support and arithmetic validity, not repeat a broad novelty claim. Preprint results warrant independent replication. |
| **Chart summarization hallucinations** | Chart-to-Text and later studies document factual errors in generated chart descriptions; ChartInsighter uses data-analysis modules and consistency checks with sentence-level hallucination labels [8–10]. | Strong evidence that fluent chart prose can be unsupported, and useful annotation patterns. Summaries lack a question and final answer, so they do not isolate the target failure mode. |
| **Explanation faithfulness and verification** | CoT can omit influences or rationalize answers [11]. Tests of explanation consistency do not automatically reveal internal model reasoning [12]. Faithful CoT uses symbolic steps and a solver; Chain-of-Verification uses independently answered checks; process supervision judges intermediate steps [17–19]. | Provides methods and conceptual cautions. Most results are from text, math, or knowledge tasks; their benefit on chart-grounded explanations needs testing. |

**Selected reported results, with their scope:** CharXiv's paper reports 47.1% accuracy for GPT-4o and 80.5% for humans on its benchmark [3]. ChartQAPro reports one model dropping from 90.5% on ChartQA to 55.81% on ChartQAPro [4]. ChartHal's preprint reports 34.46% and 22.79% on its own hallucination benchmark for GPT-5 and o4-mini, respectively [6]. These numbers are **not comparable across papers** and should not be combined into a model ranking.

## Reasoning and verification strategies: what the evidence supports

1. **Direct answer plus short evidence.** A necessary baseline. Short output may contain fewer errors simply because it makes fewer claims; record evidence coverage as well as error rate.
2. **Chain-of-thought (CoT).** Step-by-step prompting can improve reasoning-task accuracy [13]. It also creates more intermediate factual and arithmetic claims to check. Turpin et al. show that a plausible CoT can rationalize biased answers [11]; therefore more detailed reasoning should be an empirical treatment, not an assumed trust improvement.
3. **Self-consistency or search.** Sampling multiple paths and voting on the answer improves accuracy on several arithmetic/commonsense tasks [14]. Tree of Thoughts explores and evaluates branches [15]. Neither guarantees that the selected path's chart values are correct; several paths may share the same extraction error. Evaluate explanation support separately and include token/call cost.
4. **Structured representation plus executable arithmetic.** DePlot converts charts to linearized tables before language-model reasoning [2]. Program-of-Thoughts delegates calculations to code [16], and a 2026 chart-summarization preprint applies this idea to a chart-to-dictionary representation [20]. A recent table-first CQA paper reports improved ChartQA answer accuracy for its pipeline [21]. These methods make calculations auditable, but a wrong extracted value can remain a convincing, executable error. Validate the extracted table against source data or manual transcription.
5. **Independent verification.** Chain-of-Verification drafts, formulates checks, answers them independently, and revises [18]. For charts, the checks should explicitly re-read cited labels, units, and values, recompute arithmetic, and return `supported / contradicted / insufficient evidence` for each claim. An independent verifier using the same image may repeat a perceptual error; an oracle source table provides an informative upper bound.
6. **Evidence-linked claims.** Require a compact intermediate record such as `{claim, series, category, value, unit, operation, source}` and generate prose only from verified records. Faithful CoT motivates symbolic steps whose result is determined by a solver [17]; FaithChart motivates linking statements to visual evidence [7]. This is a promising project-specific strategy, but its effect on chart explanations remains to be established experimentally.

## Recommended benchmark design

**Data.** Start with ChartQA and its underlying tables where available [1]. Add a realistic holdout from CharXiv or ChartQAPro [3–4], plus targeted unanswerable/contradictory examples from ChartHal [6]. Use ChartQA-X as a source of explanation examples or a separate evaluation set [5]. Preserve original chart images, tables, questions, splits, and dataset licenses. Separate synthetic from real charts and avoid chart overlap across development and test sets.

**Generate explanations under six conditions using the same base multimodal model, decoding settings, and question set:** (A) direct, (B) CoT, (C) CoT with answer self-consistency, (D) chart-to-table plus executable arithmetic, (E) CoT followed by independent claim verification, and (F) structured evidence records with deterministic checks. Where (D) uses an extra extraction model, report its added cost and compare both *predicted* and *oracle* tables. Tree of Thoughts is a worthwhile optional seventh arm only if the budget permits; its search overhead and self-evaluation make attribution harder.

**Annotate a stratified sample** across chart type, question operation, model condition, and answer correctness. Split explanations into atomic claims and label: (i) supported, contradicted, or insufficient evidence; (ii) error type—invented/misread value, label or unit mismatch, faulty arithmetic, unsupported comparison/trend, unsupported external assertion, or answer–step inconsistency; (iii) the precise chart cell/region or calculation needed to adjudicate it. Use two annotators on a shared subset, adjudicate disagreements, and record uncertainty for illegible or genuinely ambiguous charts. Keep the original model output: later revisions must not overwrite the errors being measured.

**Primary outcomes:**

- `P(any flawed claim | answer correct)`, with a chart-clustered confidence interval. This directly measures “right answer, wrong reason.”
- Claim-level contradiction and insufficient-evidence rates; also report claims per response and the fraction of answer-relevant claims that are supported, so verbosity or empty explanations cannot appear artificially good.
- Detector precision, recall, F1, and calibration for flawed explanations, evaluated against human labels. Include false positives on correct explanations.
- Answer accuracy, answer–step consistency, numeric extraction accuracy, and arithmetic-step accuracy as separate outcomes.
- Calls, tokens, latency, and—where applicable—extraction or tool costs per question.

Use paired comparisons on the **same chart questions**, bootstrap by chart (not by individual claims from the same chart), and report results by chart type and operation. Avoid selecting only correct answers before measuring overall accuracy; form the conditional subset afterward. A small manually constructed set of “correct answer + deliberately corrupted explanation” cases can test detector sensitivity, but keep it separate from naturally occurring model errors.

## Research gap and proposed contribution

The defensible gap is **joint, fine-grained evaluation of answer correctness and explanation evidence** on realistic charts, with the conditional failure rate as a central result and a controlled comparison of generation, computation, and independent checking. ChartQA-X, ChartHal, ChartInsighter, and FaithChart each cover important neighboring parts [5–8]; a good study should explicitly position its labels, sample selection, and metrics against them. The most informative outcome may be *which stage fails*: visual extraction, arithmetic, unsupported narrative inference, or verification itself.

Two hypotheses are worth preregistering rather than assuming: (H1) longer CoT increases answer accuracy on some multi-step questions but also increases the number of unsupported claims; (H2) table-grounded computation plus independent claim verification reduces the conditional failure rate more reliably than answer self-consistency, provided extraction is accurate. Either hypothesis can fail, especially on dense scientific charts where source values are hard to read.

## References

1. Masry, A. et al. (2022). **ChartQA: A Benchmark for Question Answering about Charts with Visual and Logical Reasoning.** *Findings of ACL*. https://doi.org/10.18653/v1/2022.findings-acl.177
2. Liu, F. et al. (2023). **DePlot: One-shot visual language reasoning by plot-to-table translation.** *Findings of ACL*. https://doi.org/10.18653/v1/2023.findings-acl.660
3. Wang, Z. et al. (2024). **CharXiv: Charting Gaps in Realistic Chart Understanding in Multimodal LLMs.** *NeurIPS*. https://doi.org/10.52202/079017-3609
4. Masry, A. et al. (2025). **ChartQAPro: A More Diverse and Challenging Benchmark for Chart Question Answering.** *Findings of ACL*. https://doi.org/10.18653/v1/2025.findings-acl.978
5. Hegde, S., Fazli, P., & Seifi, H. (2026). **ChartQA-X: Generating Explanations for Visual Chart Reasoning.** *WACV*. https://doi.org/10.1109/WACV61042.2026.00624
6. Wang, X. et al. (2025). **ChartHal: A Fine-grained Framework Evaluating Hallucination of Large Vision Language Models in Chart Understanding.** *arXiv preprint*. https://doi.org/10.48550/arXiv.2509.17481
7. Mai, X. T. et al. (2026). **FaithChart: Measuring and Improving the Visual Grounding of Chart Explanations in Vision-Language Models.** *SSRN preprint*. https://doi.org/10.2139/ssrn.7200053
8. Wang, F. et al. (2025). **ChartInsighter: An Approach for Mitigating Hallucination in Time-Series Chart Summary Generation With a Benchmark Dataset.** *IEEE Transactions on Visualization and Computer Graphics*. https://doi.org/10.1109/TVCG.2025.3567122
9. Obaid ul Islam, S., Škrjanec, I., & Dušek, O. (2023). **Tackling Hallucinations in Neural Chart Summarization.** *INLG*. https://doi.org/10.18653/v1/2023.inlg-main.30
10. Kanthara, S. et al. (2022). **Chart-to-Text: A Large-Scale Benchmark for Chart Summarization.** *arXiv preprint*. https://doi.org/10.48550/arXiv.2203.06486
11. Turpin, M. et al. (2023). **Language Models Don't Always Say What They Think: Unfaithful Explanations in Chain-of-Thought Prompting.** *NeurIPS*. https://doi.org/10.52202/075280-3275
12. Pârcălăbescu, L., & Frank, A. (2024). **On Measuring Faithfulness or Self-consistency of Natural Language Explanations.** *ACL*. https://doi.org/10.18653/v1/2024.acl-long.329
13. Wei, J. et al. (2022). **Chain-of-Thought Prompting Elicits Reasoning in Large Language Models.** *NeurIPS*. https://doi.org/10.52202/068431-1800
14. Wang, X. et al. (2022). **Self-Consistency Improves Chain of Thought Reasoning in Language Models.** *arXiv preprint* (later ICLR 2023). https://doi.org/10.48550/arXiv.2203.11171
15. Yao, S. et al. (2023). **Tree of Thoughts: Deliberate Problem Solving with Large Language Models.** *NeurIPS*. https://doi.org/10.52202/075280-0517
16. Chen, W. et al. (2022). **Program of Thoughts Prompting: Disentangling Computation from Reasoning for Numerical Reasoning Tasks.** *arXiv preprint*. https://doi.org/10.48550/arXiv.2211.12588
17. Lyu, Q. et al. (2023). **Faithful Chain-of-Thought Reasoning.** *IJCNLP-AACL*. https://doi.org/10.18653/v1/2023.ijcnlp-main.20
18. Dhuliawala, S. et al. (2024). **Chain-of-Verification Reduces Hallucination in Large Language Models.** *Findings of ACL*. https://doi.org/10.18653/v1/2024.findings-acl.212
19. Lightman, H. et al. (2023). **Let's Verify Step by Step.** *arXiv preprint*. https://doi.org/10.48550/arXiv.2305.20050
20. Qu, Y., & Zhang, W. E. (2026). **From Data to Insights: Exploring Program-of-Thoughts Prompting for Chart Summarization.** *arXiv preprint*. https://doi.org/10.48550/arXiv.2605.28874
21. Aziz, A. et al. (2026). **Table-First Guarded Reasoning: Outperforming Larger MLLMs in Chart Question Answering.** *IEEE Conference on Artificial Intelligence*. https://doi.org/10.1109/CAI68641.2026.11536412
22. Luo, X. (2026). **ChartNet-Bench: A Benchmark for Faithful Multimodal Chart Understanding.** *Harvard Dataverse dataset*. https://doi.org/10.7910/DVN/3FH3VG

Bibliographic metadata and available abstracts were checked against OpenAlex/Crossref in October 2026. Results above are attributed to their respective papers and are not a new empirical replication.
