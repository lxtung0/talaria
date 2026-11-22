"""Fixed sentences for a Facility's flags (spec #26 Decisions, #28 step 6). Pure functions.

Each true flag maps to one fixed sentence. A false flag says nothing: per spec #13
false can mean "couldn't check", so only the flags phrased positively produce a ✓
line, and only when true.
"""

# Flags phrased positively: true is a good point.
GOOD_FLAGS = {
    "flag_has_government_source": "Listed on a government website",
    "flag_own_site_in_sources": "Its own website is one of our sources",
}

# Flags that put the Facility's location in doubt; any of them makes the distance approximate.
LOCATION_FLAGS = {
    "flag_state_corrected": "the state in its address was corrected from its PIN and city",
    "flag_pin_mismatch": "its PIN belongs to a different state than its address",
    "flag_address_conflict": "its PIN, city and state disagree",
    "flag_pin_unverified": "its PIN isn't in the India Post directory",
    "flag_coords_far_from_written_pin": "its map point is far from its PIN",
    "flag_no_same_prefix_pin_nearby": "no PIN from its postal region is near its map point",
    "flag_coords_shared": "another facility has exactly the same map point",
}

# Every other flag phrased as a problem: true is a warning.
WARNING_FLAGS = {
    "flag_zero_beds": "Lists zero beds",
    "flag_official_phone_not_in_list": "Its official phone isn't in its own phone list, so check the number",
    "flag_phone_list_without_official": "Has phone numbers but no official phone",
    "flag_official_website_not_in_list": "Its official website isn't in its own website list",
    "flag_bed_doctor_ratio_outlier": "Its bed and doctor counts look unusual for its type",
    "flag_specialty_unsupported_by_capability": "Its listed specialties aren't backed up by its described capabilities",
    "flag_desc_mentions_other_state": "Its description names a different state",
    "flag_affiliation_operator_conflict": "Its affiliation and operator (government or private) disagree",
    "flag_only_directory_sources": "Only found on directory or social media sites",
    "flag_single_source_domain": "Only found on one website",
    "flag_page_update_unparsable": "Its page update date can't be read",
    "flag_future_page_update": "Its page update date is in the future",
}

LIST_NAMES = {"specialties": "specialties", "procedure": "procedures", "equipment": "equipment", "capability": "capabilities"}


def location_approximate(facility: dict) -> bool:
    return any(facility.get(flag) is True for flag in LOCATION_FLAGS)


def good_points(facility: dict) -> list[str]:
    return [line for flag, line in GOOD_FLAGS.items() if facility.get(flag) is True]


def warnings(facility: dict) -> list[str]:
    lines = []
    truncated = facility.get("truncated_columns") or []
    if facility.get("needs_investigation") is True or truncated:
        names = ", ".join(LIST_NAMES.get(c, c) for c in truncated) or "some lists"
        lines.append(f"List incomplete ({names} cut off at 50 items), so a missing service may just be unlisted")
    location = [reason for flag, reason in LOCATION_FLAGS.items() if facility.get(flag) is True]
    if location:
        lines.append(f"Location may be inaccurate: {'; '.join(location)}")
    lines.extend(line for flag, line in WARNING_FLAGS.items() if facility.get(flag) is True)
    return lines
