"""
Tests for `shtab`.
"""
import logging
import os
import subprocess
from argparse import ArgumentParser

import pytest

import shtab
from shtab.main import get_main_parser, main

fix_shell = pytest.mark.parametrize("shell", shtab.SUPPORTED_SHELLS)


class Bash:
    def __init__(self, init_script=""):
        self.init = init_script

    def test(self, cmd="1", failure_message=""):
        """Equivalent to `bash -c '{init}; [[ {cmd} ]]'`."""
        init = self.init + "\n" if self.init else ""
        proc = subprocess.Popen(["bash", "-o", "pipefail", "-euc", f"{init}[[ {cmd} ]]"])
        stdout, stderr = proc.communicate()
        assert (0 == proc.wait() and not stdout and not stderr), f"""\
{failure_message}
{cmd}
=== stdout ===
{stdout or ""}=== stderr ===
{stderr or ""}"""

    def compgen(self, compgen_cmd, word, expected_completions, failure_message=""):
        self.test(
            f'"$(echo $(compgen {compgen_cmd} -- "{word}"))" = "{expected_completions}"',
            failure_message,
        )


@pytest.mark.parametrize("init,test", [("export FOO=1", '"$FOO" -eq 1'), ("", '-z "${FOO-}"')])
def test_bash(init, test):
    shell = Bash(init)
    shell.test(test)


def test_bash_compgen():
    shell = Bash()
    shell.compgen('-W "foo bar foobar"', "fo", "foo foobar")


def test_choices():
    assert "x" in shtab.Optional.FILE
    assert "" in shtab.Optional.FILE

    assert "x" in shtab.Required.FILE
    assert "" not in shtab.Required.FILE


@fix_shell
def test_main(shell, caplog):
    with caplog.at_level(logging.INFO):
        main(["-s", shell, "shtab.main.get_main_parser"])

    assert not caplog.record_tuples


@fix_shell
def test_main_self_completion(shell, caplog, capsys):
    with caplog.at_level(logging.INFO):
        try:
            main(["--print-own-completion", shell])
        except SystemExit:
            pass

    captured = capsys.readouterr()
    assert not captured.err
    expected = {
        "bash": "complete -o filenames -F _shtab_shtab shtab", "zsh": "_shtab_shtab_commands()",
        "tcsh": "complete shtab"}
    assert expected[shell] in captured.out

    assert not caplog.record_tuples


@pytest.mark.parametrize('output', ["-", "stdout", "test.txt"])
@fix_shell
def test_main_output_path(shell, caplog, capsys, change_dir, output):
    assert not capsys.readouterr().out
    with caplog.at_level(logging.INFO):
        try:
            main(["-s", shell, "shtab.main.get_main_parser", "-o", output])
        except SystemExit:
            pass

    captured = capsys.readouterr()
    assert not captured.err
    expected = {
        "bash": "complete -o filenames -F _shtab_shtab shtab", "zsh": "_shtab_shtab_commands()",
        "tcsh": "complete shtab"}

    if output in ("-", "stdout"):
        assert expected[shell] in captured.out
    else:
        assert not captured.out
        assert expected[shell] in (change_dir / output).read_text()

    assert not caplog.record_tuples


@fix_shell
def test_prog_override(shell, caplog, capsys):
    with caplog.at_level(logging.INFO):
        main(["-s", shell, "--prog", "foo", "shtab.main.get_main_parser"])

    captured = capsys.readouterr()
    assert not captured.err
    if shell == "bash":
        assert "complete -o filenames -F _shtab_shtab foo" in captured.out

    assert not caplog.record_tuples


@fix_shell
def test_prog_scripts(shell, caplog, capsys):
    with caplog.at_level(logging.INFO):
        main(["-s", shell, "--prog", "script.py", "shtab.main.get_main_parser"])

    captured = capsys.readouterr()
    assert not captured.err
    script_py = [i.strip() for i in captured.out.splitlines() if "script.py" in i]
    if shell == "bash":
        assert script_py == ["complete -o filenames -F _shtab_shtab script.py"]
    elif shell == "zsh":
        assert script_py == [
            "#compdef script.py", "_describe 'script.py commands' _commands",
            'local context state line curcontext="$curcontext" '
            "one_or_more='(*)' remainder='(-)*' default='*::: :->script.py'",
            "_shtab_shtab_options+=(': :_shtab_shtab_commands' '*::: :->script.py')", "script.py)",
            "compdef _shtab_shtab -N script.py"]
    elif shell == "tcsh":
        assert script_py == ["complete script.py \\"]
    else:
        raise NotImplementedError(shell)

    assert not caplog.record_tuples


