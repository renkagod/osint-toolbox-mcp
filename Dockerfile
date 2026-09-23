# syntax=docker/dockerfile:1

# The server with every tool but Blackbird, which has no license that allows redistributing it. Every
# Python tool gets its own virtual environment: their pinned dependencies conflict (GHunt needs
# httpx<0.28, theHarvester pins httpx 0.28.1).

FROM python:3.12-slim-trixie AS build

ARG TARGETARCH
ARG SPIDERFOOT_COMMIT=0f815a203afebf05c98b605dba5cf0475a0ee5fd
ARG PHONEINFOGA_VERSION=2.11.0
ARG SUBFINDER_VERSION=2.16.0
ARG EXIFTOOL_VERSION=13.59

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git unzip \
 && rm -rf /var/lib/apt/lists/*

# Pinned in docker/<tool>/requirements.txt, where Dependabot keeps them current
COPY docker/ /tmp/docker/
RUN for tool in sherlock holehe maigret ghunt theharvester dnstwist dnsrecon; do \
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

# PhoneInfoga and subfinder: release binaries, verified against the releases' checksums
RUN case "$TARGETARCH" in \
      amd64) phoneinfoga_arch=x86_64 ;; \
      arm64) phoneinfoga_arch=arm64 ;; \
      *) echo "no builds for $TARGETARCH" >&2; exit 1 ;; \
    esac \
 && cd /tmp \
 && release="https://github.com/sundowndev/phoneinfoga/releases/download/v$PHONEINFOGA_VERSION" \
 && curl -fsSLO "$release/phoneinfoga_Linux_$phoneinfoga_arch.tar.gz" \
 && curl -fsSLO "$release/phoneinfoga_checksums.txt" \
 && grep " phoneinfoga_Linux_$phoneinfoga_arch.tar.gz\$" phoneinfoga_checksums.txt | sha256sum -c - \
 && mkdir -p /opt/bin \
 && tar -xzf "phoneinfoga_Linux_$phoneinfoga_arch.tar.gz" -C /opt/bin phoneinfoga \
 && release="https://github.com/projectdiscovery/subfinder/releases/download/v$SUBFINDER_VERSION" \
 && curl -fsSLO "$release/subfinder_${SUBFINDER_VERSION}_linux_$TARGETARCH.zip" \
 && curl -fsSLO "$release/subfinder_${SUBFINDER_VERSION}_checksums.txt" \
 && grep " subfinder_${SUBFINDER_VERSION}_linux_$TARGETARCH.zip\$" "subfinder_${SUBFINDER_VERSION}_checksums.txt" | sha256sum -c - \
 && unzip -q -o "subfinder_${SUBFINDER_VERSION}_linux_$TARGETARCH.zip" subfinder -d /opt/bin

# ExifTool is Perl and runs straight from its release tree
RUN curl -fsSL "https://github.com/exiftool/exiftool/archive/refs/tags/$EXIFTOOL_VERSION.tar.gz" | tar -xz -C /opt \
 && mv "/opt/exiftool-$EXIFTOOL_VERSION" /opt/exiftool

COPY pyproject.toml README.md LICENSE /tmp/server/
COPY src/ /tmp/server/src/
RUN python -m venv /opt/venvs/server \
 && /opt/venvs/server/bin/pip install --no-cache-dir /tmp/server


FROM python:3.12-slim-trixie

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates perl \
 && rm -rf /var/lib/apt/lists/*

COPY --from=build /opt/venvs /opt/venvs
COPY --from=build /opt/bin /opt/bin
COPY --from=build /opt/exiftool /opt/exiftool
COPY --from=build --chown=10001:10001 /opt/spiderfoot /opt/spiderfoot

RUN for tool in sherlock holehe maigret ghunt dnstwist dnsrecon; do ln -s "/opt/venvs/$tool/bin/$tool" /usr/local/bin/; done \
 && ln -s /opt/venvs/theharvester/bin/theHarvester /usr/local/bin/ \
 && ln -s /opt/venvs/server/bin/osint-toolbox-mcp /usr/local/bin/ \
 && ln -s /opt/bin/phoneinfoga /opt/bin/subfinder /usr/local/bin/ \
 && printf '#!/bin/sh\nexec perl /opt/exiftool/exiftool "$@"\n' > /usr/local/bin/exiftool \
 && chmod +x /usr/local/bin/exiftool \
 && useradd --create-home --uid 10001 osint \
 && install -d -o osint /data /home/osint/.malfrats

ENV OSINT_SPIDERFOOT_DIR=/opt/spiderfoot \
    OSINT_TOOLBOX_CONTAINER=1 \
    PYTHONUNBUFFERED=1

LABEL org.opencontainers.image.title="osint-toolbox-mcp" \
      org.opencontainers.image.description="MCP server with Sherlock, Maigret, Holehe, GHunt, theHarvester, SpiderFoot, subfinder, dnstwist, dnsrecon, PhoneInfoga, ExifTool and built-in WHOIS, DNS, crt.sh and Wayback lookups" \
      org.opencontainers.image.source="https://github.com/renkagod/osint-toolbox-mcp" \
      org.opencontainers.image.licenses="MIT" \
      io.modelcontextprotocol.server.name="io.github.renkagod/osint-toolbox-mcp"

USER osint
WORKDIR /home/osint
ENTRYPOINT ["osint-toolbox-mcp"]
