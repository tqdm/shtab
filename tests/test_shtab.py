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


def complete(parser, shell, **kwargs):
    """convenience function to print for debugging in case of failure"""
    completion = shtab.complete(parser, shell, **kwargs)
    print(completion)
    return completion


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
    shell.compgen('-W "foo bar foobar"', "f", "foo foobar")


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
    with pytest.raises(SystemExit) as exc:
        main(["--print-own-completion", shell])
    assert exc.type is SystemExit and exc.value.code == 0
    captured = capsys.readouterr()
    assert not captured.err
    expected = {
        'bash': "complete -F _shtab_shtab shtab", 'zsh': "_shtab_shtab_commands()",
        'tcsh': "complete shtab", 'fish': "complete -c shtab"}
    assert expected[shell] in captured.out


@pytest.mark.parametrize('output', ["-", "stdout", "test.txt"])
@fix_shell
def test_main_output_path(shell, capsys, change_dir, output):
    assert not capsys.readouterr().out
    main(["-s", shell, "shtab.main.get_main_parser", "-o", output])
    captured = capsys.readouterr()
    assert not captured.err
    expected = {
        'bash': "complete -F _shtab_shtab shtab", 'zsh': "_shtab_shtab_commands()",
        'tcsh': "complete shtab", 'fish': "complete -c shtab"}
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
    if shell == 'bash':
        assert "complete -F _shtab_shtab foo" in captured.out
    else:
        pytest.skip("WiP")


@fix_shell
def test_prog_scripts(shell, capsys):
    main(["-s", shell, "--prog", "script.py", "shtab.main.get_main_parser"])

    captured = capsys.readouterr()
    assert not captured.err
    script_py = [i.strip() for i in captured.out.splitlines() if "script.py" in i]
    if shell == 'bash':
        assert script_py == ["complete -F _shtab_shtab script.py"]
    elif shell == 'zsh':
        assert script_py == [
            "#compdef script.py", "_describe 'script.py commands' _commands",
            'local context state line curcontext="$curcontext" '
            "one_or_more='(*)' remainder='(-)*:' default='*::: :->script.py'",
            "_shtab_shtab_options+=(': :_shtab_shtab_commands' '*::: :->script.py')", "script.py)",
            "compdef _shtab_shtab -N script.py"]
    elif shell == 'tcsh':
        assert script_py == ["complete script.py \\"]
    elif shell == 'fish':
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
    assert not captured.err
    if shell == 'bash':
        shell = Bash(captured.out)
        shell.compgen('-W "${_shtab_foo_option_strings[*]}"', "--h", "--help")
    else:
        pytest.skip("WiP")


@fix_shell
def test_complete(shell):
    parser = get_main_parser()
    completion = complete(parser, shell)
    if shell == 'bash':
        shell = Bash(completion)
        shell.compgen('-W "${_shtab_shtab_option_strings[*]}"', "--h", "--help")
    else:
        pytest.skip("WiP")


@fix_shell
def test_positional_choices(shell):
    parser = ArgumentParser(prog="test")
    parser.add_argument("posA", choices=["one", "two"])
    parser.add_argument("posB", choices=["BAA"]).complete = shtab.cmd("echo BZZ")
    completion = complete(parser, shell)
    assert "BAA" not in completion and "BZZ" in completion, ".complete should override choices"
    if shell == 'bash':
        shell = Bash(completion)
        shell.compgen('-W "$_shtab_test_pos_0_choices"', "o", "one")
    else:
        pytest.skip("WiP")


@fix_shell
def test_custom_complete(shell):
    parser = ArgumentParser(prog="test")
    _complete = parser.add_argument("posA").complete = {
        'bash': "_shtab_test_some_func", 'fish': "(_shtab_test_some_func)"}
    preamble = {
        'bash': "_shtab_test_some_func() { compgen -W 'one two' -- $1 ;}",
        'fish': "function _shtab_test_some_func\n  printf '%s\\n' one two\nend"}
    # with pytest.warns(DeprecationWarning):
    completion_deprecated = complete(parser, shell, preamble=preamble)
    _complete['preamble'] = preamble
    completion = complete(parser, shell)
    assert completion == completion_deprecated
    if shell == 'bash':
        shell = Bash(completion)
        shell.test('"$($_shtab_test_pos_0_COMPGEN o)" = "one"')
    elif shell == 'fish':
        assert fish_candidates(completion, "test o") == ["one"]
    else:
        pytest.skip("WiP")


