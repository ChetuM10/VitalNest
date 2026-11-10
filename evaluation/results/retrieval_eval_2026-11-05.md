# Retrieval evaluation, 2026-11-05

15 questions; corpus 6667 chunks / 1611 pages (CDC 1907 chunks, MedlinePlus 2827 chunks, WHO 1933 chunks). Hit@k = first expected page within the top k chunks; the chat pipeline sends the top 6 to Claude.

| Configuration | Hit@1 | Hit@3 | Hit@6 | Hit@20 | MRR | Facts in top 6 |
|---|---|---|---|---|---|---|
| bm25 (current) | 47% | 60% | 87% | 100% | 0.592 | 93% |
| bm25 (stop words removed) | 40% | 80% | 93% | 93% | 0.591 | 97% |
| dense (Pinecone) | 80% | 100% | 100% | 100% | 0.900 | 100% |
| RRF  current bm25 + dense, k=60  [shipped] | 60% | 87% | 100% | 100% | 0.739 | 100% |
| RRF  stop-word bm25 + dense, k=60 | 60% | 87% | 100% | 100% | 0.741 | 100% |
| RRF  current bm25 + dense, k=10 | 60% | 87% | 100% | 100% | 0.739 | 100% |
| RRF  stop-word bm25 + dense, pool 10 | 60% | 93% | 100% | 100% | 0.750 | 100% |

## Per question, shipped configuration (rank of the first expected page; top titles retrieved)

| # | Question | Rank | Top retrieved pages |
|---|---|---|---|
| q01 | What are the early warning signs of a stroke? | 6 | Signs and Symptoms of Stroke, Transient Ischemic Attack, About Stroke, Signs and Symptoms of Stroke |
| q02 | How can I lower my blood pressure without medicine? | 2 | Managing High Blood Pressure, How to Prevent High Blood Pressure, High Blood Pressure, Blood Pressure Medicines |
| q03 | What causes type 2 diabetes and who is at risk? | 1 | Diabetes Type 2, How to Prevent Diabetes, Type 2 Diabetes, Diabetes Type 2 |
| q04 | How do doctors diagnose sleep apnea? | 1 | Sleep Apnea, Sleep Apnea, Sleep Disorders, About Sleep |
| q05 | What helps with migraine headaches? | 4 | Migraine and other headache disorders, Migraine and other headache disorders, Migraine and other headache disorders, Migraine |
| q06 | Why do I get dizzy when I stand up too fast? | 3 | Vascular Diseases, Fainting, Dizziness and Vertigo, Health Risks of an Inactive Lifestyle |
| q07 | What foods have a lot of iron? | 1 | Iron, Iron, Anaemia, Healthy diet |
| q08 | How can I prevent osteoporosis? | 2 | Bone Density, Osteoporosis, Osteoporosis, Osteoporosis |
| q09 | What are the symptoms of a urinary tract infection? | 3 | Urinary Tract Infection Basics, Urinary Tract Infection Basics, Urinary Tract Infections, Urinary Tract Infection Basics |
| q10 | How do I know if I have a food allergy? | 1 | Food Allergy, Food Allergy, Food Allergy, Food Allergy |
| q11 | What is the difference between HDL and LDL cholesterol? | 1 | HDL: The "Good" Cholesterol, LDL: The "Bad" Cholesterol, Cholesterol Levels: What You Need to Know, Testing for Cholesterol |
| q12 | What are common signs of depression? | 1 | Depression, Depressive disorder (depression), Depression, Depression |
| q13 | How do I treat a minor burn at home? | 1 | Burns, Burns, How to Treat Chickenpox, Burns |
| q14 | Is the flu shot safe for pregnant women? | 1 | Flu Shot, Flu Shot, Flu Shot, Flu Shot |
| q15 | What causes heartburn and how can I stop it? | 1 | Heartburn, GERD, Pregnancy and Medicines, Safe Opioid Use |

## Questions where the expected page is not in the top 6

- bm25 (current): q01
- bm25 (current): q02
- bm25 (stop words removed): q01

## No-context threshold (best Pinecone cosine score)

- Answerable questions: lowest best-score 0.854, mean 0.879
- Unanswerable questions: highest best-score 0.838, mean 0.783
- Cleanly separable by one cutoff: True; suggested cutoff 0.846
- Shipped cutoff 0.845: wrongly refuses 0 of 15 answerable, wrongly answers 0 of 10 unanswerable

Unanswerable questions, best score and page:

- 0.789  Controlling the Emergence and Spread of Antimicrobial Resistance  <- How do I bake sourdough bread?
- 0.747  Malaria  <- Who won the football world cup in 2018?
- 0.741  Diagnosis for Flu  <- What is the capital of France?
- 0.776  Tick Bites  <- How do I fix a flat bicycle tyre?
- 0.802  Vaccines  <- Explain how a blockchain works
- 0.767  Diagnosis for Flu  <- What is the best smartphone to buy?
- 0.838  Vaccines  <- What is the dog vaccination schedule?
- 0.811  Exercise and Physical Fitness  <- How do I train for a marathon?
- 0.788  Water Pollution  <- How do I change the oil in my car?
- 0.775  Heat and health  <- What is the weather forecast for Paris tomorrow?
