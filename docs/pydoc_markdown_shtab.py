import re

from pydoc_markdown.contrib.processors.pydocmd import PydocmdProcessor


class ShtabProcessor(PydocmdProcessor):
    def _process(self, node):
        if not getattr(node, "docstring", None):
            return super()._process(node)
        # convert parameter lists to markdown list
        node.docstring.content = re.sub(r"^(\w+)(:.*?)$", r"* __\1__\2", node.docstring.content,
                                        flags=re.M)
        # fix code cross-references
        node.docstring.content = re.sub(r"<../(\S+)>",
                                        r"[\1](https://github.com/iterative/shtab/tree/main/\1)",
                                        node.docstring.content, flags=re.M)
        return super()._process(node)
