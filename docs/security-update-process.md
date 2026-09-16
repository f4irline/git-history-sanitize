# Security Update Process

The scheduled `security-refresh` workflow rebuilds the current pinned OCI image
each Monday and scans it with the current Trivy database.
It can also be run manually after a dependency or base-image update.

## Responding To Findings

1. Review the scheduled security-refresh workflow and reproduce a finding with
   the same image reference.
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
