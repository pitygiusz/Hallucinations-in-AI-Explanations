Dear Team,

Your proposed Phase 1 assessment is shown below. The scientific score follows the published rubric; any verified administrative penalty is applied separately.

Phase 1 grade calculation

Item
Points
Scientific assessment (criteria 1.1–1.5)
5/10
Confirmed formal penalty
0
Phase 1 score after confirmed penalty
5/10
Exceptional research (provisional, separate)
0/1
No confirmed formal penalty has been applied. Any administrative issues described below are recorded for correction or an instructor decision, not treated as additional deductions.

The proposed exceptional-research point has not been added to the Phase 1 mark; it requires separate verification and approval. One mandatory correction is required before final approval (validation of the LLM judge; see “Formal completeness and submission issues”).

Criterion-by-criterion assessment

Criterion
Proposed score
Maximum
1.1 State of the art
1.5
3
1.2 Datasets and their status
1.5
3
1.3 Solution concept and plan
1
2
1.4 Text quality and references
0.5
1
1.5 Data statement
0.5
1
Core total
5
10
Detailed justifications

1.1 State of the art — 1.5/3. Full-credit standard: At least 15 works, each with method, dataset, and result; quantitative comparison of published values with dataset and split for each value. Finding: 15 works are reviewed, but only about 5 give what/data/result; Table 1 has no explanation-reliability or hallucination numbers and mixes a relative gain with absolute scores.

Details: • Full credit requires at least 15 works, each described with what it does, on what data and with what result, plus a table in which every number names its dataset and split. What is missing: • Results are absent or only qualitative for most of the 15 works. ChartQA-X (“considerable improvements”, p.1), ChartQA (no result, p.2), ChartInsighter (“lowest summary hallucination rate”, no number), Obaid ul Islam et al. (no data named, no number), TinyChart (“stronger ChartQA performance”, no number), Faithful CoT (“nine of ten benchmarks”, no number), chain-of-thought (“substantial gains”), self-consistency (no dataset, no number) and Chain-of-Verification (no dataset, no number) all fall short. Only ChartHal, FaithChart, ChartQAPro, CharXiv and DePlot meet all three elements. • Table 1 (p.2) reports only answer-accuracy numbers from 4 of the 15 papers. The project is about explanation reliability, yet the table has no number on that: not FaithChart’s grounding metrics (sufficiency/comprehensiveness gap −88%, −5.5 pp accuracy), not ChartInsighter’s hallucination rate, not ChartHal’s hallucination rate, not CoVe’s hallucination reduction, and not ChartQA-X’s explanation-quality scores. Add a block of rows for explanation and hallucination metrics. • The DePlot row (Table 1) reports “Accuracy gain +29.40 pp” rather than a score. Report the absolute accuracy and the baseline it is compared with (67.6% vs MatCha 38.2% on ChartQA test, human-written queries) so it is comparable with the other rows. • The ChartHal GPT-5 row reports the “GPT-5 (high)” configuration (34.46%) as “GPT-5”. On the authors’ leaderboard, default GPT-5 scores 34.37%. Name the reasoning-effort setting. • ChartHal is said to have “1,062 human-validated cases” (p.1–2), but §3.3 says “1000 samples”. ChartInsighter is said to use “75 time-series charts” (p.2), but §3.4 says “2,000+ samples”. Reconcile these figures and define the counting unit (charts, questions or summaries). • PoT is one of your candidate strategies (§4.2), but the Program-of-Thought paper itself is not reviewed or cited. • What is good: the three-way grouping and the explicit “three closest studies” paragraph (§2.1) are well chosen, and every row of Table 1 does name both a dataset and a split.

1.2 Datasets and their status — 1.5/3. Full-credit standard: For each dataset: size, labels, numeric class balance, licence, acquisition, readiness; collection quantity, date and annotator(s) where applicable. Finding: The four public datasets carry status labels, but class balance is missing or non-numeric for three of them, licence facts are incomplete or wrong for ChartHal. The planned annotated sets are partially described in Section 4.1, including their intended sizes, annotators and timeline. However, they lack a dedicated dataset specification, explicit TO COLLECT status, detailed label definitions and a sufficiently precise annotation and validation protocol.

