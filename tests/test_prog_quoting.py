"""Regression tests for quoting parser.prog in generated scripts."""
from argparse import ArgumentParser

import shtab


RAW_PROG = "tool; echo INJECTED"


def test_quote_prog_by_shell():
    assert shtab.quote_prog("bash", RAW_PROG) == "'tool; echo INJECTED'"
    assert shtab.quote_prog("powershell", RAW_PROG) == "'tool; echo INJECTED'"
    assert "\\;" in shtab.quote_prog("tcsh", RAW_PROG)
    assert "\\;" in shtab.quote_prog("fish", RAW_PROG)
    assert shtab.quote_prog("zsh", RAW_PROG).startswith("'")


def test_generated_scripts_quote_prog():
    parser = ArgumentParser(prog=RAW_PROG)
    parser.add_argument("--flag", choices=["a", "b"])
    scripts = {shell: shtab.complete(parser, shell=shell) for shell in shtab.SUPPORTED_SHELLS}

    assert scripts["bash"].rstrip().endswith("'tool; echo INJECTED'")
    assert "CommandName 'tool; echo INJECTED'" in scripts["powershell"]
    assert "#compdef 'tool; echo INJECTED'" in scripts["zsh"]
    assert "complete tool\\;\\ echo\\ INJECTED \\" in scripts["tcsh"]
    assert "complete -c tool\\;\\ echo\\ INJECTED -e" in scripts["fish"]
