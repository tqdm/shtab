import logging
import re
from argparse import (ONE_OR_MORE, REMAINDER, SUPPRESS, ZERO_OR_MORE, Action, ArgumentParser,
                      _AppendAction, _AppendConstAction, _CountAction, _HelpAction,
                      _StoreConstAction, _VersionAction)
from collections import defaultdict
from functools import total_ordering
from importlib.metadata import PackageNotFoundError, version
from itertools import starmap
from shlex import join, quote
from string import Template
from typing import Any, Callable
from typing import Optional as Opt
from typing import Union

try:
    __version__ = version('shtab')
except PackageNotFoundError:
    __version__ = "UNKNOWN"
__all__ = [
    "complete", "add_argument_to", "glob", "cmd", "SUPPORTED_SHELLS", "FILE", "DIRECTORY", "DIR"]
log = logging.getLogger(__name__)

ShellType = str
CompleteType = dict[ShellType, Union[str, dict[ShellType, str]]]
SUPPORTED_SHELLS: list[ShellType] = []
_SUPPORTED_COMPLETERS: dict[ShellType, Callable] = {}
CHOICE_FUNCTIONS: dict[str, CompleteType] = {
    "file": {
        "bash": "_shtab_compgen_files", "zsh": "_files", "tcsh": "f",
        "fish": "(__fish_complete_path)"}, "directory": {
            "bash": "_shtab_compgen_dirs", "zsh": "_files -/", "tcsh": "d",
            "fish": "(__fish_complete_directories)"}}
FILE = CHOICE_FUNCTIONS["file"]
DIRECTORY = DIR = CHOICE_FUNCTIONS["directory"]
FLAG_OPTION = (
    _StoreConstAction,
    _HelpAction,
    _VersionAction,
    _AppendConstAction,
    _CountAction,
)


def glob(*patterns: str) -> CompleteType:
    """
    Example: `glob("*.yml", "*.yaml")`

    Consider native shell alternatives in special cases:

    - any file: `shtab.FILE` (instead of `glob("*")`)
    - any directory: `shtab.DIRECTORY` (instead of `glob("*/")`)
    """
    return {
        "bash": f"_shtab_pattern_compgen_{abs(hash(patterns))}",
        "zsh": f"_files -g '({'|'.join(patterns)})'", "tcsh": f"f:{{{','.join(patterns)}}}",
        "fish": f"(_shtab_pattern_compgen_{abs(hash(patterns))})", "preamble": {
            "bash": f"""
# $1=COMP_WORDS[1]
_shtab_pattern_compgen_{abs(hash(patterns))}() {{
  for ext in {join(patterns)}; do
    compgen -f -X "!$ext" -- $1
  done
  compgen -d -- $1  # recurse into subdirs
}}
""", "fish": f"""
function _shtab_pattern_compgen_{abs(hash(patterns))}
  set comp (commandline -ct)
  for pattern in {join(patterns)}
    __fish_complete_path "$comp" | string match -e -- "$pattern"
  end
  __fish_complete_path "$comp" | string match -e "*/"  # recurse into subdirs
end
"""}}


def cmd(command: str) -> CompleteType:
    """
    command:
      shell command to run to generate completions

    Example: `cmd("git branch")`
    """
    return {
        "bash": f"_shtab_pattern_compgen_{abs(hash(command))}", "zsh": f"($({command}))",
        "tcsh": f"`{command}`", "fish": f"({command})", "preamble": {
            "bash": f"""
# $1=COMP_WORDS[1]
_shtab_pattern_compgen_{abs(hash(command))}() {{
  compgen -W "$({command})" -- $1
}}
"""}}


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


def get_completer(shell: str):
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


def wordify(string: str) -> str:
    """Replace non-word chars [\\W] with underscores [_]"""
    return re.sub("\\W", "_", string)