Details: • Full credit requires, for every dataset the plan relies on: size, label definition, class balance as numbers (or a reason it does not apply), licence, how it was obtained, and a status label; for TO COLLECT data, also how many items, by when and annotated by whom. What is missing: • The human-annotated set (200 responses) and the LLM-as-a-judge set (1k–10k responses, §4.1) are TO COLLECT datasets but get no subsection in §3 and no status label. They have no label definition beyond four error types listed in one sentence, no definition of the unit annotated (whole explanation or individual claim), no expected class balance (e.g. the share of correct answers with flawed explanations), and no licence for the released annotations. The count (25 charts × 2 models × 4 strategies), the annotators (all four members) and the date (Nov 11–18, Table 2) are given only in §4.1 and Table 2. • Class balance: ChartHal says “an uneven four-way split” with no numbers, ChartInsighter (§3.4) has no class-balance line at all, and ChartNet gives a range of chart-type shares. Give the per-class counts. • ChartHal licence: the hfl/ChartHal Hugging Face card and the ymcui/ChartHal GitHub repository declare no licence. The CharXiv data it builds on is CC BY-SA 4.0 on Hugging Face (princeton-nlp/CharXiv); the Apache 2.0 licence you quote is the CharXiv code licence. Correct §3.3 and §5.1 accordingly. • ChartNet’s role is undefined. It is a 1.5M-sample training corpus, your plan has no training step, and its “label definition” (24 chart types) is not a label for your task. Either state which subset you will sample for evaluation and why, or drop it. ChartNet is also not cited in the References. • ChartQA-X’s “ground-truth explanations” are model-generated and selected by automatic criteria (as you say on p.1). State this in §3.1, because it matters if you use them as reference explanations. • What is good: each public dataset has a READY label, a Hugging Face or GitHub identifier, and a licence for ChartQA-X, ChartNet and ChartInsighter; these identifiers match the repositories.

1.3 Solution concept and plan — 1/2. Full-credit standard: One pipeline figure; evaluation metrics chosen in advance; two or three concrete deliverables; weekly task/owner plan. Finding: The pipeline figure, the metric list and a dated plan with owners are present, but three published elements are vague: the deliverables are conditional (“Depending on project progress and available resources, we aim to produce…”, §4.4) and the planned sizes are open ten-fold ranges (Figure 1: the larger chart set is 125–1250 charts, and the LLM-judge stage covers N = 1k–10k outputs); the main measurement, the hallucination rate, depends on a judge model that is not named (§4.1), so the metric is not defined before results; and the strategies to be compared are not fixed (“at least four of the following… selected after assessing their suitability”, §4.2). Half credit.

The proposed evaluation of hallucinations in explanations addresses a relevant research problem, but the experimental protocol is insufficiently specified. In particular, the LLM judge, its validation procedure, and the comparison between evaluation strategies require clarification. For Phase 2, you must establish a reliable evaluation protocol, including human-validated reference judgments, explicit baselines, and an assessment of judge reliability. An MSc-level contribution requires independently validated findings, not simply applying an LLM judge to model-generated explanations. Substantial methodological improvement is mandatory.

Additional evidence: Figure 1, three deliverables and a dated plan with owners (Table 2) are present, but no primary metric is designated, the judge model is unnamed and the strategy set is not fixed.

1.4 Text quality and references — 0.5/1. Full-credit standard: Scientific language and defined abbreviations; accurate published-version citations; fewer than one-third preprint-only references. Finding: ChartHal is cited as an arXiv preprint although a Findings of AACL 2026 version exists; there are undefined abbreviations (GT, PoC, pp, GenAI) and informal register in §3.

