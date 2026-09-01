import hashlib
import logging
import re
from argparse import (ONE_OR_MORE, REMAINDER, SUPPRESS, ZERO_OR_MORE, Action, ArgumentParser,
                      _ActionsContainer, _AppendAction, _AppendConstAction, _CountAction,
                      _HelpAction, _StoreConstAction, _VersionAction)
from collections import defaultdict
from contextlib import contextmanager
from functools import total_ordering
from importlib.metadata import PackageNotFoundError, version
from itertools import starmap
from shlex import join, quote
from string import Template
from textwrap import dedent
from typing import Any, Callable
from typing import Optional as Opt
from typing import TypeVar, Union

try:
    __version__ = version('shtab')
except PackageNotFoundError:
    __version__ = "UNKNOWN"
__all__ = [
    "complete", "add_argument_to", "glob", "cmd", "SUPPORTED_SHELLS", "FILE", "DIRECTORY", "DIR"]
log = logging.getLogger(__name__)

ShellType = str
CompleteType = dict[ShellType, Union[str, dict[ShellType, str]]]
_ActionsContainerT = TypeVar('_ActionsContainerT', bound=_ActionsContainer)
SUPPORTED_SHELLS: list[ShellType] = []
_SUPPORTED_COMPLETERS: dict[ShellType, Callable] = {}
CHOICE_FUNCTIONS: dict[str, CompleteType] = {
    "file": {
        "bash": "_shtab_compgen_files",
        "zsh": "_files",
        "tcsh": "f",
        "fish": "(__fish_complete_path (commandline -ct))",
        "powershell": "_shtab_powershell_compgen_files",
    },
    "directory": {
        "bash": "_shtab_compgen_dirs",
        "zsh": "_files -/",
        "tcsh": "d",
        "fish": "(__fish_complete_directories)",
        "powershell": "_shtab_powershell_compgen_dirs",
    }} # yapf: disable
FILE = CHOICE_FUNCTIONS["file"]
DIRECTORY = DIR = CHOICE_FUNCTIONS["directory"]
FLAG_OPTION = (
    _StoreConstAction,
    _HelpAction,
    _VersionAction,
    _AppendConstAction,
    _CountAction,
)


def sha(obj):
    return hashlib.sha256(repr(obj).encode()).hexdigest()[:8]


def glob(*patterns: str) -> CompleteType:
    """
    Example: `glob("*.yml", "*.yaml")`

    Consider native shell alternatives in special cases:

    - any file: `shtab.FILE` (instead of `glob("*")`)
    - any directory: `shtab.DIRECTORY` (instead of `glob("*/")`)
    """
    return {
        "bash": f"_shtab_glob_compgen_{sha(patterns)}",
        "zsh": f"_files -g '({'|'.join(patterns)})'",
        "tcsh": f"f:{{{','.join(patterns)}}}",
        "fish": f"(_shtab_glob_compgen_{sha(patterns)})",
        "powershell": f"_shtab_glob_compgen_{sha(patterns)}",
        "preamble": {
            "bash": dedent(f"""
              # $1=COMP_WORDS[1]
              _shtab_glob_compgen_{sha(patterns)}() {{
                for ext in {join(patterns)}; do
                  compgen -f -X "!$ext" -- $1
                done
                compgen -d -- $1  # recurse into subdirs
              }}
              """),
            "fish": dedent(f"""
              function _shtab_glob_compgen_{sha(patterns)}
                set comp (commandline -ct)
                for pattern in {join(patterns)}
                  __fish_complete_path "$comp" | string match -e -- "$pattern"
                end
                __fish_complete_path "$comp" | string match -e "*/"  # recurse into subdirs
              end
              """),
            "powershell": dedent(rf"""
              function _shtab_glob_compgen_{sha(patterns)} {{
                param([string]$WordToComplete)
                $dir = ''
                if ($WordToComplete -match '^(.*[\\/])') {{ $dir = $Matches[1] }}
                Get-ChildItem -Path "$WordToComplete*" `
                -Include {_powershell_list(patterns)} -File -ErrorAction SilentlyContinue |
                  ForEach-Object {{ $dir + $_.Name }}
                Get-ChildItem -Path "$WordToComplete*" -Directory -ErrorAction SilentlyContinue |
                  ForEach-Object {{ $dir + $_.Name + [System.IO.Path]::DirectorySeparatorChar }}
              }}"""),
        }} # yapf: disable


def cmd(command: str) -> CompleteType:
    """
    command:
      shell command to run to generate completions

    Example: `cmd("git branch")`
    """
    return {
        "bash": f"_shtab_cmd_compgen_{sha(command)}",
        "zsh": f"($({command}))",
        "tcsh": f"`{command}`",
        "fish": f"({command})",
        "powershell": f"_shtab_cmd_compgen_{sha(command)}",
        "preamble": {
            "bash": dedent(f"""
              # $1=COMP_WORDS[1]
              _shtab_cmd_compgen_{sha(command)}() {{
                compgen -W "$({command})" -- $1
              }}"""),
            "powershell": dedent(f"""
              function _shtab_cmd_compgen_{sha(command)} {{
                param([string]$WordToComplete)
                $items = @(Invoke-Expression {_powershell_escape(command)} 2>$null)
                $items | ForEach-Object {{ $_.ToString() }} |
                  Where-Object {{ $_ -like "$WordToComplete*" }}
              }}"""),
        }} # yapf: disable


class _ShtabPrintCompletionAction(Action):
    pass


OPTION_END = _HelpAction, _VersionAction, _ShtabPrintCompletionAction
OPTION_MULTI = _AppendAction, _AppendConstAction, _CountAction


def mark_completer(shell):
    def wrapper(func):
        if shell not in SUPPORTED_SHELLS:
            SUPPORTED_SHELLS.append(shell)
        _SUPPORTED_COMPLETERS[shell] = func
        return func

    return wrapper


def get_completer(shell):
    try:
        return _SUPPORTED_COMPLETERS[shell]
    except KeyError:
        supported = ",".join(SUPPORTED_SHELLS)
        raise NotImplementedError(f"shell ({shell}) must be in {supported}")


@total_ordering
class Choice:
    """
    WARNING: deprecated. Use `.complete = ...` instead.
    Placeholder to mark a special completion `<type>`.

    >>> ArgumentParser.add_argument(..., choices=[Choice("<type>")])
    """
    def __init__(self, choice_type: str, required: bool = False) -> None:
        """
        choice_type  : internal `type` name
        required  : controls result of comparison to empty strings
        """
        self.required = required
        self.type = choice_type

    def __repr__(self) -> str:
        return self.type + ("" if self.required else "?")

    def __cmp__(self, other: object) -> int:
        if self.required:
            return 0 if other else -1
        return 0

    def __eq__(self, other: object) -> bool:
        return self.__cmp__(other) == 0

    def __lt__(self, other: object) -> bool:
        return self.__cmp__(other) < 0


class Optional:
    """
    WARNING: deprecated. Use `.complete = ...` instead.
    Example: `ArgumentParser.add_argument(..., choices=Optional.FILE)`.
    """
    FILE = [Choice("file")]
    DIR = DIRECTORY = [Choice("directory")]


class Required:
    """
    WARNING: deprecated. Use `.complete = ...` instead.
    Example: `ArgumentParser.add_argument(..., choices=Required.FILE)`.
    """
    FILE = [Choice("file", True)]
    DIR = DIRECTORY = [Choice("directory", True)]


