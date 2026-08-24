#!/usr/bin/env python
"""
`argparse`-based CLI app with custom file completion as well as subparsers.

See `pathcomplete.py` for a more basic version.
"""
import argparse
from textwrap import dedent

import shtab  # for completion magic

# WARNING: shtab.cmd is (re)run by your shell on each tab press, so could be slow
COMPLETE_TOKEN = shtab.cmd("head -c5 /dev/random | base32")
# override powershell function to a Windows-compatible approximate equivalent
COMPLETE_TOKEN['preamble']['powershell'] = (   # type: ignore[index]
    f"function {COMPLETE_TOKEN['powershell']}"
    " { Get-Random -Count 1 -InputObject (10000..99999) }")


def process(args):
    print(f"received <token>={args.token} [<suffix>={args.suffix}]"
          f" --input-file={args.input_name} --output-name={args.output_name}"
          f" --compose-file={args.compose_file} --greeting={args.greeting}"
          f" --hidden-opt={args.hidden_opt}")


main_parser = argparse.ArgumentParser(prog="customcomplete")
subparsers = main_parser.add_subparsers(dest="subcommand", required=True)
parser = subparsers.add_parser("completion", help="print tab completion")
shtab.add_argument_to(parser, "shell", parent=main_parser) # magic!

# mypy: disable-error-code="attr-defined"
parser = subparsers.add_parser("process", help="parse files")
# dynamic command tab completion builtin shortcut
parser.add_argument("token").complete = COMPLETE_TOKEN
# file tab completion builtin shortcut
parser.add_argument("-i", "--input-file", dest="input_name").complete = shtab.FILE
# directory tab completion builtin shortcut
parser.add_argument(
    "-o",
    "--output-name",
    help=("output file name. Completes directory names to avoid users"
          " accidentally overwriting existing files."),
).complete = shtab.DIRECTORY
# glob pattern tab completion builtin shortcut
parser.add_argument("--compose-file",
                    metavar="yaml").complete = shtab.glob("docker-compose*.yml",
                                                          "docker-compose*.yaml")
parser.add_argument("suffix", choices=['json', 'csv'], default='json', nargs='?',
                    help="Output format")
# custom tab completion function
parser.add_argument("--greeting").complete = {
    'bash': "_shtab_txt_or_hello",
    # NOTE: _files -g '(*.txt)' doesn't work inside $()
    # NOTE: without subdir recursion: "($(printf '%s ' *.txt(N)) hello salut hola ciao)",
    'zsh': "($(find -name '*.txt' | sed -e 's,^./,,') hello salut hola ciao)",
    # NOTE: f:{*.txt} doesn't work alongside ``/()
    'fish': "(_shtab_txt_or_hello)",
    'tcsh': "`_shtab_txt_or_hello`",
    'preamble': {
        'bash': dedent("""
          _shtab_txt_or_hello(){
            # NOTE: function name `*_file*` implies `compopt -o filenames`
            compgen -f -X '!*.txt' -- $1
            compgen -d -- $1  # recurse into subdirs
            compgen -W 'hello salut hola ciao' -- $1
          }"""),
        'fish': dedent("""
          function _shtab_txt_or_hello
            set comp (commandline -ct)
            __fish_complete_path "$comp" | string match -e '*.txt'
            __fish_complete_path "$comp" | string match -e '*/' # recurse into subdirs
            string match -e -- "$comp" hello salut hola ciao
          end"""),
        'tcsh': "alias _shtab_txt_or_hello"
                " 'find -name \"*.txt\" | sed -e \"s,^./,,\" ; echo hello salut hola ciao'",
    }} # yapf: disable
# SUPPRESS help to exclude from CLI --help & completions
parser.add_argument("--hidden-opt", action='store_true', help=argparse.SUPPRESS)
parser.set_defaults(func=process)


def main(args=None):
    args = main_parser.parse_args(args=args)
    args.func(args)


if __name__ == '__main__':
    main()
