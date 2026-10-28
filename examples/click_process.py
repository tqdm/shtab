#!/usr/bin/env python
from importlib.metadata import version

import click

import shtab.click

ARG_HELP = version('click') >= '8.5'


@click.command('click-process')
@shtab.click.option()  # magic!
@click.argument('out-dir', type=click.Path(file_okay=False), required=False,
                **({'help': "Output directory."} if ARG_HELP else {}))
@click.option('--config', type=click.File(), help="Config file.")
@click.option('-q', '--quiet', is_flag=True, help="Suppress output.")
def process(config, out_dir, quiet):
    """Click example CLI with shtab."""
    if not quiet:
        print(f"Reading from {config} and writing to {out_dir}")


if __name__ == '__main__':
    process()  # pylint: disable=no-value-for-parameter