def zsh_specs(completion, name, tmp_path):
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
    """Help must not gain stray quotes (#224)"""
    parser = ArgumentParser(prog="test", add_help=False)
    parser.add_argument("--opt", help=help_text)
    completion = complete(parser, 'zsh')
    assert "'\"'\"'" not in completion, ("`shlex.quote`'s `'\"'\"'` idiom is invalid"
                                         " inside the double-quoted specs")
    specs = zsh_specs(completion, "_shtab_test_options", tmp_path)
    assert len(specs) == 1, f"quoting split the spec into {len(specs)} words: {specs}"
    # `_arguments` strips the backslashes; what must not appear is *extra* quotes
    assert specs[0].count("'") == help_text.count("'")
    assert specs[0].count('"') == help_text.count('"')


@fix_shell
def test_non_sequence_choices(shell, tmp_path):
    parser = ArgumentParser(prog="myprog", add_help=False)
    parser.add_argument("--mapping", choices={"one": 1, "two": 2})
    parser.add_argument("posA", choices={"three"})
    completion = complete(parser, shell)
    if shell == 'bash':
        shell = Bash(completion)
        shell.compgen('-W "${_shtab_myprog_pos_0_choices[*]}"', "t", "three")
    elif shell == 'zsh':
        specs = zsh_specs(completion, "_shtab_myprog_options", tmp_path)
        assert specs == ["--mapping[]:mapping:(one two)", ":posA:(three)"]
    elif shell == 'fish':
        assert fish_candidates(completion, "myprog t") == ["three"]
        assert fish_candidates(completion, "myprog --mapping t") == ["two"]
    else:
        pytest.skip("WiP")


def test_zsh_remainder_custom_complete_has_optional_message_colon():
    parser = ArgumentParser(prog="test")
    parser.add_argument("command", nargs=1).complete = {'zsh': "{_command_names -e}"}
    parser.add_argument("args", nargs="...").complete = {'zsh': "_normal"}
    completion = complete(parser, 'zsh')
    assert '"(-)*::args:_normal"' in completion
    assert '"(-)*:args:_normal"' not in completion


def test_zsh_custom_action_nargs_zero_takes_no_argument():
    class CustomFlagAction(Action):
        def __call__(self, parser, namespace, values, option_string=None):
            pass

    parser = ArgumentParser(prog="test", add_help=False)
    parser.add_argument("--help", "-h", action=CustomFlagAction, help="Helpy", nargs=0,
                        default=SUPPRESS)
    completion = complete(parser, 'zsh')
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


def tcsh_candidates(completion, cmdlines, cwd):
    """
    Return the completion candidates tcsh offers for each of `cmdlines`.

    tcsh has no `complete -C` equivalent, so drive an interactive one through a pty.
    """
    if not shutil.which('tcsh'):
        pytest.skip("tcsh not available")
    script = cwd / "completion.tcsh"
    script.write_text(completion)
    prompt = "|candidates|"
    # tcsh echoes what is typed, so the command setting the prompt must not contain it verbatim
    set_prompt = f'set prompt="{prompt[:6]}""{prompt[6:]}"'

    pid, fd = pty.fork()
    if pid == 0:   # child
        os.chdir(cwd)
        os.environ['TERM'] = 'xterm'
        os.environ['COLUMNS'] = '999'
        os.execvp('tcsh', ['tcsh', '-f', '-i'])
    output = ""

    def read(prompts, timeout=10.0):
        """Read until the prompt has been seen `prompts` times (or `timeout` elapses)."""
        nonlocal output
        deadline = time.time() + timeout
        while output.count(prompt) < prompts and time.time() < deadline:
            if select.select([fd], [], [], 0.1)[0]:
                try:
                    chunk = os.read(fd, 1 << 16)
                except OSError:
                    break
                if not chunk:
                    break
                output += re.sub(r"\x1b\[[0-9;]*[A-Za-z]|[\a\r\b]", "",
                                 chunk.decode('utf-8', 'replace'))
        # a command just finished, give tcsh a moment to enable its line editor again
        while select.select([fd], [], [], 0.2)[0]:
            output += re.sub(r"\x1b\[[0-9;]*[A-Za-z]|[\a\r\b]", "",
                             os.read(fd, 1 << 16).decode('utf-8', 'replace'))
        return output

    candidates = []
    try:
        os.write(fd, f"set autolist\nsource {script}\n{set_prompt}\n".encode())
        read(1)
        for cmdline in cmdlines:
            seen = len(output)
            # `autolist` lists the candidates, ^U then discards the line, \n asks for a new prompt
            os.write(fd, cmdline.encode() + b"\t\x15\n")
            chunk = read(output.count(prompt) + 1)[seen:].replace(prompt, "\n")
            # drop the echoed command line & the re-drawn prompt, leaving the listed candidates
            candidates.append([
                word for line in chunk.splitlines() if line.strip() and cmdline.strip() not in line
                for word in line.split()])
    finally:
        os.close(fd)
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
    return candidates


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


