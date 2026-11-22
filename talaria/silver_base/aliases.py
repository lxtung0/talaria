"""Alias tables for Silver base Spelling fixes (spec #1, "Spelling fixes").

Each table maps a known variant spelling, written lower-case, to its one
canonical value. Values not in a table pass through unchanged. Every entry is a
deliberate, reviewable decision: only alias a value whose meaning is unambiguous.
"""

# Facility type (`facilityTypeId`). Values are lower-cased first.
FACILITY_TYPE = {
    "farmacy": "pharmacy",
}

# Operator type (`operatorTypeId`). Values are lower-cased first.
OPERATOR_TYPE = {
    "government": "public",
}

# Affiliation types (`affiliationTypeIds` items). Values are lower-cased first.
# Values outside the allowed set (`NAAC`, `DCI`, `diagnostic-centre`, ...) are
# Invalid values and are kept, not aliased.
AFFILIATION_TYPE = {
    "private-entity": "private",
}

# British spelling (items of `specialties`, `procedure`, `equipment`, `capability`):
# British word fragment -> American, replaced wherever it occurs inside an item,
# in table order. Written lower-case; the fix also matches the fragment
# Capitalized (camelCase or Title Case) and in UPPER CASE and keeps that shape
# (`paediatricCardiology`, `clinicalHaematology`, `PAEDIATRICS`).
#
# Every fragment was checked against every word in those four columns (profiled
# 2026-11-21) and hits no correct American word. So generic endings are not
# fragments: `-ise`/`-ised`/`-ising` (correct in `advised`, `exercise`, `arising`)
# are fixed only for the stems in `_ISE_STEMS` and `_ISING_STEMS`, and `analyse` is not fixed
# (`analyses` is the American plural). Deliberately not fixed: `harbour` (the
# place Diamond Harbour), `titre` (the Sensititre brand), `tyre` (inside
# `...fertilityresearchcentre`), `programme` (inside `programmer`), `cancell`
# (`cancellation`), `storey` (`storeyed`, `storeys`), `grey`, and `disc`.
# Stems whose British -ise forms (-ise, -ised, -ises, -iser) occur in the data;
# `vapor` catches `vapouriser` after the -our fix. `_ISING_STEMS` likewise for -ising.
_ISE_STEMS = [
    "special", "personal", "central", "marginal", "operational", "local", "digital",
    "revital", "commercial", "util", "steril", "nebul", "computer", "recogn", "custom",
    "random", "subsid", "standard", "modern", "organ", "mechan", "synerg", "popular",
    "vascular", "author", "motor", "vapor", "digit", "sanit", "priorit", "immun",
]
_ISING_STEMS = ["special", "character", "organ", "priorit", "necrot", "lutein", "optim", "revolution"]

BRITISH_SPELLING = {
    # ae / oe. `paed` also covers `orthopaed`; `aemia` covers `anaemia`, `leukaemia`.
    "paed": "ped",
    "haem": "hem",
    "gynae": "gyne",
    "anaesthe": "anesthe",
    "caesar": "cesar",
    "caec": "cec",
    "aemia": "emia",
    "ischaem": "ischem",
    "faec": "fec",
    "oesophag": "esophag",
    "oedema": "edema",
    "foet": "fet",
    "homoeo": "homeo",
    "rrhoea": "rrhea",
    "pnoea": "pnea",
    "coeliac": "celiac",
    "manoeuvre": "maneuver",
    "leuco": "leuko",
    # -re. `centred` before `centre`.
    "centred": "centered",
    "centre": "center",
    "theatre": "theater",
    "fibre": "fiber",
    "litre": "liter",
    "metre": "meter",
    "goitre": "goiter",
    "calibre": "caliber",
    # -our. Before the -ise stems, so `vapouriser` -> `vaporiser` -> `vaporizer`.
    "tumour": "tumor",
    "labour": "labor",
    "colour": "color",
    "behaviour": "behavior",
    "neighbour": "neighbor",
    "honour": "honor",
    "favour": "favor",
    "endeavour": "endeavor",
    "vapour": "vapor",
    # -ise / -isation / -yse.
    "isation": "ization",
    **{f"{stem}ise": f"{stem}ize" for stem in _ISE_STEMS},
    **{f"{stem}ising": f"{stem}izing" for stem in _ISING_STEMS},
    "practis": "practic",
    "lyser": "lyzer",
    # Doubled l.
    "counsell": "counsel",
    "travell": "travel",
    "labell": "label",
    "modell": "model",
    "panelled": "paneled",
    "enrolment": "enrollment",
    "fulfilment": "fulfillment",
    # Other words. `jewellery` before `jeweller`.
    "speciality": "specialty",
    "licence": "license",
    "defence": "defense",
    "ageing": "aging",
    "mould": "mold",
    "aluminium": "aluminum",
    "sulph": "sulf",
    "jewellery": "jewelry",
    "jeweller": "jeweler",
    "cheque": "check",
    "analogue": "analog",
}