Details: • Full credit requires scientific language with no unexplained abbreviations, the published version cited for every work that has one, and preprint-only citations under one-third of the list. There are 17 references; 3 are preprint or grey literature only (Gemma 4 technical report, FaithChart on SSRN, Qwen3.5 blog post), which is under one-third. What is missing: • ChartHal (Wang et al., 2025b) is cited as arXiv:2509.17481, but it is published in Findings of the ACL: AACL 2026 (ACL Anthology 2026.findings-aacl.88). Cite the published version. • Incomplete entries: “Gemma Team (2026). Gemma 4 technical report.” has no identifier (arXiv:2607.02770), and “Qwen Team (2026). Qwen3.5: Towards native multimodal agents.” has no URL or type (blog post, February 2026, qwen.ai/blog?id=qwen3.5). FaithChart lacks its DOI (10.2139/ssrn.7200053). Several entries lack pages (DePlot 10381–10399, Faithful CoT 305–329, ChartInsighter TVCG 3733–3745). • Undefined abbreviations: GT (Figure 1), PoC (Table 2), pp (Table 1), GenAI (§5.4), SSRN (p.2), BIG-Bench (p.3), API (§4). LLM is defined; SOTA is used only as a heading. • Informal register in §3: “We’ve decided to focus…”, “Let’s evaluate these one by one”, “It’s been specifically designed”. Rewrite in scientific style.

1.5 Data statement — 0.5/1. Full-credit standard: Data source, licence, personal-data status and concrete handling safeguards. Finding: Source, licences and “no personal data” are stated, but there is no handling plan for the unlicensed ChartHal, CharXiv’s CC BY-SA terms, or the team’s own generated and annotated data.

Details: • Full credit requires: where the data comes from, the licence, whether it contains personal data, and what the team does about it. What is missing: • No action is stated for the unlicensed ChartHal. Will you contact the authors, use it only for internal evaluation, or avoid redistributing it? CharXiv-derived material is CC BY-SA 4.0 (share-alike), not Apache 2.0 as §5.1 says. • The statement says all datasets are “available on the Hugging Face platform”, but §3.4 says ChartInsighter is cloned from GitHub. • Your own data is not covered: model outputs (Qwen3.5-9B and Gemma 4 E4B, both Apache 2.0), the human annotations and the judge annotations. Say under which licence you will release them, and how you will keep the original chart, question and ground truth with every explanation, as the card’s “Data & ethics” line requires. • “None of the datasets contain personal data” is asserted without justification. ChartHal and CharXiv images come from arXiv papers, so say a word about their provenance.

Strengths, weaknesses, and methodological observations

WHAT DESERVES PRAISE (not scored): Important research question: distinguishes answer correctness from explanation support; human adjudication of a small sample is appropriate.

EXPERT NOTE / RISK (not scored): Scientific caution: user-visible generated explanations or chain-of-thought text are not a faithful readout of a model’s internal causal reasoning. | Twenty-five chart questions yielding 200 outputs do not constitute 200 independent test questions. Report confidence intervals clustered by chart/question.

Assessment summary: All five criteria are at half credit. The report passes the folder, template and deadline gates, but the LLM-use declaration (§5.4) names no tool, so that gate is only partly met. The single most important problem is that the project’s own data (the 200-response human-annotated set and the 1k–10k judge-annotated set, §4.1) is not described as a dataset: it has no status label, no label scheme, no expected class balance and no agreement protocol. These sets are the core deliverable of the topic. The single most important fix is to write §3.5 “Own annotated sets (TO COLLECT)” with an annotation guideline, label definitions, sizes, an inter-annotator agreement plan and a deadline, and to name the primary metric that this annotation supports. [Maj Barto1] 

The team's own annotated datasets are briefly introduced in Section 4.1, but their specification remains incomplete. In particular, a dedicated dataset section, explicit readiness labels, detailed annotation guidelines and an inter-annotator agreement protocol are still needed.

Required revisions and priority actions for Phase 2

