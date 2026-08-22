#!/usr/bin/env python
from importlib.metadata import version

import click

import shtab.click

ARG_HELP = version('click') >= '8.5'


@click.group()
def main():
    """Main (root) CLI group command."""


@main.command()
@click.argument('you', default="Anon", **({'help': "Your name"} if ARG_HELP else {}))
@click.argument('me', default="Casper", **({'help': "My name"} if ARG_HELP else {}))
@click.option('-g', '--goodbye', is_flag=True, help='Say "goodbye" (instead of "hello").')
@click.option('--file', type=click.File(), help="Input file to read from.")
@click.option('--path', type=click.Path(exists=True, file_okay=False),
              help="Input directory to read from.")
def greeter(you, me, goodbye, file, path):
    """Greetings and partings."""
    msg = "k thx bai!" if goodbye else "hai!"
    print(f"{me} says '{msg}' to {you} after reading from {file} and {path}")


main.command()(shtab.click.completion) # magic!

if __name__ == '__main__':
    main()
