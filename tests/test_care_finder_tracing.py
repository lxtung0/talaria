"""MLflow tracing of recommend() (ticket #31), with a fake tracer: spans are recorded, never required."""

import pytest

from talaria.care_finder import tracing
from talaria.care_finder.recommend import recommend
from tests.test_care_finder_recommend import FakeBackend, facility_at, ring_points


class Recorder:
    """Stands in for `mlflow.start_span`, recording each span's name, inputs and outputs."""

    def __init__(self):
        self.spans = []

    def start(self, name, span_type):
        recorder = self

        class Span:
            trace_id = "tr-fake"

            def __init__(self):
                self.record = {"name": name, "type": span_type, "inputs": None, "outputs": None}
                recorder.spans.append(self.record)

            def set_inputs(self, value):
                self.record["inputs"] = value

            def set_outputs(self, value):
                self.record["outputs"] = value

            def set_attributes(self, value):
                pass

        class Manager:
            def __enter__(self):
                return Span()

            def __exit__(self, *exc):
                return False

        return Manager()


def _backend(**kwargs):
    points = ring_points(1, 3)
    facilities = [facility_at(lat, lon, f"f{i}") for i, (lat, lon) in enumerate(points)]
    return FakeBackend(facilities, {f"f{i}": ("equipment", "4 hemodialysis machines", 0.95) for i in range(3)}, **kwargs)


@pytest.fixture
def recorder(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(tracing, "enabled", lambda: True)
    monkeypatch.setattr(tracing, "_start", rec.start)
    monkeypatch.setattr(tracing, "tag_trace", lambda tags: rec.spans.append({"name": "tags", "outputs": tags}))
    return rec


def test_a_trace_has_location_round_summary_scoring_and_ranking_spans(recorder):
    answer = recommend("dialysis", "Patna", backend=_backend())

    names = [s["name"] for s in recorder.spans]
    assert names[0] == "recommend"
    for expected in ["resolve_location", "round 1", "vector_search", "llm_check", "loop_summary", "scoring", "ranking"]:
        assert expected in names
    assert answer["trace_id"] == "tr-fake"


def test_the_scoring_span_shows_hits_labels_and_score_parts_of_the_top_result(recorder):
    answer = recommend("dialysis", "Patna", backend=_backend())

    scoring = next(s for s in recorder.spans if s["name"] == "scoring")["outputs"]
    top = next(r for r in scoring if r["unique_id"] == answer["top"][0]["unique_id"])
    assert top["hits"][0]["item_text"] == "4 hemodialysis machines"
    assert top["hits"][0]["label"] == "direct"
    assert {"service_evidence", "confidence_score", "distance_factor", "rank"} <= set(top)


def test_the_trace_is_tagged_with_service_location_urgency_and_fallback(recorder):
    recommend("dialysis", "Patna", "emergency", backend=_backend(llm_fails=True))

    tags = next(s for s in recorder.spans if s["name"] == "tags")["outputs"]
    assert tags["service"] == "dialysis" and tags["location"] == "Patna" and tags["urgency"] == "emergency"
    assert tags["fallback_used"] is True


def _strip(answer):
    return {k: v for k, v in answer.items() if k not in ("trace_id", "trace_url")}


def test_results_are_the_same_with_tracing_disabled_or_failing(monkeypatch, recorder):
    traced = recommend("dialysis", "Patna", backend=_backend())

    def broken(name, span_type):
        raise ConnectionError("MLflow unreachable")

    monkeypatch.setattr(tracing, "_start", broken)
    failing = recommend("dialysis", "Patna", backend=_backend())

    monkeypatch.setattr(tracing, "enabled", lambda: False)
    disabled = recommend("dialysis", "Patna", backend=_backend())

    assert _strip(traced) == _strip(failing) == _strip(disabled)
    assert failing["trace_id"] is None and disabled["trace_id"] is None


def test_a_span_that_fails_on_exit_or_output_does_not_break_the_query(monkeypatch):
    class Broken:
        def __enter__(self):
            class S:
                trace_id = None

                def set_inputs(self, v):
                    raise RuntimeError("bad inputs")

                set_outputs = set_attributes = set_inputs

            return S()

        def __exit__(self, *exc):
            raise RuntimeError("export failed")

    monkeypatch.setattr(tracing, "enabled", lambda: True)
    monkeypatch.setattr(tracing, "_start", lambda name, span_type: Broken())
    monkeypatch.setattr(tracing, "tag_trace", lambda tags: None)

    answer = recommend("dialysis", "Patna", backend=_backend())

    assert answer["status"] == "ok" and len(answer["top"]) == 3


def test_errors_from_the_traced_code_still_propagate(monkeypatch, recorder):
    class Down(FakeBackend):
        def cached_labels(self, key):
            raise RuntimeError("warehouse down")

    with pytest.raises(RuntimeError, match="warehouse down"):
        recommend("dialysis", "Patna", backend=Down([], {}))
