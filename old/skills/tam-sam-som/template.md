# TAM/SAM/SOM model layout

The builder produces a workbook with two sheets.

## Sheet: Assumptions

| key            | value   | note                                        |
| -------------- | ------- | ------------------------------------------- |
| target_entities| 50000   | # of addressable buyers (bottom-up count)   |
| acv_usd        | 24000   | annual contract value per buyer (USD)       |
| sam_fraction   | 0.20    | serviceable share of TAM (segment/geo/chan) |
| som_fraction   | 0.01    | obtainable share of SAM in ~3 years         |

## Sheet: Sizing

| metric | formula                       |
| ------ | ----------------------------- |
| TAM    | target_entities × acv_usd     |
| SAM    | TAM × sam_fraction            |
| SOM    | SAM × som_fraction            |

Every figure traces to an editable assumption — change the assumption, the
sizing recomputes. That traceability is the point: it makes the model
pressure-testable instead of a single hand-waved number.