@fix_shell
def test_file_completion(shell, change_dir, test_parser):
    (change_dir / "test_file.txt").touch()
    completion = complete(test_parser, shell)
    if shell == 'bash':
        shell = Bash(completion)
        shell.test('"$($_shtab_myprog_create_pos_1_COMPGEN test_)" = test_file.txt')
    elif shell == 'zsh':
        specs = zsh_specs(completion, "_shtab_myprog_create_options", change_dir)
        assert "(*)::paths to add:_files" in specs
    elif shell == 'tcsh':
        command_lines = ["myprog create --exclude-from ", "myprog --repo test_"]
        candidates = tcsh_candidates(completion, command_lines, change_dir)
        assert candidates == [["completion.tcsh", "test_file.txt"], []]
    elif shell == 'fish':
        assert fish_candidates(completion, "myprog create alpha test_") == ["test_file.txt"]
        assert fish_candidates(completion, "myprog create --exclude-from ") == ["test_file.txt"]
        assert not fish_candidates(completion, "myprog delete test_")
        assert not fish_candidates(completion, "myprog --repo test_")
        (change_dir / "subdir").mkdir()
        (change_dir / "subdir" / "nested.txt").touch()
        assert fish_candidates(completion,
                               "myprog create alpha subdir/nes") == ["subdir/nested.txt"]
        absolute = change_dir / "subdir" / "nes"
        candidates = fish_candidates(completion, f"myprog create --exclude-from {absolute}")
        assert candidates[0].endswith("subdir/nested.txt")
        assert len(candidates) == 1
    else:
        raise NotImplementedError(completion)


def bash_completed_line(completion, cmdline, cwd):
    """
    Source `completion` in an interactive bash, type `cmdline` followed by <TAB>,
    and return the resulting command line after readline inserted the completion.

    Needed since readline's post-processing (e.g. `-o filenames` appending `/` to
    dirs) happens after `COMPREPLY` and is thus invisible to `compgen`-based tests.
    """
    script = cwd / "completion.bash"
    script.write_text(completion)
    prompt = "|bashtest|"
    pid, fd = pty.fork()
    if pid == 0:   # child
        os.chdir(cwd)
        os.environ['TERM'] = 'dumb'
        os.environ['COLUMNS'] = '999'
        os.execvp('bash', ['bash', '--norc', '--noprofile', '-i'])
    output = ""

    def clean(chunk):
        return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]|[\a\r\b]", "", chunk.decode('utf-8', 'replace'))

    def read(condition, timeout=10.0):
        """Read until `condition()` (or `timeout` elapses), then drain."""
        nonlocal output
        deadline = time.time() + timeout
        while not condition() and time.time() < deadline:
            if select.select([fd], [], [], 0.1)[0]:
                try:
                    chunk = os.read(fd, 1 << 16)
                except OSError:
                    break
                if not chunk:
                    break
                output += clean(chunk)
        while select.select([fd], [], [], 0.3)[0]:
            try:
                chunk = os.read(fd, 1 << 16)
            except OSError:
                break
            if not chunk:
                break
            output += clean(chunk)

    try:
        os.write(fd, f"source {script}; PS1='{prompt}'\n".encode())
        read(lambda: output.count(prompt) >= 1)
        seen = len(output)
        os.write(fd, cmdline.encode() + b"\t")
        # the typed line is echoed back, followed by whatever readline inserted
        read(lambda: cmdline in output[seen:])
        completed = output[seen:]
        os.write(fd, b"\x15exit\n") # discard the line & quit
        read(lambda: True)
    finally:
        os.close(fd)
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
    return completed


