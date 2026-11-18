# Agent instructions

This repository is public. Do not write anything from private repositories or internal systems into code, docs,
commit messages or PR bodies.

## Releasing a new version

The module deploys a pre-built Lambda image whose tag defaults to the module version, so each release needs a
matching image.

1. **Before the release**, in a PR: set the `ecr_repo_tag` default in `vars.tf` to the version being released
   (`X.Y.Z`, no `v` prefix). The `Build and Push Docker Image` workflow fails a release whose tag does not match
   this default, and until the release image exists, the module's default image tag is missing from ECR.
2. A **major** version needs an entry in the README's upgrade section: what Terraform replaces or recreates, and
   a table of renamed or removed inputs.
3. **After the release** is published: bump the registry `version` in `examples/slack_*_configuration/main.tf` to
   the new version. CI validates the examples against the registry, so this cannot happen earlier.

The full maintainer steps are in the README, under "Build process (maintainers)".

## Dependency updates

New upstream versions soak for 14 days after they are published before they ship, as a defence against hijacked
releases. Pick the newest version at least 14 days old.

- Python: `[tool.uv] exclude-newer = "14 days"` in `src/pyproject.toml` makes `uv lock` apply the soak. To take a
  younger fix for a critical/high advisory, add an `exclude-newer-package` entry set to that version's upload time,
  and only after you check its PyPI provenance from the project's own publishing workflow. Remove the entry once
  the version is 14 days old.
- Dependabot opens security PRs only for `uv`. They skip the cooldown, so treat them as signals: apply the fix by
  hand once it has soaked. Actions, Terraform modules, Docker images and pre-commit hooks get one grouped monthly PR
  with a 14-day cooldown; majors open individually.
- Close Dependabot PRs by hand, naming the version you took and where.
- Pin actions by commit SHA with a `# vX.Y.Z` comment, and Docker images by digest.
- Keep the black hook's `additional_dependencies` and the ruff hook `rev` equal to the versions in `src/uv.lock`.

## Checks

Run `bash test.sh` before pushing. It runs the unit tests and pre-commit, which also regenerates
`src/requirements.txt` from `src/uv.lock` and the inputs table in `README.md`. Commit what they change.
