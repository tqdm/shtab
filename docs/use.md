# Usage

There are two ways of using `shtab`:

- [CLI Usage](#cli-usage): `shtab`'s own CLI interface for external applications
    - may not require any code modifications whatsoever
    - end-users execute `shtab your_cli_app.your_parser_object`
- [Library Usage](#library-usage): as a library integrated into your CLI application
    - adds a couple of lines to your application
    - argument mode: end-users execute `your_cli_app --print-completion {bash,zsh,tcsh,fish,powershell}`
    - subparser mode: end-users execute `your_cli_app completion {bash,zsh,tcsh,fish,powershell}`

## CLI Usage

The only requirement is that external CLI applications provide an importable
`argparse.ArgumentParser` object (or alternatively an importable function which
returns a parser object). This may require a trivial code change.

Then simply put the output of `shtab --shell=your_shell your_cli_app.your_parser_object` [somewhere](index.md#scripts) your shell looks for completions.

Below are various examples of enabling `shtab`'s own tab completion scripts.

!!! info
    If both `shtab` and the module it's completing are globally importable, eager
    usage is an option. "Eager" means automatically updating completions each
    time a terminal is opened, and likely should *not* use the `-u, --error-unimportable` flag.

    Terminal start might be slow if scripts are very complex.

=== "bash"

    ```sh
    shtab -u --shell=bash shtab.main.get_main_parser \
      | sudo tee /etc/bash_completion.d/shtab
    ```

    *Eager*

    ```sh
    # Install locally
    echo 'eval "$(shtab --shell=bash shtab.main.get_main_parser)"' \
      >> ~/.bash_completion

    # Install system-wide (pkg-config bash-completion --variable=compatdir)
    echo 'eval "$(shtab --shell=bash shtab.main.get_main_parser)"' \
      | sudo tee /etc/bash_completion.d/shtab

    # Install system-wide (pkg-config bash-completion --variable=completionsdir)
    echo 'eval "$(shtab --shell=bash shtab.main.get_main_parser)"' \
      | sudo tee /usr/share/bash-completion/completions/shtab
    ```

=== "zsh"

    Note that `zsh` requires completion script files to be named `_{EXECUTABLE}`
    (with an underscore prefix).

    ```sh
    # note the underscore `_` prefix
    shtab -u --shell=zsh shtab.main.get_main_parser \
      | sudo tee /usr/local/share/zsh/site-functions/_shtab
    ```

    *Eager*

    Place the generated script somewhere in `$fpath`.
    For example, add these lines *to the top* of `~/.zshrc`:

    ```sh
    mkdir -p ~/.zsh/completions
    fpath=($fpath ~/.zsh/completions)  # must be before `compinit` lines
    shtab --shell=zsh shtab.main.get_main_parser -o ~/.zsh/completions/_shtab
    ```

=== "tcsh"

    ```sh
    shtab -u --shell=tcsh shtab.main.get_main_parser \
      | sudo tee /etc/profile.d/completion_shtab.csh
    ```

    *Eager*

    ```sh
    # Install locally
    echo 'shtab --shell=tcsh shtab.main.get_main_parser | source /dev/stdin' \
      >> ~/.cshrc

    # Install system-wide
    echo 'shtab --shell=tcsh shtab.main.get_main_parser | source /dev/stdin' \
      | sudo tee /etc/profile.d/completion_shtab.csh
    ```

=== "fish"

    ```sh
    # Install locally
    shtab -u --shell=fish shtab.main.get_main_parser \
      -o ~/.config/fish/completions/shtab.fish

    # Install system-wide (pkg-config fish --variable=completionsdir)
    shtab -u --shell=fish shtab.main.get_main_parser \
      | sudo tee /usr/share/fish/vendor_completions.d/shtab.fish

=== "powershell"

    ```powershell
    shtab --shell=powershell shtab.main.get_main_parser --error-unimportable `
      | Out-File -FilePath ~\.config\powershell\completions\shtab.ps1
    # Add to $PROFILE:
    . ~\.config\powershell\completions\shtab.ps1
    ```

    Eager:

    Add the following to your PowerShell profile (`$PROFILE`):

    ```powershell
    shtab --shell=powershell shtab.main.get_main_parser `
      | Out-String | Invoke-Expression
    ```

    Or save to a file and dot-source it from your profile:

    ```powershell
    shtab --shell=powershell shtab.main.get_main_parser `
      | Out-File -FilePath ~\.config\powershell\completions\shtab.ps1
    # Add to $PROFILE:
    . ~\.config\powershell\completions\shtab.ps1
    ```

Any existing `argparse`-based scripts should be supported with minimal effort.
For example, starting with this existing code:

```{.py title="main.py" linenums="1" #main.py}
#!/usr/bin/env python
import argparse

def get_main_parser():
    parser = argparse.ArgumentParser(prog="MY_PROG", ...)
    parser.add_argument(...)
    parser.add_subparsers(...)
    ...
    return parser

if __name__ == "__main__":
    parser = get_main_parser()
    args = parser.parse_args()
    ...
```

Assuming this code example is installed in `MY_PROG.command.main`, simply run:

=== "bash"

    ```sh
    shtab --shell=bash -u MY_PROG.command.main.get_main_parser \
      | sudo tee /etc/bash_completion.d/MY_PROG
    ```

=== "zsh"

    ```sh
    shtab --shell=zsh -u MY_PROG.command.main.get_main_parser \
      | sudo tee /usr/local/share/zsh/site-functions/_MY_PROG
    ```

=== "tcsh"

    ```sh
    shtab --shell=tcsh -u MY_PROG.command.main.get_main_parser \
      | sudo tee /etc/profile.d/MY_PROG.completion.csh
    ```

=== "fish"

    ```sh
    shtab --shell=fish -u MY_PROG.command.main.get_main_parser \
      | sudo tee /usr/share/fish/vendor_completions.d/MY_PROG.fish

=== "powershell"

    ```powershell
    shtab --shell=powershell -u MY_PROG.command.main.get_main_parser `
      | Out-File -FilePath ~\.config\powershell\completions\MY_PROG.ps1
    . ~\.config\powershell\completions\MY_PROG.ps1
    ```

## Library Usage

!!! tip
    For more, see:

    - `shtab`'s own [examples/](https://github.com/tqdm/shtab/tree/main/examples) folder
    - [git-fame#135](https://github.com/casperdcl/git-fame/commit/d2577f821368fd2337e975dc6a31ce73ab09e7ed) for how to migrate to using `shtab` in a real project

Complex projects with subparsers and custom completions for paths matching
certain patterns (e.g. `--file=*.txt` or `--branch=$(git branch)`) are fully supported (see
[examples/customcomplete.py](https://github.com/tqdm/shtab/tree/main/examples/customcomplete.py)
or even
[treeverse/dvc:commands/completion.py](https://github.com/treeverse/dvc/blob/main/dvc/commands/completion.py)
for example).

Add direct support to scripts for a little more configurability:

=== "argparse"

    ```{.py title="pathcomplete.py" linenums="1" hl_lines="7 9-11 14"}
    #!/usr/bin/env python
    import argparse
    import shtab  # for completion magic

    def get_main_parser():
        parser = argparse.ArgumentParser(prog="pathcomplete")
        shtab.add_argument_to(parser, ["-s", "--print-completion"])  # magic!
        # file & directory tab complete
        parser.add_argument("file", nargs="?").complete = shtab.FILE
        parser.add_argument("--dir", default=".").complete = shtab.DIRECTORY
        parser.add_argument("--config").complete = shtab.glob('*.toml', '*.yml', '*.yaml', '*.json')
        # WARNING: shtab.cmd is (re)run by your shell on each tab press, so could be slow
        parser.add_argument("--branch",
                            help="git branch from current workdir").complete = shtab.cmd("git branch")
        return parser

    if __name__ == "__main__":
        parser = get_main_parser()
        args = parser.parse_args()
        print(f"received <file>={args.file} --dir={args.dir}"
              f" --config={args.config} --branch={args.branch}")
    ```

=== "docopt"

    Simply use [argopt](https://pypi.org/project/argopt) to create a parser
    object from [docopt](https://pypi.org/project/docopt) syntax:

    ```{.py title="docopt-greeter.py" linenums="1" hl_lines="17"}
    #!/usr/bin/env python
    """Greetings and partings.

    Usage:
      greeter [options] [<you>] [<me>]

    Options:
      -g, --goodbye  : Say "goodbye" (instead of "hello")

    Arguments:
      <you>  : Your name [default: Anon]
      <me>  : My name [default: Casper]
    """
    import argopt, shtab

    parser = argopt.argopt(__doc__)
    shtab.add_argument_to(parser, ["-s", "--print-completion"])  # magic!
    if __name__ == "__main__":
        args = parser.parse_args()
        msg = "k thx bai!" if args.goodbye else "hai!"
        print("{} says '{}' to {}".format(args.me, msg, args.you))
    ```
