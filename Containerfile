# syntax=docker/dockerfile:1.7
ARG BASE_IMAGE=ubuntu@sha256:2260313b31c8c011cd2eebe728008efac1b3982be73eb71348ea2648d2c0e09b
ARG SOURCE_DATE_EPOCH=0
ARG SOURCE_REVISION=unknown
ARG PACKAGE_VERSION=0.1.2

FROM ${BASE_IMAGE} AS builder
ARG SOURCE_DATE_EPOCH
ARG SOURCE_REVISION
ARG PACKAGE_VERSION
ARG TARGETARCH
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
WORKDIR /build

COPY container/toolchain.lock.json requirements/container-runtime.txt scripts/bootstrap-test-git.sh scripts/verify-container-toolchain.py ./
RUN sed -i -e 's|http://archive.ubuntu.com/ubuntu/|https://snapshot.ubuntu.com/ubuntu/20260916T000000Z/|g' -e 's|http://ports.ubuntu.com/ubuntu-ports/|https://snapshot.ubuntu.com/ubuntu/20260916T000000Z/|g' /etc/apt/sources.list.d/ubuntu.sources \
    && apt-get -o Acquire::Retries=20 -o Acquire::https::Timeout=30 -o Acquire::https::Verify-Peer=false update -qq \
    && apt-get -o Acquire::https::Verify-Peer=false install -qq -y --no-install-recommends ca-certificates=20260601~26.04.1 \
    && apt-get -o Acquire::Retries=20 -o Acquire::https::Timeout=30 update -qq \
    && apt-get install -qq -y --no-install-recommends \
        build-essential=12.12ubuntu2.26.04.2 gettext=0.23.2-1 git=1:2.53.0-1ubuntu1 \
        gnupg=2.4.8-4ubuntu3.1 libcurl4-gnutls-dev=8.18.0-1ubuntu2.5 \
        libexpat1-dev=2.7.4-1 libssl-dev=3.5.5-1ubuntu3.5 python3=3.14.3-0ubuntu2 \
        python3-venv=3.14.3-0ubuntu2 zlib1g-dev=1:1.3.dfsg+really1.3.1-1ubuntu3.1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN ./bootstrap-test-git.sh /opt/git-2.47.0 \
    && python3 -m venv /opt/build \
    && /opt/build/bin/pip install --no-index /usr/share/python-wheels/setuptools-*.whl \
    && /opt/build/bin/pip wheel --no-build-isolation --no-deps --wheel-dir /wheel . \
    && python3 -m venv /opt/runtime \
    && /opt/runtime/bin/pip install --require-hashes --no-deps --requirement container-runtime.txt \
    && /opt/runtime/bin/pip install --no-index --no-deps /wheel/*.whl \
    && PATH=/opt/git-2.47.0/bin:/opt/runtime/bin:$PATH git filter-repo --version | grep -Fx a40bce548d2c \
    && python3 verify-container-toolchain.py --lock toolchain.lock.json --architecture "$TARGETARCH" \
        --package-version "$PACKAGE_VERSION" --source-revision "$SOURCE_REVISION" \
        --output toolchain-manifest.json

FROM builder AS test
COPY . .
RUN PATH=/opt/git-2.47.0/bin:/opt/runtime/bin:$PATH env -u PYTHONPATH /opt/runtime/bin/python -m unittest discover -s tests -t . -v

FROM ${BASE_IMAGE} AS runtime
ARG SOURCE_DATE_EPOCH
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH} \
    PATH=/opt/git-2.47.0/bin:/opt/runtime/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
RUN sed -i -e 's|http://archive.ubuntu.com/ubuntu/|https://snapshot.ubuntu.com/ubuntu/20260916T000000Z/|g' -e 's|http://ports.ubuntu.com/ubuntu-ports/|https://snapshot.ubuntu.com/ubuntu/20260916T000000Z/|g' /etc/apt/sources.list.d/ubuntu.sources \
    && apt-get -o Acquire::Retries=20 -o Acquire::https::Timeout=30 -o Acquire::https::Verify-Peer=false update -qq \
    && apt-get -o Acquire::https::Verify-Peer=false install -qq -y --no-install-recommends ca-certificates=20260601~26.04.1 \
    && apt-get -o Acquire::Retries=20 -o Acquire::https::Timeout=30 update -qq \
    && apt-get install -qq -y --no-install-recommends \
        libcurl4t64=8.18.0-1ubuntu2.5 libexpat1=2.7.4-1 libssl3t64=3.5.5-1ubuntu3.5 \
        python3=3.14.3-0ubuntu2 python3-venv=3.14.3-0ubuntu2 \
        zlib1g=1:1.3.dfsg+really1.3.1-1ubuntu3.1 \
    && groupadd --gid 65532 sanitize \
    && useradd --uid 65532 --gid 65532 --create-home --shell /usr/sbin/nologin sanitize \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder --chown=root:root /opt/git-2.47.0 /opt/git-2.47.0
COPY --from=builder --chown=root:root /opt/runtime /opt/runtime
COPY --from=builder --chown=root:root /build/toolchain-manifest.json /usr/local/share/git-history-sanitize/toolchain-manifest.json
COPY --chown=root:root container/oci-manifest-required /usr/local/etc/git-history-sanitize/oci-manifest-required
COPY --chown=root:root container/oci-runtime-entrypoint.sh /usr/local/bin/oci-runtime-entrypoint.sh
RUN chmod -R a-w /opt/git-2.47.0 /opt/runtime /usr/local/share/git-history-sanitize /usr/local/etc/git-history-sanitize \
    && chmod 0555 /usr/local/bin/oci-runtime-entrypoint.sh

USER 65532:65532
ENTRYPOINT ["/usr/local/bin/oci-runtime-entrypoint.sh"]
