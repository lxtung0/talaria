"""Silver Stage 3 (#35), tested only through `build_silver_stage3`, on real Silver
facilities output and the reference CSVs in the repo."""

import datetime
import json

import pytest
from pyspark.sql import functions as F

from talaria.silver_facilities import build_silver_facilities
from talaria.silver_stage3 import build_silver_stage3
from talaria.silver_stage3.checks import check_silver_stage3
from talaria.silver_stage3.columns import NEW_COLUMNS, REPLACED_COLUMNS
from talaria.silver_stage3.rule_counts import rule_counts

RUN_DATE = datetime.date(2026, 11, 22)

# Five specialties in five categories that count for R3, none of them GENERIC.
FIVE_CATEGORIES = ["cardiology", "nephrology", "urology", "ophthalmology", "dermatology"]


def bronze_row(case, *, name=None, kind=None, beds=None, doctors=None, specialties=None, procedure=None,
               equipment=None, capability=None):
    """A partial bronze row; list arguments are Python lists, written as JSON text."""
    row = {"unique_id": case, "name": name, "facilityTypeId": kind}
    row |= {"capacity": None if beds is None else str(beds), "numberDoctors": None if doctors is None else str(doctors)}
    for column, items in [("specialties", specialties), ("procedure", procedure), ("equipment", equipment),
                          ("capability", capability)]:
        row[column] = None if items is None else json.dumps(items)
    return row


# A Facility passing every large hospital step; cases override what they test.
LARGE = dict(name="City General Hospital", kind="hospital", beds=200, doctors=40, specialties=FIVE_CATEGORIES)


@pytest.fixture
def stage3(make_silver_inputs, no_pincodes):
    """`(silver_facilities, stage3)` from partial bronze rows, after the runtime checks pass."""

    def run(*rows):
        bronze, silver_base = make_silver_inputs(*rows)
        facilities = build_silver_facilities(silver_base, bronze, no_pincodes, RUN_DATE).localCheckpoint()
        result = build_silver_stage3(facilities)
        check_silver_stage3(facilities, result)
        return facilities, result

    return run


@pytest.fixture
def build(stage3):
    """Stage 3 rows by `unique_id`."""

    def run(*rows):
        return {row.unique_id: row for row in stage3(*rows)[1].collect()}

    return run


def test_drops_replaced_flags_and_adds_new_columns(stage3):
    facilities, result = stage3(bronze_row("facility-1", name="City Hospital"))

    kept = [name for name in facilities.columns if name not in REPLACED_COLUMNS]
    assert set(REPLACED_COLUMNS) <= set(facilities.columns)
    assert result.columns == kept + [column.name for column in NEW_COLUMNS]


def test_refuses_input_that_already_has_a_new_column(make_silver_inputs, no_pincodes):
    bronze, silver_base = make_silver_inputs(bronze_row("facility-1"))
    facilities = build_silver_facilities(silver_base, bronze, no_pincodes, RUN_DATE).withColumn("flag_partial", F.lit(None))

    with pytest.raises(ValueError, match="flag_partial"):
        build_silver_stage3(facilities)


def test_counts_are_kept_as_they_are(build):
    facility = build(bronze_row("facility-1", kind="hospital", beds=9000, doctors=1))["facility-1"]

    assert (facility.bed_count, facility.number_doctors) == (9000, 1)
    assert facility.flag_facility_capacity_outlier


def test_specialty_categories(build):
    facility = build(
        bronze_row("facility-1", specialties=["cardiology", "internalMedicine", "radiology", "notAKnownCode", "cardiology"])
    )["facility-1"]

    assert facility.specialty_categories == [
        "Cardiology", "Internal / Family / General Medicine", "Other / Unclassified", "Radiology & Imaging"
    ]
    # Radiology counts for R3; general medicine and unknown codes don't.
    assert facility.n_specialty_categories == 2
    assert facility.core_categories == ["Cardiology"]


def test_no_specialties_means_no_categories(build):
    facility = build(bronze_row("facility-1"))["facility-1"]

    assert (facility.specialty_categories, facility.n_specialty_categories, facility.core_categories) == ([], 0, [])


