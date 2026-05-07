![shtab](https://static.iterative.ai/img/shtab/banner.png)

[![Downloads](https://img.shields.io/pypi/dm/shtab.svg?label=pypi%20downloads&logo=PyPI&logoColor=white)](https://pepy.tech/project/shtab)
[![Tests](https://img.shields.io/github/actions/workflow/status/iterative/shtab/test.yml?logo=github&label=tests)](https://github.com/iterative/shtab/actions)
[![Coverage](https://codecov.io/gh/iterative/shtab/branch/main/graph/badge.svg)](https://codecov.io/gh/iterative/shtab)
[![PyPI](https://img.shields.io/pypi/v/shtab.svg?label=pip&logo=PyPI&logoColor=white)](https://pypi.org/project/shtab)
[![conda-forge](https://img.shields.io/conda/v/conda-forge/shtab.svg?label=conda&logo=conda-forge)](https://anaconda.org/conda-forge/shtab)

- What: Automatically generate shell tab completion scripts for Python CLI apps
- Why: Speed & correctness. Alternatives like
  [argcomplete](https://pypi.org/project/argcomplete) and
  [pyzshcomplete](https://pypi.org/project/pyzshcomplete) are slow and have side-effects
- How: `shtab` processes an `argparse.ArgumentParser` object to generate a tab completion script for your shell

## Features

- Outputs tab completion scripts for
    - `bash`
    - `zsh`
    - `tcsh`
-   Supports
    - [argparse](https://docs.python.org/library/argparse)
    - [docopt](https://pypi.org/project/docopt) (via [argopt](https://pypi.org/project/argopt))
- Supports arguments, options and subparsers
- Supports choices (e.g. `--say={hello,goodbye}`)
- Supports file and directory path completion
- Supports custom path completion (e.g. `--file={*.txt}`)

------------------------------------------------------------------------

## Installation

=== "pip"

    ```sh
    pip install shtab
    ```

=== "conda"

    ```sh
    conda install -c conda-forge shtab
    ```

`bash` users who have never used any kind of tab completion before should also
follow the OS-specific instructions below.

=== "Ubuntu/Debian"

    Recent versions should have completion already enabled. For older versions,
    first run `sudo apt install --reinstall bash-completion`, then make sure
    these lines appear in `~/.bashrc`:

    ```sh
    # enable bash completion in interactive shells
    if ! shopt -oq posix; then
      if [ -f /usr/share/bash-completion/bash_completion ]; then
        . /usr/share/bash-completion/bash_completion
      elif [ -f /etc/bash_completion ]; then
        . /etc/bash_completion
      fi
    fi
    ```

=== "MacOS"

    First run `brew install bash-completion`, then add the following to
    `~/.bash_profile`:

    ```sh
    if [ -f $(brew --prefix)/etc/bash_completion ]; then
      . $(brew --prefix)/etc/bash_completion
    fi
    ```

## FAQs

Not working?

- Make sure that `shtab` and the application you're trying to complete are both accessible from your environment.
- Make sure that `prog` is set:
    - if using [`options.entry_points.console_scripts=MY_PROG=...`](https://setuptools.pypa.io/en/latest/userguide/entry_point.html), then ensure the main parser's `prog` matches `argparse.ArgumentParser(prog="MY_PROG")` or override it using `shtab MY_PROG.get_main_parser --prog=MY_PROG`.
    - if executing a script file `./MY_PROG.py` (with a [shebang](<https://en.wikipedia.org/wiki/Shebang_(Unix)>) `#!/usr/bin/env python`) directly, then use `argparse.ArgumentParser(prog="MY_PROG.py")` or override it using `shtab MY_PROG.get_main_parser --prog=MY_PROG.py`.
- Make sure that all arguments have `help` messages (`parser.add_argument('positional', help="documented; i.e. not hidden")`).
- [Ask a general question on StackOverflow](https://stackoverflow.com/questions/tagged/shtab).
- [Report bugs and open feature requests on GitHub][GH-issue].

"Eager" installation (completions are re-generated upon login/terminal start) is
recommended. Naturally, `shtab` and the CLI application to complete should be
accessible/importable from the login environment. If installing `shtab` in a
different virtual environment, you'd have to add a line somewhere appropriate
(e.g. `$CONDA_PREFIX/etc/conda/activate.d/env_vars.sh`).

By default, `shtab` will silently do nothing if it cannot import the requested
application. Use `-u, --error-unimportable` to noisily complain.

## Alternatives

- [argcomplete](https://pypi.org/project/argcomplete)
    - executes the underlying script *every* time `<TAB>` is pressed (slow and has side-effects)
- [pyzshcomplete](https://pypi.org/project/pyzshcomplete)
    - executes the underlying script *every* time `<TAB>` is pressed (slow and has side-effects)
    - only provides `zsh` completion
- [click](https://pypi.org/project/click)
    - different framework completely replacing the builtin `argparse`
    - solves multiple problems (rather than POSIX-style "do one thing well")

## Contributions

Please do open [issues][GH-issue] & [pull requests][GH-pr]! Some ideas:

- support `fish` ([#174](https://github.com/iterative/shtab/pull/174))
- support `powershell`

See
[CONTRIBUTING.md](https://github.com/iterative/shtab/tree/main/CONTRIBUTING.md)
for more guidance.

[![Hits](https://cgi.cdcl.ml/hits?q=shtab&style=social&r=https://github.com/iterative/shtab&a=hidden)](https://cgi.cdcl.ml/hits?q=shtab&a=plot&r=https://github.com/iterative/shtab&style=social)

[GH-issue]: https://github.com/iterative/shtab/issues
[GH-pr]: https://github.com/iterative/shtab/pulls