def complete2pattern(opt_complete: CompleteType, shell: str, choice_type2fn: dict[str, str],
                     preambles: list[str]) -> str:
    if isinstance(opt_complete, dict):
        if preamble := opt_complete.get("preamble", {}).get(shell, ""): # type: ignore[union-attr]
            preambles.append(preamble)

    if isinstance(opt_complete, dict):
        return opt_complete.get(shell, "") # type: ignore[return-value]
    return choice_type2fn[opt_complete]


def wordify(string: str):
    """Replace non-word chars [\\W] with underscores [_]"""
    return re.sub("\\W", "_", string)


def get_public_subcommands(sub) -> dict[str, str]:
    """returns {'subcommand': "help text", ...} for a given subparser"""
    public_parsers = {id(sub.choices[i.dest]): i.help for i in sub._get_subactions()}
    # check SUPPRESS to be forward-compatible with python/cpython#67037
    return {
        k: h
        for k, v in sub.choices.items() if (h := public_parsers.get(id(v), SUPPRESS)) != SUPPRESS}


def is_subparser(positional):
    return isinstance(positional.choices, dict) and positional._get_subactions() and all(
        isinstance(v, ArgumentParser) for v in positional.choices.values())


def get_bash_commands(root_parser, root_prefix, choice_functions=None):
    """
    Recursive subcommand parser traversal, returning lists of information on
    commands (formatted for output to the completions script).
    printing bash helper syntax.

    Returns:
      subparsers  : list of subparsers for each parser
      option_strings  : list of options strings for each parser
      compgens  : list of shtab `.complete` functions corresponding to actions
      choices  : list of choices corresponding to actions
      nargs  : list of number of args allowed for each action (if not 0 or 1)
      preambles  : list of preamble functions
    """
    choice_type2fn = {k: v["bash"] for k, v in CHOICE_FUNCTIONS.items()}
    if choice_functions:
        choice_type2fn.update(choice_functions)
    subparsers = []
    option_strings = []
    compgens = []
    choices = []
    nargs = []
    preambles = []

    def recurse(parser, prefix):
        """Recurse through subparsers, appending to the return lists"""
        # positional arguments
        discovered_subparsers = []
        for i, positional in enumerate(parser._get_positional_actions()):
            if positional.help == SUPPRESS:
                continue

            if hasattr(positional, 'complete'):
                # shtab `.complete = ...` functions
                comp_pattern = complete2pattern(positional.complete, 'bash', choice_type2fn,
                                                preambles)
                compgens.append(f"{prefix}_pos_{i}_COMPGEN={quote(comp_pattern)}")
            elif positional.choices:
                # choices (including subparsers & shtab `.complete` functions)
                log.debug(f"choices:{prefix}:{sorted(positional.choices)}")
                if is_subparser(positional):
                    public_cmds = get_public_subcommands(positional)
                this_positional_choices = []
                for choice in positional.choices:
                    if isinstance(choice, Choice):
                        # append special completion type to `compgens`
                        # NOTE: overrides `.complete` attribute
                        log.debug(f"Choice.{choice.type}:{prefix}:{positional.dest}")
                        compgens.append(f"{prefix}_pos_{i}_COMPGEN="
                                        f"{quote(choice_type2fn[choice.type])}")
                    elif is_subparser(positional):
                        # subparser, so append to list of subparsers & recurse
                        log.debug("subcommand:%s", choice)
                        if choice in public_cmds:
                            discovered_subparsers.append(str(choice))
                            this_positional_choices.append(str(choice))
                            recurse(positional.choices[choice], f"{prefix}_{wordify(choice)}")
                        else:
                            log.debug("skip:subcommand:%s", choice)
                    else:
                        # simple choice
                        this_positional_choices.append(str(choice))

                if this_positional_choices:
                    choices.append(f"{prefix}_pos_{i}_choices=({join(this_positional_choices)})")

            # skip default `nargs` values
            if positional.nargs not in (None, "1", "?"):
                nargs.append(f"{prefix}_pos_{i}_nargs={quote(str(positional.nargs))}")

        if discovered_subparsers:
            subparsers.append(f"{prefix}_subparsers=({join(discovered_subparsers)})")
            log.debug(f"subcommands:{prefix}:{discovered_subparsers}")

        # optional arguments
        option_strings_list = join(
            sum((opt.option_strings
                 for opt in parser._get_optional_actions() if opt.help != SUPPRESS), []))
        option_strings.append(f"{prefix}_option_strings=({option_strings_list})")
        for optional in parser._get_optional_actions():
            if optional.help == SUPPRESS:
                continue
            for option_string in optional.option_strings:
                if hasattr(optional, 'complete'):
                    # shtab `.complete = ...` functions
                    comp_pattern_str = complete2pattern(optional.complete, 'bash', choice_type2fn,
                                                        preambles)
                    compgens.append(
                        f"{prefix}_{wordify(option_string)}_COMPGEN={quote(comp_pattern_str)}")
                elif optional.choices:
                    # choices (including shtab `.complete` functions)
                    this_optional_choices = []
                    for choice in optional.choices:
                        # append special completion type to `compgens`
                        # NOTE: overrides `.complete` attribute
                        if isinstance(choice, Choice):
                            log.debug(f"Choice.{choice.type}:{prefix}:{optional.dest}")
                            func_str = choice_type2fn[choice.type]
                            compgens.append(f"{prefix}_{wordify(option_string)}_COMPGEN="
                                            f"{quote(func_str)}")
                        else:
                            # simple choice
                            this_optional_choices.append(str(choice))

                    if this_optional_choices:
                        choices.append(f"{prefix}_{wordify(option_string)}_choices="
                                       f"({join(this_optional_choices)})")

                # Check for nargs.
                if optional.nargs is not None and optional.nargs != 1:
                    nargs.append(f"{prefix}_{wordify(option_string)}_nargs="
                                 f"{quote(str(optional.nargs))}")

        return subparsers, option_strings, compgens, choices, nargs, preambles

    return recurse(root_parser, root_prefix)


