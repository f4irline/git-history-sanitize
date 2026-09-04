# Git History Sanitize examples

Each directory is laid out like a small project repository: source folders,
configuration, package metadata where relevant, a policy, and the integration
that project would use. The sources are illustrative—not applications intended
to be built or tested here. Copy one into its own repository, set a policy
cutoff appropriate for that repository's history, and use the accompanying
integration with a published Git History Sanitize artifact.

| Example | Illustrative project | Integration |
| --- | --- | --- |
| [`basic-cli/`](basic-cli/) | Invoice reminder service | Developer runs the released CLI against a local `.git`. |
| [`docker-buildkit/`](docker-buildkit/) | Order webhook API | Trusted BuildKit build exports a sanitized bare repository. |
| [`github-actions/`](github-actions/) | Settlement reconciliation worker | Trusted CI producer publishes an artifact for a checkout-free consumer. |
| [`devcontainer/`](devcontainer/) | Proto-shaped support case API | Devcontainer installs sanitized history while masking the host `.git`. |

None of these examples fabricates Git history or acts as a sanitizer test
suite. The package test suite remains the place for behavioral verification.
