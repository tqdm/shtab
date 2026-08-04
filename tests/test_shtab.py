"""Tests for `shtab`."""
import logging
import os
import pty
import re
import select
import shutil
import signal
import subprocess
import time
from argparse import SUPPRESS, Action, ArgumentParser

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
        proc = subprocess.Popen(['bash', '-o', 'pipefail', '-euc', f"{init}[[ {cmd} ]]"],
                                text=True)
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


@pytest.fixture(autouse=True)
def no_log_info(caplog):
    with caplog.at_level(logging.INFO, logger="shtab"):
        yield
    assert not caplog.get_records('call')


@fix_shell
def test_main(shell):
    main(["-s", shell, "shtab.main.get_main_parser"])


@fix_shell
def test_main_self_completion(shell, capsys):
    try:
        main(["--print-own-completion", shell])
    except SystemExit:
        pass
    captured = capsys.readouterr()
    assert not captured.err
    expected = {
        "bash": "complete -o filenames -F _shtab_shtab shtab", "zsh": "_shtab_shtab_commands()",
        "tcsh": "complete shtab", "fish": "complete -c shtab"}
    assert expected[shell] in captured.out


@pytest.mark.parametrize('output', ["-", "stdout", "test.txt"])
@fix_shell
def test_main_output_path(shell, capsys, change_dir, output):
    assert not capsys.readouterr().out
    try:
        main(["-s", shell, "shtab.main.get_main_parser", "-o", output])
    except SystemExit:
        pass
    captured = capsys.readouterr()
    assert not captured.err
    expected = {
        "bash": "complete -o filenames -F _shtab_shtab shtab", "zsh": "_shtab_shtab_commands()",
        "tcsh": "complete shtab", "fish": "complete -c shtab"}
    if output in ("-", "stdout"):
        assert expected[shell] in captured.out
    else:
        assert not captured.out
        assert expected[shell] in (change_dir / output).read_text()


@fix_shell
def test_prog_override(shell, capsys):
    main(["-s", shell, "--prog", "foo", "shtab.main.get_main_parser"])
    captured = capsys.readouterr()
    assert not captured.err
    if shell == "bash":
        assert "complete -o filenames -F _shtab_shtab foo" in captured.out


@fix_shell
def test_prog_scripts(shell, capsys):
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
            "one_or_more='(*)' remainder='(-)*:' default='*::: :->script.py'",
            "_shtab_shtab_options+=(': :_shtab_shtab_commands' '*::: :->script.py')", "script.py)",
            "compdef _shtab_shtab -N script.py"]
    elif shell == "tcsh":
        assert script_py == ["complete script.py \\"]
    elif shell == "fish":
        start = 'complete -c script.py -n _shtab_shtab_using'
        assert script_py == [
            'complete -c script.py -e', 'complete -c script.py -f',
            f"{start} -s h -l help -d 'show this help message and exit'",
            f"{start} -l version -d 'show program'\"'\"'s version number and exit'",
            f'{start} -s s -l shell -xka "bash zsh tcsh fish"',
            f"{start} -s o -l output -x -d 'output file (- for stdout)'",
            f"{start} -l prefix -x -d 'prepended to generated functions to avoid clashes'",
            f"{start} -l preamble -x -d 'prepended to generated script'",
            f"{start} -l prog -x -d 'custom program name (overrides `parser.prog`)'",
            f"{start} -s u -l error-unimportable -d"
            " 'raise errors if `parser` is not found in $PYTHONPATH'",
            f"{start} -l verbose -d 'Log debug information'",
            f'{start} -l print-own-completion -xka "bash zsh tcsh fish" -d'
            " 'print shtab'\"'\"'s own completion'"]
    else:
        raise NotImplementedError(shell)


@fix_shell
def test_prefix_override(shell, capsys):
    main(["-s", shell, "--prefix", "foo", "shtab.main.get_main_parser"])
    captured = capsys.readouterr()
    print(captured.out)
    assert not captured.err
    if shell == "bash":
        shell = Bash(captured.out)
        shell.compgen('-W "${_shtab_foo_option_strings[*]}"', "--h", "--help")


