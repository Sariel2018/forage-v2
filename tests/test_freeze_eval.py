import inspect
from forage.core.loop import run


def test_mode_parameter_exists():
    """run() should accept mode parameter (v2: replaces freeze_eval)."""
    sig = inspect.signature(run)
    assert "mode" in sig.parameters, "run() should accept mode parameter"
