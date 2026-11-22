"""Specialty groups and their synonyms, for group C (spec #13, #17). Reviewable data, no Spark.

A specialty code is split into lower-case words first (`internalMedicine` ->
`internal medicine`). It belongs to every group with a `specialties` term in
those words. It is backed when a capability sentence contains its own words, or
any `synonyms` term of one of its groups.

Synonyms are only other forms of the specialty's own name (`dentistry` ->
`dental`, `dentist`; `cardiology` -> `cardiac`), never generic related words such
as `teeth`, `heart`, `surgery` or `24/7`, which would back a specialty on weak
evidence (decided on #17). Silver base already turned British spellings
American, so only American forms are listed.

A term matches whole words, case-insensitive. A trailing `*` matches the start
of a word instead (`ophthalm*` matches `ophthalmology` and `ophthalmologist`).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SpecialtyGroup:
    name: str
    specialties: list[str]
    synonyms: list[str]


SPECIALTY_GROUPS = [
    SpecialtyGroup(
        "general medicine",
        ["internal medicine", "family medicine", "general medicine", "general physician", "geriatric*"],
        ["internal medicine", "family medicine", "general medicine", "general physician*", "geriatric*"],
    ),
    SpecialtyGroup(
        "women's health",
        ["gynec*", "obstetric*", "maternal*", "urogynec*"],
        ["gynec*", "obstetric*", "maternal*"],
    ),
    SpecialtyGroup(
        "fertility",
        ["fertility", "infertility", "reproductive*", "ivf", "androlog*"],
        ["fertility", "infertility", "ivf", "reproductive medicine", "androlog*"],
    ),
    SpecialtyGroup(
        "children",
        ["pediatric*", "neonat*", "perinat*", "pedodont*"],
        ["pediatric*", "neonat*", "pedodont*"],
    ),
    SpecialtyGroup(
        "dental",
        ["dent*", "endodont*", "orthodont*", "prosthodont*", "periodont*", "pedodont*", "implantolog*",
         "maxillofacial", "maxillo*"],
        ["dent*", "endodont*", "orthodont*", "prosthodont*", "periodont*", "pedodont*", "implantolog*",
         "maxillofacial"],
    ),
    SpecialtyGroup(
        "eye",
        ["ophthalm*", "retina*", "vitreo*", "cataract*", "glaucoma", "cornea*", "uveitis", "ocul*",
         "strabismus", "squint", "eye", "lasik", "keratoconus"],
        ["ophthalm*", "retina*", "vitreo*", "cataract*", "glaucoma", "cornea*", "lasik", "squint",
         "optometr*", "ocul*"],
    ),
    SpecialtyGroup(
        "ear, nose and throat",
        ["ent", "otolaryng*", "otorhinolaryng*", "laryng*", "rhinolog*", "otolog*", "audiolog*"],
        ["ent", "otolaryng*", "otorhinolaryng*", "laryng*", "audiolog*"],
    ),
    SpecialtyGroup(
        "heart",
        ["cardi*", "electrophysiolog*"],
        ["cardi*"],
    ),
    SpecialtyGroup(
        "bones and joints",
        ["orthop*", "arthroscop*", "joint reconstruction", "joint replacement"],
        ["orthop*", "arthroscop*"],
    ),
    SpecialtyGroup(
        "skin and cosmetic",
        ["dermat*", "cosmet*", "aesthetic*"],
        ["dermat*", "cosmet*", "aesthetic*"],
    ),
    SpecialtyGroup(
        "plastic surgery",
        ["plastic*", "reconstructive"],
        ["plastic*", "reconstructive"],
    ),
    SpecialtyGroup(
        "kidney",
        ["nephrolog*", "dialysis"],
        ["nephrolog*", "dialysis"],
    ),
    SpecialtyGroup(
        "urinary",
        ["urolog*", "endourolog*", "uro"],
        ["urolog*", "endourolog*"],
    ),
    SpecialtyGroup(
        "digestive",
        ["gastro*", "hepat*", "colorectal", "proctolog*", "endoscop*", "bariatric"],
        ["gastro*", "hepat*", "endoscop*", "colorectal", "proctolog*", "bariatric"],
    ),
    SpecialtyGroup(
        "minimally invasive surgery",
        ["laparoscop*", "minimally invasive", "robotic*"],
        ["laparoscop*", "minimally invasive", "robotic*"],
    ),
    SpecialtyGroup(
        "transplant",
        ["transplant*"],
        ["transplant*"],
    ),
    SpecialtyGroup(
        "brain and nerves",
        ["neuro*", "epilep*"],
        ["neuro*", "epilep*"],
    ),
    SpecialtyGroup(
        "mental health",
        ["psychiat*", "psycholog*", "neuropsychiat*", "addiction*"],
        ["psychiat*", "psycholog*", "addiction*", "de-addiction"],
    ),
    SpecialtyGroup(
        "cancer",
        ["oncolog*", "onco*", "cancer*", "radiotherap*"],
        ["oncolog*", "onco*", "cancer*", "chemotherap*", "radiotherap*"],
    ),
    SpecialtyGroup(
        "lungs",
        ["pulmon*", "respiratory*"],
        ["pulmon*", "respiratory medicine"],
    ),
    SpecialtyGroup(
        "imaging",
        ["radiolog*", "imaging", "nuclear medicine"],
        ["radiolog*", "sonograph*", "ultrasonograph*", "nuclear medicine"],
    ),
    SpecialtyGroup(
        "laboratory",
        ["patholog*", "cytolog*", "microbiolog*", "biochemistry", "laboratory*"],
        ["patholog*", "laborator*", "biochem*", "microbiolog*", "cytolog*"],
    ),
    SpecialtyGroup(
        "blood",
        ["hematolog*"],
        ["hematolog*"],
    ),
    SpecialtyGroup(
        "emergency and critical care",
        ["emergency*", "critical care", "neurocritical care"],
        ["emergenc*", "critical care", "intensive care", "icu"],
    ),
    SpecialtyGroup(
        "anesthesia",
        ["anesthe*"],
        ["anesthe*"],
    ),
    SpecialtyGroup(
        "hormones and diabetes",
        ["endocrin*", "diabet*"],
        ["endocrin*", "diabet*"],
    ),
    SpecialtyGroup(
        "rehabilitation",
        ["rehabilitation", "physical medicine", "physiotherap*", "pmr"],
        ["rehabilitat*", "physiotherap*", "physical medicine"],
    ),
    SpecialtyGroup(
        "infection",
        ["infectious*"],
        ["infectious*"],
    ),
    SpecialtyGroup(
        "rheumatology",
        ["rheumatolog*"],
        ["rheumat*"],
    ),
    SpecialtyGroup(
        "palliative care",
        ["palliative*", "hospice*"],
        ["palliative*", "hospice*"],
    ),
    SpecialtyGroup(
        "nutrition",
        ["nutrition*", "dietetic*", "dietitian*"],
        ["nutrition*", "dietetic*", "dietitian*"],
    ),
    SpecialtyGroup(
        "traditional medicine",
        ["ayurved*", "homeopath*"],
        ["ayurved*", "homeopath*"],
    ),
    SpecialtyGroup(
        "foot care",
        ["podiatr*"],
        ["podiatr*"],
    ),
]