@mark_completer("bash")
def complete_bash(parser, root_prefix=None, preamble="", choice_functions=None):
    """
    Returns bash syntax autocompletion script.

    See `complete` for arguments.
    """
    root_prefix = wordify(f"_shtab_{root_prefix or parser.prog}")
    subparsers, option_strings, compgens, choices, nargs, extra_preambles = get_bash_commands(
        parser, root_prefix, choice_functions=choice_functions)
    preamble = "\n".join(list(dict.fromkeys(([preamble] if preamble else []) + extra_preambles)))
    # References:
    # - https://www.gnu.org/software/bash/manual/html_node/Programmable-Completion.html
    # - https://opensource.com/article/18/3/creating-bash-completion-script
    # - https://stackoverflow.com/questions/12933362
    return Template("""\
# AUTOMATICALLY GENERATED by https://github.com/tqdm/shtab
# Usage:
# 1) Copy this to somewhere (e.g. ~/.local/share/bash_completion/${prog}).
# 2) Add the following line to your .bashrc:
#    source ~/.local/share/bash_completion/${prog}
# See also: https://github.com/scop/bash-completion/blob/main/doc/configuration.md

${subparsers}

${option_strings}

${compgens}

${choices}

${nargs}

${preamble}
# $1=COMP_WORDS[1]
_shtab_compgen_files() {
  compgen -f -- $1  # files
}

# $1=COMP_WORDS[1]
_shtab_compgen_dirs() {
  compgen -d -- $1  # recurse into subdirs
}

# $1=COMP_WORDS[1]
_shtab_replace_nonword() {
  echo "${1//[^[:word:]]/_}"
}

# set default values (called for the initial parser & any subparsers)
_set_parser_defaults() {
  local subparsers_var="${prefix}_subparsers[@]"
  sub_parsers=${!subparsers_var-}

  local current_option_strings_var="${prefix}_option_strings[@]"
  current_option_strings=${!current_option_strings_var}

  completed_positional_actions=0

  _set_new_action "pos_$completed_positional_actions" true
}

# $1=action identifier
# $2=positional action (bool)
# set all identifiers for an action's parameters
_set_new_action() {
  current_action="${prefix}_$(_shtab_replace_nonword $1)"

  local current_action_compgen_var=${current_action}_COMPGEN
  current_action_compgen="${!current_action_compgen_var-}"

  local current_action_choices_var="${current_action}_choices[@]"
  current_action_choices="${!current_action_choices_var-}"

  local current_action_nargs_var="${current_action}_nargs"
  if [ -n "${!current_action_nargs_var-}" ]; then
    current_action_nargs="${!current_action_nargs_var}"
  else
    current_action_nargs=1
  fi

  current_action_args_start_index=$(( $word_index + 1 - $pos_only ))

  current_action_is_positional=$2
}

# Notes:
# `COMPREPLY`: what will be rendered after completion is triggered
# `completing_word`: currently typed word to generate completions for
# `${!var}`: evaluates the content of `var` and expand its content as a variable
#     hello="world"
#     x="hello"
#     ${!x} -> ${hello} -> "world"
${root_prefix}() {
  local completing_word="${COMP_WORDS[COMP_CWORD]}"
  local previous_word="${COMP_WORDS[COMP_CWORD-1]}"
  local completed_positional_actions
  local current_action
  local current_action_args_start_index
  local current_action_choices
  local current_action_compgen
  local current_action_is_positional
  local current_action_nargs
  local current_option_strings
  local sub_parsers
  COMPREPLY=()

  local prefix=${root_prefix}
  local word_index=0
  local pos_only=0 # "--" delimiter not encountered yet
  _set_parser_defaults
  word_index=1

  # determine what arguments are appropriate for the current state
  # of the arg parser
  while [ $word_index -ne $COMP_CWORD ]; do
    local this_word="${COMP_WORDS[$word_index]}"

    if [[ $pos_only = 1 || " $this_word " != " -- " ]]; then
      if [[ -n $sub_parsers && " ${sub_parsers[@]} " == *" $this_word "* ]]; then
        # valid subcommand: add it to the prefix & reset the current action
        prefix="${prefix}_$(_shtab_replace_nonword $this_word)"
        _set_parser_defaults
      fi

      if [[ " ${current_option_strings[@]} " == *" $this_word "* ]]; then
        # a new action should be acquired (due to recognised option string or
        # no more input expected from current action);
        # the next positional action can fill in here
        _set_new_action $this_word false
      fi

      if [[ "$current_action_nargs" != "*" ]] && \\
         [[ "$current_action_nargs" != "+" ]] && \\
         [[ "$current_action_nargs" != "?" ]] && \\
         [[ "$current_action_nargs" != *"..." ]] && \\
         (( $word_index + 1 - $current_action_args_start_index - $pos_only >= \\
            $current_action_nargs )); then
        $current_action_is_positional && let "completed_positional_actions += 1"
        _set_new_action "pos_$completed_positional_actions" true
      fi
    else
      pos_only=1 # "--" delimiter encountered
    fi

    let "word_index+=1"
  done

  # Generate the completions

  COMPREPLY=()
  if [[ $pos_only = 0 && "$completing_word" == -* &&
        ( -z "$current_action_compgen" || "$current_action_is_positional" = true ) ]]; then
    # optional argument started: use option strings
    while IFS= read -r line; do COMPREPLY+=("$line"); done < <(
      compgen -W "${current_option_strings[*]}" -- "$completing_word")
  elif [[ "$previous_word" =~ ^[0-9\\&]*[\\<\\>]\\>?$ ]]; then
    # handle redirection operators
    compopt -o filenames 2>/dev/null || : # bash>=4
    while IFS= read -r line; do COMPREPLY+=("$line"); done < <(compgen -f -- "$completing_word")
  else
    # use choices & compgen
    local action_compgen_word="$completing_word"
    # handle tab-completing in the middle of a line (#248 <- #116)
    [[ -n "$current_action_compgen" && "$completing_word" == -* ]] && action_compgen_word=""
    [ -n "$current_action_compgen" ] && {
      [[ "$current_action_compgen" =~ _(file|dir|glob|FILE|DIR|GLOB)|File|Dir|Glob ]] &&
        compopt -o filenames 2>/dev/null || : # bash>=4
      while IFS= read -r line; do COMPREPLY+=("$line"); done < <(
        "$current_action_compgen" "$action_compgen_word")
    }
    while IFS= read -r line; do COMPREPLY+=("$line"); done < <(
      compgen -W "${current_action_choices[*]}" -- "$completing_word")
  fi

  return 0
}

complete -F ${root_prefix} ${prog}""").safe_substitute(
        subparsers="\n".join(subparsers),
        option_strings="\n".join(option_strings),
        compgens="\n".join(compgens),
        choices="\n".join(choices),
        nargs="\n".join(nargs),
        preamble=f"\n# Custom Preamble\n{preamble}\n# End Custom Preamble\n" if preamble else "",
        root_prefix=root_prefix,
        prog=parser.prog,
    )


def head(string):
    return str(string).strip().split("\n")[0] if string else ""


@contextmanager
def get_formatter(parser):
    formatter = parser._get_formatter()
    backup_width = formatter._width
    try:
        formatter._width = 999 # large number to effectively disable wrapping

        def inner(str_or_parser):
            return head(
                formatter._format_text(str_or_parser if isinstance(str_or_parser, str) else
                                       formatter._expand_help(str_or_parser)))

        yield inner
    finally:
        formatter._width = backup_width


def escape_zsh(string):
    """
    Backslash-escape for interpolation into a double-quoted `_arguments` spec.

    NOTE: cannot use `shlex.quote` (a single-quoted word only valid at top level).
    """
    # excessive but safe
    return head(re.sub(r"([^\w\s.,()-])", r"\\\1", str(string))) if string else ""


