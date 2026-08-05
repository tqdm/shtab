![shtab](https://tqdm.github.io/img/shtab-banner.png)

[![Tests](https://img.shields.io/github/actions/workflow/status/tqdm/shtab/test.yml?logo=github&label=tests)](https://github.com/tqdm/shtab/actions)
[![Coverage](https://codecov.io/gh/tqdm/shtab/branch/main/graph/badge.svg)](https://codecov.io/gh/tqdm/shtab)
[![Quality](https://app.codacy.com/project/badge/Grade/0ce50da5c6e04236a891b092c7012753)](https://app.codacy.com/gh/tqdm/shtab/dashboard)
[![PyPI](https://img.shields.io/pypi/v/shtab.svg?label=pip&logo=PyPI&logoColor=white)](https://pypi.org/project/shtab)
[![Conda](https://img.shields.io/conda/v/conda-forge/shtab.svg?label=conda&logo=conda-forge)](https://anaconda.org/conda-forge/shtab)
[![Downloads](https://static.pepy.tech/personalized-badge/shtab?left_text=downloads%2Fmonth)](https://pepy.tech/project/shtab)
[![LICENCE](https://img.shields.io/pypi/l/shtab.svg)](https://raw.githubusercontent.com/tqdm/shtab/main/LICENCE)

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
    - `fish`
    - `powershell`
- Supports
    - [`argparse`](https://docs.python.org/library/argparse)
    - [`docopt`](https://pypi.org/project/docopt) (via [`argopt`](https://pypi.org/project/argopt))
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

- Ensure that `shtab` and the application you're trying to complete are both accessible from your environment.
- Ensure that `prog` is set:
    - if using [`options.entry_points.console_scripts=MY_PROG=...`](https://setuptools.pypa.io/en/latest/userguide/entry_point.html), then ensure the main parser's `prog` matches `argparse.ArgumentParser(prog="MY_PROG")` or override it using `shtab MY_PROG.get_main_parser --prog=MY_PROG`.
    - if executing a script file `./MY_PROG.py` (with a [shebang](<https://en.wikipedia.org/wiki/Shebang_(Unix)>) `#!/usr/bin/env python`) directly, then use `argparse.ArgumentParser(prog="MY_PROG.py")` or override it using `shtab MY_PROG.get_main_parser --prog=MY_PROG.py`.
- Ensure that all arguments have `help` messages (`parser.add_argument('positional', help="documented; i.e. not hidden")`).
- Path completion is disabled by default, and must be enabled explicitly (`parser.add_argument('positional').complete = shtab.FILE`).
- [Ask a general question on StackOverflow](https://stackoverflow.com/questions/tagged/shtab).
- [Report bugs and open feature requests on GitHub][issues].

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

Please do open [issues] & [pull requests](https://github.com/tqdm/shtab/pulls)!

See [CONTRIBUTING.md](https://github.com/tqdm/shtab/tree/main/CONTRIBUTING.md) for more guidance.

[issues]: https://github.com/tqdm/shtab/issues

[![git-fame](https://git-fame.cdcl.ml/gh/tqdm/shtab?min=1&w=1&M=1&C=1&enum=1)](https://git-fame.cdcl.ml/gh/tqdm/shtab?w=1&M=1&C=1&enum=1)

[![Hits](https://cgi.cdcl.ml/hits?q=shtab&style=social&r=https://github.com/tqdm/shtab&a=hidden)](https://cgi.cdcl.ml/hits?q=shtab&a=plot&r=https://github.com/tqdm/shtab&style=social)