# R0. (facility type, name, beds, doctors) -> outlier_reason.
CAPACITY = {
    "R0-1 over 4,000 beds": ("hospital", "City Hospital", 4001, 100, "R0-1"),
    "R0-2 doctors over twice the beds": ("hospital", "City Hospital", 10, 21, "R0-2"),
    "R0-3 clinic type with 150 doctors": ("clinic", "Care Centre", None, 150, "R0-3"),
    "R0-3 clinic name with 150 doctors": (None, "Apollo Clinic", None, 150, "R0-3"),
    "R0-3 hospital name isn't a clinic": (None, "Apollo Clinic and Hospital", None, 150, None),
    "R0-4 a doctor per 100 beds or fewer": ("hospital", "City Hospital", 500, 5, "R0-4"),
    "R0-5 hospital with one doctor": ("hospital", "City Hospital", None, 1, "R0-5"),
    "R0-5 clinic with one doctor": ("clinic", "Care Centre", None, 1, None),
    "R0-6 hospital with 1-5 beds": ("hospital", "City Hospital", 5, None, "R0-6"),
    "several rules": ("hospital", "City Hospital", 3, 7, "R0-2; R0-6"),
    "plausible": ("hospital", "City Hospital", 100, 20, None),
    "no counts": ("hospital", "City Hospital", None, None, None),
}


def test_capacity_outliers(build):
    rows = build(
        *[
            bronze_row(case, kind=kind, name=name, beds=beds, doctors=doctors)
            for case, (kind, name, beds, doctors, _) in CAPACITY.items()
        ]
    )

    assert {case: rows[case].outlier_reason for case in CAPACITY} == {
        case: reason for case, (*_, reason) in CAPACITY.items()
    }
    for case, (*_, reason) in CAPACITY.items():
        assert rows[case].flag_facility_capacity_outlier is (reason is not None), case


def test_bed_and_doctor_outliers(build):
    rows = build(
        bronze_row("beds", kind="hospital", beds=3, doctors=4),
        bronze_row("doctors", kind="hospital", beds=None, doctors=1),
    )

    assert (rows["beds"].bed_outlier, rows["beds"].doctor_outlier) == (True, False)
    assert (rows["doctors"].bed_outlier, rows["doctors"].doctor_outlier) == (False, True)


# F1. (name, facility type) -> flag_name_facilityType.
NAME_TYPE = {
    "hospital name, clinic type": ("City Hospital", "clinic", True),
    "medical college, doctor type": ("Government Medical College", "doctor", True),
    "dental hospital, dentist type": ("Smile Dental Hospital", "dentist", False),
    "clinic name, hospital type": ("Apollo Clinic", "hospital", True),
    "diagnostic name, hospital type": ("Sai Diagnostics", "hospital", True),
    "both names, hospital type": ("City Hospital and Diagnostic Centre", "hospital", False),
    "hospital name, hospital type": ("City Hospital", "hospital", False),
    "no type": ("City Hospital", None, False),
    "no name": (None, "clinic", False),
}


def test_name_contradicts_facility_type(build):
    rows = build(*[bronze_row(case, name=name, kind=kind) for case, (name, kind, _) in NAME_TYPE.items()])

    assert {case: rows[case].flag_name_facilityType for case in NAME_TYPE} == {
        case: expected for case, (*_, expected) in NAME_TYPE.items()
    }


# R1-R5. Overrides of LARGE -> large_hospital_step_failed.
LARGE_HOSPITAL = {
    "passes every step": ({}, None),
    "doctors alone are enough": (dict(beds=None), None),
    "hospital name, other type": (dict(kind="clinic", name="City Hospital and Diagnostic Centre"), None),
    "R1 veterinary": (dict(name="City Veterinary Hospital"), "R1"),
    "R1 pet": (dict(name="Pet Care Hospital"), "R1"),
    "R2 not a hospital": (dict(kind="clinic", name="Care Centre"), "R2"),
    "R3 four categories": (dict(specialties=FIVE_CATEGORIES[:4] + ["internalMedicine"]), "R3"),
    "R4 small": (dict(beds=50, doctors=15), "R4"),
    "R4 beds flagged in R0": (dict(beds=5000, doctors=10), "R4"),
    "R5 traditional medicine": (dict(name="Ayurveda Hospital"), "R5"),
    "R5 name contradicts type": (dict(name="City Clinic"), "R5"),
}


def test_large_hospital_funnel(build):
    rows = build(*[bronze_row(case, **(LARGE | overrides)) for case, (overrides, _) in LARGE_HOSPITAL.items()])

    assert {case: rows[case].large_hospital_step_failed for case in LARGE_HOSPITAL} == {
        case: step for case, (_, step) in LARGE_HOSPITAL.items()
    }
    for case, (_, step) in LARGE_HOSPITAL.items():
        assert rows[case].flag_large_hospital is (step is None), case
        assert rows[case].is_veterinary is (step == "R1"), case


# C1. (procedure, equipment, capability) -> unverified_reason.
UNVERIFIED = {
    "all three": (["Dialysis"], ["Dialysis machine"], ["Dialysis unit"], None),
    "procedure and equipment missing": (None, [], ["Dialysis unit"], "procedure, equipment"),
    "blank items only": ([" "], ["Dialysis machine"], ["Dialysis unit"], "procedure"),
    "none": (None, None, None, "procedure, equipment, capability"),
}