@mark_completer("zsh")
def complete_zsh(parser, root_prefix=None, preamble="", choice_functions=None):
    """
    Returns zsh syntax autocompletion script.

    See `complete` for arguments.
    """
    prog = parser.prog
    preambles = [preamble] if preamble else []
    root_prefix = wordify(f"_shtab_{root_prefix or prog}")

    choice_type2fn = {k: v["zsh"] for k, v in CHOICE_FUNCTIONS.items()}
    if choice_functions:
        choice_type2fn.update(choice_functions)

    def get_candidates(arg):
        if hasattr(arg, 'complete'):
            return complete2pattern(arg.complete, 'zsh', choice_type2fn, preambles)
        if arg.choices:
            first = next(iter(arg.choices))
            if isinstance(first, Choice):
                return choice_type2fn[first.type]
            return "({})".format(" ".join(map(str, arg.choices)))

    def format_optional(opt, get_help):
        return (('{nargs}{options}"[{help}]"' if (isinstance(opt, FLAG_OPTION) or opt.nargs == 0)
                 else '{nargs}{options}"[{help}]:{dest}:{pattern}"').format(
                     nargs=('"(- : *)"' if (isinstance(opt, OPTION_END) or opt.nargs == REMAINDER)
                            else '"*"' if isinstance(opt, OPTION_MULTI) else ""),
                     options=("{{{}}}".format(",".join(opt.option_strings)) if len(
                         opt.option_strings) > 1 else '"{}"'.format("".join(opt.option_strings))),
                     help=escape_zsh(get_help(opt) if opt.help else opt.metavar or opt.dest),
                     dest=opt.metavar or opt.dest, pattern=get_candidates(opt)
                     or "").replace('""', ''))

    def format_positional(opt, get_help):
        return '"{nargs}:{help}:{pattern}"'.format(
            nargs={ONE_OR_MORE: "(*)", ZERO_OR_MORE: "(*):",
                   REMAINDER: "(-)*:"}.get(opt.nargs, ""),
            help=escape_zsh(get_help(opt) if opt.help else opt.metavar or opt.dest),
            pattern=get_candidates(opt) or "")

    # {cmd: {"help": help, "arguments": [arguments]}}
    with get_formatter(parser) as get_help:
        all_commands = {
            root_prefix: {
                "cmd": prog, "arguments": [
                    format_optional(opt, get_help)
                    for opt in parser._get_optional_actions() if opt.help != SUPPRESS] + [
                        format_positional(opt, get_help)
                        for opt in parser._get_positional_actions()
                        if opt.help != SUPPRESS and not is_subparser(opt)],
                "help": head(parser.description), "commands": [], "paths": []}}

    def recurse(parser, prefix, paths=None):
        paths = paths or []
        subcmds = []
        for sub in parser._get_positional_actions():
            if sub.help == SUPPRESS or not is_subparser(sub):
                continue
            log.debug(f"subparser:choices:{prefix}:{sorted(sub.choices)}")
            public_cmds = get_public_subcommands(sub)
            for cmd, subparser in sub.choices.items():
                if cmd not in public_cmds:
                    log.debug("skip:subcommand:%s", cmd)
                    continue
                log.debug("subcommand:%s", cmd)
                with get_formatter(subparser) as get_help:
                    # optionals
                    arguments = [
                        format_optional(opt, get_help)
                        for opt in subparser._get_optional_actions() if opt.help != SUPPRESS]
                    # positionals
                    arguments.extend(
                        format_positional(opt, get_help)
                        for opt in subparser._get_positional_actions()
                        if opt.help != SUPPRESS and not is_subparser(opt))
                    # help text
                    desc = get_help(subparser.description or public_cmds[cmd])
                new_pref = f"{prefix}_{wordify(cmd)}"
                options = all_commands[new_pref] = {
                    "cmd": cmd, "help": desc, "arguments": arguments, "paths": [*paths, cmd]}
                new_subcmds = recurse(subparser, new_pref, [*paths, cmd])
                options["commands"] = {
                    all_commands[pref]["cmd"]: all_commands[pref]
                    for pref in new_subcmds if pref in all_commands}
                subcmds.extend([*new_subcmds, new_pref])
                log.debug("subcommands:%s:%s", cmd, options)
        return subcmds

    recurse(parser, root_prefix)
    all_commands[root_prefix]["commands"] = {
        options["cmd"]: options
        for prefix, options in sorted(all_commands.items())
        if len(options.get("paths", [])) < 2 and prefix != root_prefix}
    subcommands = {
        prefix: options
        for prefix, options in all_commands.items() if options.get("commands")}
    subcommands.setdefault(root_prefix, all_commands[root_prefix])
    log.debug("subcommands:%s:%s", root_prefix, sorted(all_commands))

    def command_case(prefix, options):
        name = options["cmd"]
        commands = options["commands"]
        case_fmt_on_no_sub = """{name}) _arguments -C -s ${prefix}_{name_wordify}_options ;;"""
        case_fmt_on_sub = """{name}) {prefix}_{name_wordify} ;;"""

        cases = []
        for _, options in sorted(commands.items()):
            fmt = case_fmt_on_sub if options.get("commands") else case_fmt_on_no_sub
            cases.append(
                fmt.format(name=options["cmd"], name_wordify=wordify(options["cmd"]),
                           prefix=prefix))
        cases = "\n\t".expandtabs(8).join(cases)

        return Template("""\
${prefix}() {
  local context state line \
curcontext="$curcontext" one_or_more='(*)' remainder='(-)*:' default='*::: :->${name}'

  # Add default positional/remainder specs only if none exist, and only once per session
  if (( ! ${prefix}_defaults_added )); then
    if (( ${${prefix}_options[(I)${(q)one_or_more}*]} +\
          ${${prefix}_options[(I)${(q)remainder}*]} +\
          ${${prefix}_options[(I)${(q)default}]} == 0 )); then
      ${prefix}_options+=(': :${prefix}_commands' '*::: :->${name}')
    fi
    ${prefix}_defaults_added=1
  fi
  _arguments -C -s $$${prefix}_options

  case $state in
    ${name})
      words=($line[1] "${words[@]}")
      (( CURRENT += 1 ))
      curcontext="${curcontext%:*:*}:${prefix}-$line[1]:"
      case $line[1] in
        ${cases}
      esac
  esac
}
""").safe_substitute(name=name, prefix=prefix, cases=cases)

    def command_option(prefix, options):
        arguments = "\n  ".join(options["arguments"])
        return f"""\
{prefix}_options=(
  {arguments}
)

# guard to ensure default positional specs are added only once per session
{prefix}_defaults_added=0
"""

    def command_list(prefix, options):
        name = " ".join([prog, *options["paths"]])
        commands = "\n    ".join(f'{quote(cmd)}:{quote(opt["help"])}'
                                 for cmd, opt in sorted(options["commands"].items()))
        return f"""
{prefix}_commands() {{
  local _commands=(
    {commands}
  )
  _describe '{name} commands' _commands
}}"""

    preamble = "\n".join(list(dict.fromkeys(preambles)))
    # References:
    # - https://github.com/zsh-users/zsh-completions
    # - http://zsh.sourceforge.net/Doc/Release/Completion-System.html
    # - https://mads-hartmann.com/2017/08/06/writing-zsh-completion-scripts.html
    # - http://www.linux-mag.com/id/1106/
    return Template("""\
#compdef ${prog}

# AUTOMATICALLY GENERATED by https://github.com/tqdm/shtab
# Usage:
# 1) Copy this to a file named _${prog} (e.g. ~/.local/share/zsh_completion/_${prog}).
# 2) Add the following line to your .zshrc:
#    fpath=(~/.local/share/zsh_completion $fpath)
# See also: https://github.com/zsh-users/zsh-completions/blob/master/zsh-completions-howto.org

${command_commands}

${command_options}

${command_cases}
${preamble}

typeset -A opt_args

if [[ $zsh_eval_context[-1] == eval ]]; then
  # eval/source/. command, register function for later
  compdef ${root_prefix} -N ${prog}
else
  # autoload from fpath, call function directly
  ${root_prefix} "$@\"
fi
""").safe_substitute(
        prog=prog,
        root_prefix=root_prefix,
        command_cases="\n".join(starmap(command_case, sorted(subcommands.items()))),
        command_commands="\n".join(starmap(command_list, sorted(subcommands.items()))),
        command_options="\n".join(starmap(command_option, sorted(all_commands.items()))),
        preamble=f"""# Custom Preamble\n{preamble}\n# End Custom Preamble\n""" if preamble else "",
    )


