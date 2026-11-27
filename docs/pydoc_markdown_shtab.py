import re
from functools import partial

from docspec import Docstring
from pydoc_markdown.contrib.processors.pydocmd import PydocmdProcessor

sub = partial(re.sub, flags=re.M)

# docstrings for module-level constants
_CONSTANT_DOCS = {'FILE': 'Existing filenames.', 'DIRECTORY': 'Existing directories.'}


class ShtabProcessor(PydocmdProcessor):
    def _process(self, node):
        if not getattr(node, "docstring", None):
            if node.name in _CONSTANT_DOCS:
                node.docstring = Docstring(location=node.location,
                                           content=_CONSTANT_DOCS[node.name])
            else:
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
