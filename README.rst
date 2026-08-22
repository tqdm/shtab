|Logo|

shtab
=====

|Tests| |Coverage| |Quality|
|PyPI| |Conda|
|PyPI-Downloads| |Licence|

- What: Automatically generate shell tab completion scripts for Python CLI apps
- Why: Speed & correctness. Alternatives like
  `argcomplete <https://pypi.org/project/argcomplete>`_ and
  `pyzshcomplete <https://pypi.org/project/pyzshcomplete>`_ are slow and have
  side-effects
- How: ``shtab`` processes an ``argparse.ArgumentParser`` object to generate a
  tab completion script for your shell

Features
--------

- Outputs tab completion scripts for multiple shells

  - ``bash``, ``zsh``, ``fish``, ``tcsh``

- Supports

  - `argparse <https://docs.python.org/library/argparse>`_
  - `docopt <https://pypi.org/project/docopt>`_ (via `argopt <https://pypi.org/project/argopt>`_)
  - `click <https://pypi.org/project/click>`_

- ``<arguments>``, ``--options`` and ``sub commands``
- Choices (``--say={hello,goodbye}```)
- Paths (``--file={*.y*ml,*.toml}``, ``--dir=*/``)
- Dynamic shell commands (``--branch=$(git branch)``)

------------------------------------------

.. contents:: Table of Contents
   :backlinks: top

Installation
------------

Choose one of:

- ``pip install shtab``, or
- ``conda install -c conda-forge shtab``

See `operating system-specific instructions in the docs <https://tqdm.github.io/shtab/#installation>`_.

Usage
-----

There are two ways of using ``shtab``:

- `CLI Usage <https://tqdm.github.io/shtab/use/#cli-usage>`_: ``shtab``'s own CLI interface for external applications

  - may not require any code modifications whatsoever
  - end-users execute ``shtab your_cli_app.your_parser_object``

- `Library Usage <https://tqdm.github.io/shtab/use/#library-usage>`_: as a library integrated into your CLI application

  - adds a couple of lines to your application
  - argument mode: end-users execute ``your_cli_app --print-completion {bash,zsh,tcsh,fish}``
  - subparser mode: end-users execute ``your_cli_app completion {bash,zsh,tcsh,fish}``

Examples
--------

See `the docs for usage examples <https://tqdm.github.io/shtab/use/>`_.

FAQs
----

Not working? Check out `frequently asked questions <https://tqdm.github.io/shtab/#faqs>`_.

Alternatives
------------

- `argcomplete <https://pypi.org/project/argcomplete>`_

  - executes the underlying script *every* time ``<TAB>`` is pressed (slow and has side-effects)

- `pyzshcomplete <https://pypi.org/project/pyzshcomplete>`_

  - executes the underlying script *every* time ``<TAB>`` is pressed (slow and has side-effects)
  - only provides ``zsh`` completion

- `click <https://pypi.org/project/click>`_

  - executes the underlying script *every* time ``<TAB>`` is pressed (slow and has side-effects)
  - solves multiple problems (rather than POSIX-style "do one thing well")
  - don't want to migrate away from ``click``? Use `shtab's click integration <https://tqdm.github.io/shtab/use/#library-usage>`_ instead

Contributions
-------------

Please do open `issues <https://github.com/tqdm/shtab/issues>`_ & `pull requests <https://github.com/tqdm/shtab/pulls>`_! Some ideas:

- support ``powershell`` (#212)
- support ``python -m`` prefix (#55)

See
`CONTRIBUTING.md <https://github.com/tqdm/shtab/blob/main/CONTRIBUTING.md>`_
for more guidance.

|git-fame|

|Hits|

.. |Logo| image:: https://github.com/tqdm/shtab/raw/main/meta/logo.png
.. |Tests| image:: https://img.shields.io/github/actions/workflow/status/tqdm/shtab/test.yml?logo=github&label=tests
   :target: https://github.com/tqdm/shtab/actions
   :alt: Tests
.. |Coverage| image:: https://codecov.io/gh/tqdm/shtab/branch/main/graph/badge.svg
   :target: https://codecov.io/gh/tqdm/shtab
   :alt: Coverage
.. |Quality| image:: https://app.codacy.com/project/badge/Grade/0ce50da5c6e04236a891b092c7012753
   :target: https://app.codacy.com/gh/tqdm/shtab/dashboard
   :alt: Quality
.. |Conda| image:: https://img.shields.io/conda/v/conda-forge/shtab.svg?label=conda&logo=conda-forge
   :target: https://anaconda.org/conda-forge/shtab
   :alt: conda-forge
.. |PyPI| image:: https://img.shields.io/pypi/v/shtab.svg?label=pip&logo=PyPI&logoColor=white
   :target: https://pypi.org/project/shtab
   :alt: PyPI
.. |PyPI-Downloads| image:: https://static.pepy.tech/personalized-badge/shtab?left_text=downloads%2Fmonth
   :target: https://pepy.tech/project/shtab
   :alt: Downloads
.. |git-fame| image:: https://git-fame.cdcl.ml/gh/tqdm/shtab?min=1&w=1&M=1&C=1&enum=1
   :alt: git-fame
   :target: https://git-fame.cdcl.ml/gh/tqdm/shtab?w=1&M=1&C=1&enum=1
.. |Hits| image:: https://cgi.cdcl.ml/hits?q=shtab&style=social&r=https://github.com/tqdm/shtab&a=hidden
   :target: https://cgi.cdcl.ml/hits?q=shtab&a=plot&r=https://github.com/tqdm/shtab&style=social
   :alt: Hits
.. |LICENCE| image:: https://img.shields.io/pypi/l/shtab.svg
   :target: https://raw.githubusercontent.com/tqdm/shtab/main/LICENCE