@fix_shell
def test_complete(shell):
    parser = get_main_parser()
    completion = shtab.complete(parser, shell=shell)
    print(completion)
    if shell == "bash":
        shell = Bash(completion)
        shell.compgen('-W "${_shtab_shtab_option_strings[*]}"', "--h", "--help")


@fix_shell
def test_positional_choices(shell):
    parser = ArgumentParser(prog="test")
    parser.add_argument("posA", choices=["one", "two"])
    parser.add_argument("posB", choices=["BAA"]).complete = shtab.cmd("echo BZZ")
    completion = shtab.complete(parser, shell=shell)
    print(completion)
    assert "BAA" not in completion and "BZZ" in completion, ".complete should override choices"
    if shell == "bash":
        shell = Bash(completion)
        shell.compgen('-W "$_shtab_test_pos_0_choices"', "o", "one")


@fix_shell
def test_custom_complete(shell):
    parser = ArgumentParser(prog="test")
    complete = parser.add_argument("posA").complete = {
        "bash": "_shtab_test_some_func", "fish": "(_shtab_test_some_func)"}
    preamble = {
        "bash": "_shtab_test_some_func() { compgen -W 'one two' -- $1 ;}",
        "fish": "function _shtab_test_some_func\n  printf '%s\\n' one two\nend"}
    # with pytest.warns(DeprecationWarning):
    completion_deprecated = shtab.complete(parser, shell=shell, preamble=preamble)
    complete['preamble'] = preamble
    completion = shtab.complete(parser, shell=shell)
    assert completion == completion_deprecated
    print(completion)
    if shell == "bash":
        shell = Bash(completion)
        shell.test('"$($_shtab_test_pos_0_COMPGEN o)" = "one"')
    elif shell == "fish":
        assert fish_candidates(completion, "test o") == ["one"]


def zsh_spec_array(completion, name, tmp_path):
    """`zsh -n` the completion, then return the values zsh assigns to array `name`."""
    if not shutil.which('zsh'):
        pytest.skip("zsh not available")
    subprocess.check_call(['zsh', '-nc', completion])
    script = tmp_path / "completion.zsh"
    script.write_text(completion)
    # `eval` so the script registers itself rather than running `compdef` (unavailable here)
    values = subprocess.check_output(
        ['zsh', '-f', '-c', f'eval "$(<{script})" 2>/dev/null; print -rl -- "${{(@){name}}}"'],
        text=True)
    return values.splitlines()


@pytest.mark.parametrize("help_text", [
    "plain help", "don't do this", "e.g. '>size_added,path'", 'a "quoted" value',
    "cost: $5 (100%%) `tick`"])
def test_zsh_help_quoting(help_text, tmp_path):
    """Help must not gain stray quotes: https://github.com/tqdm/shtab/issues/224"""
    parser = ArgumentParser(prog="test", add_help=False)
    parser.add_argument("--opt", help=help_text)
    completion = shtab.complete(parser, shell="zsh")
    assert "'\"'\"'" not in completion, ("`shlex.quote`'s `'\"'\"'` idiom is invalid"
                                         " inside the double-quoted specs")
    specs = zsh_spec_array(completion, "_shtab_test_options", tmp_path)
    assert len(specs) == 1, f"quoting split the spec into {len(specs)} words: {specs}"
    # `_arguments` strips the backslashes; what must not appear is *extra* quotes
    assert specs[0].count("'") == help_text.count("'")
    assert specs[0].count('"') == help_text.count('"')


def test_zsh_non_sequence_choices():
    parser = ArgumentParser(prog="test")
    parser.add_argument("--mapping", choices={"one": 1, "two": 2})
    parser.add_argument("posA", choices={"three"})
    completion = shtab.complete(parser, shell="zsh")
    assert ':mapping:(one two)"' in completion
    assert '":posA:(three)"' in completion


def test_zsh_remainder_custom_complete_has_optional_message_colon():
    parser = ArgumentParser(prog="test")
    parser.add_argument("command", nargs=1).complete = {"zsh": "{_command_names -e}"}
    parser.add_argument("args", nargs="...").complete = {"zsh": "_normal"}
    completion = shtab.complete(parser, shell="zsh")
    assert '"(-)*::args:_normal"' in completion
    assert '"(-)*:args:_normal"' not in completion


