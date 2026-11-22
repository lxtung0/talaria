---
status: accepted
---

# Silver base corrects a Facility's state from the pincode directory

Silver base was meant never to take a value from another column or table, but a state that conflicts with its PIN is usually a plain mistake (Hyderabad written as Andhra Pradesh on a Telangana PIN), and leaving every one to Silver facilities would push easy, objective fixes past Silver base. So, for `address_state` only (decided with the user on 2026-11-21, #9), Silver base checks each Facility's official state against the India Post pincode directory. When the state conflicts with its PIN's states, and the city's single directory state is one of the PIN's states, the city and PIN agree against the written state: `address_state` becomes the city's state and `flag_state_corrected` is set.

The other outcomes keep the written state and only flag it, for Silver facilities to resolve:

- `flag_pin_mismatch`: the city agrees with the written state, so the PIN is the wrong value.
- `flag_address_conflict`: the city cannot settle it (border areas such as NCR, the Chandigarh tri-city or Puducherry's enclaves, or a city too vague to break the tie).
- `flag_pin_unverified`: a 6-digit PIN that is not in the directory, or only under `NA`.

## Consequences

- This is a correction, not an Inferred value: it only replaces a state the source wrote, when two other source values agree against it. A missing or unofficial state is never checked or filled (filling stays in Silver facilities or Gold), and the PIN is never changed.
- Coordinates are not used, because they appear to be geocoded from the PIN and so are not independent evidence.
- `build_silver_base` takes the bronze pincode directory as a second input.
