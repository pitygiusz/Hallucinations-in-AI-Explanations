# 10. Right Answer, Wrong Reason: Hallucinations in AI Explanations

Supervisor: Bartosz Maj  
Difficulty: Hard (14/25)

## Example of a research question

Can we detect hallucinations and unsupported reasoning in AI-generated explanations, even when the final answer is correct? Can different reasoning or verification strategies help reduce these errors?

## Why it matters

AI models can produce convincing explanations that contain made-up facts, incorrect values or assumptions not supported by the available evidence. Sometimes they even arrive at the correct answer despite mistakes in their explanation. This is particularly problematic when interpreting charts and scientific data, where we need to trust not only the result but also the evidence behind it.

## Data — READY / TO COLLECT / NDA

Status: READY / TO COLLECT

- READY: Public datasets for chart understanding, question answering and explanation generation, including charts, questions, answers and supporting data.
- TO COLLECT: A small sample of AI-generated explanations, annotated for hallucinated information, incorrect values and unsupported reasoning steps.

## What you will do

- Investigate how hallucinations appear in AI-generated explanations and how they differ from ordinary reasoning mistakes. You may start with simpler image-based tasks before moving to charts and numerical reasoning.
- Explore different ways to detect or reduce these errors (e.g. direct prompting, Chain-of-Thought, Program-of-Thought, self-consistency, Tree-of-Thoughts, structured intermediate representations or independent verification). You are encouraged to explore your own ideas as well.
- Compare at least 4 approaches on chart-based questions, focusing on answer accuracy, hallucination detection and the reliability of generated explanations. Investigate whether more elaborate reasoning actually helps or sometimes introduces additional errors.

## What success looks like

- An annotated set of chart-based explanations, including examples where the final answer is correct but the explanation contains hallucinations or reasoning errors.
- A reproducible comparison of 4-6 approaches from different reasoning or verification strategies, measuring answer accuracy, hallucination rates and the ability to detect unsupported explanations.
- An analysis of common hallucination patterns, their possible causes and which approaches help reduce or detect them, including their limitations and computational costs.

## Out of scope

Determining how a model actually reasons internally or assuming that generated reasoning steps reflect its real decision-making process. The focus is on identifying and verifying hallucinations and unsupported statements in the explanations models produce.

## Starting point

Prior work: Previous research has explored hallucinations in language and multimodal models, different reasoning strategies, and methods for evaluating AI-generated explanations. Studies have shown that models can produce incorrect intermediate steps, invent supporting evidence or provide convincing but unreliable explanations.

New this year: What remains interesting is how these problems appear in tasks that require interpreting visual and numerical evidence, and whether additional reasoning actually makes explanations more trustworthy. This project investigates ways to detect and reduce such errors, with a particular focus on chart understanding and scientific data.

## Data & ethics

Use public datasets within their licence terms, document generated explanations and retain the original evidence used to evaluate them.

## Level & skills

Level: Hard (score 14/25, see the difficulty table below)  
Skills: Python, LLM prompting and evaluation, multimodal reasoning and basic statistics.

## Contact & availability

Bartosz Maj — bartosz.maj.dokt@pw.edu.pl  
Availability: consultations by arrangement.

## Team slots

Max 1 team

## Difficulty dimensions

| Dimension | Value (1–5) | Basis in this proposal |
| --- | --- | --- |
| D1 Data work | 4 | Annotated sample of AI-generated explanations (to collect). |
| D2 Compute and infrastructure | 3 | Multimodal models with 4–6 reasoning/verification strategies. |
| D3 Technical depth | 3 | Chain-of-Thought, Program-of-Thought, self-consistency and verification pipelines. |
| D4 Methodological demands | 3 | 3 of 6 elements: human annotation of hallucinations, ≥4 approaches compared, analysis of hallucination patterns. |
| D5 External dependencies and risks | 1 | 1 stated dependency: dataset licences (datasets are not named in the proposal). |
| Total | 14 | Hard |