def get_public_subcommands(sub):
    """Get all the publicly-visible subcommands for a given subparser."""
    public_parsers = {id(sub.choices[i.dest]) for i in sub._get_subactions()}
    return {k for k, v in sub.choices.items() if id(v) in public_parsers}


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

                this_positional_choices = []
                for choice in positional.choices:
                    if isinstance(choice, Choice):
                        # append special completion type to `compgens`
                        # NOTE: overrides `.complete` attribute
                        log.debug(f"Choice.{choice.type}:{prefix}:{positional.dest}")
                        compgens.append(f"{prefix}_pos_{i}_COMPGEN="
                                        f"{quote(choice_type2fn[choice.type])}")
                    elif isinstance(positional.choices, dict):
                        # subparser, so append to list of subparsers & recurse
                        log.debug("subcommand:%s", choice)
                        public_cmds = get_public_subcommands(positional)
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
            if optional == SUPPRESS:
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
    # - https://www.gnu.org/software/bash/manual/html_node/
    #   Programmable-Completion.html
    # - https://opensource.com/article/18/3/creating-bash-completion-script
    # - https://stackoverflow.com/questions/12933362
    return Template("""\
# AUTOMATICALLY GENERATED by https://github.com/tqdm/shtab

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

  _set_new_action "pos_${completed_positional_actions}" true
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
      if [[ -n $sub_parsers && " ${sub_parsers[@]} " == *" ${this_word} "* ]]; then
        # valid subcommand: add it to the prefix & reset the current action
        prefix="${prefix}_$(_shtab_replace_nonword $this_word)"
        _set_parser_defaults
      fi

      if [[ " ${current_option_strings[@]} " == *" ${this_word} "* ]]; then
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
        _set_new_action "pos_${completed_positional_actions}" true
      fi
    else
      pos_only=1 # "--" delimiter encountered
    fi

    let "word_index+=1"
  done

  # Generate the completions

  if [[ $pos_only = 0 && "${completing_word}" == -* ]]; then
    # optional argument started: use option strings
    mapfile -t COMPREPLY < <(compgen -W "${current_option_strings[*]}" -- "${completing_word}")
  elif [[ "${previous_word}" == ">" || "${previous_word}" == ">>" ||
          "${previous_word}" =~ ^[12]">" || "${previous_word}" =~ ^[12]">>" ]]; then
    # handle redirection operators
    mapfile -t COMPREPLY < <(compgen -f -- "${completing_word}")
  else
    # use choices & compgen
    [ -n "${current_action_compgen}" ] &&
      mapfile -t COMPREPLY < <("${current_action_compgen}" "${completing_word}")
    mapfile -t -O "${#COMPREPLY[@]}" COMPREPLY < <(
      compgen -W "${current_action_choices[*]}" -- "${completing_word}")
  fi

  return 0
}

complete -o filenames -F ${root_prefix} ${prog}""").safe_substitute(
        subparsers="\n".join(subparsers),
        option_strings="\n".join(option_strings),
        compgens="\n".join(compgens),
        choices="\n".join(choices),
        nargs="\n".join(nargs),
        preamble=f"\n# Custom Preamble\n{preamble}\n# End Custom Preamble\n" if preamble else "",
        root_prefix=root_prefix,
        prog=parser.prog,
    )


