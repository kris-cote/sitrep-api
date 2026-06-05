# Decision Logic (TRL-4)

## Output
- `GO`
- `HOLD`
- `NO_GO`
- `UNKNOWN` (insufficient data / upstream failure)

## Inputs (current)
- weather status
- NOTAM status
- (optional) satellite freshness

## Rules (starter)
- If either weather or NOTAM is UNKNOWN → HOLD (or UNKNOWN depending on policy)
- If any indicates NO_GO condition → NO_GO
- If both GREEN / acceptable → GO

## Notes
At TRL-4, the emphasis is on:
- explicit rule definitions
- deterministic results for identical inputs
- reproducible test vectors
