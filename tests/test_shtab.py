"""Tests for `shtab`."""
import logging
import os
import pty
import re
import select
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
from argparse import SUPPRESS, Action, ArgumentParser
from contextlib import contextmanager
from functools import partial
from pathlib import Path

import pytest

import shtab
from shtab.main import get_main_parser, main

fix_shell = pytest.mark.parametrize("shell", shtab.SUPPORTED_SHELLS)


def complete(parser, shell, **kwargs):
    """convenience function to print for debugging in case of failure"""
    completion = shtab.complete(parser, shell, **kwargs)
    print(completion)
    return completion


# --- exec framework: run a generated completion in its shell & read back the candidates ---

PROMPT = "|candidates|"
# `\x18\x0c` is `^X^L` (bound below), `\x15` is `^U` (discard the line)
LIST_KEYS = {'zsh': b"\x18\x0c", 'tcsh': b"\x04"}
# bash splits `COMP_LINE` on whitespace *and* on each of these, keeping them as words
COMP_WORDBREAKS = " \t\n\"'><=;|&(:"


def comp_words(cmdline):
    """Split `cmdline` into bash's `(COMP_WORDS, COMP_CWORD)` (see `COMP_WORDBREAKS`)."""
    words, word = [], ""
    for char in cmdline:
        if char in COMP_WORDBREAKS:
            if word:
                words.append(word)
                word = ""
            if char not in " \t\n":
                words.append(char)
        else:
            word += char
    if word:
        words.append(word)
    if not cmdline or cmdline[-1] in " \t\n":
        words.append("") # the (empty) word the cursor sits on
    return words, len(words) - 1


def bash_candidates(completion, cmdlines, cwd=None):
    """Source `completion` in bash, then return the candidates offered for each of `cmdlines`."""
    func = re.search(r"^complete .*-F (\S+) ", completion, flags=re.M).group(1)
    result = []
    for cmdline in cmdlines:
        words, cword = comp_words(cmdline)
        driver = f"""
COMP_LINE={shlex.quote(cmdline)}
COMP_POINT=${{#COMP_LINE}}
COMP_WORDS=({" ".join(map(shlex.quote, words))})
COMP_CWORD={cword}
COMPREPLY=()
{func}
printf '%s\\n' "${{COMPREPLY[@]}}\""""
        proc = subprocess.run(['bash', '-o', 'pipefail', '-uc', completion + driver], cwd=cwd,
                              capture_output=True, text=True)
        assert not proc.stderr, proc.stderr
        result.append([line for line in proc.stdout.splitlines() if line.strip()])
    return result


def fish_candidates(completion, cmdlines, cwd=None):
    """Source `completion` in fish, then return the candidates offered for each of `cmdlines`."""
    if not shutil.which('fish'):
        pytest.skip("fish not available")
    result = []
    for cmdline in cmdlines:
        quoted = "'" + cmdline.replace("\\", "\\\\").replace("'", "\\'") + "'"
        out = subprocess.check_output(['fish', '-c', f"{completion}\ncomplete -C{quoted}"],
                                      cwd=cwd, text=True)
        # each output line is "candidate<TAB>description" (or just "candidate")
        result.append([line.split("\t")[0] for line in out.splitlines() if line.strip()])
    return result


def pty_candidates(shell, setup, cmdlines, cwd):
    """
    Return the candidates `shell` offers for each of `cmdlines`.

    Neither zsh nor tcsh has a `complete -C` equivalent, so drive an interactive one through
    a pty: type the command line, press the shell's list key, then `^U` to discard the line.
    `setup` must end up setting the prompt to `PROMPT`.
    """
    if not shutil.which(shell):
        pytest.skip(f"{shell} not available")
    pid, fd = pty.fork()
    if pid == 0:   # child
        os.chdir(cwd)
        os.environ['TERM'] = 'xterm'
        os.environ['COLUMNS'] = '999'
        os.execvp(shell, [shell, '-f', '-i'])
    output = ""

    def read(prompts, timeout=10.0):
        """Read until the prompt has been seen `prompts` times (or `timeout` elapses)."""
        nonlocal output
        strip = r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[=>]|[\a\r\b]"
        deadline = time.time() + timeout
        while output.count(PROMPT) < prompts and time.time() < deadline:
            if select.select([fd], [], [], 0.1)[0]:
                try:
                    chunk = os.read(fd, 1 << 16)
                except OSError:
                    break
                if not chunk:
                    break
                output += re.sub(strip, "", chunk.decode('utf-8', 'replace'))
        # a command just finished, give the shell a moment to enable its line editor again
        while select.select([fd], [], [], 0.2)[0]:
            output += re.sub(strip, "", os.read(fd, 1 << 16).decode('utf-8', 'replace'))
        return output

    result = []
    try:
        os.write(fd, setup.encode())
        read(1)
        for cmdline in cmdlines:
            seen = len(output)
            os.write(fd, cmdline.encode() + LIST_KEYS[shell] + b"\x15\n")
            chunk = read(output.count(PROMPT) + 1)[seen:].replace(PROMPT, "\n")
            # drop the echoed command line, the re-drawn prompt and zsh's partial-line marker,
            # leaving the listed candidates
            result.append([
                word for line in chunk.splitlines()
                if line.strip() not in ("", "%") and cmdline.strip() not in line
                for word in line.split()])
    finally:
        os.close(fd)
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
    return result


