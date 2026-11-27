import pytest

SLOW_SHELL_SPAWNERS = {
    "powershell_candidates", "ps_cands", "bash_candidates", "zsh_candidates", "tcsh_candidates"}


def pytest_collection_modifyitems(config, items):
    for item in items:
        func = getattr(item, "function", None)
        if func is not None and set(func.__code__.co_names) & SLOW_SHELL_SPAWNERS:
            item.add_marker(pytest.mark.slow)