@fix_shell
def test_prefix_override(shell, caplog, capsys):
    with caplog.at_level(logging.INFO):
        main(["-s", shell, "--prefix", "foo", "shtab.main.get_main_parser"])
    captured = capsys.readouterr()
    print(captured.out)
    assert not captured.err

    if shell == "bash":
        shell = Bash(captured.out)
        shell.compgen('-W "${_shtab_foo_option_strings[*]}"', "--h", "--help")

    assert not caplog.record_tuples


@fix_shell
def test_complete(shell, caplog):
    parser = get_main_parser()
    with caplog.at_level(logging.INFO):
        completion = shtab.complete(parser, shell=shell)
    print(completion)

    if shell == "bash":
        shell = Bash(completion)
        shell.compgen('-W "${_shtab_shtab_option_strings[*]}"', "--h", "--help")

    assert not caplog.record_tuples


@fix_shell
def test_positional_choices(shell, caplog):
    parser = ArgumentParser(prog="test")
    parser.add_argument("posA", choices=["one", "two"])
    with caplog.at_level(logging.INFO):
        completion = shtab.complete(parser, shell=shell)
    print(completion)

    if shell == "bash":
        shell = Bash(completion)
        shell.compgen('-W "$_shtab_test_pos_0_choices"', "o", "one")

    assert not caplog.record_tuples


@fix_shell
def test_custom_complete(shell, caplog):
    parser = ArgumentParser(prog="test")
    parser.add_argument("posA").complete = {"bash": "_shtab_test_some_func"}
    preamble = {"bash": "_shtab_test_some_func() { compgen -W 'one two' -- $1 ;}"}
    with caplog.at_level(logging.INFO):
        completion = shtab.complete(parser, shell=shell, preamble=preamble)
    print(completion)

    if shell == "bash":
        shell = Bash(completion)
        shell.test('"$($_shtab_test_pos_0_COMPGEN o)" = "one"')

    assert not caplog.record_tuples


@fix_shell
def test_subparser_custom_complete(shell, caplog):
    parser = ArgumentParser(prog="test")
    subparsers = parser.add_subparsers()
    sub = subparsers.add_parser("sub", help="help message")
    sub.add_argument("posA").complete = {"bash": "_shtab_test_some_func"}
    preamble = {"bash": "_shtab_test_some_func() { compgen -W 'one two' -- $1 ;}"}
    with caplog.at_level(logging.INFO):
        completion = shtab.complete(parser, shell=shell, preamble=preamble)
    print(completion)

    if shell == "bash":
        shell = Bash(completion)
        shell.compgen('-W "${_shtab_test_subparsers[*]}"', "s", "sub")
        shell.compgen('-W "$_shtab_test_pos_0_choices"', "s", "sub")
        shell.test('"$($_shtab_test_sub_pos_0_COMPGEN o)" = "one"')
        shell.test('-z "${_shtab_test_COMPGEN-}"')

    assert not caplog.record_tuples


@fix_shell
def test_subparser_aliases(shell, caplog):
    parser = ArgumentParser(prog="test")
    subparsers = parser.add_subparsers()
    sub = subparsers.add_parser("sub", aliases=["xsub", "ysub"], help="help message")
    sub.add_argument("posA").complete = {"bash": "_shtab_test_some_func"}
    preamble = {"bash": "_shtab_test_some_func() { compgen -W 'one two' -- $1 ;}"}
    with caplog.at_level(logging.INFO):
        completion = shtab.complete(parser, shell=shell, preamble=preamble)
    print(completion)

    if shell == "bash":
        shell = Bash(completion)
        shell.compgen('-W "${_shtab_test_subparsers[*]}"', "s", "sub")
        shell.compgen('-W "${_shtab_test_pos_0_choices[*]}"', "s", "sub")
        shell.compgen('-W "${_shtab_test_subparsers[*]}"', "x", "xsub")
        shell.compgen('-W "${_shtab_test_pos_0_choices[*]}"', "x", "xsub")
        shell.compgen('-W "${_shtab_test_subparsers[*]}"', "y", "ysub")
        shell.compgen('-W "${_shtab_test_pos_0_choices[*]}"', "y", "ysub")
        shell.test('"$($_shtab_test_sub_pos_0_COMPGEN o)" = "one"')
        shell.test('-z "${_shtab_test_COMPGEN-}"')

    assert not caplog.record_tuples