1)               Add §3.5 describing the two TO COLLECT annotated sets: status label, unit of annotation (claim or explanation), label taxonomy with definitions and examples, expected class balance, number of items, deadline, annotators, inter-annotator agreement procedure (overlap size, kappa/alpha, adjudication) and release licence.
2)               In §4.3, name one primary metric and define “hallucination rate” precisely; name the judge model, its version and its prompt; and fix the 4–6 strategies to be compared.
3)               Extend Table 1 (criterion 2.5) with explanation-reliability and hallucination numbers (FaithChart, ChartInsighter, ChartHal hallucination rate, CoVe, ChartQA-X explanation metrics), with dataset and split for every number. Replace the DePlot gain with absolute scores, and add the six works listed above.
4)               Give data and a numeric result for every reviewed work (currently missing for ChartQA-X, ChartQA, ChartInsighter, Obaid ul Islam et al., TinyChart, Faithful CoT, CoT, self-consistency and CoVe).
5)               Correct the licence facts (ChartHal has no licence; CharXiv data is CC BY-SA 4.0) and state what you will do about them in §5.1. Add numeric class balance for ChartHal and ChartInsighter, reconcile the dataset sizes, and justify or drop ChartNet.
6)               Cite ChartHal’s published version, complete the Gemma 4, Qwen3.5 and FaithChart entries, and cite ChartNet and PoT.
7)               Name the LLM tools in §5.4 and fix the supervisor in the header.
8)               State RQ1/RQ2 and the out-of-scope stance on reasoning traces explicitly.
9)               In §4.3/§4.1, acknowledge that the 200 responses derive from only 25 charts (2 models × 4 strategies), so they are not 200 independent observations; report confidence intervals clustered by chart or question rather than treating all 200 as i.i.d.
10)          Phase 2 requires a rebuttal that answers every point of this feedback at a named place in the revised report (criterion 2.4) and an extended SOTA table (criterion 2.5).
Further actions raised in the parallel review:

1)               Resolve ChartHal rights explicitly; a derivative dataset does not automatically inherit unrestricted reuse rights.
2)               Define the unit of hallucination annotation (atomic claim, explanation step, or whole answer), with a repeatable codebook and inter-annotator agreement.
3)               Calibrate the external automatic judge against independent human labels before scaling to 1,000–10,000 explanations.
Alignment with the assigned project topic (formative, not an additional Phase 1 deduction)

• The report addresses the card’s core phenomenon (correct answers with unsupported explanations on charts). It plans 4–6 prompting and verification strategies and adopts the three success deliverables (annotated set, reproducible comparison, analysis of patterns and costs). There are gaps against the card: 1. An explicit hypothesis is provided in Section 4. However, the research questions should be formulated more clearly, distinguishing the detection of unsupported explanations from the evaluation of strategies intended to reduce them. [Maj Barto2] The card asks both whether such errors can be detected and whether strategies reduce them. Write RQ1 (detection: judge vs human P/R/F1) and RQ2 (reduction: error rate per strategy), plus the card’s question whether more elaborate reasoning introduces additional errors. 2. The READY / TO COLLECT labels are used only for public data; the card’s TO COLLECT annotated sample is not labelled. 3. On out of scope: §4 motivates open-weight models because they “allow us to collect their generated reasoning traces”. State explicitly that traces are treated as generated text to be verified, not as evidence of internal decision-making, in line with the card and with Turpin et al. (2023). 4. The card’s difficulty profile assumes human annotation of hallucinations as a key methodological element; the annotation protocol (guideline, unit, agreement) is the weakest part of the report. 5. The card names no seed publication or external comparison point. The closest external comparison points in your review are ChartHal and FaithChart; say which published number you will compare against. • The topic allows one team and no sibling team submitted on it.

Questions to answer in the Phase 2 rebuttal

1.               Is the annotation unit an explanation claim, a reasoning step or a whole answer, and how is it adjudicated?
2.               How will you estimate uncertainty when several generated outputs share the same underlying chart/question?
Additional methodological validity checks (formative, not scored in Phase 1)

Additional evidence to seek for Phase 2 (not part of the Phase 1 grade): Create a validated explanation-support annotation codebook with clustered uncertainty estimates.

Formal completeness and submission issues

Mandatory correction — LLM-as-a-judge validation (required before final approval): The LLM judge is to be validated against 200 human-annotated responses (§4.1, §4.3), but these come from only 25 chart–question pairs and no agreement procedure among the four human annotators is planned. Name the judge model and give its prompt, with the four error categories (incorrect readings, invented information, unsupported claims, calculation errors) and the output format. Report inter-annotator agreement on the human set (overlap size, Cohen’s κ or Krippendorff’s α, adjudication), and state the acceptance threshold (e.g. minimum F1 or κ against the human labels) that the judge must reach before it annotates the 1k–10k set.

