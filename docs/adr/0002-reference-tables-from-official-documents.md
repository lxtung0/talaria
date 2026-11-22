---
status: proposed
---

# Reference tables may be built from official documents

The glossary said the three Virtue Foundation source tables are the only data the project uses. Gold needs to judge whether a Facility's equipment and procedures back up the specialties it claims, for example whether a nephrology Facility lists dialysis machines. The source tables can't say which equipment or procedures a specialty needs, and a list we invented ourselves would make that judgement impossible to defend. The datathon rules require using the provided facility dataset; they don't forbid extra reference material.

So we may build **reference tables**: small, hand-built tables of outside knowledge, such as the equipment and procedures each specialty needs.

- Every row cites the official document and page it came from. Candidates: Indian Public Health Standards (IPHS), NABH standards and WHO medical device lists, each checked before use.
- A reference table is only compared against facility data. It never fills, replaces or corrects a Facility value, so it never creates an Inferred value.
- Reference tables live in the repo as small, reviewable Python data, like the Silver base alias tables.
- Scope is limited to the specialties the project's use cases need.

## Consequences

- Silver facilities can flag which expected items a Facility lists, and Gold can award a **bonus** for them. Missing items are **not penalised**: web-scraped equipment lists are sparse (median 3 items per Facility), so absence of a mention isn't absence of equipment.
- The presentation must name the documents behind each reference table.
- Each reference table needs a review pass, because its keywords decide what matches.
- The source tables stay the only source of facts about Facilities.
