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
import argopt

import shtab

parser = argopt.argopt(__doc__)
shtab.add_argument_to(parser, ["-s", "--print-completion"]) # magic!
if __name__ == "__main__":
    args = parser.parse_args()

    msg = "k thx bai!" if args.goodbye else "hai!"
    print(f"{args.me} says '{msg}' to {args.you}")
