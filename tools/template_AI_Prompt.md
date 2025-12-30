Estimate calories for the meals I list.

Rules:
- Consistency over precision. Use middle-of-the-road assumptions.
- One calorie number per meal (no ranges).
- If cooking oil/sauce is likely but not stated, add 60 kcal.
- If clearly restaurant food, add +15%.
- Return the "Daily Log Block" in the exact schema below.

Schema:
date: YYYY-MM-DD
day_type: normal|travel|holiday|sick|social
source: ai_estimate

meals_text:
  breakfast: |
    <lines>
  lunch: |
    <lines>
  dinner: |
    <lines>
  snacks: |
    <lines>

estimates:
  breakfast_kcal: int
  lunch_kcal: int
  dinner_kcal: int
  snacks_kcal: int
  total_kcal: int
  protein_g: int_or_null

notes: |
  <lines>

Meals:
<PASTE YOUR MEALS HERE>
