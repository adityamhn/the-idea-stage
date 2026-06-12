# TAM / SAM / SOM sizing

Top-down sizing ("1% of a $50B market") is how founders fool themselves. Build
bottom-up and write every assumption down so it can be attacked.

## Method

1. **Bottom-up TAM.** `# of target entities × annual contract value (ACV)`.
   State both numbers and where each came from.
2. **SAM.** The slice you can actually serve (geography, segment, channel).
3. **SOM.** A realistic 3-year obtainable share given GTM reality, not hope.
4. **List every assumption** (entity count, ACV, penetration, churn) in
   `key_assumptions`. Each is a line a critic can pull.
5. **Label the market** expanding / consolidating / mature — it changes timing.

## Output discipline

Report `tam_usd`, `sam_usd`, `som_usd` as concrete USD/year figures and put the
derivation in `method`. Never report a number you cannot trace back to an entity
count and an ACV.

**Cite everything.** Attach real sources (URL + title + quote) for the entity
count, the ACV, and any market figure you pulled from the web. A number without a
source or a stated assumption behind it does not belong in the model. Never invent
a URL.
