---
status: proposed
---

# Gold confidence score: tiers, points and caps

Gold has to turn the boolean flags from Silver into one trust score per Facility that a community health worker can read, and the app (#26) has to explain it. Not all flags are equal: a PIN that isn't in the India Post directory says more than a page date that can't be read. A plain sum of equal penalties hides that difference. A weighted average hides the reasons.

So every scored flag gets a **tier**, and the score is built in points (0–100) from a start value:

| Tier | Points | Cap | Meaning |
|---|---|---|---|
| critical | −20 | 55 | the location or address is wrong, or nothing backs the record |
| major | −10 | 75 | the record contradicts itself, but the Facility likely exists |
| minor | −3 | 90 | a format problem, a value already fixed, or an incomplete record |
| positive | +10 | — | evidence that raises trust |

- **Start at 80, not 100.** False means "not found", never "checked and fine" (#13). A Facility with no problems found but no positive evidence scores 80; only a government source or its own website lifts it to 100.
- **The worst tier present caps the score.** Positive evidence can't cover a real problem: a Facility with a major problem never scores above 75, whatever its sources. Caps sit just above "start plus one penalty" (critical 60 → 55, major 70 → 75), so scores still spread within a tier by the number of problems and the evidence. With caps at 40 and 70, every critical Facility scored exactly 40 and almost every major one exactly 70.
- **The log is the score.** `confidence_reasons` lists the start, one signed line per fired rule and, only when it lowered the score, the cap. Replaying it gives the score, and the runtime checks do exactly that.

Tier assignments (in `talaria/gold/scoring.py`):

- **critical:** coordinates far from the written PIN, no same-region PIN nearby, address conflict, PIN mismatch, PIN not in the directory, no sources. A health worker would be sent to the wrong place, or there is nothing behind the record.
- **major:** description names another state (often a chain's other branches, so not critical), shared coordinates, affiliation vs operator conflict, beds-per-doctor outlier, official phone or website missing from its own list, only directory or social sources (1,400 Facilities: a directory listing doesn't make a Facility fake).
- **minor:** state corrected (already fixed), zero beds (normal for an outpatient clinic), phone list without an official phone, a single source host, unreadable or future page date, Needs investigation (lists cut at 50 items mean too much information, not wrong information).
- **positive:** a government source, the Facility's own website among the sources.

On the Silver facilities export of 2026-11-22 (9,959 Facilities, before the location and own-site fixes): worst tier critical 246, major 1,884, minor 2,835, none 4,994; 28 distinct scores.

## Consequences

- `flag_specialty_unsupported_by_capability` is not scored. Julia's specialty Reference table (ADR 0002) will produce new specialty flags; each becomes one more rule. ADR 0002 says expected items are a **bonus** only, so those rules belong in the positive tier.
- Known flag caveats are inherited: `flag_coords_far_from_written_pin` under-reports and `flag_own_site_in_sources` is generous until branch `fix-location-own-site` lands; `flag_official_website_not_in_list` has one false positive (`["esic.nic.in"]`). Gold needs no change when they are fixed; the scores shift on the next run.
- Changing a weight or a cap is one edit to `TIERS`; moving a flag is one edit to `RULES`. Both change the score of every Facility, so a change goes through a pull request with the new distribution.
