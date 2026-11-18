# CharXiv pilot: answers and chart-grounded reasoning

**Research question:** How often does a model give the reference answer while its explanation or returned reasoning makes a false or unsupported claim about the chart?

## Results analysis

### Matched setup and prompts

This pilot compares [Gemma](../outputs/prompt_strategies/gemma_v2.json) (`google/gemma-4-e4b`) and [Qwen](../outputs/prompt_strategies/strategies_test_qwen.json) (`qwen/qwen3.5-9b`) on the **same five CharXiv validation charts** sampled with seed 42. Each chart received direct, structured, chain-of-thought, and two-call verification treatments from each model. The stored prompts, including the verification draft prompt, are identical across the two runs.

These are the **full system prompts** saved in both result files. Verification uses its draft prompt first, then sends the draft response and chart to a second call with the check prompt.

**Direct**

> Answer the question using only the attached chart. Do not invent chart labels, values, or units. For comparisons, inspect the relevant series over the same range; for slopes, compare their vertical changes between two visible x-values rather than relying only on whether the lines look parallel. When the chart is readable, choose the best-supported candidate even if the difference is small, and express any uncertainty in the explanation. Say that the answer cannot be determined only when the relevant chart evidence is absent or unreadable. Give a brief explanation based on the chart, followed by a line beginning 'Final answer:'.

**Structured**

> Answer the question using only the attached chart. Do not invent chart labels, values, or units. For comparisons, inspect the relevant series over the same range; for slopes, compare their vertical changes between two visible x-values rather than relying only on whether the lines look parallel. When the chart is readable, choose the best-supported candidate even if the difference is small, and express any uncertainty in the explanation. Say that the answer cannot be determined only when the relevant chart evidence is absent or unreadable. First write 'Chart evidence:' and list only the chart labels, values, units, and comparisons needed for this question. Then write 'Explanation:' connecting that evidence to your answer. Finish with a line beginning 'Final answer:'.

**Chain-of-thought**

> Answer the question using only the attached chart. Do not invent chart labels, values, or units. For comparisons, inspect the relevant series over the same range; for slopes, compare their vertical changes between two visible x-values rather than relying only on whether the lines look parallel. When the chart is readable, choose the best-supported candidate even if the difference is small, and express any uncertainty in the explanation. Say that the answer cannot be determined only when the relevant chart evidence is absent or unreadable. Explain the sequence of chart-reading and calculation steps that supports your answer. State which visible chart evidence supports each step, and show any arithmetic. Finish with a line beginning 'Final answer:'.

**Verification draft**

> Answer the question using only the attached chart. Do not invent chart labels, values, or units. For comparisons, inspect the relevant series over the same range; for slopes, compare their vertical changes between two visible x-values rather than relying only on whether the lines look parallel. When the chart is readable, choose the best-supported candidate even if the difference is small, and express any uncertainty in the explanation. Say that the answer cannot be determined only when the relevant chart evidence is absent or unreadable. Draft an answer with a brief chart-based explanation and a line beginning 'Final answer:'. This draft will be checked in a second pass.

**Verification check**

> Answer the question using only the attached chart. Do not invent chart labels, values, or units. For comparisons, inspect the relevant series over the same range; for slopes, compare their vertical changes between two visible x-values rather than relying only on whether the lines look parallel. When the chart is readable, choose the best-supported candidate even if the difference is small, and express any uncertainty in the explanation. Say that the answer cannot be determined only when the relevant chart evidence is absent or unreadable. You are checking a fallible draft response. Re-read the chart and check every material claim in the draft, including labels, values, units, comparisons, and arithmetic. If the draft abstains, check whether the chart still supports a best answer. Correct unsupported claims. Write 'Checks:' with the evidence you verified, then 'Explanation:' and a line beginning 'Final answer:'.

### Disclaimer
This is a pilot annotation conducted by GPT-6.1-sol inside codex environment. The five charts are a small sample of the CharXiv validation set, and the results are not statistically representative. The pilot is intended to illustrate the types of reasoning errors that can occur in chart-grounded explanations, and to inform the design of larger-scale experiments.


### Reference-answer matches

An **answer match** means the response's `Final answer:` agrees with the CharXiv reference after trivial normalization such as `h=0.06` versus `0.06`. Abstentions, extra incorrect options, and other numbers count as mismatches.

| Strategy | Gemma | Qwen | Calls per chart |
| --- | ---: | ---: | ---: |
| Direct | 1/5 | 3/5 | 1 |
| Structured | 0/5 | 2/5 | 1 |
| Chain-of-thought | 0/5 | 4/5 | 1 |
| Verification | 1/5 | 3/5 | 2 |
| **Total** | **2/20 (10%)** | **12/20 (60%)** | **25 per model** |