def zsh_candidates(completion, cmdlines, cwd=None):
    """Load `completion` in zsh, then return the candidates offered for each of `cmdlines`."""
    with script_file(completion, 'zsh') as script:
        setup = f"""autoload -Uz compinit; compinit -u
eval "$(<{script})"
unsetopt alwayslastprompt menucomplete automenu
zstyle ':completion:*' menu no
zstyle ':completion:*' verbose no
_shtab_list_only() {{ compstate[insert]=''; compstate[list]='list force'; _main_complete }}
zle -C shtab-list-only complete-word _shtab_list_only
bindkey '^X^L' shtab-list-only
PROMPT="{PROMPT[:6]}""{PROMPT[6:]}"
"""
        return pty_candidates('zsh', setup, cmdlines, cwd or os.getcwd())


def tcsh_candidates(completion, cmdlines, cwd=None):
    """Source `completion` in tcsh, then return the candidates offered for each of `cmdlines`."""
    with script_file(completion, 'tcsh') as script:
        # `^D` (`list-choices`) lists the candidates without inserting even a unique match
        setup = f"""set ignoreeof
source {script}
set prompt="{PROMPT[:6]}""{PROMPT[6:]}"
"""
        return pty_candidates('tcsh', setup, cmdlines, cwd or os.getcwd())


@contextmanager
def script_file(completion, shell):
    """`completion` as a file outside `cwd`, so it is not itself a file completion candidate."""
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / f"completion.{shell}"
        script.write_text(completion)
        yield script


shell_candidates = {
    'bash': bash_candidates, 'zsh': zsh_candidates, 'tcsh': tcsh_candidates,
    'fish': fish_candidates}


def candidates(shell, completion, cmdline, cwd=None):
    """Return the completion candidates `shell` offers for `cmdline`."""
    return shell_candidates[shell](completion, [cmdline], cwd)[0]


def plain(found):
    """Sorted candidates without the trailing `/` some shells add to directories."""
    return sorted(candidate.rstrip("/") for candidate in found)


def expected_options(shell, *options):
    """tcsh completes the text *after* the `--`, so its candidates omit the leading dashes."""
    return [option.lstrip("-") if shell == 'tcsh' else option for option in options]


@fix_shell
def test_candidates(shell, change_dir):
    """The exec framework itself: every shell must agree on a trivial completion."""
    parser = ArgumentParser(prog="myprog")
    parser.add_argument("posA", choices=["foo", "bar", "foobar"])
    completion = complete(parser, shell)
    assert candidates(shell, completion, "myprog f", change_dir) == ["foo", "foobar"]
    assert candidates(shell, completion, "myprog foob", change_dir) == ["foobar"]


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
        'bash': "complete -o filenames -F _shtab_shtab shtab", 'zsh': "_shtab_shtab_commands()",
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
        'bash': "complete -o filenames -F _shtab_shtab shtab", 'zsh': "_shtab_shtab_commands()",
        'tcsh': "complete shtab", 'fish': "complete -c shtab"}
    if output in ("-", "stdout"):
        assert expected[shell] in captured.out
    else:
        assert not captured.out
        assert expected[shell] in (change_dir / output).read_text()


@fix_shell
def test_prog_override(shell, capsys, change_dir):
    main(["-s", shell, "--prog", "foo", "shtab.main.get_main_parser"])
    captured = capsys.readouterr()
    assert not captured.err
    if shell == 'bash':
        assert "complete -o filenames -F _shtab_shtab foo" in captured.out
    # the completion is registered for `foo`, not for `shtab`
    assert candidates(shell, captured.out, "foo --h") == expected_options(shell, "--help")


@fix_shell
def test_prog_scripts(shell, capsys):
    main(["-s", shell, "--prog", "script.py", "shtab.main.get_main_parser"])

    captured = capsys.readouterr()
    assert not captured.err
    script_py = [i.strip() for i in captured.out.splitlines() if "script.py" in i]
    if shell == 'bash':
        assert script_py == ["complete -o filenames -F _shtab_shtab script.py"]
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
def test_prefix_override(shell, capsys, change_dir):
    main(["-s", shell, "--prefix", "foo", "shtab.main.get_main_parser"])
    captured = capsys.readouterr()
    assert not captured.err
    assert candidates(shell, captured.out, "shtab --h") == expected_options(shell, "--help")


