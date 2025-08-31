# systems/simula/ci/pipelines.py
from __future__ import annotations

import textwrap


def github_actions_yaml(*, use_xdist: bool = True) -> str:
    return (
        textwrap.dedent(f"""
    name: Simula Hygiene
    on: [pull_request]
    jobs:
      hygiene:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
          - uses: actions/setup-python@v5
            with: {{ python-version: '3.11' }}
          - run: pip install -U pip pytest mypy ruff
          - run: pytest {'-n auto' if use_xdist else ''} -q --maxfail=1 || true
          - run: ruff check . || true
          - run: mypy --hide-error-context --pretty . || true
    """).strip()
        + "\n"
    )


def gitlab_ci_yaml(*, use_xdist: bool = True) -> str:
    return (
        textwrap.dedent(f"""
    stages: [hygiene]
    hygiene:
      stage: hygiene
      image: python:3.11
      script:
        - pip install -U pip pytest mypy ruff
        - pytest {'-n auto' if use_xdist else ''} -q --maxfail=1 || true
        - ruff check . || true
        - mypy --hide-error-context --pretty . || true
    """).strip()
        + "\n"
    )


def render_ci(provider: str = "github", *, use_xdist: bool = True) -> str:
    return (
        github_actions_yaml(use_xdist=use_xdist)
        if provider.lower().startswith("gh")
        else gitlab_ci_yaml(use_xdist=use_xdist)
    )
