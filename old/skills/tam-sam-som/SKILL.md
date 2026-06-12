---
name: tam-sam-som
description: Build a defensible bottom-up TAM/SAM/SOM market-sizing model and pressure-test its assumptions. Use for market sizing, addressable-market estimates, or producing an xlsx sizing model. Ships a deterministic builder script.
---

# TAM / SAM / SOM sizing

Top-down sizing ("1% of a $50B market") is how founders fool themselves. Build
bottom-up and write every assumption down so it can be attacked.

## Method

1. **Bottom-up TAM.** `# of target entities × annual contract value (ACV)`.
   State both numbers and their source.
2. **SAM.** The slice you can actually serve (geography, segment, channel).
3. **SOM.** A realistic 3-year obtainable share given GTM reality, not hope.
4. **List every assumption** (entity count, ACV, penetration, churn). Each is a
   line a critic can pull.
5. **Label the market** expanding / consolidating / mature — it changes timing.

## Deterministic model builder

This skill ships `build_model.py`. Run it to generate the xlsx so the numbers are
reproducible rather than hallucinated:

```bash
python .claude/skills/tam-sam-som/build_model.py \
  --entities 50000 --acv 24000 --sam-frac 0.20 --som-frac 0.01 \
  --out /tmp/tam_model.xlsx
```

It writes a workbook with an `Assumptions` sheet and a `Sizing` sheet (TAM = entities×ACV,
SAM = TAM×sam_frac, SOM = SAM×som_frac) and prints the computed figures as JSON.
Report the path in `model_path` and the figures in the sizing fields. See
`template.md` for the sheet layout. If `openpyxl` is unavailable, the script falls
back to a `.csv` with the same numbers.
