# syntax=docker/dockerfile:1

# The server with eight of its nine tools; Blackbird is left out because it has no license that allows
# redistributing it. Every Python tool gets its own virtual environment: their pinned dependencies
# conflict (GHunt needs httpx<0.28, theHarvester pins httpx 0.28.1).

FROM python:3.14-slim-trixie AS build

ARG TARGETARCH
ARG SPIDERFOOT_COMMIT=0f815a203afebf05c98b605dba5cf0475a0ee5fd
ARG PHONEINFOGA_VERSION=2.11.0
ARG EXIFTOOL_VERSION=13.59

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git \
 && rm -rf /var/lib/apt/lists/*

# Pinned in docker/<tool>/requirements.txt, where Dependabot keeps them current
COPY docker/ /tmp/docker/
RUN for tool in sherlock holehe maigret ghunt theharvester; do \
      python -m venv /opt/venvs/$tool \
      && /opt/venvs/$tool/bin/pip install --no-cache-dir -r /tmp/docker/$tool/requirements.txt \
      || exit 1; \
    done

# SpiderFoot runs from a git checkout; the server uses the .venv inside it
COPY patches/ /tmp/patches/
RUN git init --quiet /opt/spiderfoot \
 && git -C /opt/spiderfoot fetch --quiet --depth 1 https://github.com/smicallef/spiderfoot "$SPIDERFOOT_COMMIT" \
 && git -C /opt/spiderfoot checkout --quiet FETCH_HEAD \
 && git -C /opt/spiderfoot apply /tmp/patches/spiderfoot-requirements.patch \
 && rm -rf /opt/spiderfoot/.git \
 && python -m venv /opt/spiderfoot/.venv \
 && /opt/spiderfoot/.venv/bin/pip install --no-cache-dir -r /opt/spiderfoot/requirements.txt

# PhoneInfoga: the release binary, verified against the release checksums
RUN case "$TARGETARCH" in \
      amd64) arch=x86_64 ;; \
      arm64) arch=arm64 ;; \
      *) echo "no PhoneInfoga build for $TARGETARCH" >&2; exit 1 ;; \
    esac \
 && release="https://github.com/sundowndev/phoneinfoga/releases/download/v$PHONEINFOGA_VERSION" \
 && cd /tmp \
 && curl -fsSLO "$release/phoneinfoga_Linux_$arch.tar.gz" \
 && curl -fsSLO "$release/phoneinfoga_checksums.txt" \
 && grep " phoneinfoga_Linux_$arch.tar.gz\$" phoneinfoga_checksums.txt | sha256sum -c - \
 && mkdir /opt/phoneinfoga \
 && tar -xzf "phoneinfoga_Linux_$arch.tar.gz" -C /opt/phoneinfoga phoneinfoga

# ExifTool is Perl and runs straight from its release tree
RUN curl -fsSL "https://github.com/exiftool/exiftool/archive/refs/tags/$EXIFTOOL_VERSION.tar.gz" | tar -xz -C /opt \
 && mv "/opt/exiftool-$EXIFTOOL_VERSION" /opt/exiftool

COPY pyproject.toml README.md LICENSE /tmp/server/
COPY src/ /tmp/server/src/
RUN python -m venv /opt/venvs/server \
 && /opt/venvs/server/bin/pip install --no-cache-dir /tmp/server


FROM python:3.14-slim-trixie

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates perl \
 && rm -rf /var/lib/apt/lists/*

COPY --from=build /opt/venvs /opt/venvs
COPY --from=build /opt/phoneinfoga /opt/phoneinfoga
COPY --from=build /opt/exiftool /opt/exiftool
COPY --from=build --chown=10001:10001 /opt/spiderfoot /opt/spiderfoot

RUN for tool in sherlock holehe maigret ghunt; do ln -s "/opt/venvs/$tool/bin/$tool" /usr/local/bin/; done \
 && ln -s /opt/venvs/theharvester/bin/theHarvester /usr/local/bin/ \
 && ln -s /opt/venvs/server/bin/osint-toolbox-mcp /usr/local/bin/ \
 && ln -s /opt/phoneinfoga/phoneinfoga /usr/local/bin/ \
 && printf '#!/bin/sh\nexec perl /opt/exiftool/exiftool "$@"\n' > /usr/local/bin/exiftool \
 && chmod +x /usr/local/bin/exiftool \
 && useradd --create-home --uid 10001 osint \
 && install -d -o osint /data /home/osint/.malfrats

ENV OSINT_SPIDERFOOT_DIR=/opt/spiderfoot \
    OSINT_TOOLBOX_CONTAINER=1 \
    PYTHONUNBUFFERED=1

LABEL org.opencontainers.image.title="osint-toolbox-mcp" \
      org.opencontainers.image.description="MCP server with Sherlock, Holehe, Maigret, GHunt, theHarvester, SpiderFoot, PhoneInfoga and ExifTool" \
      org.opencontainers.image.source="https://github.com/renkagod/osint-toolbox-mcp" \
      org.opencontainers.image.licenses="MIT" \
      io.modelcontextprotocol.server.name="io.github.renkagod/osint-toolbox-mcp"

USER osint
WORKDIR /home/osint
ENTRYPOINT ["osint-toolbox-mcp"]