Formal correction required before final approval: The LLM-use declaration refers to generic GenAI tools without naming them. Correct before final acceptance. Fix the topic supervisor attribution as well.

Evidence recorded during the independent review:

• Contribution table: present-complete — §5.2 (p.5) lists all four members per task with hours (P.J. 7 h, K.K. 5 h, J.W. 4 h, T.Ż. 5 h). Note that the “contributed equally” footnote on p.1 does not match these hours. • LLM-use declaration: present-incomplete — §5.4 says “GenAI tools” were used for literature search, model selection, planning, language and LaTeX, but names no tool. Name each tool (e.g. ChatGPT, Claude, Copilot) and state what each was used for. • Folder naming: compliant — The folder jurczyk_krawiec_wyrzykowski_zochowski matches the four authors on p.1 (Jurczyk, Krawiec, Wyrzykowski, Żochowski). • Template: compliant — Two-column ACL-derived course layout with the “Project Proposal for NLP Course, Winter 2026/27” header. The supervisor block, however, names Anna Wróblewska; the topic supervisor is Bartosz Maj. • Deadline (4.11): on time — Committed on 4.11 before midnight CET.

Proposed exceptional-research recognition: 0/1. This optional point is not a deduction and does not change the /10 score; it is awarded only for a completed, verifiable contribution beyond the core rubric.

Suggested literature and bibliographic checks for Phase 2

The entries below are suggestions from an independent bibliographic review. Verify all metadata and the suitability of each source against the original publication before citing it.

1)               Chen, W., Ma, X., Wang, X., and Cohen, W. W. (2023). Program of Thoughts Prompting: Disentangling Computation from Reasoning for Numerical Reasoning Tasks. Transactions on Machine Learning Research. https://arxiv.org/abs/2211.12588 — This is the original PoT method, which you list as a strategy in §4.2 but do not cite. It is needed to define your PoT variant and its expected numerical-reasoning gains.
2)               Guan, T., Liu, F., Wu, X., Xian, R., et al. (2024). HallusionBench: An Advanced Diagnostic Suite for Entangled Language Hallucination and Visual Illusion in Large Vision-Language Models. CVPR 2024, pp. 14375–14385. https://doi.org/10.1109/CVPR52733.2024.01363 — A standard VLM hallucination benchmark that includes charts and tables; its separation of language-prior errors from visual misreading maps directly onto your error categories.
3)               Lim, Ahn, and Kim (2025). ChartCap: Mitigating Hallucination of Dense Chart Captioning. ICCV 2025, pp. 13171–13182. https://doi.org/10.1109/ICCV51701.2025.01224 — Recent chart-specific hallucination work with a reference-free consistency evaluation that you can contrast with your LLM-as-a-judge.
4)               Suri, M., Mathur, P., Lipka, N., Dernoncourt, F., et al. (2025). ChartLens: Fine-grained Visual Attribution in Charts. ACL 2025 (Long Papers), pp. 22447–22462. https://doi.org/10.18653/v1/2025.acl-long.1094 — Attributes chart answers to specific chart elements; it is a concrete method for checking whether each explanation claim is supported by the visual evidence.
5)               Min, S., Krishna, K., Lyu, X., Lewis, M., et al. (2023). FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation. EMNLP 2023, pp. 12076–12100. https://doi.org/10.18653/v1/2023.emnlp-main.741 — An atomic-claim decomposition protocol that you can adopt as the annotation unit for both human and judge labelling of explanations.
6)               Huang, J., Chen, X., Mishra, S., Zheng, H. S., Yu, A. W., et al. (2024). Large Language Models Cannot Self-Correct Reasoning Yet. ICLR 2024. https://arxiv.org/abs/2310.01798 — Evidence that self-verification without external feedback can degrade answers. It bears directly on your “verification pipeline” strategy and on the card’s question whether more reasoning introduces errors.
For Phase 2, respond point by point to the substantive feedback and questions, indicating whether each item was corrected, rejected with justification, or deferred. Refer to the corresponding section, table, figure, code file or experiment. Additional advice above does not retroactively reduce the Phase 1 core score.

Best regards, Anna Wróblewska