@mark_completer("tcsh")
def complete_tcsh(parser, root_prefix=None, preamble="", choice_functions=None):
    """
    Return tcsh syntax autocompletion script.

    root_prefix:
      ignored (tcsh has no support for functions)

    See `complete` for other arguments.
    """
    optionals_single = set()
    optionals_double = set()
    specials = []
    # `--opt=<TAB>` rules, emitted before the generic `c/--/` one which would shadow them
    eq_specials = []
    index_choices = defaultdict(dict)
    preambles = [preamble] if preamble else []

    choice_type2fn = {k: v["tcsh"] for k, v in CHOICE_FUNCTIONS.items()}
    if choice_functions:
        choice_type2fn.update(choice_functions)

    def get_specials(arg, arg_type, arg_sel, check_subparser=False):
        if hasattr(arg, 'complete'):
            complete_fn = complete2pattern(arg.complete, 'tcsh', choice_type2fn, preambles)
            if complete_fn:
                yield f"'{arg_type}/{arg_sel}/{complete_fn}/'"
        elif arg.choices:
            if check_subparser and is_subparser(arg):
                choice_strs = ' '.join(get_public_subcommands(arg))
            else:
                choice_strs = ' '.join(map(str, arg.choices))
            yield f"'{arg_type}/{arg_sel}/({choice_strs})/'"

    def recurse_parser(cparser, positional_idx, requirements=None):
        log_prefix = "| " * positional_idx
        log.debug("%sParser @ %d", log_prefix, positional_idx)
        if requirements:
            log.debug("%s- Requires: %s", log_prefix, " ".join(requirements))
        else:
            requirements = []

        for optional in cparser._get_optional_actions():
            if optional.help == SUPPRESS:
                continue
            log.debug("%s| Optional: %s", log_prefix, optional.dest)
            # Mingle all optional arguments for all subparsers
            for optional_str in optional.option_strings:
                log.debug("%s| | %s", log_prefix, optional_str)
                if optional_str.startswith('--'):
                    optionals_double.add(optional_str[2:])
                elif optional_str.startswith('-'):
                    optionals_single.add(optional_str[1:])
                specials.extend(get_specials(optional, 'n', optional_str))
                if optional.nargs != 0:
                    eq_specials.extend(get_specials(optional, 'c', optional_str + '='))

        for positional in cparser._get_positional_actions():
            positional_idx += 1
            if positional.help == SUPPRESS:
                continue
            log.debug("%s| Positional #%d: %s", log_prefix, positional_idx, positional.dest)
            index_choices[positional_idx][tuple(requirements)] = positional
            if is_subparser(positional):
                public_cmds = get_public_subcommands(positional)
                for subcmd, subparser in positional.choices.items():
                    if subcmd in public_cmds:
                        log.debug("%s| | SubParser: %s", log_prefix, subcmd)
                        recurse_parser(subparser, positional_idx, requirements + [subcmd])
                    else:
                        log.debug("%s| | SubParser skip: %s", log_prefix, subcmd)

    recurse_parser(parser, 0)

    for idx, ndict in index_choices.items():
        if len(ndict) == 1:
            # Single choice, no requirements
            arg = next(iter(ndict.values()))
            specials.extend(get_specials(arg, 'p', str(idx), True))
        else:
            # Multiple requirements
            nlist = []
            for nn, arg in ndict.items():
                if nn and idx == len(nn) + 1:
                    # lookup preceding (sub)command name for completions
                    specials.extend(get_specials(arg, 'n', nn[-1]))
                    continue
                max_idx = len(nn) + 1
                checks = [f'("$cmd[{iidx}]" == "{n}")' for iidx, n in enumerate(nn, start=2)]
                condition = f"$#cmd >= {max_idx} && " + " && ".join(checks)
                if hasattr(arg, 'complete'):
                    complete_fn = complete2pattern(arg.complete, 'tcsh', choice_type2fn, preambles)
                    if complete_fn:
                        if complete_fn.startswith('`') and complete_fn.endswith('`'):
                            # nested backticks crash tcsh's parser, use `eval` instead
                            nlist.append(f"if ( {condition} ) eval {complete_fn.strip('`')}")
                        else:
                            log.debug("warning: tcsh cannot express completion patterns"
                                      " (`f:*.txt`, `d`, ...) as commands")
                elif arg.choices:
                    nlist.append(f"if ( {condition} ) echo {join(map(str, arg.choices))}")
            if nlist:
                nlist_str = '; '.join(nlist)
                # pad $cmd so indexing it never runs out of range.
                # $COMMAND_LINE must stay unquoted to allow csh word splitting.
                padding = ' '.join(['""'] * 9)
                specials.append(
                    f"'p@{str(idx)}@`set cmd=($COMMAND_LINE {padding}); {nlist_str}`@'")

    if optionals_double:
        if optionals_single:
            optionals_single.add('-')
        else:
            # Don't add a space after completing "--" from "-"
            optionals_single = ('-', '-')

    specials = list(dict.fromkeys(specials))
    eq_specials = list(dict.fromkeys(eq_specials))
    preamble = "\n".join(list(dict.fromkeys(preambles)))
    return Template("""\
# AUTOMATICALLY GENERATED by https://github.com/tqdm/shtab
# Usage:
# 1) Copy this to somewhere (e.g. ~/.local/share/tcsh_completion/${prog}).
# 2) Add the following line to your .cshrc or .tcshrc:
#    source ~/.local/share/tcsh_completion/${prog}
# See also: https://github.com/tcsh-org/tcsh/blob/master/complete.tcsh

${preamble}

complete ${prog} \\
        ${optionals_eq}'c/--/(${optionals_double})/' \\
        'c/-/(${optionals_single})/' \\
        ${optionals_special} \\
        'p/*/()/'""").safe_substitute(
        preamble=f"\n# Custom Preamble\n{preamble}\n# End Custom Preamble\n" if preamble else "",
        prog=parser.prog, optionals_double=' '.join(sorted(optionals_double)),
        optionals_single=' '.join(sorted(optionals_single)),
        optionals_eq=''.join(f'{eq} \\\n        ' for eq in eq_specials),
        optionals_special=' \\\n        '.join(specials))


