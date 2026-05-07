# Usage

There are two ways of using `shtab`:

- [CLI Usage](#cli-usage): `shtab`'s own CLI interface for external applications
    - may not require any code modifications whatsoever
    - end-users execute `shtab your_cli_app.your_parser_object`
- [Library Usage](#library-usage): as a library integrated into your CLI application
    - adds a couple of lines to your application
    - argument mode: end-users execute `your_cli_app --print-completion {bash,zsh,tcsh}`
    - subparser mode: end-users execute `your_cli_app completion {bash,zsh,tcsh}`

## CLI Usage

The only requirement is that external CLI applications provide an importable
`argparse.ArgumentParser` object (or alternatively an importable function which
returns a parser object). This may require a trivial code change.

Once that's done, simply put the output of `shtab --shell=your_shell
your_cli_app.your_parser_object` somewhere your shell looks for completions.

Below are various examples of enabling `shtab`'s own tab completion scripts.

!!! info
    If both shtab and the module it's completing are globally importable, eager
    usage is an option. "Eager" means automatically updating completions each
    time a terminal is opened.

=== "bash"

    ```sh
    shtab --shell=bash shtab.main.get_main_parser --error-unimportable \
      | sudo tee "$BASH_COMPLETION_COMPAT_DIR"/shtab
    ```

=== "Eager bash"

    There are a few options:

    ```sh
    # Install locally
    echo 'eval "$(shtab --shell=bash shtab.main.get_main_parser)"' \
      >> ~/.bash_completion

    # Install locally (lazy load for bash-completion>=2.8)
    echo 'eval "$(shtab --shell=bash shtab.main.get_main_parser)"' \
      > "${BASH_COMPLETION_USER_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/bash-completion}/completions/shtab"

    # Install system-wide
    echo 'eval "$(shtab --shell=bash shtab.main.get_main_parser)"' \
      | sudo tee "$(pkg-config --variable=completionsdir bash-completion)"/shtab

    # Install system-wide (legacy)
    echo 'eval "$(shtab --shell=bash shtab.main.get_main_parser)"' \
      | sudo tee "$BASH_COMPLETION_COMPAT_DIR"/shtab
    ```

=== "zsh"

    Note that `zsh` requires completion script files to be named `_{EXECUTABLE}`
    (with an underscore prefix).

    ```sh
    # note the underscore `_` prefix
    shtab --shell=zsh shtab.main.get_main_parser --error-unimportable \
      | sudo tee /usr/local/share/zsh/site-functions/_shtab
    ```

=== "Eager zsh"

    To be more eager, place the generated script somewhere in `$fpath`. For
    example, add these lines to the top of `~/.zshrc`:

    ```sh
    mkdir -p ~/.zsh/completions
    fpath=($fpath ~/.zsh/completions)  # must be before `compinit` lines
    shtab --shell=zsh shtab.main.get_main_parser -o ~/.zsh/completions/_shtab
    ```

=== "tcsh"

    ```sh
    shtab --shell=tcsh shtab.main.get_main_parser --error-unimportable \
      | sudo tee /etc/profile.d/shtab.completion.csh
    ```

=== "Eager tcsh"

    There are a few options:

    ```sh
    # Install locally
    echo 'shtab --shell=tcsh shtab.main.get_main_parser | source /dev/stdin' \
      >> ~/.cshrc

    # Install system-wide
    echo 'shtab --shell=tcsh shtab.main.get_main_parser | source /dev/stdin' \
      | sudo tee /etc/profile.d/eager-completion.csh
    ```

!!! tip
    See the [examples/](https://github.com/iterative/shtab/tree/main/examples)
    folder for more.

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
      | sudo tee "$BASH_COMPLETION_COMPAT_DIR"/MY_PROG
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

## Library Usage

!!! tip
    See the [examples/](https://github.com/iterative/shtab/tree/main/examples)
    folder for more.

Complex projects with subparsers and custom completions for paths matching
certain patterns (e.g. `--file=*.txt`) are fully supported (see
[examples/customcomplete.py](https://github.com/iterative/shtab/tree/main/examples/customcomplete.py)
or even
[iterative/dvc:commands/completion.py](https://github.com/iterative/dvc/blob/main/dvc/commands/completion.py)
for example).

Add direct support to scripts for a little more configurability:

=== "argparse"

    ```{.py title="pathcomplete.py" linenums="1" hl_lines="7 9-10"}
    #!/usr/bin/env python
    import argparse
    import shtab  # for completion magic

    def get_main_parser():
        parser = argparse.ArgumentParser(prog="pathcomplete")
        shtab.add_argument_to(parser, ["-s", "--print-completion"])  # magic!
        # file & directory tab complete
        parser.add_argument("file", nargs="?").complete = shtab.FILE
        parser.add_argument("--dir", default=".").complete = shtab.DIRECTORY
        return parser

    if __name__ == "__main__":
        parser = get_main_parser()
        args = parser.parse_args()
        print("received <file>=%r --dir=%r" % (args.file, args.dir))
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