@fix_shell
def test_complete(shell, change_dir):
    parser = get_main_parser()
    completion = complete(parser, shell)
    assert candidates(shell, completion, "shtab --h") == expected_options(shell, "--help")


@fix_shell
def test_positional_choices(shell, change_dir):
    parser = ArgumentParser(prog="test")
    parser.add_argument("posA", choices=["one", "two"])
    parser.add_argument("posB", choices=["BAA"]).complete = shtab.cmd("echo BZZ")
    completion = complete(parser, shell)
    assert "BAA" not in completion and "BZZ" in completion, ".complete should override choices"
    assert candidates(shell, completion, "test o") == ["one"]


@fix_shell
def test_custom_complete(shell, change_dir):
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
    if shell in ('zsh', 'tcsh'):
        pytest.skip("no custom completer defined for this shell")
    assert candidates(shell, completion, "test o") == ["one"]


def zsh_specs(completion, name):
    """`zsh -n` the completion, then return the values zsh assigns to array `name`."""
    if not shutil.which('zsh'):
        pytest.skip("zsh not available")
    subprocess.check_call(['zsh', '-nc', completion])
    with script_file(completion, 'zsh') as script:
        # `eval` so the script registers itself rather than running `compdef` (unavailable here)
        values = subprocess.check_output(
            ['zsh', '-f', '-c', f'eval "$(<{script})" 2>/dev/null; print -rl -- "${{(@){name}}}"'],
            text=True)
    return values.splitlines()


@pytest.mark.parametrize("help_text", [
    "plain help", "don't do this", "e.g. '>size_added,path'", 'a "quoted" value',
    "cost: $5 (100%%) `tick`"])
def test_zsh_help_quoting(help_text):
    """Help must not gain stray quotes (#224)"""
    parser = ArgumentParser(prog="test", add_help=False)
    parser.add_argument("--opt", help=help_text)
    completion = complete(parser, 'zsh')
    assert "'\"'\"'" not in completion, ("`shlex.quote`'s `'\"'\"'` idiom is invalid"
                                         " inside the double-quoted specs")
    specs = zsh_specs(completion, "_shtab_test_options")
    assert len(specs) == 1, f"quoting split the spec into {len(specs)} words: {specs}"
    # `_arguments` strips the backslashes; what must not appear is *extra* quotes
    assert specs[0].count("'") == help_text.count("'")
    assert specs[0].count('"') == help_text.count('"')


@fix_shell
def test_non_sequence_choices(shell, change_dir):
    parser = ArgumentParser(prog="myprog", add_help=False)
    parser.add_argument("--mapping", choices={"one": 1, "two": 2})
    parser.add_argument("posA", choices={"three"})
    completion = complete(parser, shell)
    if shell == 'zsh': # the spec is what carries the choices; check it too
        specs = zsh_specs(completion, "_shtab_myprog_options")
        assert specs == ["--mapping[]:mapping:(one two)", ":posA:(three)"]
    assert candidates(shell, completion, "myprog t") == ["three"]
    assert candidates(shell, completion, "myprog --mapping t") == ["two"]


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
    (change_dir / "subdir").mkdir()
    (change_dir / "subdir" / "nested.txt").touch()
    completion = complete(test_parser, shell)
    if shell == 'zsh': # `_files` is what does the work, so check the spec too
        specs = zsh_specs(completion, "_shtab_myprog_create_options")
        assert "(*)::paths to add:_files" in specs
    files = partial(candidates, shell, completion, cwd=change_dir)
    assert files("myprog create alpha test_") == ["test_file.txt"]
    assert plain(files("myprog create --exclude-from ")) == ["subdir", "test_file.txt"]

    # only `--exclude-from` and `paths` complete files
    assert not files("myprog delete test_")
    assert not files("myprog --repo test_")

    # zsh & tcsh list the basename, bash & fish the whole path
    nested = files("myprog create alpha subdir/nes")
    assert len(nested) == 1 and nested[0].endswith("nested.txt")
    nested = files(f"myprog create --exclude-from {change_dir / 'subdir' / 'nes'}")
    assert len(nested) == 1 and nested[0].endswith("nested.txt")


@fix_shell
def test_global_option_value(shell, change_dir, test_parser):
    """Subcommands complete after `--global-opt value` (#228)"""
    completion = complete(test_parser, shell)
    if shell == 'tcsh':
        pytest.xfail("tcsh completes files instead of subcommands after a global option's value")
    assert {"create", "delete",
            "list"} <= set(candidates(shell, completion, "myprog --repo x ", change_dir))


