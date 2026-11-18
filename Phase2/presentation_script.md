# Right Answer, Wrong Reason: Hallucinations in AI Explanations
## Mid-term Presentation Script (target: 10:00)

**Speaking pace:** about 140 words per minute. Spoken text is in plain paragraphs. Slide cues are in *[brackets]*. Timings are cumulative targets.

---

## Slide 1: Title and team (0:00 - 0:20)

*[Slide: title, four team members, supervisor, Warsaw University of Technology, NLP course Winter 2026/27]*

Hello everyone. We are presenting our NLP project, "Right Answer, Wrong Reason: Hallucinations in AI Explanations". Today we'll cover the research problem, the state of the art, our methodology, the proof-of-concept we've run so far, our preliminary findings, and our next steps.

---

## Slide 2: Research problem (0:20 - 1:35)

*[Slide: a chart with a question. Two outputs below it: "Final answer: correct ✔" and "Explanation: contains a wrong value ✘"]*

Language and vision-language models can answer questions about charts, and they usually explain how they got there. But a correct final answer doesn't guarantee a correct explanation. A model can pick the right bar or the right year while describing a value that isn't in the chart, attaching a label to the wrong bar, or doing arithmetic that doesn't support its own conclusion.

This matters most for scientific charts and numerical data, where we need to trust both the result and the evidence behind it. If we only score the final answer, these errors stay invisible.

*[Slide: two research questions]*

So we ask two questions.

**RQ1, detection:** can we detect hallucinated or unsupported claims in chart explanations, even when the final answer is correct? We'll measure this by comparing an automatic judge against human annotation.

**RQ2, reduction:** do different prompting and verification strategies reduce these errors? And does more elaborate reasoning actually help, or does it sometimes introduce new errors?

One point on scope. We treat generated explanations and reasoning traces as text to be verified. We make no claim about how the model actually reasons internally.

---

## Slide 3: State of the art (1:35 - 3:05)

*[Slide: three closest studies, then three themes]*

We reviewed fifteen studies. Three are closest to our work.

**ChartQA-X** provides about thirty thousand chart question-answer pairs with natural-language explanations. It gives us explanation examples and a generation baseline.

**ChartHal** studies hallucination in chart understanding with about a thousand human-validated cases, including questions about irrelevant, nonexistent or contradictory chart information. It's a hard benchmark: GPT-5 reaches only about 34 percent accuracy on it.

**FaithChart** directly asks whether chart explanations are grounded in the visual evidence. Its central message is that a correct answer alone is not sufficient evidence of a well-grounded explanation. That is exactly our motivation.

*[Slide: themes]*

The remaining work falls into three groups.

*Chart benchmarks*: ChartQA, ChartQAPro and CharXiv. These mostly evaluate final answers, not explanation quality. On CharXiv reasoning questions, GPT-4o scores 47 percent versus 80 percent for humans.

*Separating chart reading from computation*: DePlot turns charts into tables, TinyChart generates programs, and Faithful Chain-of-Thought uses a deterministic solver.

*Reasoning and verification*: chain-of-thought, self-consistency, Chain-of-Verification, and Turpin and colleagues' finding that plausible explanations can omit what actually influenced the model.

Existing work either scores answers or scores whole explanations. Few studies look at individual claims in an explanation, and almost none compare prompting strategies on that basis. That is the gap we target.

---

## Slide 4: Proposed methodology (3:05 - 5:05)

*[Slide: pipeline figure. Charts, then Qwen and Gemma, then outputs, then manual verification (small set) and LLM-as-a-judge (large set), then analysis]*

Our pipeline has three parts.

**First, models.** We use two small, open-weight multimodal models that run locally: Qwen3.5-9B and Gemma-4-E4B. We chose open-weight models because they give us full control over versions and settings, which helps reproducibility, and because they return their reasoning traces, so we can check those too.

**Second, strategies.** *[Slide: strategy list]* We compare exactly four prompting and verification strategies on the same chart questions:

- **Direct:** answer plus a brief explanation.
- **Structured:** first list the relevant chart evidence, then explain.
- **Chain-of-thought:** step-by-step reasoning, with the evidence for each step and the arithmetic shown.
- **Verification:** a second call that re-reads the chart and checks the draft's claims.

**Third, annotation.** We'll build two evaluation sets. A small, manually annotated set, built from 25 chart-question pairs, with two models and four strategies giving 200 responses. And a larger set of one thousand to ten thousand responses, annotated by a stronger, separate multimodal model acting as an LLM judge.

*[Slide: error categories]*