@mark_completer("fish")
def complete_fish(parser, root_prefix=None, preamble="", choice_functions=None):
    """
    Return fish syntax autocompletion script.

    See `complete` for arguments.
    """
    prog = parser.prog
    prefix = wordify(f"_shtab_{root_prefix or prog}")
    completions = []
    commands = []           # all (sub)command paths, e.g. ["sub", "sub subsub"]
    opts_with_value = set() # option strings which consume a following value token
    preambles = [preamble] if preamble else []

    choice_type2fn = {k: v["fish"] for k, v in CHOICE_FUNCTIONS.items()}
    if choice_functions:
        choice_type2fn.update(choice_functions)

    def get_candidates(arg):
        if hasattr(arg, 'complete'):
            return complete2pattern(arg.complete, 'fish', choice_type2fn, preambles)
        if arg.choices:
            return join(map(str, arg.choices))

    def pos_condition(index, width, open_ended):
        """Condition suffix restricting a completion to the given positional slot(s)."""
        npos = f"${prefix}_npos"
        if open_ended or width is None:
            return f"; and test {npos} -ge {index}"
        if width == 1:
            return f"; and test {npos} -eq {index}"
        return f"; and test {npos} -ge {index}; and test {npos} -le {index + width - 1}"

    def start_output(path, pos_test=""):
        """`complete` command start, with a condition matching the (sub)command `path`."""
        cond = " ".join([f"{prefix}_using"] + [quote(cmd) for cmd in path]) + pos_test
        return ["complete", "-c", prog, f"-n {quote(cond)}"]

    def recurse_parser(cparser: ArgumentParser, path: list[str]):
        """
        path:
          the list of subcommands that led to current
        """
        log_prefix = "| " * len(path)
        log.debug("%sParser @ %d", log_prefix, len(path))
        for optional in cparser._get_optional_actions():
            log.debug("%s| Optional: %s", log_prefix, optional.dest)
            if optional.help == SUPPRESS:
                continue
            output = start_output(path)
            for optional_str in optional.option_strings:
                log.debug("%s| | %s", log_prefix, optional_str)
                if optional_str.startswith("--"):
                    output.append(f"-l {optional_str[2:]}")
                elif optional_str.startswith("-"):
                    output.append(f"-s {optional_str[1:]}")
            if not (isinstance(optional, FLAG_OPTION) or optional.nargs == 0):
                opts_with_value.update(optional.option_strings)
                candidates = get_candidates(optional)
                output.append(f'-xka "{candidates}"' if candidates else "-x")
            with get_formatter(cparser) as get_help:
                if desc := head(
                        get_help(optional) if optional.help else optional.metavar or optional.dest
                ):
                    output.append(f'-d {quote(desc)}')
            completions.append(' '.join(output))

        index = 0          # the next positional slot (number of preceding positional arguments)
        open_ended = False # an earlier positional consumes any number of tokens

        for positional in cparser._get_positional_actions():
            if positional.help == SUPPRESS:
                continue
            log.debug("%s| Positional #%d: %s", log_prefix, index, positional.dest)
            if is_subparser(positional):
                public_cmds = get_public_subcommands(positional)
                pos_test = pos_condition(index, 1, open_ended)
                for subcmd, subparser in positional.choices.items(): # type: ignore[union-attr]
                    if subcmd not in public_cmds:
                        continue
                    log.debug("%s| | SubParser: %s", log_prefix, subcmd)
                    commands.append(" ".join(path + [subcmd]))
                    output = start_output(path, pos_test)
                    output.append(f"-a {quote(subcmd)}")
                    with get_formatter(subparser) as get_help:
                        if desc := get_help(subparser.description or public_cmds[subcmd]):
                            output.append(f'-d {quote(desc)}')
                    completions.append(' '.join(output))
                    recurse_parser(subparser, path + [subcmd])
                index += 1

            else:
                # simple argument (file, name...)
                width = (positional.nargs if isinstance(positional.nargs, int) else
                         1 if positional.nargs in (None, "?") else None)
                candidates = get_candidates(positional)
                if candidates:
                    output = start_output(path, pos_condition(index, width, open_ended))
                    output.append(f'-ka "{candidates}"')
                    with get_formatter(cparser) as get_help:
                        if desc := head(
                                get_help(positional) if positional.
                                help else positional.metavar or positional.dest):
                            output.append(f'-d {quote(desc)}')
                    completions.append(' '.join(output))
                if width is None:
                    open_ended = True
                else:
                    index += width

    recurse_parser(parser, [])

    preamble = "\n".join(list(dict.fromkeys(preambles)))
    return Template("""\
# AUTOMATICALLY GENERATED by https://github.com/tqdm/shtab
# Usage:
# 1) Copy this to ~/.config/fish/completions/${prog}.fish
# 2) Ensure a binary named ${prog} is in your PATH
# See also: https://fishshell.com/docs/current/completions.html#where-to-put-completions

${preamble}
# Parse current commandline:
# - ${prefix}_cmdpath=(sub)command path seen so far
# - ${prefix}_npos=number of positional arguments given after it
# - options are skipped based on ${prefix}_opts_with_value & ${prefix}_commands lists
function ${prefix}_scan
  set -g ${prefix}_cmdpath ''
  set -g ${prefix}_npos 0
  set -l tokens (commandline -opc)
  set -e tokens[1]
  set -l expect_value 0
  for t in $tokens
    if test $expect_value -eq 1
      set expect_value 0
      continue
    end
    switch "$t"
      case '--*=*'
        continue
      case '-*'
        if contains -- $t $$${prefix}_opts_with_value
          set expect_value 1
        end
        continue
      case '*'
        if test $$${prefix}_npos -eq 0
          set -l candidate $t
          if test -n "$$${prefix}_cmdpath"
            set candidate "$$${prefix}_cmdpath $t"
          end
          if contains -- $candidate $$${prefix}_commands
            set -g ${prefix}_cmdpath $candidate
            continue
          end
        end
        set -g ${prefix}_npos (math $$${prefix}_npos + 1)
    end
  end
end

# Condition helper: true if the current (sub)command path equals the given one.
function ${prefix}_using
  ${prefix}_scan
  test "$$${prefix}_cmdpath" = "$argv"
end

set -g ${prefix}_commands ${commands}
set -g ${prefix}_opts_with_value ${opts_with_value}

complete -c ${prog} -e
complete -c ${prog} -f

${completions}
""").safe_substitute(
        preamble=f"# Custom Preamble\n{preamble}\n# End Custom Preamble\n" if preamble else "",
        prog=parser.prog,
        prefix=prefix,
        commands=' '.join(quote(cmd) for cmd in commands),
        opts_with_value=' '.join(quote(opt) for opt in sorted(opts_with_value)),
        completions='\n'.join(completions),
    )


def _powershell_escape(string: str) -> str:
    """
    Similar to `shlex.quote`, see:
    https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/
    about/about_quoting_rules
    """
    s = str(string)
    # all five `single-quote-character`s close a verbatim string literal
    # (PowerShell Language Specification 3.0 section 2.3.5.1.1)
    for ch in "'\u2018\u2019\u201a\u201b":
        s = s.replace(ch, ch * 2)
    return f"'{s}'"


def _powershell_list(items):
    """Serialize a list of strings to a PowerShell array literal."""
    escaped = ", ".join(_powershell_escape(i) for i in items)
    return f"@({escaped})"


def _powershell_hashtable(d):
    """Serialize a dict[str, list[str]] to PowerShell @{} syntax."""
    if not d:
        return "@{}"
    entries = [
        f"    {_powershell_escape(key)} = {_powershell_list(values)}"
        for key, values in sorted(d.items())]
    return "@{\n" + "\n".join(entries) + "\n}"


def _powershell_flat_hashtable(d):
    """Serialize a dict[str, str] to PowerShell @{} syntax."""
    if not d:
        return "@{}"
    entries = [
        f"    {_powershell_escape(key)} = {_powershell_escape(value)}"
        for key, value in sorted(d.items())]
    return "@{\n" + "\n".join(entries) + "\n}"


