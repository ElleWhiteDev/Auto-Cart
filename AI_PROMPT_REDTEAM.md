# AI Prompt Red-Team Cases

This document stress-tests the three OpenAI prompt flows in `models.py`:

- `Recipe.clean_ingredients_with_openai`
- `Recipe.parse_ingredients`
- `GroceryList.consolidate_ingredients_with_openai`

Goal: catch drift, malformed output, destructive merges, and ambiguity handling before regressions hit users.

## How To Use

1. Pick a case below.
2. Run the relevant endpoint/flow.
3. Compare actual output to expected behavior.
4. Mark pass/fail and add notes for prompt refinement.

## A. Cleaning Prompt Cases

### C1 - OCR + symbol noise
- Input:
  - `▢ 1/4cuphoney`
  - `✔ 2 T  olive   oil`
- Expected:
  - `1/4 cup honey`
  - `2 tbsp olive oil`
- Fail signs:
  - Symbols remain, merged tokens remain, or unit not normalized.

### C2 - descriptor preservation
- Input:
  - `1 cup finely diced yellow onions`
  - `2 lbs ground beef`
- Expected:
  - descriptors preserved (`finely diced`, `yellow`, `ground`).
- Fail signs:
  - descriptors dropped or over-normalized to generic ingredient names.

### C3 - decimal normalization
- Input:
  - `0.5 cup sugar`
  - `0.25 tsp salt`
- Expected:
  - `1/2 cup sugar`
  - `1/4 tsp salt`
- Fail signs:
  - decimals not converted where exact mapping exists.

### C4 - minimal invention
- Input:
  - `salt to taste`
- Expected:
  - line remains readable without fabricated specifics.
- Fail signs:
  - model invents quantity/unit beyond allowed normalization intent.

## B. Parsing Prompt Cases

### P1 - strict JSON contract
- Input:
  - `2 cups flour`
- Expected:
  - valid JSON array only
  - object keys exactly: `quantity`, `measurement`, `ingredient_name`
- Fail signs:
  - markdown fences, prose, extra keys, invalid JSON.

### P2 - range handling
- Input:
  - `3-4 lb chicken thighs`
- Expected:
  - quantity should be `"3"` (first number rule)
- Fail signs:
  - keeps range string or uses `"4"` or average.

### P3 - mixed fraction handling
- Input:
  - `2 1/2 cups milk`
- Expected:
  - quantity `"2 1/2"` with canonical unit `"cup"`
- Fail signs:
  - quantity collapse to `"2"` or malformed numeric string.

### P4 - unitless ingredient
- Input:
  - `milk`
- Expected:
  - quantity `"1"`, measurement `"unit"`, ingredient `"milk"`
- Fail signs:
  - empty fields or missing default values.

### P5 - descriptor + variant preservation
- Input:
  - `1 tbsp unsalted butter`
  - `1 cup yellow onion, diced`
- Expected:
  - keep `unsalted`, `yellow`, `diced` in `ingredient_name`
- Fail signs:
  - variant adjectives removed.

### P6 - multi-line stability
- Input:
  - several lines including punctuation, blanks, trailing spaces
- Expected:
  - one parsed object per meaningful line
- Fail signs:
  - line drops, duplicates, or cross-line contamination.

## C. Consolidation Prompt Cases

### G1 - aggressive merge of prep variants
- Input lines:
  - `1 cup chopped onion`
  - `1 cup diced onion`
- Expected:
  - merged into one onion line with summed quantity.
- Fail signs:
  - kept separate without clear variant distinction.

### G2 - keep varietal distinctions
- Input lines:
  - `1 cup yellow onion`
  - `1 cup red onion`
- Expected:
  - remain separate.
- Fail signs:
  - merged into generic `onion`.

### G3 - keep butter type distinctions
- Input lines:
  - `1 tbsp salted butter`
  - `1 tbsp unsalted butter`
- Expected:
  - remain separate.
- Fail signs:
  - merged into generic `butter`.

### G4 - always remove water
- Input lines:
  - `2 cup water`
  - `1 cup warm water`
  - `1 cup flour`
- Expected:
  - output includes flour only; no water lines.
- Fail signs:
  - any water line survives.

### G5 - output format contract
- Input:
  - normal ingredient set with duplicates
- Expected:
  - plain text, one line each: `quantity measurement ingredient_name`
- Fail signs:
  - bullets, prose, markdown, malformed lines that parser regex cannot consume.

### G6 - no destructive omission
- Input:
  - 10 distinct non-water items
- Expected:
  - no arbitrary drops.
- Fail signs:
  - unrelated items disappear.

## D. Regression Checklist

- Parsing returns valid JSON 100% of runs for fixed input.
- Consolidation never removes non-water ingredients unless merged into an equivalent retained line.
- Descriptor/variant retention behavior is consistent with shopping intent.
- Outputs remain parseable by current post-processing regex in `consolidate_ingredients_with_openai`.

## E. Known High-Risk Inputs

- Fractions with unicode symbols (`½`, `¼`) and mixed units.
- Parenthetical notes (`(optional)`, `(divided)`).
- Ingredient lines containing commas, semicolons, or slash-separated alternatives.
- Locale variants (`litre`, `gramme`, `tblsp`).
