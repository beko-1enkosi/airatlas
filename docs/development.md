# Development guide

## Prerequisites

- Git.
- Python 3.12 recommended for local development and used by CI.
- pip, normally included with Python.

The package currently allows Python 3.12 and newer. Future integrations may narrow that range. Check `python --version` before creating the environment.

## Local setup

Clone the repository and create a virtual environment to keep project tools separate from other Python projects:

```bash
git clone https://github.com/beko-1enkosi/airatlas.git
cd airatlas
python -m venv .venv
```

If `python` does not select Python 3.12, use `py -3.12 -m venv .venv` on Windows or `python3.12 -m venv .venv` on Linux/macOS, with Python 3.12 installed.

Activate the environment for your shell.

**Windows PowerShell:**

```powershell
.\.venv\Scripts\Activate.ps1
```

**Linux/macOS (bash or zsh):**

```bash
source .venv/bin/activate
```

If PowerShell blocks activation, use `.\.venv\Scripts\python.exe` instead of `python` in subsequent commands without activating the environment.

From the repository root, install the project and development tools:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Editable installation links the environment to `src/airatlas`, so Python source edits are available without reinstalling. Rerun installation after changing project metadata or dependencies. The `[dev]` extra installs Ruff and pytest; no application dependencies are currently declared. `pyproject.toml` is the configuration source for packaging and these tools.

Run `deactivate` when finished if you activated the environment. Virtual environments, package metadata, and tool caches are ignored by Git. `.env.example` contains only future configuration comments; no credentials or environment configuration are needed for M1 checks.

## Code quality

Run commands from the repository root with the development environment active. Linting finds potential code-quality problems; formatting keeps Python code consistently styled.

```bash
# Check linting
python -m ruff check .

# Apply safe lint fixes; review the resulting changes
python -m ruff check . --fix

# Format Python code
python -m ruff format .

# Check formatting without modifying files
python -m ruff format --check .
```

Ruff targets Python 3.12, uses an 88-character line-length target, and prefers double quotes. Its rules cover core Python style/errors, unused imports and undefined names, import sorting, modern syntax, and common bug patterns.

## Testing

```bash
python -m pytest
```

pytest automatically discovers tests under `tests/` using the configuration in `pyproject.toml`. The current M1 suite contains one foundation smoke test, `tests/test_package.py`, that verifies the installed `airatlas` package imports successfully. Tests will grow alongside future pipeline functionality; the current test does not validate a data pipeline.

## Continuous integration

The workflow in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) automatically runs on repository pushes, including feature branches, and pull requests. It uses an Ubuntu runner with Python 3.12 to:

1. Upgrade pip and install AirAtlas with `.[dev]`.
2. Check Ruff linting.
3. Validate Ruff formatting without changing files.
4. Run pytest using automatic discovery.

A failed installation or check fails the job. CI uses read-only repository permissions, requires no custom secrets, and performs no deployment. Review hosted results in the repository's Actions tab; local checks alone do not confirm a hosted run.

## Git workflow

Use Git incrementally with focused changes and clear Conventional Commit messages, such as `docs: clarify local setup` or `test: add validation cases`. Review `git diff` and run the relevant checks before committing.

Branches may be used for larger features, experiments, risky changes, or work that benefits from isolation. Small, low-risk maintenance or documentation changes may be committed directly to `main` when appropriate for this solo project; a new branch is not required for every small edit.

See the [planned architecture](architecture.md) for future system direction, or return to the [project overview](../README.md).