def test_unverified(build):
    rows = build(
        *[
            bronze_row(case, procedure=procedure, equipment=equipment, capability=capability)
            for case, (procedure, equipment, capability, _) in UNVERIFIED.items()
        ]
    )

    assert {case: rows[case].unverified_reason for case in UNVERIFIED} == {
        case: reason for case, (*_, reason) in UNVERIFIED.items()
    }
    for case, (*_, reason) in UNVERIFIED.items():
        assert rows[case].flag_unverified is (reason is not None), case


# C2. (procedure, equipment, capability) -> partial_reason.
PARTIAL = {
    "procedure with its equipment": (["Hemodialysis"], ["Dialysis machine"], None, None),
    "procedure without equipment": (["Hemodialysis"], ["X-ray machine"], None, "procedure without equipment: Dialysis"),
    "equipment without procedure": (["Physiotherapy"], ["MRI 1.5T"], None, "equipment without procedure: MRI scan"),
    "capability backs the equipment": (["Physiotherapy"], ["MRI 1.5T"], ["MRI services"], None),
    "forward only rule": (["Physiotherapy"], ["Slit lamp"], None, None),
    "both ways": (
        ["Hemodialysis", "Endoscopy"], ["MRI 1.5T"], None,
        "procedure without equipment: Dialysis, Endoscopy | equipment without procedure: MRI scan",
    ),
    "noise items are ignored": (["Hemodialysis"], ["Dialysis chair", "Wheelchair"], None, None),
    "no equipment, not checked": (["Hemodialysis"], None, None, None),
}


def test_partial(build):
    rows = build(
        *[
            bronze_row(case, procedure=procedure, equipment=equipment, capability=capability)
            for case, (procedure, equipment, capability, _) in PARTIAL.items()
        ]
    )

    assert {case: rows[case].partial_reason for case in PARTIAL} == {
        case: reason for case, (*_, reason) in PARTIAL.items()
    }
    for case, (*_, reason) in PARTIAL.items():
        assert rows[case].flag_partial is (reason is not None), case


# C3. (bronze row) -> (unsupported_specialties, unsupported_specialty_share, flag_specialty_unsupported).
SPECIALTY_UNSUPPORTED = {
    "half missing": (
        dict(specialties=["cardiology", "nephrology"], procedure=["Echocardiography"]),
        (["Nephrology & Dialysis"], 0.5, True),
    ),
    "all backed": (
        dict(specialties=["cardiology", "nephrology"], procedure=["ECG"], equipment=["Dialysis machine"]),
        ([], 0.0, False),
    ),
    "a related category counts": (dict(specialties=["urology"], capability=["Dialysis unit"]), ([], 0.0, False)),
    "generic categories are ignored": (
        dict(specialties=["cardiology", "radiology", "internalMedicine"], procedure=["ECG"]), ([], 0.0, False)
    ),
    "a third missing": (
        dict(specialties=["cardiology", "dermatology", "urology"], procedure=["ECG", "Cystoscopy"]),
        (["Dermatology"], 0.333, False),
    ),
    "noise item doesn't back a specialty": (
        dict(specialties=["cardiology"], capability=["Parking near the cardiology block"]),
        (["Cardiology"], 1.0, True),
    ),
    "no text, not checked": (dict(specialties=["cardiology"]), (None, None, False)),
    "only generic specialties, not checked": (dict(specialties=["radiology"], procedure=["ECG"]), (None, None, False)),
    "large hospital, most missing": (LARGE | dict(procedure=["ECG"]), (None, 0.8, False)),
    "large hospital, all missing": (LARGE | dict(procedure=["Physiotherapy"]), (None, 1.0, True)),
}


def test_specialty_unsupported(build):
    rows = build(*[bronze_row(case, **row) for case, (row, _) in SPECIALTY_UNSUPPORTED.items()])

    actual = {
        case: (rows[case].unsupported_specialties, _rounded(rows[case].unsupported_specialty_share),
               rows[case].flag_specialty_unsupported)
        for case in SPECIALTY_UNSUPPORTED
    }
    expected = {case: result for case, (_, result) in SPECIALTY_UNSUPPORTED.items()}
    # A large hospital's missing categories are its five, in its own order; only their count matters here.
    for case in ["large hospital, most missing", "large hospital, all missing"]:
        missing, share, flag = actual[case]
        actual[case] = (None, share, flag)
        assert len(missing) == round(share * 5), case
    assert actual == expected


def _rounded(share):
    return None if share is None else round(share, 3)


