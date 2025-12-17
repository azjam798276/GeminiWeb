# Packaging & Release

## Versioning

This project uses SemVer-style versioning while `<1.0`:

- Patch (`0.y.Z`): bugfixes, docs, internal refactors
- Minor (`0.Y.0`): new backward-compatible features/fields/endpoints
- Major (`1.0.0+`): breaking API/behavior changes (avoid until stable)

Single source of truth: `pyproject.toml` (`[project].version`).

## Supported Python versions

- Runtime: Python `>=3.10` (see `pyproject.toml`)
- CI: `3.10`, `3.11`, `3.12`

## CI automation

- PR/push CI: `.github/workflows/ci.yml` runs:
  - `pytest -q` (matrix)
  - `ruff check .` and `mypy src`
  - `python -m build` and `twine check dist/*`
- Tag release: `.github/workflows/release.yml` builds artifacts and creates a GitHub Release.

## Release checklist

1. Ensure clean working tree and up-to-date main branch.
2. Bump version in `pyproject.toml`.
3. Update `CHANGELOG.md` (add a section for the new version).
4. Run checks locally:
   - `make test`
   - `make lint`
5. Build artifacts:
   - `python3 -m pip install -e ".[release]"` (or install `build` + `twine`)
   - `make build`
   - `make distcheck`
6. Smoke-test the built wheel in a fresh venv (recommended):
   - `python3 -m venv /tmp/gwsp-release && . /tmp/gwsp-release/bin/activate`
   - `python3 -m pip install dist/*.whl`
   - `geminiweb-safe-provider --help` (or start the server and hit `/healthz`)
7. Tag the release and push tags:
   - `git tag -a vX.Y.Z -m "vX.Y.Z"`
   - `git push --tags`
8. Publish (choose one):
   - Manual: `python3 -m twine upload dist/*` (using an API token)
   - CI: trusted publishing (recommended):
     - Configure the PyPI project for OIDC trusted publishing.
     - Set the repo variable `PUBLISH_TO_PYPI=true` (publish on tags), or run the workflow manually with `publish_to_pypi=true`.

## Distribution approach

- Artifacts: `sdist` + `wheel`
- Entry point: `geminiweb-safe-provider` (console script)