@fix_shell
def test_value_equal_to_command_name(shell, change_dir, test_parser):
    """Values matching command names must not confuse (#229)"""
    completion = complete(test_parser, shell)
    if shell == 'tcsh':
        pytest.xfail("tcsh offers the options of sibling subcommands")
    # `list` is the value of `delete`'s `name` positional, not the `list` subcommand
    found = candidates(shell, completion, "myprog delete list --", change_dir)
    assert "--force" in found
    assert "--exclude-from" not in found # `create`'s option


@fix_shell
def test_positional_order(shell, change_dir, test_parser):
    """Positionals are completed at the right slot (#230)"""
    completion = complete(test_parser, shell)
    # first slot offers the `name` choices
    assert {"alpha", "beta"} <= set(candidates(shell, completion, "myprog create ", change_dir))
    if shell == 'zsh':
        pytest.xfail("zsh re-offers the `name` choices at the `paths` slot")
    # later slots (the `paths` positional) must not re-offer them
    assert "alpha" not in candidates(shell, completion, "myprog create alpha alp", change_dir)


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
def test_subparser_custom_complete(shell, change_dir):
    parser = ArgumentParser(prog="test")
    subparsers = parser.add_subparsers()
    sub = subparsers.add_parser("sub", help="help message")
    sub.add_argument("posA").complete = {
        'bash': "_shtab_test_some_func", 'fish': "(_shtab_test_some_func)", 'preamble': {
            'bash': "_shtab_test_some_func() { compgen -W 'one two' -- $1 ;}",
            'fish': "function _shtab_test_some_func\n  printf '%s\\n' one two\nend"}}
    completion = complete(parser, shell)
    assert candidates(shell, completion, "test s") == ["sub"]
    if shell in ('zsh', 'tcsh'):
        pytest.skip("no custom completer defined for this shell")
    assert candidates(shell, completion, "test sub o") == ["one"]


@fix_shell
def test_subparser_aliases(shell, change_dir):
    parser = ArgumentParser(prog="test")
    subparsers = parser.add_subparsers()
    sub = subparsers.add_parser("sub", aliases=["xsub", "ysub"], help="help message")
    sub.add_argument("posA").complete = {
        'bash': "_shtab_test_some_func",
        'preamble': {'bash': "_shtab_test_some_func() { compgen -W 'one two' -- $1 ;}"}}
    completion = complete(parser, shell)
    for word, alias in [("s", "sub"), ("x", "xsub"), ("y", "ysub")]:
        assert candidates(shell, completion, f"test {word}") == [alias]
    if shell in ('zsh', 'tcsh', 'fish'):
        pytest.skip("no custom completer defined for this shell")
    assert candidates(shell, completion, "test sub o") == ["one"]


@fix_shell
def test_subparser_colons(shell, change_dir):
    parser = ArgumentParser(prog="test")
    subparsers = parser.add_subparsers()
    subparsers.add_parser("sub:cmd", help="help message")
    completion = complete(parser, shell)
    if shell == 'zsh':
        pytest.xfail("`_describe` reads the `:` as its name/description separator")
    assert candidates(shell, completion, "test s") == ["sub:cmd"]


@fix_shell
def test_subparser_slashes(shell, change_dir):
    parser = ArgumentParser(prog="test")
    subparsers = parser.add_subparsers()
    subparsers.add_parser("sub/cmd", help="help message")
    completion = complete(parser, shell)
    if shell == 'zsh': # the function name must not contain the `/`
        assert "_shtab_test_sub/cmd" not in completion
        assert "_shtab_test_sub_cmd" in completion
    if shell == 'tcsh':
        pytest.xfail("tcsh treats the `/` in a word list as a pathname separator")
    assert candidates(shell, completion, "test s") == ["sub/cmd"]


@fix_shell
def test_add_argument_to_optional(shell, change_dir):
    parser = ArgumentParser(prog="test")
    shtab.add_argument_to(parser, ["-s", "--shell"])
    completion = complete(parser, shell)
    assert candidates(shell, completion, "test --s") == expected_options(shell, "--shell")


@fix_shell
def test_add_argument_to_positional(shell, capsys, change_dir):
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
    assert candidates(shell, completion, "test c") == ["completion"]
    assert candidates(shell, completion, "test completion ba") == ["bash"]
    assert candidates(shell, completion, "test completion z") == ["zsh"]


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


@pytest.mark.parametrize("redirection", [">", ">>", "1>", "1>>", "2>", "2>>"])
def test_path_completion_after_redirection(change_dir, redirection):
    parser = ArgumentParser(prog="test")
    shtab.add_argument_to(parser, ["-s", "--shell"])
    completion = complete(parser, 'bash')
    (change_dir / "test_file.txt").touch()
    assert candidates('bash', completion, f"test {redirection} tes",
                      change_dir) == ["test_file.txt"]
