---
status: proposed
---

# Gold confidence score: tiers, points and caps

Gold reads Silver Stage 3 (#35) and has to turn its boolean flags into one trust score per Facility that a community health worker can read, and the app (#26) has to explain it. Not all flags are equal: a PIN that isn't in the India Post directory says more than a page date that can't be read. A plain sum of equal penalties hides that difference. A weighted average hides the reasons.

So every scored flag gets a **tier**, and the score is built in points (0–100) from a start value:

| Tier | Points | Cap | Meaning |
|---|---|---|---|
| critical | −20 | 55 | the location or address is wrong, or nothing backs the record |
| major | −10 | 75 | the record contradicts itself, but the Facility likely exists |
| minor | −3 | 90 | a format problem, a value already fixed, or an incomplete record |
| positive | +10 | — | evidence that raises trust |
| info | 0 | — | missing information: logged for the reader, never scored |

- **Start at 80, not 100.** False means "not found", never "checked and fine" (#13). A Facility with no problems found but no positive evidence scores 80; only a government source or its own website lifts it to 100.
- **The worst tier present caps the score.** Positive evidence can't cover a real problem: a Facility with a major problem never scores above 75, whatever its sources. Caps sit just above "start plus one penalty" (critical 60 → 55, major 70 → 75), so scores still spread within a tier by the number of problems and the evidence. With caps at 40 and 70, every critical Facility scored exactly 40 and almost every major one exactly 70.
- **The log is the score.** `confidence_reasons` lists the start, one signed line per fired rule and, only when it lowered the score, the cap. Replaying it gives the score, and the runtime checks do exactly that.

Tier assignments (in `talaria/gold/scoring.py`):

- **critical:** coordinates far from the written PIN, no same-region PIN nearby, address conflict, PIN mismatch, PIN not in the directory, no sources, procedures from a different field than the specialties (`flag_merge_different`, a likely merge of two records), name vs facility type (`flag_name_facilityType`). A health worker would be sent to the wrong place or the wrong kind of facility, or there is nothing behind the record.
- **major:** description names another state (often a chain's other branches, so not critical), shared coordinates, affiliation vs operator conflict, capacity outlier (`flag_facility_capacity_outlier`, which replaced the beds-per-doctor outlier in Stage 3) unless R0-5 alone fired, high-risk item without a matching specialty (`flag_major_orphan`), specialties without support (`flag_specialty_unsupported`), official phone or website missing from its own list, only directory or social sources (1,400 Facilities: a directory listing doesn't make a Facility fake).
- **minor:** a hospital with exactly 1 doctor and no other capacity rule (R0-5 alone, 449 Facilities: a placeholder value, not a wrong facility), state corrected (already fixed), zero beds (normal for an outpatient clinic), phone list without an official phone, a single source host, unreadable or future page date, Needs investigation (lists cut at 50 items mean too much information, not wrong information).
- **positive:** a government source, the Facility's own website among the sources, a large hospital (`flag_large_hospital`: five or more specialty categories with trusted bed or doctor counts, so the record is consistent).
- **info:** `flag_unverified` (procedure, equipment or capability empty) and `flag_partial` (procedure without its equipment or the reverse). ADR 0002: web-scraped lists are sparse, so absence of a mention isn't absence of a service. They are logged as `0 [info] …` lines.

Veterinary facilities (`is_veterinary`, 16) are left out of both Gold tables: the care finder is for people.

On the Silver facilities export of 2026-11-22 (9,959 Facilities, before the location and own-site fixes and before Stage 3): worst tier critical 246, major 1,884, minor 2,835, none 4,994; 28 distinct scores.

## Consequences

- The Stage 3 consistency flags split along ADR 0002: "information is missing" (C1, C2) is info only; "the listed information contradicts itself" (C3–C5) is penalised.
- The location and own-site fixes (#32) have landed. A known caveat remains: `flag_official_website_not_in_list` has one false positive (`["esic.nic.in"]`). 
- Changing a weight or a cap is one edit to `TIERS`; moving a flag is one edit to `RULES`. Both change the score of every Facility, so a change goes through a pull request with the new distribution.