def get_powershell_commands(root_parser, root_prefix, choice_functions=None):
    """
    Recursive subcommand parser traversal, returning dicts of information on
    commands (formatted for output to the PowerShell completions script).

    Returns:
      subparsers  : dict mapping prefix -> list of subparser names
      option_strings  : dict mapping prefix -> list of option strings
      compgens  : dict mapping action key -> completer function name
      choices  : dict mapping action key -> list of choice strings
      nargs  : dict mapping action key -> nargs value (string)
      preambles  : list of preamble functions
    """
    choice_type2fn = {k: v["powershell"] for k, v in CHOICE_FUNCTIONS.items()}
    if choice_functions:
        choice_type2fn.update(choice_functions)
    subparsers = {}
    option_strings = {}
    compgens = {}
    choices = {}
    nargs = {}
    help_text = {}
    preambles = []

    def recurse(parser, prefix):
        get_help = parser._get_formatter()._expand_help
        discovered_subparsers = []
        for i, positional in enumerate(parser._get_positional_actions()):
            action_key = f"{prefix}_pos_{i}"
            if hasattr(positional, 'complete'):
                comp_pattern = complete2pattern(positional.complete, 'powershell', choice_type2fn,
                                                preambles)
                if comp_pattern:
                    compgens[action_key] = comp_pattern
            elif positional.choices:
                log.debug(f"choices:{prefix}:{sorted(positional.choices)}")
                this_positional_choices = []
                for choice in positional.choices:
                    if isinstance(positional.choices, dict):
                        log.debug("subcommand:%s", choice)
                        public_cmds = get_public_subcommands(positional)
                        if choice in public_cmds:
                            discovered_subparsers.append(str(choice))
                            this_positional_choices.append(str(choice))
                            subparser = positional.choices[choice]
                            subcmd_help = next(
                                (sub.help for sub in positional._get_subactions()
                                 if sub.dest == choice and sub.help not in (None, SUPPRESS)), None)
                            desc = (subparser.description or subcmd_help or "").strip()
                            if desc:
                                help_text[f"{prefix}_{wordify(choice)}"] = desc.split("\n")[0]
                            recurse(subparser, f"{prefix}_{wordify(choice)}")
                        else:
                            log.debug("skip:subcommand:%s", choice)
                    else:
                        this_positional_choices.append(str(choice))
                if this_positional_choices:
                    choices[action_key] = this_positional_choices
            if positional.help not in (None, SUPPRESS):
                help_text[action_key] = get_help(positional)
            if positional.nargs not in (None, "1", "?"):
                nargs[action_key] = str(positional.nargs)
        if discovered_subparsers:
            subparsers[prefix] = discovered_subparsers
            log.debug(f"subcommands:{prefix}:{discovered_subparsers}")
        option_strings[prefix] = sum(
            (opt.option_strings for opt in parser._get_optional_actions() if opt.help != SUPPRESS),
            [])
        for optional in parser._get_optional_actions():
            if optional == SUPPRESS:
                continue
            for option_string in optional.option_strings:
                opt_key = f"{prefix}_{wordify(option_string)}"
                if hasattr(optional, 'complete'):
                    comp_pattern = complete2pattern(optional.complete, 'powershell',
                                                    choice_type2fn, preambles)
                    if comp_pattern:
                        compgens[opt_key] = comp_pattern
                if optional.choices:
                    choices[opt_key] = list(map(str, optional.choices))
                if optional.help not in (None, SUPPRESS):
                    help_text[opt_key] = get_help(optional)
                if optional.nargs is not None and optional.nargs != 1:
                    nargs[opt_key] = str(optional.nargs)

    recurse(root_parser, root_prefix)
    return subparsers, option_strings, compgens, choices, nargs, help_text, preambles


