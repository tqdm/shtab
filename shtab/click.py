"""
Add "completion" command to `main` click group:

>>> import shtab.click
>>> main.command()(shtab.click.completion)
"""
import argparse
import logging

import click

from . import DIRECTORY, FILE, SUPPORTED_SHELLS
from . import complete as _complete

__all__ = ['completion', 'complete']
log = logging.getLogger(__name__)


@click.argument('shell', default="bash", type=click.Choice(SUPPORTED_SHELLS))
@click.option('--prefix', default=None, help="Prepended to generated functions to avoid clashes.")
@click.option('--preamble', default="", help="Prepended to generated script.")
@click.pass_context
def completion(ctx, shell, prefix, preamble):
    """Print shell completion script."""
    root = ctx.find_root()
    print(complete(root.command, shell=shell, root_prefix=prefix, preamble=preamble))


def complete(command: click.Command, **kwargs):
    """
    Generate a completion script for the given click command.
    See <../../examples/click_greeter.py> for usage.

    kwargs:
      See `shtab.complete`.
    """
    parser = click2argparse(command)
    return _complete(parser, **kwargs)


def _complete_paths(arg, param):
    if isinstance(param.type, click.File):
        # for safety, don't complete files in write-only (creation) mode
        arg.complete = FILE if set("ra+") & set(param.type.mode.lower()) else DIRECTORY
    elif isinstance(param.type, click.Path):
        if param.type.file_okay:
            arg.complete = FILE
        elif param.type.dir_okay:
            arg.complete = DIRECTORY


def click2argparse(command: click.Command, parser=None):
    if parser is None:
        log.debug("parser:%s", command.name)
        parser = argparse.ArgumentParser(prog=command.name, description=command.help)
    for param in command.params:
        if getattr(param, 'deprecated', False): # click>=8.2
            continue
        if getattr(param, 'hidden', False):     # pallets/click#3788
            continue

        spec = {'help': getattr(param, 'help', None)} # click>=8.5
        if param.param_type_name == 'option':
            log.debug("optional:%s", param.opts)
            if param.is_flag:
                spec['action'] = 'store_true'
            else:
                spec['metavar'] = param.metavar
                spec['nargs'] = param.nargs
                spec['required'] = param.required
            if isinstance(param.type, click.Choice):
                spec['choices'] = param.type.choices
            log.debug("spec:%s", spec)
            arg = parser.add_argument(*param.opts, **spec)
            _complete_paths(arg, param)
        elif param.param_type_name == 'argument':
            log.debug("positional:%s", param.name)
            if param.nargs == -1:
                spec['nargs'] = '+' if param.required else '*'
            else:
                spec['nargs'] = param.nargs
            if isinstance(param.type, click.Choice):
                spec['choices'] = param.type.choices
            log.debug("spec:%s", spec)
            arg = parser.add_argument(param.name, **spec)
            _complete_paths(arg, param)

    if hasattr(command, 'commands') and len(command.commands) > 0:
        log.debug("subcommands:%s", command.commands)
        subparsers = parser.add_subparsers(dest=command.name, help=command.short_help,
                                           description=command.help, required=True)
        for name, subcmd in command.commands.items():
            if subcmd.hidden or getattr(subcmd, 'deprecated', False):       # click>=8.2
                continue
            log.debug("subcommand:%s", name)
            subparser = subparsers.add_parser(name, help=subcmd.short_help,
                                              description=subcmd.help)
            click2argparse(subcmd, subparser)
    return parser
