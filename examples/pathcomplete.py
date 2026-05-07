#!/usr/bin/env python
"""
`argparse`-based CLI app using
`add_argument().complete = shtab.(FILE|DIR)` for file/dir tab completion.

See `customcomplete.py` for a more advanced version.
"""
import argparse

import shtab  # for completion magic


def get_main_parser():
    parser = argparse.ArgumentParser(prog="pathcomplete")
    shtab.add_argument_to(parser, ["-s", "--print-completion"]) # magic!

    # file & directory tab complete
    parser.add_argument("file", nargs="?").complete = shtab.FILE
    parser.add_argument("--dir", default=".").complete = shtab.DIRECTORY
    return parser


if __name__ == "__main__":
    parser = get_main_parser()
    args = parser.parse_args()
    print(f"received <file>={args.file!r} --dir={args.dir!r}")
