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

## Checks

Run `bash test.sh` before pushing. It runs the unit tests and pre-commit, which also regenerates
`src/requirements.txt` from `src/uv.lock` and the inputs table in `README.md`. Commit what they change.
