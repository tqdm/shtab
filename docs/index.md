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

- Outputs tab completion scripts for multiple shells
    - `bash`, `zsh`, `fish`, `tcsh`, `powershell`
- Supports
    - [`argparse`](https://docs.python.org/library/argparse)
    - [`docopt`](https://pypi.org/project/docopt) (via [`argopt`](https://pypi.org/project/argopt))
    - [`click`](https://pypi.org/project/click)
- `<arguments>`, `--options` and `sub commands`
- Choices (`--say={hello,goodbye}`)
- Paths (`--file={*.y*ml,*.toml}`, `--dir=*/`)
- Dynamic shell commands (`--branch=$(git branch)`)

------------------------------------------------------------------------

## Installation

### scripts

!!! tip
    TL;DR where to save a completion script for a program called `NAME`

shell | location
--|--
[`bash`](https://github.com/scop/bash-completion/blob/main/doc/configuration.md) | `/etc/bash_completion.d/NAME`
[`zsh`](https://github.com/zsh-users/zsh-completions/blob/master/zsh-completions-howto.org) | `/usr/local/share/zsh/site-functions/_NAME`
[`tcsh`](https://github.com/tcsh-org/tcsh/blob/master/complete.tcsh) | `/etc/profile.d/completion_NAME.csh`, source in `~/.cshrc` or `~/.tcshrc`
[`fish`](https://fishshell.com/docs/current/completions.html#where-to-put-completions) | `~/.config/fish/completions/NAME.fish`
[`powershell`](https://learn.microsoft.com/en-us/powershell/scripting/learn/shell/creating-profiles#adding-customizations-to-your-profile) | `~\.config\powershell\completions\NAME.ps1`, source in `$PROFILE`

For more information, click on the shells above, and/or see [CLI Usage](use.md#cli-usage).

### `shtab`

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

- Ensure that `shtab` and the application you're trying to complete are both accessible from your environment.
- Ensure that `prog` matches the executable name:
    - if using [`project.scripts.MY-PROG=...`](https://setuptools.pypa.io/en/latest/userguide/entry_point.html), then
        - set the main parser's name (`argparse.ArgumentParser(prog="MY-PROG")`, `argopt(prog="MY-PROG")`, `click.group("MY-PROG")`, `click.command("MY-PROG")`, etc)
        - or override it using `shtab MY_PROG.get_main_parser --prog=MY-PROG`
    - if executing a script file `./MY_PROG.py` (with a [shebang](<https://en.wikipedia.org/wiki/Shebang_(Unix)>) `#!/usr/bin/env python`) directly, then use `prog="MY_PROG.py"`
- Any suppressed argument (`help=argparse.SUPPRESS`, click `hidden=True`/`deprecated=True`) is skipped.
- Default completion (when no choices are specified) is disabled. Enable it explicitly via e.g. `parser.add_argument('positional').complete = shtab.FILE`.
- Some shells (e.g. `zsh`, `fish`) print information during tab completion:
    - subparser `description` takes precedence over `help`
    - argument `metavar` takes precedence over `dest`
- [Ask a general question on StackOverflow](https://stackoverflow.com/questions/tagged/shtab).
- [Report bugs and open feature requests on GitHub][issues].

## Alternatives

All these execute the underlying script *every* time `<TAB>` is pressed (slow and have side-effects):

- [argcomplete](https://pypi.org/project/argcomplete)
- [pyzshcomplete](https://pypi.org/project/pyzshcomplete) (only provides `zsh` completion)
- [click](https://pypi.org/project/click) (don't want to migrate away from `click`? Use `shtab`'s one-liner `click` integration [in the CLI](use.md#click) or [in a library](use.md#library-usage))

## Contributions

Please do open [issues] & [pull requests](https://github.com/tqdm/shtab/pulls)!

See [CONTRIBUTING.md](https://github.com/tqdm/shtab/blob/main/CONTRIBUTING.md) for more guidance.

[issues]: https://github.com/tqdm/shtab/issues

[![git-fame](https://git-fame.cdcl.ml/gh/tqdm/shtab?min=1&w=1&M=1&C=1&enum=1)](https://git-fame.cdcl.ml/gh/tqdm/shtab?w=1&M=1&C=1&enum=1)

[![Hits](https://cgi.cdcl.ml/hits?q=shtab&style=social&r=https://github.com/tqdm/shtab&a=hidden)](https://cgi.cdcl.ml/hits?q=shtab&a=plot&r=https://github.com/tqdm/shtab&style=social)
