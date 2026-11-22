"""MLflow tracing for `recommend()` that can never break a query (ticket #31).

`span(name, inputs)` is a context manager around `mlflow.start_span`. If MLflow is
missing, disabled (`TALARIA_TRACING=0`) or failing, it yields a no-op span instead;
errors raised by the traced code itself still propagate unchanged.

Traces go to the experiment `/Shared/talaria-care-finder`, or under the user's own
folder when `/Shared` isn't writable.
"""

import contextlib
import logging
import os

log = logging.getLogger(__name__)

EXPERIMENT = "/Shared/talaria-care-finder"
_state: dict = {"ready": None, "experiment_id": None, "host": None}


def enabled() -> bool:
    if os.environ.get("TALARIA_TRACING", "1") == "0":
        return False
    if _state["ready"] is None:
        _state["ready"] = _setup()
    return _state["ready"]


def _setup() -> bool:
    try:
        import mlflow
        from databricks.sdk import WorkspaceClient

        mlflow.set_tracking_uri("databricks")
        w = WorkspaceClient()
        host = w.config.host
        _state["host"] = host if host.startswith("http") else f"https://{host}"
        try:
            experiment = mlflow.set_experiment(EXPERIMENT)
        except Exception:
            me = w.current_user.me().user_name
            experiment = mlflow.set_experiment(f"/Users/{me}/talaria-care-finder")
        _state["experiment_id"] = experiment.experiment_id
        return True
    except Exception as e:
        log.warning("Tracing disabled: %s", e)
        return False


def trace_url(trace_id: str | None) -> str | None:
    """The trace's page in the workspace, when the host and experiment are known."""
    if not trace_id or not _state["host"] or not _state["experiment_id"]:
        return None
    return f"{_state['host'].rstrip('/')}/ml/experiments/{_state['experiment_id']}/traces/{trace_id}"


class _NoopSpan:
    trace_id = None

    def set_inputs(self, inputs):
        pass

    def set_outputs(self, outputs):
        pass

    def set_attributes(self, attributes):
        pass


class _SafeSpan:
    """An MLflow span whose setters swallow MLflow errors."""

    def __init__(self, span):
        self._span = span
        self.trace_id = getattr(span, "trace_id", None)

    def _call(self, method, value):
        try:
            getattr(self._span, method)(value)
        except Exception as e:
            log.debug("span %s failed: %s", method, e)

    def set_inputs(self, inputs):
        self._call("set_inputs", inputs)

    def set_outputs(self, outputs):
        self._call("set_outputs", outputs)

    def set_attributes(self, attributes):
        self._call("set_attributes", attributes)


def _start(name: str, span_type: str):
    import mlflow

    return mlflow.start_span(name=name, span_type=span_type)


@contextlib.contextmanager
def span(name: str, inputs=None, span_type: str = "CHAIN"):
    manager, current = None, _NoopSpan()
    if enabled():
        try:
            manager = _start(name, span_type)
            current = _SafeSpan(manager.__enter__())
            if inputs is not None:
                current.set_inputs(inputs)
        except Exception as e:
            log.debug("span %s not started: %s", name, e)
            manager, current = None, _NoopSpan()
    try:
        yield current
    except BaseException as error:
        _exit(manager, error)
        raise
    else:
        _exit(manager, None)


def _exit(manager, error) -> None:
    if manager is None:
        return
    try:
        if error is None:
            manager.__exit__(None, None, None)
        else:
            manager.__exit__(type(error), error, error.__traceback__)
    except Exception as e:
        log.debug("span exit failed: %s", e)


def tag_trace(tags: dict) -> None:
    if not enabled():
        return
    try:
        import mlflow

        mlflow.update_current_trace(tags={k: str(v) for k, v in tags.items()})
    except Exception as e:
        log.debug("trace tags failed: %s", e)
