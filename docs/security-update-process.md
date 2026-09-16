# Security Update Process

Dependabot opens weekly review pull requests for the pinned Ubuntu base-image
digest and GitHub Actions revisions. The `security-refresh` workflow rebuilds
and scans the pinned OCI image each Monday, and also runs for a pull request
that changes a reviewed toolchain input. It can be run manually after a
dependency or base-image update.

## Refreshing The Toolchain Lock

Treat a Dependabot base-image pull request as an update proposal, not as a
release-ready change. Before it can merge, regenerate and review the matching
`container/toolchain.lock.json` records for the selected immutable Ubuntu
snapshot on both amd64 and arm64. Update only the base digest, snapshot,
package locks, and affected toolchain records; do not build from a mutable tag
or package index. The regular CI platform contracts and this workflow must pass
before normal review and merge. The workflow has read-only permissions and
never pushes images or creates pull requests.

## Responding To Findings

1. Review the Dependabot pull request or scheduled security-refresh workflow
   and reproduce a finding with the same image reference.
2. Update the affected dependency or base-image pin, then rerun the scan.
3. Do not publish a release image until its digest scan passes. The release
   workflow scans and attests the pushed digest before applying release tags.

## Temporary Exceptions

`security/trivyignore.yaml` starts empty and uses JSON, which is valid YAML for
Trivy. An exception requires `id`, `statement`, `owner`, `issue`, and
`expired_at`; `paths` may scope a path-specific exception. The validator rejects
malformed records, missing ownership, expired records, and expiries over 30 days.
Remove the exception once remediation is available.

Review every exception before its `expired_at` date. Expired exceptions must
not be renewed without confirming that remediation is still unavailable.