def test_bash_subcommand_dir_collision(change_dir, test_parser):
    """Subcommands matching a dir name must not gain a trailing slash (#67)"""
    if subprocess.call(['bash', '-c', 'type compopt'], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL):
        pytest.skip("bash without compopt")
    (change_dir / "create").mkdir()
    (change_dir / "subdir").mkdir()
    completion = complete(test_parser, 'bash')
    assert "complete -F _shtab_myprog myprog" in completion, \
        "`-o filenames` must not apply readline filename post-processing globally"
    line = bash_completed_line(completion, "myprog cre", change_dir)
    assert line == "myprog create ", "subcommand was completed like a directory"
    # dir/file completions must still get filename treatment (trailing `/` on dirs)
    line = bash_completed_line(completion, "myprog create alpha sub", change_dir)
    assert line == "myprog create alpha subdir/"


def test_bash_compgen_dir_collision(change_dir):
    """Non-path compgen candidates matching a dir name must not gain a trailing slash (#67)"""
    if subprocess.call(['bash', '-c', 'type compopt'], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL):
        pytest.skip("bash without compopt")
    parser = ArgumentParser(prog="otherprog")
    parser.add_argument("branch").complete = shtab.cmd("echo master other")
    parser.add_argument("--config").complete = shtab.glob("*.yml")
    (change_dir / "master").mkdir()
    (change_dir / "subdir").mkdir()
    completion = complete(parser, 'bash')
    line = bash_completed_line(completion, "otherprog mas", change_dir)
    assert line == "otherprog master ", "`shtab.cmd` candidate was completed like a directory"
    # `shtab.glob` completes paths, so dirs must still get a trailing `/`
    line = bash_completed_line(completion, "otherprog master --config sub", change_dir)
    assert line == "otherprog master --config subdir/"


def test_fish_global_option_value(test_parser):
    """Subcommands complete after `--global-opt value` (#228)"""
    completion = complete(test_parser, 'fish')
    candidates = fish_candidates(completion, "myprog --repo x ")
    assert {"create", "delete", "list"} <= set(candidates)


def test_fish_value_equal_to_command_name(test_parser):
    """Values matching command names must not confuse (#229)"""
    completion = complete(test_parser, 'fish')
    # `list` is the value of `delete`'s `name` positional, not the `list` subcommand
    candidates = fish_candidates(completion, "myprog delete list --")
    assert "--force" in candidates
    assert "--short" not in candidates


def test_fish_positional_order(test_parser):
    """Positionals are completed at the right slot (#230)"""
    completion = complete(test_parser, 'fish')
    # first slot offers the `name` choices
    assert {"alpha", "beta"} <= set(fish_candidates(completion, "myprog create "))
    # later slots (the `paths` positional) must not re-offer them
    assert "alpha" not in fish_candidates(completion, "myprog create alpha alp")


@fix_shell
def test_placeholder_help_expansion(shell):
    if shell in ('bash', 'tcsh'):
        pytest.skip("WiP")
    parser = ArgumentParser(prog="test")
    parser.add_argument("--retries", type=int, default=3, help="retries (default %(default)s)")
    parser.add_argument("posA", choices=["one", "two"], help="also %(prog)s thing")
    completion = complete(parser, shell)
    assert "retries (default 3)" in completion
    assert "also test thing" in completion


def test_fish_subcommand_description():
    """add_parser(help=...) is used when there is no description (#231)"""
    parser = ArgumentParser(prog="test")
    subparsers = parser.add_subparsers()
    subparsers.add_parser("subA", help="help message")
    subparsers.add_parser("subB", description="description wins\nsecond line", help="unused")
    completion = complete(parser, 'fish')
    assert "-a subA -d 'help message'" in completion
    assert "-a subB -d 'description wins'" in completion


