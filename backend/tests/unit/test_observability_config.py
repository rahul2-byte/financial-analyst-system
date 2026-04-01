import inspect

from app.core import observability


def test_observability_uses_central_settings_instead_of_os_getenv():
    source = inspect.getsource(observability)
    assert "os.getenv(" not in source