@fix_shell
def test_subparser_colons(shell, caplog):
    parser = ArgumentParser(prog="test")
    subparsers = parser.add_subparsers()
    subparsers.add_parser("sub:cmd", help="help message")
    with caplog.at_level(logging.INFO):
        completion = shtab.complete(parser, shell=shell)
    print(completion)

    if shell == "bash":
        shell = Bash(completion)
        shell.compgen('-W "${_shtab_test_subparsers[*]}"', "s", "sub:cmd")
        shell.compgen('-W "${_shtab_test_pos_0_choices[*]}"', "s", "sub:cmd")
        shell.test('-z "${_shtab_test_COMPGEN-}"')

    assert not caplog.record_tuples


@fix_shell
def test_subparser_slashes(shell, caplog):
    parser = ArgumentParser(prog="test")
    subparsers = parser.add_subparsers()
    subparsers.add_parser("sub/cmd", help="help message")
    with caplog.at_level(logging.INFO):
        completion = shtab.complete(parser, shell=shell)
    print(completion)

    if shell == "bash":
        shell = Bash(completion)
        shell.compgen('-W "${_shtab_test_subparsers[*]}"', "s", "sub/cmd")
        shell.compgen('-W "${_shtab_test_pos_0_choices[*]}"', "s", "sub/cmd")
        shell.test('-z "${_shtab_test_COMPGEN-}"')
    elif shell == "zsh":
        assert "_shtab_test_sub/cmd" not in completion
        assert "_shtab_test_sub_cmd" in completion


@fix_shell
def test_add_argument_to_optional(shell, caplog):
    parser = ArgumentParser(prog="test")
    shtab.add_argument_to(parser, ["-s", "--shell"])
    with caplog.at_level(logging.INFO):
        completion = shtab.complete(parser, shell=shell)
    print(completion)

    if shell == "bash":
        shell = Bash(completion)
        shell.compgen('-W "${_shtab_test_option_strings[*]}"', "--s", "--shell")

    assert not caplog.record_tuples


@fix_shell
def test_add_argument_to_positional(shell, caplog, capsys):
    parser = ArgumentParser(prog="test")
    subparsers = parser.add_subparsers()
    sub = subparsers.add_parser("completion", help="help message")
    shtab.add_argument_to(sub, "shell", parent=parser)
    from argparse import Namespace

    with caplog.at_level(logging.INFO):
        completion_manual = shtab.complete(parser, shell=shell)
        with pytest.raises(SystemExit) as exc:
            sub._actions[-1](sub, Namespace(), shell)
            assert exc.type == SystemExit
            assert exc.value.code == 0
    completion, err = capsys.readouterr()
    print(completion)
    assert completion_manual.rstrip() == completion.rstrip()
    assert not err

    if shell == "bash":
        shell = Bash(completion)
        shell.compgen('-W "${_shtab_test_subparsers[*]}"', "c", "completion")
        shell.compgen('-W "${_shtab_test_pos_0_choices[*]}"', "c", "completion")
        shell.compgen('-W "${_shtab_test_completion_pos_0_choices[*]}"', "ba", "bash")
        shell.compgen('-W "${_shtab_test_completion_pos_0_choices[*]}"', "z", "zsh")

    assert not caplog.record_tuples


@fix_shell
def test_get_completer(shell):
    shtab.get_completer(shell)


def test_get_completer_invalid():
    try:
        shtab.get_completer("invalid")
    except NotImplementedError:
        pass
    else:
        raise NotImplementedError("invalid")


@pytest.fixture
def change_dir(tmp_path):
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(original_cwd)


def test_path_completion_after_redirection(caplog, change_dir):
    parser = ArgumentParser(prog="test")
    shtab.add_argument_to(parser, ["-s", "--shell"])
    with caplog.at_level(logging.INFO):
        completion = shtab.complete(parser, shell="bash")
    print(completion)

    (change_dir / "test_file.txt").touch()

    for redirection in [">", ">>", "1>", "1>>", "2>", "2>>"]:
        shell = Bash(completion +
                     f"\nCOMP_WORDS=(test '{redirection}' tes); COMP_CWORD=2; _shtab_test;")
        shell.test('"${COMPREPLY[@]}" = "test_file.txt"', f"Redirection {redirection} failed")

    assert not caplog.record_tuples
