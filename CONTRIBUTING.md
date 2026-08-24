# Contributing

## Tests

When contributing pull requests, it's a good idea to run basic checks locally:

```bash
shtab (main)$ pip install pre-commit
shtab (main)$ pre-commit install  # install pre-commit hooks into git workspace
shtab (main)$ pre-commit run -a   # run hooks on all files
```

Example scripts may also be installed via `pip install -e .` after modifying `pyproject.toml`:

```diff
diff --git a/pyproject.toml b/pyproject.toml
index edfd3b2..44c3748 100644
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -7,3 +7,3 @@ build-backend = "setuptools.build_meta"
 [tool.setuptools.packages.find]
-include = ["shtab", "shtab.*"]
+include = ["shtab", "shtab.*", "examples"]

@@ -77,2 +77,6 @@ dev = ["pytest>=6", "pytest-cov", "click"]
 shtab = "shtab.main:main"
+pathcomplete = "examples.pathcomplete:main"
+customcomplete = "examples.customcomplete:main"
+click-process = "examples.click_process:process"
+click-subcommand = "examples.click_subcommand:main"
```

## Layout

Most of the magic lives in [`shtab/__init__.py`](./shtab/__init__.py).

- [shtab/](./shtab/)
  - [`__init__.py`](./shtab/__init__.py)
    - `complete()` - primary API, calls shell-specific versions
    - `complete_bash()`
    - `complete_zsh()`
    - `complete_tcsh()`
    - `complete_fish()`
    - `complete_powershell()`
    - ...
    - `add_argument_to()` - convenience function for library integration
    - `Optional()`, `Required()`, `Choice()` - legacy helpers for advanced completion (e.g. dirs, files, `*.txt`)
  - [`main.py`](./shtab/main.py)
    - `get_main_parser()` - returns `shtab`'s own parser object
    - `main()` - `shtab`'s own CLI application

Given that the number of completions a program may need would likely be less
than a million, the focus is on readability rather than premature speed
optimisations. The generated code itself, on the other hand, should be fast.

Helper functions such as `replace_format` allow use of curly braces `{}` in
string snippets without clashes between Python's `str.format` and shell
parameter expansion.

The generated shell code itself is also meant to be readable.

## Releases

Tests and deployment are handled automatically by continuous integration. Simply
tag a commit `v{major}.{minor}.{patch}` and wait for a draft release to appear
at <https://github.com/tqdm/shtab/releases>. Tidy up the draft's
description before publishing it.
