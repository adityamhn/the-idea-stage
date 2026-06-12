---
name: hypothesis-sharpening
description: Turn a vague startup idea into ONE testable problem hypothesis. Use when sharpening, scoping, or specifying a problem statement so it names who has it, how often, how severe, and the current workaround.
---

# Hypothesis sharpening

A problem statement that can't say *who / how often / how severe / what they do
today* is not testable. Your job is to force that specificity.

## Method

1. **Strip the solution.** Restate the idea as a *problem*, not a product.
   "People struggle with X" is an observation, not a hypothesis.
2. **Name the sufferer precisely.** Job title + company type + team context +
   seniority. "Finance managers at mid-market (200–1000 employee) SaaS firms",
   not "businesses".
3. **Quantify frequency.** How often do they actually hit this? Daily, per close,
   per contract? Vague cadence = untestable.
4. **Quantify severity.** Time lost, dollars, risk, or pain per occurrence.
5. **Capture the current workaround.** What do they do *today*? If there's no
   workaround, the problem may not be real or not painful enough.
6. **Compose one sentence** in the form:
   *"[WHO] [lose SEVERITY] [at FREQUENCY] because [ROOT CAUSE], so today they
   [WORKAROUND]."*
7. **Self-check.** If any of the four dimensions is still generic, set
   `is_specific = false` and say which.

## Good vs bad

- ❌ "Contract review takes too long."
- ✅ "In-house legal teams at mid-market companies spend 3+ days per contract
  review cycle because redlines live across email threads instead of one
  version-controlled doc, so today they manually diff Word files."
