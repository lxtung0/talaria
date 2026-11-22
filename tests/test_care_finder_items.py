"""App table unpacking, tested through `build_app_tables` (ticket #27)."""

import pytest
from pyspark.sql import types as T

from talaria.care_finder.items import build_app_tables

_LISTS = ["specialties", "procedure", "equipment", "capability", "source_urls", "truncated_columns"]
_DOUBLES = ["latitude", "longitude"]
_BOOLS = ["flag_has_government_source", "flag_coords_shared", "needs_investigation"]
_STRINGS = [
    "unique_id", "name", "facility_type", "address_line1", "address_line2", "address_line3",
    "address_city", "address_state", "address_pincode", "official_phone", "official_website", "description",
]
SOURCE_SCHEMA = T.StructType(
    [T.StructField(c, T.StringType()) for c in _STRINGS]
    + [T.StructField(c, T.ArrayType(T.StringType())) for c in _LISTS]
    + [T.StructField(c, T.DoubleType()) for c in _DOUBLES]
    + [T.StructField(c, T.BooleanType()) for c in _BOOLS]
)


@pytest.fixture
def make_source(spark):
    """A fake source Facilities table from partial rows; other columns are NULL."""

    def build(*rows, schema=SOURCE_SCHEMA):
        records = [tuple(row.get(f.name) for f in schema.fields) for row in rows]
        return spark.createDataFrame(records, schema)

    return build


def _items(source):
    _, items = build_app_tables(source)
    return sorted((r.item_id, r.unique_id, r.item_type, r.item_text) for r in items.collect())


def test_each_list_item_becomes_a_row(make_source):
    source = make_source(
        {
            "unique_id": "f1",
            "specialties": ["nephrology"],
            "procedure": ["Hemodialysis"],
            "equipment": ["4 hemodialysis machines", "CT scanner"],
            "capability": ["24/7 emergency care"],
        }
    )

    assert _items(source) == [
        ("f1-c0", "f1", "capability", "24/7 emergency care"),
        ("f1-e0", "f1", "equipment", "4 hemodialysis machines"),
        ("f1-e1", "f1", "equipment", "CT scanner"),
        ("f1-p0", "f1", "procedure", "Hemodialysis"),
        ("f1-s0", "f1", "specialty", "nephrology"),
    ]


def test_description_splits_into_sentences_on_full_stop_exclamation_and_question_mark(make_source):
    source = make_source({"unique_id": "f1", "description": "We offer dialysis. Open 24/7! Need an MRI? Call us"})

    assert _items(source) == [
        ("f1-d0", "f1", "description_sentence", "We offer dialysis."),
        ("f1-d1", "f1", "description_sentence", "Open 24/7!"),
        ("f1-d2", "f1", "description_sentence", "Need an MRI?"),
        ("f1-d3", "f1", "description_sentence", "Call us"),
    ]


def test_a_decimal_point_does_not_split_a_sentence(make_source):
    source = make_source({"unique_id": "f1", "description": "A 1.5 Tesla MRI."})

    assert [text for *_, text in _items(source)] == ["A 1.5 Tesla MRI."]


def test_null_and_empty_items_and_descriptions_make_no_rows(make_source):
    source = make_source(
        {"unique_id": "f1", "equipment": ["", "  ", None, "X-ray"], "capability": [], "description": "   "},
        {"unique_id": "f2"},
    )

    assert _items(source) == [("f1-e3", "f1", "equipment", "X-ray")]


def test_item_text_is_verbatim(make_source):
    source = make_source({"unique_id": "f1", "capability": ["  Dialysis   UNIT (24x7) "]})

    assert [text for *_, text in _items(source)] == ["  Dialysis   UNIT (24x7) "]


def test_the_same_text_in_two_lists_is_kept_in_both(make_source):
    source = make_source({"unique_id": "f1", "procedure": ["Dialysis"], "capability": ["Dialysis"]})

    assert [(item_type, text) for _, _, item_type, text in _items(source)] == [
        ("capability", "Dialysis"),
        ("procedure", "Dialysis"),
    ]


def test_item_id_is_the_same_across_two_runs(make_source):
    rows = [
        {"unique_id": "f1", "equipment": ["MRI", "CT"], "description": "One. Two."},
        {"unique_id": "f2", "capability": ["ICU"]},
    ]

    assert _items(make_source(*rows)) == _items(make_source(*reversed(rows)))


def test_facilities_keep_shown_flag_and_quality_columns_with_placeholder_confidence(make_source):
    source = make_source({"unique_id": "f1", "name": "City Hospital", "flag_coords_shared": True})

    facilities, _ = build_app_tables(source)

    row = facilities.collect()[0]
    assert row.name == "City Hospital"
    assert row.flag_coords_shared is True
    assert "flag_has_government_source" in facilities.columns
    assert "needs_investigation" in facilities.columns and "truncated_columns" in facilities.columns
    assert "description" not in facilities.columns
    assert row.confidence_score == 0.5


def test_confidence_score_is_copied_when_the_source_has_it(make_source):
    schema = T.StructType([*SOURCE_SCHEMA.fields, T.StructField("confidence_score", T.DoubleType())])
    source = make_source({"unique_id": "f1", "confidence_score": 0.83}, schema=schema)

    facilities, _ = build_app_tables(source)

    assert facilities.collect()[0].confidence_score == 0.83


def test_gold_supplies_the_confidence_and_drops_facilities_it_leaves_out(make_source, spark):
    source = make_source(
        {"unique_id": "f1", "equipment": ["MRI"]},
        {"unique_id": "vet", "equipment": ["X-ray"]},
    )
    gold = spark.createDataFrame(
        [("f1", 0.67, ["start 80", "-10 [major] flag_single_source_domain", "cap 75 [major]"])],
        "unique_id string, confidence_score double, confidence_reasons array<string>",
    )

    facilities, items = build_app_tables(source, gold)

    rows = facilities.collect()
    assert [r.unique_id for r in rows] == ["f1"]
    assert rows[0].confidence_score == 0.67
    assert rows[0].confidence_reasons == ["start 80", "-10 [major] flag_single_source_domain", "cap 75 [major]"]
    assert {r.unique_id for r in items.collect()} == {"f1"}


def test_without_gold_the_confidence_log_is_empty(make_source):
    facilities, _ = build_app_tables(make_source({"unique_id": "f1"}))

    assert facilities.collect()[0].confidence_reasons is None
