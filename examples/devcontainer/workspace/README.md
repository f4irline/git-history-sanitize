# Proto-style workspace

This directory documents the runtime workspace used by the devcontainer
integration. The source project is the parent directory, a self-contained
Node/Express API with a Kubernetes deployment, deliberately shaped like
[`proto/`](../../../proto/).

The container does not execute the prototype's sanitizer. Its trusted build
stage calls the published Git History Sanitize image, and startup installs only
the resulting bare database into the tmpfs-mounted `/workspace/.git`.