def test_zsh_custom_action_nargs_zero_takes_no_argument():
    class CustomFlagAction(Action):
        def __call__(self, parser, namespace, values, option_string=None):
            pass

    parser = ArgumentParser(prog="test", add_help=False)
    parser.add_argument("--help", "-h", action=CustomFlagAction, help="Helpy", nargs=0,
                        default=SUPPRESS)
    completion = shtab.complete(parser, shell="zsh")
    assert '{--help,-h}"[Helpy]"' in completion
    assert '{--help,-h}"[Helpy]:help:"' not in completion


def fish_candidates(completion, cmdline):
    """Source `completion` in fish, then return the completion candidates for `cmdline`."""
    if not shutil.which('fish'):
        pytest.skip("fish not available")
    quoted = "'" + cmdline.replace("\\", "\\\\").replace("'", "\\'") + "'"
    proc = subprocess.check_output(['fish', '-c', f"{completion}\ncomplete -C{quoted}"], text=True)
    # each output line is "candidate<TAB>description" (or just "candidate")
    return [line.split("\t")[0] for line in proc.splitlines() if line.strip()]


def tcsh_candidates(completion, cmdline, cwd):
    """
    Return the completion candidates tcsh offers for `cmdline`.

    tcsh has no `complete -C` equivalent, so drive an interactive one through a pty.
    """
    if not shutil.which('tcsh'):
        pytest.skip("tcsh not available")
    script = cwd / "completion.tcsh"
    script.write_text(completion)

    pid, fd = pty.fork()
    if pid == 0:   # child
        os.chdir(cwd)
        os.environ['TERM'] = 'xterm'
        os.execvp('tcsh', ['tcsh', '-f', '-i'])

    def read(timeout=5.0):
        """Read until nothing arrives for a while (or `timeout` elapses)."""
        out = b""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if select.select([fd], [], [], 0.1)[0]:
                try:
                    chunk = os.read(fd, 1 << 16)
                except OSError:
                    break
                if not chunk:
                    break
                out += chunk
                deadline = min(deadline, time.time() + 0.5)
        return out.decode('utf-8', 'replace')

    try:
        read()                                 # prompt
        os.write(fd, f"set autolist\nsource {script}\n".encode())
        read()
        os.write(fd, cmdline.encode() + b"\t") # `autolist` lists the candidates
        output = re.sub(r"\x1b\[[0-9;]*[A-Za-z]|[\a\r]", "", read())
    finally:
        os.close(fd)
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)

    # drop the echoed command line & the re-drawn prompt, leaving the listed candidates
    return [
        word for line in output.splitlines() if line.strip() and cmdline.strip() not in line
        for word in line.split()]


@pytest.fixture
def test_parser():
    # NOTE: `prog="test"` fails on fish<4 due to autoloading of builtin `complete -c test -e`
    parser = ArgumentParser(prog="myprog")
    parser.add_argument("--repo", "-r", help="repository to use")
    subparsers = parser.add_subparsers(dest="cmd")
    create = subparsers.add_parser("create", help="create something")
    create.add_argument("--exclude-from", help="exclude patterns file").complete = shtab.FILE
    create.add_argument("name", choices=["alpha", "beta"], help="name of the thing to create")
    create.add_argument("paths", nargs="*", help="paths to add").complete = shtab.FILE
    delete = subparsers.add_parser("delete", help="delete something")
    delete.add_argument("--force", action="store_true", help="force deletion")
    delete.add_argument("name", help="name of the thing to delete")
    subparsers.add_parser("list", help="list things")
    return parser


def test_fish_file_completion(change_dir, test_parser):
    """`shtab.FILE` completes files: https://github.com/tqdm/shtab/issues/227"""
    (change_dir / "test_file.txt").touch()
    completion = shtab.complete(test_parser, shell="fish")
    # positional marked `shtab.FILE` (`paths`, after the `name` slot)
    assert "test_file.txt" in fish_candidates(completion, "myprog create alpha test_")
    # value of an option marked `shtab.FILE` completes files, not the positional's choices
    candidates = fish_candidates(completion, "myprog create --exclude-from ")
    assert "test_file.txt" in candidates
    assert "alpha" not in candidates
    # arguments not marked `shtab.FILE` don't complete files (as in the other shells)
    assert fish_candidates(completion, "myprog delete test_") == []
    assert fish_candidates(completion, "myprog --repo test_") == []


