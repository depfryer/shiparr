# Shiparr Dockerfile (à compléter selon les besoins de build)

FROM python:3.14-slim AS base

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl ca-certificates tar xz-utils \
    && rm -rf /var/lib/apt/lists/*

# Installer sops, age et docker-cli (client uniquement)
ENV SOPS_VERSION=3.9.0 \
    AGE_VERSION=1.1.1 \
    DOCKER_CLI_VERSION=27.3.1

# sops binaire
RUN arch="$(uname -m)" \ 
    && if [ "$arch" = "x86_64" ] || [ "$arch" = "amd64" ]; then sops_arch="amd64"; else sops_arch="amd64"; fi \ 
    && curl -fsSL "https://github.com/getsops/sops/releases/download/v${SOPS_VERSION}/sops-v${SOPS_VERSION}.linux.${sops_arch}" -o /usr/local/bin/sops \ 
    && chmod +x /usr/local/bin/sops

# age binaire
RUN arch="$(uname -m)" \ 
    && if [ "$arch" = "x86_64" ] || [ "$arch" = "amd64" ]; then age_arch="amd64"; else age_arch="amd64"; fi \ 
    && curl -fsSL "https://github.com/FiloSottile/age/releases/download/v${AGE_VERSION}/age-v${AGE_VERSION}-linux-${age_arch}.tar.gz" -o /tmp/age.tar.gz \ 
    && tar -xzf /tmp/age.tar.gz -C /tmp \ 
    && mv /tmp/age/age /usr/local/bin/age \ 
    && mv /tmp/age/age-keygen /usr/local/bin/age-keygen \ 
    && chmod +x /usr/local/bin/age /usr/local/bin/age-keygen \ 
    && rm -rf /tmp/age /tmp/age.tar.gz

# docker CLI statique
RUN arch="$(uname -m)" \ 
    && if [ "$arch" = "x86_64" ] || [ "$arch" = "amd64" ]; then docker_arch="x86_64"; else docker_arch="x86_64"; fi \ 
    && curl -fsSL "https://download.docker.com/linux/static/stable/${docker_arch}/docker-${DOCKER_CLI_VERSION}.tgz" -o /tmp/docker.tgz \ 
    && tar -xzf /tmp/docker.tgz -C /tmp \ 
    && mv /tmp/docker/docker /usr/local/bin/docker \ 
    && chmod +x /usr/local/bin/docker \ 
    && rm -rf /tmp/docker /tmp/docker.tgz

WORKDIR /app

COPY pyproject.toml ./
COPY LICENSE ./
COPY README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

USER 1000
EXPOSE 8080

CMD ["python", "-m", "Shiparr.app"]