# C4. (bronze row) -> orphan_reason.
MAJOR_ORPHAN = {
    "procedure without its specialty": (
        dict(specialties=["cardiology"], procedure=["Hemodialysis"]), "procedure: Nephrology & Dialysis"
    ),
    "equipment without its specialty": (
        dict(specialties=["cardiology"], equipment=["Infant incubator"]), "equipment: Neonatology / NICU"
    ),
    "capability unit without its specialty": (
        dict(specialties=["cardiology"], capability=["24x7 dialysis unit"]), "capability unit: Dialysis Unit"
    ),
    "all parts": (
        dict(specialties=["cardiology"], procedure=["Hemodialysis"], capability=["24x7 dialysis unit"]),
        "procedure: Nephrology & Dialysis; capability unit: Dialysis Unit",
    ),
    "own specialty": (dict(specialties=["nephrology"], procedure=["Hemodialysis"]), None),
    "accepted related specialty": (
        dict(specialties=["urology"], procedure=["Hemodialysis"], capability=["Dialysis unit"]), None
    ),
    "not high risk": (dict(specialties=["cardiology"], procedure=["Cataract surgery"]), None),
    "large hospital, not checked": (LARGE | dict(procedure=["Infant incubator"]), None),
}


def test_major_orphan(build):
    rows = build(*[bronze_row(case, **row) for case, (row, _) in MAJOR_ORPHAN.items()])

    assert {case: rows[case].orphan_reason for case in MAJOR_ORPHAN} == {
        case: reason for case, (_, reason) in MAJOR_ORPHAN.items()
    }
    for case, (_, reason) in MAJOR_ORPHAN.items():
        assert rows[case].flag_major_orphan is (reason is not None), case


# C5. (bronze row) -> flag_merge_different.
MERGE_DIFFERENT = {
    "procedures of another specialty": (dict(specialties=["ophthalmology"], procedure=["Knee replacement"]), True),
    "capability of another specialty too": (
        dict(specialties=["ophthalmology"], procedure=["Knee replacement"], capability=["Fracture clinic"]), True
    ),
    "capability backs the specialty": (
        dict(specialties=["ophthalmology"], procedure=["Knee replacement"], capability=["Eye care"]), False
    ),
    "capability names generic categories only": (
        dict(specialties=["ophthalmology"], procedure=["Knee replacement"], capability=["X-ray"]), False
    ),
    "a procedure backs the specialty": (
        dict(specialties=["ophthalmology"], procedure=["Knee replacement", "Cataract surgery"]), False
    ),
    "generic procedures only": (dict(specialties=["ophthalmology"], procedure=["Blood test"]), False),
    "no procedure": (dict(specialties=["ophthalmology"], capability=["Fracture clinic"]), False),
    "no core specialty": (dict(specialties=["radiology"], procedure=["Knee replacement"]), False),
}


def test_merge_different(build):
    rows = build(*[bronze_row(case, **row) for case, (row, _) in MERGE_DIFFERENT.items()])

    assert {case: rows[case].flag_merge_different for case in MERGE_DIFFERENT} == {
        case: expected for case, (_, expected) in MERGE_DIFFERENT.items()
    }


def test_rule_counts(stage3):
    _, result = stage3(
        bronze_row("large", **LARGE),
        bronze_row("vet", name="Animal Hospital", kind="hospital", beds=3),
        bronze_row("clinic", name="Care Centre", kind="clinic"),
    )

    counts = {row.rule_id: row.rows_flagged_or_remaining for row in rule_counts(result).collect()}

    assert list(counts) == [
        "R0", "R0-1", "R0-2", "R0-3", "R0-4", "R0-5", "R0-6", "F1", "R1", "R2", "R3", "R4", "R5",
        "C1", "C2", "C3", "C4", "C5",
    ]
    assert (counts["R0"], counts["R0-6"], counts["R1"]) == (1, 1, 1)
    # The funnel: the vet fails R1 and the clinic R2, so R2-R5 keep the large hospital only.
    assert [counts[step] for step in ["R2", "R3", "R4", "R5"]] == [1, 1, 1, 1]
    assert counts["C1"] == 3


def test_checks_fail_when_a_kept_value_changes(stage3):
    facilities, result = stage3(bronze_row("facility-1", name="City Hospital"))

    with pytest.raises(ValueError, match="name: 1 row\\(s\\) changed from Silver facilities"):
        check_silver_stage3(facilities, result.withColumn("name", F.lit("Other Hospital")))


def test_checks_fail_when_a_flag_is_null(stage3):
    facilities, result = stage3(bronze_row("facility-1", name="City Hospital"))

    with pytest.raises(ValueError, match="flag_partial: 1 row\\(s\\) with a NULL flag"):
        check_silver_stage3(facilities, result.withColumn("flag_partial", F.lit(None).cast("boolean")))
