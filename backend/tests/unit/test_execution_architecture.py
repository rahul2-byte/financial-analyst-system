import importlib

import pytest


def test_legacy_tool_executor_wrapper_is_removed_from_runtime_path():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.core.tools.tool_executor")
