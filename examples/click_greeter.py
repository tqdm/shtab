#!/usr/bin/env python
from importlib.metadata import version

import click

import shtab.click

ARG_HELP = version('click') >= '8.5'


@click.command()
@click.argument('you', default="Anon", **({'help': "Your name"} if ARG_HELP else {}))
@click.argument('me', default="Casper", **({'help': "My name"} if ARG_HELP else {}))
@click.option('-g', '--goodbye', is_flag=True, help='Say "goodbye" (instead of "hello").')
@click.option('--print-completion', default=None, required=False,
              type=click.Choice(shtab.click.SUPPORTED_SHELLS),
              help="Print shell completion script.")
@click.pass_context
def greeter(ctx, you, me, goodbye, print_completion):
    """Greetings and partings."""
    if print_completion:
        root = ctx.find_root()
        print(shtab.click.complete(root.command, shell=print_completion)) # magic!
        return
    msg = "k thx bai!" if goodbye else "hai!"
    print(f"{me} says '{msg}' to {you}")


if __name__ == '__main__':
    greeter()      # pylint: disable=no-value-for-parameter