def test_fish_global_option_value(test_parser):
    """Subcommands complete after `--global-opt value`: https://github.com/tqdm/shtab/issues/228"""
    completion = shtab.complete(test_parser, shell="fish")
    candidates = fish_candidates(completion, "myprog --repo x ")
    assert {"create", "delete", "list"} <= set(candidates)


def test_fish_value_equal_to_command_name(test_parser):
    """Values matching command names must not confuse: https://github.com/tqdm/shtab/issues/229"""
    completion = shtab.complete(test_parser, shell="fish")
    # `list` is the value of `delete`'s `name` positional, not the `list` subcommand
    candidates = fish_candidates(completion, "myprog delete list --")
    assert "--force" in candidates
    assert "--short" not in candidates


def test_fish_positional_order(test_parser):
    """Positionals are completed at the right slot: https://github.com/tqdm/shtab/issues/230"""
    completion = shtab.complete(test_parser, shell="fish")
    # first slot offers the `name` choices
    assert {"alpha", "beta"} <= set(fish_candidates(completion, "myprog create "))
    # later slots (the `paths` positional) must not re-offer them
    assert "alpha" not in fish_candidates(completion, "myprog create alpha alp")


def test_fish_help_expansion():
    """%(default)s etc. are expanded in descriptions: https://github.com/tqdm/shtab/issues/231"""
    parser = ArgumentParser(prog="test")
    parser.add_argument("--retries", type=int, default=3, help="retries (default: %(default)s)")
    parser.add_argument("posA", choices=["one", "two"], help="%(prog)s thing")
    completion = shtab.complete(parser, shell="fish")
    assert "-d 'retries (default: 3)'" in completion
    assert "-d 'test thing'" in completion


def test_fish_subcommand_description():
    """add_parser(help=...) is used when there is no description: tqdm/shtab#231"""
    parser = ArgumentParser(prog="test")
    subparsers = parser.add_subparsers()
    subparsers.add_parser("subA", help="help message")
    subparsers.add_parser("subB", description="description wins\nsecond line", help="unused")
    completion = shtab.complete(parser, shell="fish")
    assert "-a subA -d 'help message'" in completion
    assert "-a subB -d 'description wins'" in completion


def test_fish_choice_flags():
    parser = ArgumentParser(prog="test")
    parser.add_argument("--cust", help="custom").complete = {"bash": "_some_func"}
    parser.add_argument("--fmt", choices=["json", "csv"], help="format")
    parser.add_argument("posB", choices=["one", "two"], help="a word")
    completion = shtab.complete(parser, shell="fish")
    assert "-l cust -x -d custom" in completion
    assert '-l fmt -xka "json csv" -d format' in completion
    assert '-ka "one two" -d \'a word\'' in completion


def get_tcsh_pattern_parser():
    """Two subcommands sharing positional slot 2, one of them `.complete`-ing a pattern."""
    parser = ArgumentParser(prog="myprog")
    subparsers = parser.add_subparsers()
    build = subparsers.add_parser("build", help="build")
    build.add_argument("cfg", help="config").complete = shtab.glob("*.yml", "*.yaml")
    run = subparsers.add_parser("run", help="run")
    run.add_argument("mode", choices=["fast", "slow"], help="mode")
    return parser


def test_tcsh_pattern_in_shared_slot():
    """Patterns are anchored on the (sub)command: tqdm/shtab#236"""
    completion = shtab.complete(get_tcsh_pattern_parser(), shell="tcsh")
    # a pattern is not a command, so it can't go in the `p@2@`...`@` list
    assert "'n/build/f:{*.yml,*.yaml}/'" in completion
    assert "f:{*.yml,*.yaml}`" not in completion and ") f:" not in completion
    # commands & choices still do
    assert '("$cmd[2]" == "run") ' in completion


def test_tcsh_pattern_completion(change_dir):
    """The generated pattern rule works in tcsh itself: tqdm/shtab#236"""
    for name in ("app.yml", "conf.yaml", "notes.md"):
        (change_dir / name).touch()
    completion = shtab.complete(get_tcsh_pattern_parser(), shell="tcsh")

    assert tcsh_candidates(completion, "myprog build ", change_dir) == ["app.yml", "conf.yaml"]
    assert tcsh_candidates(completion, "myprog run ", change_dir) == ["fast", "slow"]
    assert tcsh_candidates(completion, "myprog ", change_dir) == ["build", "run"]


