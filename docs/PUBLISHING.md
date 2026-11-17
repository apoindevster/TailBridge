# Publishing TailBridge

## What belongs in Git

Source, tests, packaging templates, synthetic screenshots, design documentation,
licenses and `.github` workflows are public project files. Build output, virtual
environments, caches, local notes, logs, packet captures, keys, network profiles,
Tailscale state and device recovery backups are ignored and must stay private.
The vendor display overlay is also excluded because its redistribution license
has not been established. The installer fetches and verifies it locally.

`scripts/check_publication.py` checks both tracked and non-ignored untracked files.
It rejects sensitive/generated file types, symlinks, unexpected binaries, image
metadata and missing release files. `--stage-source` creates an exact source
snapshot for Gitleaks; use a new empty directory on each run. This boundary check
does not detect every possible secret or identify sensitive pixels in an image.

## Before the first push

1. Review `git status --short` and `git status --short --ignored`. Confirm that
   private working files are ignored and no ignored files are already tracked.
2. Run the commands in [CONTRIBUTING.md](../CONTRIBUTING.md), including source and
   release scans. Review staged content with `git diff --cached` before committing.
   Screenshots must come from the synthetic test, with no real enrollment QR.
3. Create an empty GitHub repository, then add its URL as `origin`, commit the
   reviewed source and push `main`. Configure your preferred Git author identity
   or GitHub no-reply address locally before committing. No repository URL or
   maintainer email is hardcoded in this project.
4. In repository settings, enable private vulnerability reporting and available
   secret scanning/push protection. Require the two CI jobs before merges and
   review Dependabot updates. A first GitHub-hosted run is still required to
   establish that repository's permissions and artifact upload behavior.
5. For a release, download the successful run's artifact, verify the `.sha256`,
   review the accompanying results and test on a Pi. Attach only the reviewed
   archive, checksum and optional integration patch. Do not rearchive an installed
   Pi or include a locally downloaded vendor overlay, credentials or backups.

The workflow uses read-only repository permissions, full-SHA action pins and
nonpersistent checkout credentials. It runs on `push`, `pull_request` and manual
dispatch, with no deployment credentials or `pull_request_target`. Gitleaks scans
the source snapshot, available full Git history and release contents with redacted
output; no credential-bearing diagnostic artifacts are uploaded. CI runs on
GitHub-hosted runners, never a runner on the appliance or LAN.
As with any PR workflow, fork code is untrusted; do not add secrets or a private
network runner to these jobs.

Go uses the current stable toolchain in CI; ts-redir's source revision and embedded
CSS are fixed. Builds record no local paths in the Go binary (`-trimpath`), and tar
owners/timestamps and gzip headers are normalized. This removes incidental builder
metadata; byte-for-byte reproducibility across changing toolchains is not claimed.
The tool downloads have fixed versions and SHA-256 checksums. Dependabot covers
GitHub Actions and Python development requirements; reviewed upstream source/tool
pin changes remain a maintainer responsibility.

## Publication review — 2026-11-17

The review covers Git-visible source, native synthetic captures and the rebuilt
Linux arm64 package. It excludes local caches, virtual environments, old build
directories and private device state; these are not publication inputs. There
were no existing Git commits/history at the time of the review.

- Removed two private account/staging paths from RESULTS.md. Examples use
  synthetic network names, addresses and enrollment URLs. No credentials or real
  device identifiers were found in the reviewed publishable files.
- Preserved intentional public upstream repository names, copyright holders and
  license attribution; those are provenance, not deployment secrets.
- Added MIT licensing, reporting/contribution guidance, ignore rules and CI.
  PNGs are stripped of metadata; tar entries have numeric zero ownership.
- Kept private device state and the unlicensed-for-redistribution vendor overlay
  out of the source and release artifact. Installer tests use synthetic overlay
  bytes for their temporary filesystem checks.

See [RESULTS.md](../RESULTS.md) for commands actually executed and their outcomes.
Automated scans and this review are not a guarantee that future edits are safe to
publish. No new physical test or GitHub-hosted run is implied by this preparation.