def test_fish_choice_flags():
    parser = ArgumentParser(prog="test")
    parser.add_argument("--cust", help="custom").complete = {'bash': "_some_func"}
    parser.add_argument("--fmt", choices=["json", "csv"], help="format")
    parser.add_argument("posB", choices=["one", "two"], help="a word")
    completion = complete(parser, 'fish')
    assert "-l cust -x -d custom" in completion
    assert '-l fmt -xka "json csv" -d format' in completion
    assert '-ka "one two" -d \'a word\'' in completion


@pytest.fixture
def tcsh_pattern_parser():
    """Two subcommands sharing positional slot 2, one of them `.complete`-ing a pattern."""
    parser = ArgumentParser(prog="myprog")
    parser.add_argument("--conf", help="config file")
    subparsers = parser.add_subparsers()
    build = subparsers.add_parser("build", help="build")
    build.add_argument("cfg", help="config").complete = shtab.glob("*.yml", "*.yaml")
    build.add_argument("stage", choices=["dev", "prod"], help="stage")
    run = subparsers.add_parser("run", help="run")
    run.add_argument("mode", choices=["fast", "slow"], help="mode")
    run.add_argument("target", choices=["all", "one"], help="target")
    return parser


def test_tcsh_slot_after_subcommand(tcsh_pattern_parser):
    """A slot directly following a (sub)command is keyed off that word (#236)"""
    completion = complete(tcsh_pattern_parser, 'tcsh')
    assert "'n/build/f:{*.yml,*.yaml}/'" in completion
    assert "f:{*.yml,*.yaml}`" not in completion and ") f:" not in completion
    assert "'n/run/(fast slow)/'" in completion
    # a slot further away from its (sub)command can only be keyed off its index
    assert '("$cmd[2]" == "run") ) echo all one' in completion
    assert '("$cmd[2]" == "build") ) echo dev prod' in completion


def test_tcsh_pattern_completion(tcsh_pattern_parser, change_dir):
    """The generated pattern rule works in tcsh itself (#236)"""
    for name in ("app.yml", "conf.yaml", "notes.md"):
        (change_dir / name).touch()
    completion = complete(tcsh_pattern_parser, 'tcsh')
    cmdlines = [
        "myprog build ", "myprog run ", "myprog ", "myprog --conf c.yml build ",
        "myprog --conf c.yml run "]
    yml, fast_slow = ["app.yml", "conf.yaml"], ["fast", "slow"]
    assert tcsh_candidates(completion, cmdlines,
                           change_dir) == [yml, fast_slow, ["build", "run"], yml, fast_slow]


@fix_shell
def test_subparser_custom_complete(shell):
    parser = ArgumentParser(prog="test")
    subparsers = parser.add_subparsers()
    sub = subparsers.add_parser("sub", help="help message")
    sub.add_argument("posA").complete = {
        'bash': "_shtab_test_some_func", 'fish': "(_shtab_test_some_func)", 'preamble': {
            'bash': "_shtab_test_some_func() { compgen -W 'one two' -- $1 ;}",
            'fish': "function _shtab_test_some_func\n  printf '%s\\n' one two\nend"}}
    completion = complete(parser, shell)
    if shell == 'bash':
        shell = Bash(completion)
        shell.compgen('-W "${_shtab_test_subparsers[*]}"', "s", "sub")
        shell.compgen('-W "$_shtab_test_pos_0_choices"', "s", "sub")
        shell.test('"$($_shtab_test_sub_pos_0_COMPGEN o)" = "one"')
        shell.test('-z "${_shtab_test_COMPGEN-}"')
    elif shell == 'fish':
        assert fish_candidates(completion, "test sub o") == ["one"]
    else:
        pytest.skip("WiP")