@mark_completer("powershell")
def complete_powershell(parser, root_prefix=None, preamble="", choice_functions=None):
    """
    Returns PowerShell syntax autocompletion script.

    See `complete` for arguments.
    """
    root_prefix = wordify(f"_shtab_{root_prefix or parser.prog}")
    (subparsers, option_strings, compgens, choices, nargs, help_text,
     extra_preambles) = get_powershell_commands(parser, root_prefix,
                                                choice_functions=choice_functions)
    # References:
    # - https://learn.microsoft.com/en-us/powershell/module/
    #   microsoft.powershell.core/register-argumentcompleter
    # - https://learn.microsoft.com/en-us/powershell/scripting/
    #   learn/shell/tab-completion
    preamble = "\n".join(list(dict.fromkeys(([preamble] if preamble else []) + extra_preambles)))
    return Template(r"""# AUTOMATICALLY GENERATED by https://github.com/tqdm/shtab
# Usage:
# 1) Copy this to somewhere (e.g. ~\.config\powershell\completions\${prog}.ps1
# 2) Add the following line to your $PROFILE:
#    . ~\.config\powershell\completions\${prog}.ps1
# See also: https://learn.microsoft.com/en-us/powershell/scripting/learn/shell&NoBreak;
/creating-profiles#adding-customizations-to-your-profile

${preamble}
# --- Completion data ---
$$${root_prefix}_subparsers = ${subparsers_ht}
$$${root_prefix}_option_strings = ${option_strings_ht}
$$${root_prefix}_compgens = ${compgens_ht}
$$${root_prefix}_choices = ${choices_ht}
$$${root_prefix}_nargs = ${nargs_ht}
$$${root_prefix}_help = ${help_ht}

# --- Helper functions ---

function _shtab_powershell_compgen_files {
  param([string]$WordToComplete)
  $dir = ''
  if ($WordToComplete -match '^(.*[\\/])') { $dir = $Matches[1] }
  Get-ChildItem -Path "$WordToComplete*" -File -ErrorAction SilentlyContinue |
    ForEach-Object { $dir + $_.Name }
  Get-ChildItem -Path "$WordToComplete*" -Directory -ErrorAction SilentlyContinue |
    ForEach-Object { $dir + $_.Name + [System.IO.Path]::DirectorySeparatorChar }
}

function _shtab_powershell_compgen_dirs {
  param([string]$WordToComplete)
  $dir = ''
  if ($WordToComplete -match '^(.*[\\/])') { $dir = $Matches[1] }
  Get-ChildItem -Path "$WordToComplete*" -Directory -ErrorAction SilentlyContinue |
    ForEach-Object { $dir + $_.Name + [System.IO.Path]::DirectorySeparatorChar }
}

function _shtab_powershell_replace_nonword {
  param([string]$Text)
  $Text -replace '[^\w]', '_'
}

# --- Main completer ---

Register-ArgumentCompleter -Native -CommandName ${prog} -ScriptBlock {
  param($wordToComplete, $commandAst, $cursorPosition)

  # Tokenize the command line (skip program name)
  $allTokens = @()
  if ($commandAst.CommandElements.Count -gt 1) {
    $allTokens = @($commandAst.CommandElements[1..($commandAst.CommandElements.Count - 1)] |
      ForEach-Object { $_.ToString() })
  }

  # Determine which tokens are "completed" (before the word being typed)
  # The last token is the one currently being completed if it matches wordToComplete
  $tokens = @()
  if ($allTokens.Count -gt 0) {
    if ($wordToComplete -and $allTokens[-1] -eq $wordToComplete) {
      if ($allTokens.Count -gt 1) {
        $tokens = $allTokens[0..($allTokens.Count - 2)]
      }
    } else {
      $tokens = $allTokens
    }
  }

  # State tracking
  $prefix = '${root_prefix}'
  $completedPositionals = 0
  $currentActionKey = "${prefix}_pos_0"
  $currentActionNargs = 1
  $currentActionArgsConsumed = 0
  $currentActionIsPositional = $true
  $posOnly = $false

  # Helper: look up nargs for a given action key (default 1)
  function Get-ActionNargs($actionKey) {
    $n = $$${root_prefix}_nargs[$actionKey]
    if ($n) { return $n } else { return '1' }
  }

  # Helper: look up help text for a given action key (empty if none)
  function Get-ActionHelp($actionKey) {
    return $$${root_prefix}_help[$actionKey]
  }

  # Walk completed tokens to determine current parser state
  foreach ($token in $tokens) {
    if ($posOnly -or $token -ne '--') {
      # Check for subparser match
      $currentSubparsers = $$${root_prefix}_subparsers[$prefix]
      if ($currentSubparsers -and $currentSubparsers -contains $token) {
        $prefix = $prefix + '_' + (_shtab_powershell_replace_nonword $token)
        $completedPositionals = 0
        $currentActionKey = "${prefix}_pos_0"
        $currentActionNargs = Get-ActionNargs $currentActionKey
        $currentActionArgsConsumed = 0
        $currentActionIsPositional = $true
        continue
      }
      # Check for option string match
      $currentOptions = $$${root_prefix}_option_strings[$prefix]
      if ($currentOptions -and $currentOptions -contains $token) {
        $currentActionKey = $prefix + '_' + (_shtab_powershell_replace_nonword $token)
        $currentActionNargs = Get-ActionNargs $currentActionKey
        $currentActionArgsConsumed = 0
        $currentActionIsPositional = $false
        continue
      }
      # Consume argument for current action
      $currentActionArgsConsumed++
      if ($currentActionNargs -ne '*' -and
        $currentActionNargs -ne '+' -and
        $currentActionNargs -ne '?' -and
        $currentActionNargs -notlike '*...*') {
        if ($currentActionArgsConsumed -ge [int]$currentActionNargs) {
          if ($currentActionIsPositional) { $completedPositionals++ }
          $currentActionKey = "${prefix}_pos_${completedPositionals}"
          $currentActionNargs = Get-ActionNargs $currentActionKey
          $currentActionArgsConsumed = 0
          $currentActionIsPositional = $true
        }
      }
    } else {
      $posOnly = $true
    }
  }
  # --- Generate completions ---
  if ($env:SHTAB_DEBUG -eq 'true') {
    Write-Host "shtab: wordToComplete='$wordToComplete' prefix='$prefix' `
    actionKey='$currentActionKey' isPositional='$currentActionIsPositional' posOnly='$posOnly'"
  }

  $completions = @()

  if (-not $posOnly -and $wordToComplete -like '-*') {
    # Complete option strings, tooltipped with each option's own help text
    $opts = $$${root_prefix}_option_strings[$prefix]
    if ($opts) {
      foreach ($opt in $opts) {
        if ($opt -like "$wordToComplete*") {
          $optKey = $prefix + '_' + (_shtab_powershell_replace_nonword $opt)
          $completions += , @{Text = $opt; Tooltip = Get-ActionHelp $optKey}
        }
      }
    }
  } else {
    # Complete subparsers (only when current action is positional),
    # tooltipped with each subcommand's own help text
    if ($currentActionIsPositional) {
      $subs = $$${root_prefix}_subparsers[$prefix]
      if ($subs) {
        foreach ($sub in $subs) {
          if ($sub -like "$wordToComplete*") {
            $subKey = $prefix + '_' + (_shtab_powershell_replace_nonword $sub)
            $completions += , @{Text = $sub; Tooltip = Get-ActionHelp $subKey}
          }
        }
      }
    }

    $actionHelp = Get-ActionHelp $currentActionKey

    # Complete choices for current action (positional or option)
    $actionChoices = $$${root_prefix}_choices[$currentActionKey]
    if ($actionChoices) {
      foreach ($choice in $actionChoices) {
        if ($choice -like "$wordToComplete*") {
          $completions += , @{Text = $choice; Tooltip = $actionHelp}
        }
      }
    }
    # Complete using compgen function for current action
    $actionCompgen = $$${root_prefix}_compgens[$currentActionKey]
    if ($actionCompgen) {
      foreach ($item in @(& $actionCompgen $wordToComplete)) {
        $completions += , @{Text = $item; Tooltip = $actionHelp}
      }
    }
  }
  # Deduplicate (by text) and emit CompletionResult objects
  $seen = New-Object System.Collections.Generic.HashSet[string]
  $results = @()
  foreach ($c in $completions) {
    if ($seen.Add($c.Text)) {
      $tooltip = if ($c.Tooltip) { $c.Tooltip } else { $c.Text }
      $results += [System.Management.Automation.CompletionResult]::new(
        $c.Text,          # completionText
        $c.Text,          # listItemText
        'ParameterValue',  # resultType
        $tooltip          # toolTip
      )
    }
  }
  # Prevent fallback file-path completion (PowerShell/PowerShell#19628)
  if ($results.Count -eq 0) { return $null }
  $results
}
""".replace("&NoBreak;\n", "")).safe_substitute(
        subparsers_ht=_powershell_hashtable(subparsers),
        option_strings_ht=_powershell_hashtable(option_strings),
        compgens_ht=_powershell_flat_hashtable(compgens),
        choices_ht=_powershell_hashtable(choices),
        nargs_ht=_powershell_flat_hashtable(nargs),
        help_ht=_powershell_flat_hashtable(help_text),
        preamble=f"\n# Custom Preamble\n{preamble}\n# End Custom Preamble\n" if preamble else "",
        root_prefix=root_prefix,
        prog=parser.prog,
    )


def complete(parser: ArgumentParser, shell: str = "bash", root_prefix: Opt[str] = None,
             preamble: str = "", choice_functions: Opt[Any] = None) -> str:
    """
    shell:
      bash/zsh/tcsh/fish/powershell
    root_prefix:
      prefix for shell functions to avoid clashes (default: "_{parser.prog}")
    preamble:
      text to prepend to generated script
      (e.g. `"_myprog_custom_function(){ echo hello }"`).
      Consider using `parser.add_argument().complete = shtab.cmd("echo hello")` instead.
    choice_functions:
      *deprecated*

    NOTE: `parser.add_argument().complete = ...` can be used to define custom
    completions (e.g. filenames). See <../examples/pathcomplete.py>.
    """
    if isinstance(preamble, dict):
        # warn("replace `complete(preamble={...})` with `.complete = {'preamble': {...}}`",
        #      DeprecationWarning, stacklevel=2)
        preamble = preamble.get(shell, "")
    completer = get_completer(shell)
    return completer(
        parser,
        root_prefix=root_prefix,
        preamble=preamble,
        choice_functions=choice_functions,
    )


def completion_action(parent: Opt[ArgumentParser] = None, preamble: Union[str, dict[str,
                                                                                    str]] = ""):
    class PrintCompletionAction(_ShtabPrintCompletionAction):
        def __call__(self, parser, namespace, values, option_string=None):
            print(complete(parent or parser, values, preamble=preamble))
            parser.exit(0)

    return PrintCompletionAction


def add_argument_to(
    parser: _ActionsContainerT,
    option_string: Union[str, list[str]] = "--print-completion",
    help: str = "print shell completion script",                    # pylint: disable=W0622
    parent: Opt[ArgumentParser] = None,
    preamble: Union[str, dict[str, str]] = "",
) -> _ActionsContainerT:
    """
    option_string:
      iff positional (no `-` prefix) then `parser` is assumed to actually be
      a subparser (subcommand mode)
    parent:
      required in subcommand mode
    preamble:
      see `complete` for details
    """
    if isinstance(option_string, str):
        option_string = [option_string]
    kwargs = {
        "choices": SUPPORTED_SHELLS, "default": None, "help": help,
        "action": completion_action(parent, preamble)}

    if option_string[0][0] != "-": # subparser mode
        kwargs.update(default=SUPPORTED_SHELLS[0], nargs="?")
        if parent is None:
            raise ValueError("subcommand mode: parent required")

    parser.add_argument(*option_string, **kwargs)
    return parser
