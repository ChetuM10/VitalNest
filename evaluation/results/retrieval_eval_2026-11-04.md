# Retrieval evaluation, 2026-11-04

15 questions; corpus 2827 chunks / 1,017 MedlinePlus pages. Hit@k = first expected page within the top k chunks; the chat pipeline sends the top 6 to Claude.

| Configuration | Hit@1 | Hit@3 | Hit@6 | Hit@20 | MRR | Facts in top 6 |
|---|---|---|---|---|---|---|
| bm25 (current) | 47% | 73% | 80% | 100% | 0.623 | 97% |
| bm25 (stop words removed) | 53% | 93% | 93% | 93% | 0.711 | 98% |
| dense (Pinecone) | 93% | 100% | 100% | 100% | 0.967 | 100% |
| RRF  current bm25 + dense, k=60  [shipped] | 80% | 100% | 100% | 100% | 0.889 | 100% |
| RRF  stop-word bm25 + dense, k=60 | 73% | 100% | 100% | 100% | 0.856 | 100% |
| RRF  current bm25 + dense, k=10 | 80% | 100% | 100% | 100% | 0.889 | 100% |
| RRF  stop-word bm25 + dense, pool 10 | 73% | 100% | 100% | 100% | 0.856 | 100% |

## Per question, shipped configuration (rank of the first expected page; top titles retrieved)

| # | Question | Rank | Top retrieved pages |
|---|---|---|---|
| q01 | What are the early warning signs of a stroke? | 2 | Transient Ischemic Attack, Stroke, Stroke, Hemorrhagic Stroke |
| q02 | How can I lower my blood pressure without medicine? | 1 | High Blood Pressure, How to Prevent High Blood Pressure, Blood Pressure Medicines, How to Prevent High Blood Pressure |
| q03 | What causes type 2 diabetes and who is at risk? | 1 | Diabetes Type 2, How to Prevent Diabetes, Diabetes Type 2, Diabetes |
| q04 | How do doctors diagnose sleep apnea? | 1 | Sleep Apnea, Sleep Apnea, Sleep Disorders, Sleep Disorders |
| q05 | What helps with migraine headaches? | 1 | Migraine, Migraine, Migraine, Migraine |
| q06 | Why do I get dizzy when I stand up too fast? | 3 | Fainting, Vascular Diseases, Dizziness and Vertigo, Health Risks of an Inactive Lifestyle |
| q07 | What foods have a lot of iron? | 1 | Iron, Iron, Iron, Anemia |
| q08 | How can I prevent osteoporosis? | 2 | Bone Density, Osteoporosis, Osteoporosis, Osteoporosis |
| q09 | What are the symptoms of a urinary tract infection? | 1 | Urinary Tract Infections, Urinary Incontinence, Prostate Diseases, Ureteral Disorders |
| q10 | How do I know if I have a food allergy? | 1 | Food Allergy, Food Allergy, Food Allergy, Food Allergy |
| q11 | What is the difference between HDL and LDL cholesterol? | 1 | HDL: The "Good" Cholesterol, LDL: The "Bad" Cholesterol, Cholesterol Levels: What You Need to Know, Cholesterol |
| q12 | What are common signs of depression? | 1 | Depression, Depression, Seasonal Affective Disorder, Depression |
| q13 | How do I treat a minor burn at home? | 1 | Burns, Hemorrhoids, Burns, Cold and Cough Medicines |
| q14 | Is the flu shot safe for pregnant women? | 1 | Flu Shot, Flu Shot, Flu Shot, Flu Shot |
| q15 | What causes heartburn and how can I stop it? | 1 | Heartburn, Stomach Disorders, Heart Attack, Pregnancy and Medicines |

## Questions where the expected page is not in the top 6

- bm25 (current): q01
- bm25 (current): q06
- bm25 (current): q13
- bm25 (stop words removed): q01

## No-context threshold (best Pinecone cosine score)

- Answerable questions: lowest best-score 0.853, mean 0.878
- Unanswerable questions: highest best-score 0.838, mean 0.776
- Cleanly separable by one cutoff: True; suggested cutoff 0.845
- Shipped cutoff 0.84: wrongly refuses 0 of 15 answerable, wrongly answers 0 of 10 unanswerable

Unanswerable questions, best score and page:

- 0.776  Nutrition  <- How do I bake sourdough bread?
- 0.737  COVID-19 (Coronavirus Disease 2019)  <- Who won the football world cup in 2018?
- 0.724  Heart Surgery  <- What is the capital of France?
- 0.776  Tick Bites  <- How do I fix a flat bicycle tyre?
- 0.802  Vaccines  <- Explain how a blockchain works
- 0.760  Radiation Exposure  <- What is the best smartphone to buy?
- 0.838  Vaccines  <- What is the dog vaccination schedule?
- 0.811  Exercise and Physical Fitness  <- How do I train for a marathon?
- 0.788  Water Pollution  <- How do I change the oil in my car?
- 0.752  Body Weight  <- What is the weather forecast for Paris tomorrow?