The answers by chart show where those totals come from. Within each model, the order is **direct / structured / chain-of-thought / verification**.

| Chart and reference | Gemma answers | Qwen answers |
| --- | --- | --- |
| [1: women's slope](../outputs/prompt_strategies/images/001_1524.jpg): **1905** | abstain / abstain / abstain / 1905 | 1905 / 1905 / 1905 / 1905 |
| [2: MSRC-21 bars](../outputs/prompt_strategies/images/002_270.jpg): **5** | 3, 4, 5 / 3, 4 / 3, 4, 5 / 4 | 5 / 5 / 5 / 5 |
| [3: cooperation heatmap](../outputs/prompt_strategies/images/003_56.jpg): **2** | 0 / 5 / 5 / 5 | 3 / 3 / 2 / 2 |
| [4: selection-strength groups](../outputs/prompt_strategies/images/004_1773.jpg): **2** | 0 / 6 / 6 / 6 | 6 / 6 / 6 / 6 |
| [5: density error](../outputs/prompt_strategies/images/005_640.jpg): **0.06** | 0.06 / 0.05 / 0.05 / 0.07 | 0.06 / 0.05 / 0.06 / 0.05 |

Qwen matched more references on this five-chart set, especially on charts 1 and 2. No model answered chart 4 correctly under any strategy. Verification did not improve the total over direct prompting for either model, despite doubling calls for that strategy. 

## Reasoning analysis

### Right answer, wrong reason

Answer correctness and explanation support are separate outcomes. We checked chart claims in both `model_answer` (the final answer plus explanation) and `model_reasoning` (the separate resoning traces returned by models). A response is flagged here only for a **clear material contradiction** with the saved chart or with its own calculation. Small visual approximations and the subjective boundary in chart 3 are not automatically counted as errors. 

Among the **14 reference-matching responses**, at least **2** have a contradicted claim in the final explanation, at least **3** have one in returned reasoning, and **3 distinct responses** have one in either field: **at least 3/14 (21%)**. These are confirmed examples and a lower bound, not a fully adjudicated hallucination rate.

The counts below show **reference-correct responses with at least one confirmed contradiction in either field / all reference-correct responses**. A zero means this single-reviewer audit did not identify a clear contradiction; it does not certify the explanation as fully supported.

| Strategy | Gemma | Qwen | Combined |
| --- | ---: | ---: | ---: |
| Direct | 1/1 | 0/3 | 1/4 |
| Structured | 0/0 | 1/2 | 1/2 |
| Chain-of-thought | 0/0 | 0/4 | 0/4 |
| Verification | 1/1 | 0/3 | 1/4 |
| **Total** | **2/2** | **1/12** | **3/14** |

Detailed examples of the **3 reference-correct responses with contradicted claims** are shown below.

| Reference-correct response | What the chart supports | False or unsupported reasoning claim | Location |
| --- | --- | --- | --- |
| **Gemma, verification, [chart 1](../outputs/prompt_strategies/images/001_1524.jpg): 1905** | In the lower-left women's panel, the 1905 line starts **below** the 1885 line near age 60 and approaches it near age 100. It therefore rises farther over the same interval. | The returned trace says 1905 starts **above** 1885, gives invented starting values near `-3.8` and `-4.2`, and calculates **equal** endpoint slopes of `0.11` before accepting the draft's 1905 answer. The final explanation omits those false numbers. This is a visual-reading error plus an answer–step inconsistency. | Returned reasoning |
| **Qwen, structured, [chart 2](../outputs/prompt_strategies/images/002_270.jpg): 5** | In panel (c), the gray MSRC-21 size-5 bar is **unlabeled** and near 1.0; the blue size-5 bar is labeled **1.1**. The **0.7** label belongs to the blue size-4 bar. Thus size 5 still satisfies gray < blue. | The final explanation and trace both say the gray size-5 bar is **labeled 0.7**. The answer is right, but a value and label are attached to the wrong bar. | Final explanation and returned reasoning |
| **Gemma, direct, [chart 5](../outputs/prompt_strategies/images/005_640.jpg): 0.06** | The green solid line (`h=0.06`) is the reference choice at 25 s; the yellow/orange `h=0.05` solid line is in the roughly 0.3 region there. | The final explanation and trace both put the yellow/orange line at **0.38–0.39** at 25 s. This exaggerates the gap from the selected green line. | Final explanation and returned reasoning |

The chart-1 verifier is particularly instructive: a correct final year followed a draft despite a returned calculation that did **not** support choosing either year. The chart-2 structured response shows that an evidence-list format can give a correct final size while inventing a supporting label. The chart-5 direct response shows a correct selected series supported by a materially wrong estimate for a competitor. In each case, scoring only the final answer would hide the error.


