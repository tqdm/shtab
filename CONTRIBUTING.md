# Contributing

## Tests

When contributing pull requests, it's a good idea to run basic checks locally:

```bash
# install development dependencies
shtab (main)$ pip install pre-commit -e ".[dev]"
shtab (main)$ pre-commit install  # install pre-commit checks
shtab (main)$ pytest              # run all tests
```

## Layout

Most of the magic lives in [`shtab/__init__.py`](./shtab/__init__.py).

- [shtab/](./shtab/)
  - [`__init__.py`](./shtab/__init__.py)
    - `complete()` - primary API, calls shell-specific versions
    - `complete_bash()`
    - `complete_zsh()`
    - `complete_tcsh()`
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
at <https://github.com/iterative/shtab/releases>. Tidy up the draft's
description before publishing it.