@fix_shell
def test_subparser_custom_complete(shell):
    parser = ArgumentParser(prog="test")
    subparsers = parser.add_subparsers()
    sub = subparsers.add_parser("sub", help="help message")
    sub.add_argument("posA").complete = {
        "bash": "_shtab_test_some_func", "fish": "(_shtab_test_some_func)", 'preamble': {
            "bash": "_shtab_test_some_func() { compgen -W 'one two' -- $1 ;}",
            "fish": "function _shtab_test_some_func\n  printf '%s\\n' one two\nend"}}
    completion = shtab.complete(parser, shell=shell)
    print(completion)
    if shell == "bash":
        shell = Bash(completion)
        shell.compgen('-W "${_shtab_test_subparsers[*]}"', "s", "sub")
        shell.compgen('-W "$_shtab_test_pos_0_choices"', "s", "sub")
        shell.test('"$($_shtab_test_sub_pos_0_COMPGEN o)" = "one"')
        shell.test('-z "${_shtab_test_COMPGEN-}"')
    elif shell == "fish":
        assert fish_candidates(completion, "test sub o") == ["one"]


@fix_shell
def test_subparser_aliases(shell):
    parser = ArgumentParser(prog="test")
    subparsers = parser.add_subparsers()
    sub = subparsers.add_parser("sub", aliases=["xsub", "ysub"], help="help message")
    sub.add_argument("posA").complete = {
        "bash": "_shtab_test_some_func",
        'preamble': {"bash": "_shtab_test_some_func() { compgen -W 'one two' -- $1 ;}"}}
    completion = shtab.complete(parser, shell=shell)
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


@fix_shell
def test_subparser_colons(shell):
    parser = ArgumentParser(prog="test")
    subparsers = parser.add_subparsers()
    subparsers.add_parser("sub:cmd", help="help message")
    completion = shtab.complete(parser, shell=shell)
    print(completion)
    if shell == "bash":
        shell = Bash(completion)
        shell.compgen('-W "${_shtab_test_subparsers[*]}"', "s", "sub:cmd")
        shell.compgen('-W "${_shtab_test_pos_0_choices[*]}"', "s", "sub:cmd")
        shell.test('-z "${_shtab_test_COMPGEN-}"')


@fix_shell
def test_subparser_slashes(shell):
    parser = ArgumentParser(prog="test")
    subparsers = parser.add_subparsers()
    subparsers.add_parser("sub/cmd", help="help message")
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
def test_add_argument_to_optional(shell):
    parser = ArgumentParser(prog="test")
    shtab.add_argument_to(parser, ["-s", "--shell"])
    completion = shtab.complete(parser, shell=shell)
    print(completion)
    if shell == "bash":
        shell = Bash(completion)
        shell.compgen('-W "${_shtab_test_option_strings[*]}"', "--s", "--shell")


@fix_shell
def test_add_argument_to_positional(shell, capsys):
    parser = ArgumentParser(prog="test")
    subparsers = parser.add_subparsers()
    sub = subparsers.add_parser("completion", help="help message")
    shtab.add_argument_to(sub, "shell", parent=parser)
    from argparse import Namespace
    completion_manual = shtab.complete(parser, shell=shell)
    with pytest.raises(SystemExit) as exc:
        sub._actions[-1](sub, Namespace(), shell)
        assert exc.type is SystemExit
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


def test_path_completion_after_redirection(change_dir):
    parser = ArgumentParser(prog="test")
    shtab.add_argument_to(parser, ["-s", "--shell"])
    completion = shtab.complete(parser, shell="bash")
    print(completion)
    (change_dir / "test_file.txt").touch()
    for redirection in [">", ">>", "1>", "1>>", "2>", "2>>"]:
        shell = Bash(completion +
                     f"\nCOMP_WORDS=(test '{redirection}' tes); COMP_CWORD=2; _shtab_test;")
        shell.test('"${COMPREPLY[@]}" = "test_file.txt"', f"Redirection {redirection} failed")