def escape_zsh(string):
    """
    Backslash-escape for interpolation into a double-quoted `_arguments` spec.

    NOTE: cannot use `shlex.quote` (a single-quoted word only valid at top level).
    """
    # excessive but safe
    return re.sub(r"([^\w\s.,()-])", r"\\\1", str(string))


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

    def format_optional(opt, parser):
        get_help = parser._get_formatter()._expand_help
        return (('{nargs}{options}"[{help}]"' if (isinstance(opt, FLAG_OPTION) or opt.nargs == 0)
                 else '{nargs}{options}"[{help}]:{dest}:{pattern}"').format(
                     nargs=('"(- : *)"' if (isinstance(opt, OPTION_END) or opt.nargs == REMAINDER)
                            else '"*"' if isinstance(opt, OPTION_MULTI) else ""),
                     options=("{{{}}}".format(",".join(opt.option_strings)) if len(
                         opt.option_strings) > 1 else '"{}"'.format("".join(opt.option_strings))),
                     help=escape_zsh(get_help(opt)) if opt.help else "", dest=opt.dest,
                     pattern=get_candidates(opt) or "").replace('""', ''))

    def format_positional(opt, parser):
        get_help = parser._get_formatter()._expand_help
        return '"{nargs}:{help}:{pattern}"'.format(
            nargs={ONE_OR_MORE: "(*)", ZERO_OR_MORE: "(*):",
                   REMAINDER: "(-)*:"}.get(opt.nargs, ""), help=escape_zsh(
                       (get_help(opt) if opt.help else opt.dest).strip().split("\n")[0]),
            pattern=get_candidates(opt) or "")

    # {cmd: {"help": help, "arguments": [arguments]}}
    all_commands = {
        root_prefix: {
            "cmd": prog, "arguments": [
                format_optional(opt, parser)
                for opt in parser._get_optional_actions() if opt.help != SUPPRESS] + [
                    format_positional(opt, parser) for opt in parser._get_positional_actions()
                    if opt.help != SUPPRESS and opt.choices is None],
            "help": (parser.description
                     or "").strip().split("\n")[0], "commands": [], "paths": []}}

    def recurse(parser, prefix, paths=None):
        paths = paths or []
        subcmds = []
        for sub in parser._get_positional_actions():
            if sub.help == SUPPRESS or not sub.choices:
                continue
            if not sub.choices or not isinstance(sub.choices, dict):
                # positional argument
                all_commands[prefix]["arguments"].append(format_positional(sub, parser))
            else:  # subparser
                log.debug(f"choices:{prefix}:{sorted(sub.choices)}")
                public_cmds = get_public_subcommands(sub)
                for cmd, subparser in sub.choices.items():
                    if cmd not in public_cmds:
                        log.debug("skip:subcommand:%s", cmd)
                        continue
                    log.debug("subcommand:%s", cmd)

                    # optionals
                    arguments = [
                        format_optional(opt, parser) for opt in subparser._get_optional_actions()
                        if opt.help != SUPPRESS]

                    # positionals
                    arguments.extend(
                        format_positional(opt, parser)
                        for opt in subparser._get_positional_actions()
                        if not isinstance(opt.choices, dict) if opt.help != SUPPRESS)

                    # help text
                    formatter = subparser._get_formatter()
                    backup_width = formatter._width
                    formatter._width = 1234567 # large number to effectively disable wrapping
                    desc = formatter._format_text(subparser.description or "").strip()
                    formatter._width = backup_width

                    new_pref = f"{prefix}_{wordify(cmd)}"
                    options = all_commands[new_pref] = {
                        "cmd": cmd, "help": desc.split("\n")[0], "arguments": arguments,
                        "paths": [*paths, cmd]}
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

        return f"""\
{prefix}() {{
  local context state line \
curcontext="$curcontext" one_or_more='(*)' remainder='(-)*:' default='*::: :->{name}'

  # Add default positional/remainder specs only if none exist, and only once per session
  if (( ! {prefix}_defaults_added )); then
    if (( ${{{prefix}_options[(I)${{(q)one_or_more}}*]}} +\
          ${{{prefix}_options[(I)${{(q)remainder}}*]}} +\
          ${{{prefix}_options[(I)${{(q)default}}]}} == 0 )); then
      {prefix}_options+=(': :{prefix}_commands' '*::: :->{name}')
    fi
    {prefix}_defaults_added=1
  fi
  _arguments -C -s ${prefix}_options

  case $state in
    {name})
      words=($line[1] "${{words[@]}}")
      (( CURRENT += 1 ))
      curcontext="${{curcontext%:*:*}}:{prefix}-$line[1]:"
      case $line[1] in
        {cases}
      esac
  esac
}}
"""

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
    #   - https://github.com/zsh-users/zsh-completions
    #   - http://zsh.sourceforge.net/Doc/Release/Completion-System.html
    #   - https://mads-hartmann.com/2017/08/06/
    #     writing-zsh-completion-scripts.html
    #   - http://www.linux-mag.com/id/1106/
    return Template("""\
#compdef ${prog}

# AUTOMATICALLY GENERATED by https://github.com/tqdm/shtab

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

    def get_specials(arg, arg_type, arg_sel):
        if hasattr(arg, 'complete'):
            complete_fn = complete2pattern(arg.complete, 'tcsh', choice_type2fn, preambles)
            if complete_fn:
                yield f"'{arg_type}/{arg_sel}/{complete_fn}/'"
        elif arg.choices:
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
            log.debug("%s| Optional: %s", log_prefix, optional.dest)
            if optional.help != SUPPRESS:
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
            if positional.help != SUPPRESS:
                positional_idx += 1
                log.debug("%s| Positional #%d: %s", log_prefix, positional_idx, positional.dest)
                index_choices[positional_idx][tuple(requirements)] = positional
                if isinstance(positional.choices, dict):
                    for subcmd, subparser in positional.choices.items():
                        log.debug("%s| | SubParser: %s", log_prefix, subcmd)
                        recurse_parser(subparser, positional_idx, requirements + [subcmd])

    recurse_parser(parser, 0)

    for idx, ndict in index_choices.items():
        if len(ndict) == 1:
            # Single choice, no requirements
            arg = next(iter(ndict.values()))
            specials.extend(get_specials(arg, 'p', str(idx)))
        else:
            # Multiple requirements
            nlist = []
            for nn, arg in ndict.items():
                max_idx = len(nn) + 1
                checks = [f'("$cmd[{iidx}]" == "{n}")' for iidx, n in enumerate(nn, start=2)]
                condition = f"$#cmd >= {max_idx} && " + " && ".join(checks)
                if hasattr(arg, 'complete'):
                    complete_fn = complete2pattern(arg.complete, 'tcsh', choice_type2fn, preambles)
                    if complete_fn:
                        if complete_fn.startswith('`') and complete_fn.endswith('`'):
                            # nested backticks crash tcsh's parser, use `eval` instead
                            nlist.append(f"if ( {condition} ) eval {complete_fn.strip('`')}")
                        elif nn and idx == len(nn) + 1:
                            # completion patterns (`f:*.txt`, `d`, ...) are not commands, so
                            # they can't go in the list below; this slot directly follows a
                            # (sub)command, so key off that word instead
                            specials.append(f"'n/{nn[-1]}/{complete_fn}/'")
                        # else: no way to express a pattern for this slot in tcsh
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

${preamble}

complete ${prog} \\
        ${optionals_eq_str}'c/--/(${optionals_double_str})/' \\
        'c/-/(${optionals_single_str})/' \\
        ${optionals_special_str} \\
        'p/*/()/'""").safe_substitute(
        preamble=f"\n# Custom Preamble\n{preamble}\n# End Custom Preamble\n" if preamble else "",
        root_prefix=root_prefix, prog=parser.prog,
        optionals_double_str=' '.join(sorted(optionals_double)),
        optionals_single_str=' '.join(sorted(optionals_single)),
        optionals_eq_str=''.join(f'{eq} \\\n        ' for eq in eq_specials),
        optionals_special_str=' \\\n        '.join(specials))


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
        get_help = cparser._get_formatter()._expand_help
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
            if optional.help:
                output.append(f'-d {quote(get_help(optional))}')
            completions.append(' '.join(output))

        index = 0          # the next positional slot (number of preceding positional arguments)
        open_ended = False # an earlier positional consumes any number of tokens

        for positional in cparser._get_positional_actions():
            if positional.help == SUPPRESS:
                continue
            log.debug("%s| Positional #%d: %s", log_prefix, index, positional.dest)
            if isinstance(positional.choices, dict):
                # positional subcommand
                public = get_public_subcommands(positional)
                pos_test = pos_condition(index, 1, open_ended)
                # fallback to `add_parser(help)` when missing subparser(description);
                # keyed by id() to cover aliases
                subcmd_help = {
                    id(positional.choices[i.dest]): i.help
                    for i in positional._get_subactions()  # type: ignore[attr-defined]
                    if i.dest in positional.choices}

                for subcmd, subparser in positional.choices.items():
                    if subcmd not in public:
                        continue
                    log.debug("%s| | SubParser: %s", log_prefix, subcmd)
                    commands.append(" ".join(path + [subcmd]))
                    output = start_output(path, pos_test)
                    output.append(f"-a {quote(subcmd)}")
                    desc = subparser.description or subcmd_help.get(id(subparser)) or ""
                    desc = desc.strip().split("\n")[0]
                    if desc:
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
                    if positional.help:
                        desc = get_help(positional).strip().split("\n")[0]
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
  for t in $$tokens
    if test $$expect_value -eq 1
      set expect_value 0
      continue
    end
    switch "$$t"
      case '--*=*'
        continue
      case '-*'
        if contains -- $$t $$${prefix}_opts_with_value
          set expect_value 1
        end
        continue
      case '*'
        if test $$${prefix}_npos -eq 0
          set -l candidate $$t
          if test -n "$$${prefix}_cmdpath"
            set candidate "$$${prefix}_cmdpath $$t"
          end
          if contains -- $$candidate $$${prefix}_commands
            set -g ${prefix}_cmdpath $$candidate
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
  test "$$${prefix}_cmdpath" = "$$argv"
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


def complete(parser: ArgumentParser, shell: str = "bash", root_prefix: Opt[str] = None,
             preamble: str = "", choice_functions: Opt[Any] = None) -> str:
    """
    shell:
      bash/zsh/tcsh/fish
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
    parser: ArgumentParser,
    option_string: Union[str, list[str]] = "--print-completion",
    help: str = "print shell completion script",                    # pylint: disable=W0622
    parent: Opt[ArgumentParser] = None,
    preamble: Union[str, dict[str, str]] = "",
):
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
