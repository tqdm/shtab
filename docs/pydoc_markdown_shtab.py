import re
from functools import partial

from pydoc_markdown.contrib.processors.pydocmd import PydocmdProcessor

sub = partial(re.sub, flags=re.M)


class ShtabProcessor(PydocmdProcessor):
    def _process(self, node):
        if not getattr(node, "docstring", None):
            return super()._process(node)
        # convert parameter lists to markdown list
        c = sub(r"^([a-z]\w+)(:.*?)$", r"* __\1__\2", node.docstring.content)
        # fix file cross-references
        c = sub(r"<(?:\.\./)+(\S+)>", r"[\1](https://github.com/tqdm/shtab/blob/main/\1)", c)
        # fix code cross-references
        c = sub(r"([sS]ee )`(shtab\.)?(\w+)`", r"\1[`\2\3`](ref.md#\3)", c)
        # convert REPL code blocks to code
        c = sub(r"^(>>>|\.\.\.)(.*?)$", r"```\n\1\2\n```", c)
        c = sub(r"^(>>>|\.\.\.)(.*?)\n```\n```\n(>>>|\.\.\.)", r"\1\2\n\3", c)
        c = sub(r"^(>>>|\.\.\.)(.*?)\n```\n```\n(>>>|\.\.\.)", r"\1\2\n\3", c)
        node.docstring.content = sub(r"^(```)(\n>>>)", r"\1python\2", c)
        return super()._process(node)
