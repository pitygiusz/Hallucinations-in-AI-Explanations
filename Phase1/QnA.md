### Q: At 7:46 you say no model answered Chart 4 correctly under any strategy. Do you know why? Is the chart just very hard, is the question unclear or sth else?

A: We can’t identify a definite cause from this five-chart pilot. Chart 4 is a dense scatter plot: 
![Chart 4](../outputs/images/004_1773.jpg)
and the question is. "In subplot (b), under how many selection strength groups does the point with the highest log_K value also exhibit the highest slope value?"

The correct answer is 2 (10^-2 and 10^-1). The question is difficult because answering requires comparing two maxima—log K (shown by color) and slope—within each of six selection-strength groups. Both models answered “6” under every strategy, suggesting they may have relied on the overall color pattern rather than checking each group’s maxima. We should treat chart difficulty, question clarity, and model strategy as possible explanations, not established causes.

---

### Q: Which chart dataset(s) do you plan to sample the 25 human-annotated and 1,000–10,000 judge-evaluated chart-question pairs from?

A: The pilot uses five reasoning questions from the **CharXiv validation** split. The dataset proved to be challenging for the models. We are yet to decide wheather we want to also include easier charts for our analysis. 

---

### Q: Do you plan to analyze whether certain chart types, such as line plots versus bar charts, lead to more explanation hallucinations than others?

A: This is an interesting question and we might include it in our LLM-as-a-judge analysis, which can label each experiment as “line plot,” “bar chart,” etc. 

---

### Q: Your main metric measures flawed explanations among correct answers. In the pilot, Gemma-4-E4B only answered 10% of questions correctly, which gives you almost no valid samples to compare prompting strategies and makes it unclear if these errors also occur for larger models. How do you plan to address this?

A: We plan to address it in two ways. First, our large scale experiments will use more precise version of both models (16bit vs 4bit quantization used in test run), which might improve accuracy. Second, with much larger sample sizes, we should have enough correct answers to compare explanation quality across strategies. 

---

### Q: You check claims in both the reasoning trace and the final explanation. A wrong value in an exploratory trace that the model later corrects is not the same as a wrong value in the explanation shown to the user. Will you report the two separately? Gemma and Qwen may also return traces of very different length, so a strategy with longer traces simply has more text where an error can be found.

A: In the first experiments we capped the maximum number of generated tokens to 1536, which is both for resoning and the final explanation, none of the models hit the limit.

In later experiment with Gemma covering 500 charts 58 of them hit the limit, which is 11.6% of the total. Thet indicates that we probably should increase the limit. We will label the limited responses in the final analysis.

---


### Q: before scaling up to 1,000 - 10,000 resposes. Will you fix the exact threshold in advance, before seeing the judge's results, and what value are you considering? And what is the fallback if all judges fail it?

A: ???

---

### Q: Step-by-step prompts can produce more claims than direct prompts, so they have more chances to make at least one mistake. Would you report the fraction of individual claims that are incorrect or unsupported alongside the fraction of responses with any error?

A: This is an interesting question and we might include it in our LLM-as-a-judge analysis, which can count the number of incorrect claims per response and report the average number of errors per response, in addition to the overall error rate. This would help account for differences in explanation length and provide a more granular view of hallucination frequency.

---

### Q: Your main metric looks at flawed explanations among correct answers. Since different prompts may get different chart questions right, would you also compare explanations on the same questions where both prompts gave the correct answer for the same model?


A: This is a good idea. We will compare strategies on the same chart-question pairs and report a paired analysis restricted to questions where both strategies answered correctly for that model. That comparison addresses whether explanation quality differs on shared successes.

---


### Q: Why do you think verification did not improve the results?


A: The pilot does not establish why. One possibility is that the verifier used the same model and chart, so it shared the draft’s visual-reading limitations and could confirm an incorrect interpretation instead of catching it. The pilot also contains only five charts, so small differences are not reliable evidence of an effect. 

---

### Q: How will annotators distinguish an acceptable approximation when reading a low-resolution chart from a genuinely invented numerical value, and will they use a predefined tolerance?

A: We will specify the tolerance in advance, based on the chart’s readable scale and resolution.


---

### Q: At 5:28 you plan to use a stronger multimodal LLM judge to detect incorrect chart readings across 1,000–10,000 responses. Will the judge receive the underlying chart data tables, or will it rely only on the raw images where frontier models still struggle?

A: Our experiments were based on CharXiv charts, which do not have underlying data tables. We will rely on the raw images. The judge will be a stronger multimodal LLM that can handle visual reasoning, but we acknowledge that it may still struggle with certain chart types or low-resolution images. We will evaluate its performance and consider additional strategies if necessary.

---

### Q: Besides validating the judge against human labels, if your charts come with underlying data tables, could you check the numbers in the explanations against them? That wouldn't depend on a vision model reading the pixels.

A: If we have access to underlying data tables, we will include a numerical validation step to check the explanations against the actual data. 


---

### Q: On the findings slide you report 3 of 14 correct answers flagged, but two of the three cases are Gemma, and Gemma had only 2 correct answers in total, so it is 2/2 for Gemma and 1/12 for Qwen. Does the "right answer, wrong reason" effect still show up for the stronger model? How do you interpret the performance of chain-of-thought strategy in this context?


This was only a pilot with five charts, so we cannot draw strong conclusions. Based on first tests with state-of-the-art models, we observed very good quality of answers.


