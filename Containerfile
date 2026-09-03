FROM ubuntu:26.04 AS base

RUN apt-get update -qq \
    && apt-get install -qq -y git git-filter-repo python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

ENV PYTHONPATH=/app/src

FROM base AS test

RUN python3 -m unittest discover -s tests -v

FROM base AS runtime

ENTRYPOINT ["python3", "-m", "git_history_sanitize"]