@fix_shell
def test_subparser_aliases(shell):
    parser = ArgumentParser(prog="test")
    subparsers = parser.add_subparsers()
    sub = subparsers.add_parser("sub", aliases=["xsub", "ysub"], help="help message")
    sub.add_argument("posA").complete = {
        'bash': "_shtab_test_some_func",
        'preamble': {'bash': "_shtab_test_some_func() { compgen -W 'one two' -- $1 ;}"}}
    completion = complete(parser, shell)
    if shell == 'bash':
        shell = Bash(completion)
        shell.compgen('-W "${_shtab_test_subparsers[*]}"', "s", "sub")
        shell.compgen('-W "${_shtab_test_pos_0_choices[*]}"', "s", "sub")
        shell.compgen('-W "${_shtab_test_subparsers[*]}"', "x", "xsub")
        shell.compgen('-W "${_shtab_test_pos_0_choices[*]}"', "x", "xsub")
        shell.compgen('-W "${_shtab_test_subparsers[*]}"', "y", "ysub")
        shell.compgen('-W "${_shtab_test_pos_0_choices[*]}"', "y", "ysub")
        shell.test('"$($_shtab_test_sub_pos_0_COMPGEN o)" = "one"')
        shell.test('-z "${_shtab_test_COMPGEN-}"')
    else:
        pytest.skip("WiP")


@fix_shell
def test_subparser_colons(shell):
    parser = ArgumentParser(prog="test")
    subparsers = parser.add_subparsers()
    subparsers.add_parser("sub:cmd", help="help message")
    completion = complete(parser, shell)
    if shell == 'bash':
        shell = Bash(completion)
        shell.compgen('-W "${_shtab_test_subparsers[*]}"', "s", "sub:cmd")
        shell.compgen('-W "${_shtab_test_pos_0_choices[*]}"', "s", "sub:cmd")
        shell.test('-z "${_shtab_test_COMPGEN-}"')
    else:
        pytest.skip("WiP")


@fix_shell
def test_subparser_slashes(shell):
    parser = ArgumentParser(prog="test")
    subparsers = parser.add_subparsers()
    subparsers.add_parser("sub/cmd", help="help message")
    completion = complete(parser, shell)
    if shell == 'bash':
        shell = Bash(completion)
        shell.compgen('-W "${_shtab_test_subparsers[*]}"', "s", "sub/cmd")
        shell.compgen('-W "${_shtab_test_pos_0_choices[*]}"', "s", "sub/cmd")
        shell.test('-z "${_shtab_test_COMPGEN-}"')
    elif shell == 'zsh':
        assert "_shtab_test_sub/cmd" not in completion
        assert "_shtab_test_sub_cmd" in completion
    else:
        pytest.skip("WiP")


@fix_shell
def test_add_argument_to_optional(shell):
    parser = ArgumentParser(prog="test")
    shtab.add_argument_to(parser, ["-s", "--shell"])
    completion = complete(parser, shell)
    if shell == 'bash':
        shell = Bash(completion)
        shell.compgen('-W "${_shtab_test_option_strings[*]}"', "--s", "--shell")
    else:
        pytest.skip("WiP")


@fix_shell
def test_add_argument_to_positional(shell, capsys):
    parser = ArgumentParser(prog="test")
    subparsers = parser.add_subparsers()
    sub = subparsers.add_parser("completion", help="help message")
    shtab.add_argument_to(sub, "shell", parent=parser)
    from argparse import Namespace
    completion_manual = complete(parser, shell)
    assert completion_manual.rstrip() == capsys.readouterr().out.rstrip()
    with pytest.raises(SystemExit) as exc:
        sub._actions[-1](sub, Namespace(), shell)
    assert exc.type is SystemExit and exc.value.code == 0
    completion, err = capsys.readouterr()
    assert completion_manual.rstrip() == completion.rstrip()
    assert not err
    if shell == 'bash':
        shell = Bash(completion)
        shell.compgen('-W "${_shtab_test_subparsers[*]}"', "c", "completion")
        shell.compgen('-W "${_shtab_test_pos_0_choices[*]}"', "c", "completion")
        shell.compgen('-W "${_shtab_test_completion_pos_0_choices[*]}"', "ba", "bash")
        shell.compgen('-W "${_shtab_test_completion_pos_0_choices[*]}"', "z", "zsh")
    else:
        pytest.skip("WiP")


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
    completion = complete(parser, 'bash')
    (change_dir / "test_file.txt").touch()
    for redirection in [">", ">>", "1>", "1>>", "2>", "2>>"]:
        shell = Bash(completion +
                     f"\nCOMP_WORDS=(test '{redirection}' tes); COMP_CWORD=2; _shtab_test;")
        shell.test('"${COMPREPLY[@]}" = "test_file.txt"', f"Redirection {redirection} failed")