# City (`address_city`): officially renamed cities, old name -> current name.
# Cities are Title Cased first; only official renames are listed, not
# nicknames or short forms (`Trichy`, `Vizag`, `Ooty` are left as written).
CITY = {
    "bangalore": "Bengaluru",
    "gurgaon": "Gurugram",
    "bombay": "Mumbai",
    "calcutta": "Kolkata",
    "madras": "Chennai",
    "trivandrum": "Thiruvananthapuram",
    "mysore": "Mysuru",
    "poona": "Pune",
    "mangalore": "Mangaluru",
    "belgaum": "Belagavi",
    "bellary": "Ballari",
    "gulbarga": "Kalaburagi",
    "shimoga": "Shivamogga",
    "tumkur": "Tumakuru",
    "hubli": "Hubballi",
    "baroda": "Vadodara",
    "cochin": "Kochi",
    "calicut": "Kozhikode",
    "trichur": "Thrissur",
    "quilon": "Kollam",
    "alleppey": "Alappuzha",
    "cannanore": "Kannur",
    "pondicherry": "Puducherry",
    "allahabad": "Prayagraj",
    "gauhati": "Guwahati",
    "nasik": "Nashik",
    "panjim": "Panaji",
}

# The 36 official state and UT names: the India Post pincode directory's
# `statename` values in Title Case. These are the canonical state spellings.
OFFICIAL_STATES = [
    "Andaman And Nicobar Islands",
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chandigarh",
    "Chhattisgarh",
    "Delhi",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jammu And Kashmir",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Ladakh",
    "Lakshadweep",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Puducherry",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "The Dadra And Nagar Haveli And Daman And Diu",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
]

# State (`address_stateOrRegion`): variant spellings seen in the facilities table
# (profiled 2026-11-21) -> official name. An abbreviation is only listed when it
# unambiguously names one state in this dataset (checked against each row's city
# and PIN). Cities, districts and ambiguous values (`Thane`, `Mumbai`, `Madhya`,
# `Punjab Region`, `Kashmir`, `Ut`, `Nct`, ...) are deliberately absent, so they
# pass through unchanged. Official names in any case match without an entry here.
STATE = {
    # Typos.
    "tamilnadu": "Tamil Nadu",
    "uttar prades h": "Uttar Pradesh",
    "chattisgarh": "Chhattisgarh",
    "telengana": "Telangana",
    "uttranchal": "Uttarakhand",
    # Joined words.
    "uttarpradesh": "Uttar Pradesh",
    "madhyapradesh": "Madhya Pradesh",
    # Abbreviations.
    "up": "Uttar Pradesh",
    "u.p.": "Uttar Pradesh",
    "u.p": "Uttar Pradesh",
    "mp": "Madhya Pradesh",
    "m.p.": "Madhya Pradesh",
    "ts": "Telangana",
    "gj": "Gujarat",
    "mh": "Maharashtra",
    "ms": "Maharashtra",  # the one row is in Mumbai, PIN 400007
    "br": "Bihar",
    "cg": "Chhattisgarh",
    "dl": "Delhi",
    "u.k.": "Uttarakhand",
    "j&k": "Jammu And Kashmir",
    # Old or official-form names.
    "orissa": "Odisha",
    "pondicherry": "Puducherry",
    "u.t of puducherry": "Puducherry",
    "uttaranchal": "Uttarakhand",
    "nct of delhi": "Delhi",
    "nct delhi": "Delhi",
    "new delhi": "Delhi",
    "delhi ncr": "Delhi",
    "delhi/ncr": "Delhi",
    "chandigarh (ut)": "Chandigarh",
    "jammu & kashmir": "Jammu And Kashmir",
    "daman and diu": "The Dadra And Nagar Haveli And Daman And Diu",
    "dadra & nagar haveli & daman & diu": "The Dadra And Nagar Haveli And Daman And Diu",
    "dadra and nagar haveli and daman and diu": "The Dadra And Nagar Haveli And Daman And Diu",
}