Annotators label each response for four kinds of errors: incorrect chart readings, invented information, unsupported claims, and calculation errors.

For metrics, we report answer accuracy, the explanation error rate, and the key quantity of this project: the share of correct answers that come with a flawed explanation. We also measure the judge's precision, recall and F1 against human labels, plus runtime and token cost.

---

## Slide 5: Proof-of-concept progress (5:05 - 6:15)

*[Slide: pilot setup. 5 charts, 2 models, 4 strategies, 40 responses]*

For the proof of concept, we ran a pilot on five CharXiv validation charts, sampled with a fixed random seed of 42.

Each chart went through both models under four strategies: direct, structured, chain-of-thought and two-call verification. That gives 40 responses and 25 model calls per model. The system prompts are identical across both models.

We then checked each response against the CharXiv reference answer. Separately, we checked the claims inside both the final explanation and the returned reasoning trace. We flagged a response only for a clear, material contradiction with the chart or with its own calculation.

One important caveat. This pilot audit was done by a single reviewer using an LLM, inside a coding environment. It isn't human annotation, and it isn't validated. It's meant to show which error types occur and to shape the larger design, not to give final numbers.

---

## Slide 6: Preliminary findings (6:15 - 8:15)

*[Slide: accuracy table. Gemma 2/20, Qwen 12/20]*

First, answer accuracy. Gemma matched the reference in 2 of 20 responses, or 10 percent. Qwen matched in 12 of 20, or 60 percent. So 14 responses had a correct final answer.

Two things stand out. No model answered chart four correctly under any strategy. And verification did not improve the total over direct prompting for either model, even though it doubles the number of calls.

*[Slide: the right-answer-wrong-reason result. 3 of 14, 21%]*

Now the core question. Among those 14 correct responses, **at least 3, or 21 percent, contained a clearly contradicted claim** in the explanation or in the returned reasoning. This is a lower bound, not a final hallucination rate, because a single reviewer checked only for clear contradictions.

*[Slide: three examples]*

Here are the three cases.

**One: Gemma with verification, chart one.** The final answer, 1905, was correct. But the reasoning trace said 1905 starts *above* 1885, when it starts below. It invented starting values, and its own calculation gave equal slopes, which doesn't support either year. It then accepted the draft anyway. This is a reading error plus an inconsistency between answer and reasoning.

**Two: Qwen with structured prompting, chart two.** The answer, size 5, was correct. But the explanation attached the label 0.7 to the wrong bar. The evidence list format gave a right answer with an invented supporting label.

**Three: Gemma with direct prompting, chart five.** The answer, 0.06, was correct. But the explanation put the competing line at about 0.38 when it's around 0.3, exaggerating the gap.

In all three cases, scoring only the final answer would have hidden the problem.

*[Slide: strategy table, showing correct-but-flawed per strategy]*

By strategy: direct 1 of 4, structured 1 of 2, verification 1 of 4, and chain-of-thought 0 of 4. Chain-of-thought had no flagged cases here. However, 14 correct responses is too little to formulate any conclusions.

---

## Slide 7: Next steps (8:15 - 10:00)

*[Slide: next steps overview. Annotation, judge validation, scale-up, analysis]*

Our pilot shows the phenomenon exists, but five charts can't support firm conclusions. Our next steps are about turning it into a rigorous study.

*[Slide: next steps list]*

**One: complete the human-annotated set.** We'll extend the pilot to 25 chart-question pairs, with two models and four strategies, giving 200 responses. All four team members annotate them.

**Two: a proper annotation protocol.** We'll define the unit of annotation, most likely the atomic claim, following FActScore. We'll write a codebook with definitions and examples for our four error types. We'll measure inter-annotator agreement with Cohen's kappa or Krippendorff's alpha on an overlapping subset, with adjudication of disagreements.

**Three: validate the LLM judge before scaling.** We'll fix the judge model, version and prompt, and set an acceptance threshold, such as a minimum F1 or kappa against the human labels. Only after the judge passes does it annotate the large set of one thousand to ten thousand responses.

**Four: analysis.** We'll define the hallucination rate precisely and compare the four strategies on answer accuracy, explanation errors and computational cost. We'll look for common hallucination patterns and test whether extra reasoning steps help or introduce new errors.

*[Slide: closing]*

To summarize: even in a small pilot, correct answers often came with unsupported explanations, and extra reasoning steps did not reliably fix that. Our goal now is to measure this rigorously, with validated human annotation, a validated judge, and honest uncertainty estimates.

Thank you for watching.

