FROM ubuntu@sha256:2260313b31c8c011cd2eebe728008efac1b3982be73eb71348ea2648d2c0e09b AS base

RUN apt-get update -qq \
    && apt-get install -qq -y --no-install-recommends \
        build-essential ca-certificates gettext git libcurl4-gnutls-dev \
        libexpat1-dev libssl-dev python3 python3-venv zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

RUN scripts/bootstrap-test-git.sh /opt/git-2.47.0 \
    && test "$(/opt/git-2.47.0/bin/git --version)" = "git version 2.47.0" \
    && python3 -m venv /opt/git-filter-repo \
    && /opt/git-filter-repo/bin/pip install --no-deps git-filter-repo==2.47.0 \
    && ln -s /opt/git-filter-repo/bin/git-filter-repo /usr/local/bin/git-filter-repo \
    && test "$(PATH=/opt/git-2.47.0/bin:$PATH git filter-repo --version)" = "bc98e38e057b" \
    && python3 -m venv /opt/runtime \
    && /opt/runtime/bin/pip install --no-deps .

ENV PATH=/opt/git-2.47.0/bin:/opt/runtime/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin

FROM base AS test

RUN python3 -m venv /opt/test \
    && /opt/test/bin/pip install --no-deps -e . \
    && env -u PYTHONPATH /opt/test/bin/python tests/support/toolchain.py \
    && env -u PYTHONPATH /opt/test/bin/python -m unittest discover -s tests -t . -v

FROM base AS runtime

ENTRYPOINT ["/opt/runtime/bin/python", "-m", "git_history_sanitize"]
