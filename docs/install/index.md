# Linux RAG T2 – First-Time Installation Guide

This admin guide assembles every component required to run the Linux RAG T2
stack on a fresh systemd-based host. Work through each section in order to
install the supporting services, compile the CLIs, and launch the backend as
a managed systemd service.

## 1. Prerequisites

- Linux distribution with systemd (verified on Ubuntu 22.04 and Fedora 39)
- Packages:
  - **Go 1.23+**
  - **Python 3.12+** and `pip`
  - **uv** (Python dependency manager)
  - `git`, `curl`, `tar`, `make`
- Outbound network access to download release archives and Python wheels
- Root privileges for installing binaries and systemd units

Example package installation (Debian/Ubuntu):

```bash
sudo apt update
sudo apt install -y golang-go python3.12 python3.12-venv python3-pip git curl tar make
pipx install uv  # or pip install --user uv
```

## 2. Clone the Repository

```bash
sudo mkdir -p /opt
sudo chown "$USER":"$USER" /opt
git clone https://github.com/linux-rag-t2/linux-rag-t2.git /opt/linux-rag-t2
cd /opt/linux-rag-t2
```

## 3. Install Dependency Services

The backend expects three local services: **Ollama** for inference,
**Weaviate** for vector storage, and **Arize Phoenix** for observability.
Scripts in `docs/install/scripts/` automate the installation, user creation,
and systemd registration for each dependency.

### 3.1 Ollama – Local Model Server

```bash
sudo docs/install/scripts/install_ollama.sh
```

This script:

- Downloads the latest Ollama release for the host architecture
- Creates the `ollama` system user and home at `/usr/share/ollama`
- Installs `docs/install/systemd/ollama.service`
- Pulls the `gemma3:1b` and `embeddinggemma:latest` models

Validate the service:

```bash
sudo systemctl status ollama
sudo journalctl -u ollama -f
```

### 3.2 Weaviate – Vector Database

```bash
sudo docs/install/scripts/install_weaviate.sh 1.26.4
```

This script:

- Downloads the specified Weaviate release into `/opt/weaviate`
- Creates the `weaviate` system user and data directory `/var/lib/weaviate`
- Writes `/etc/weaviate/weaviate.env` (template: `docs/install/config/weaviate.env`)
- Installs `docs/install/systemd/weaviate.service`

Validate readiness:

```bash
sudo systemctl status weaviate
curl http://localhost:8080/v1/.well-known/ready
```

### 3.3 Arize Phoenix – Observability

```bash
sudo docs/install/scripts/install_phoenix.sh
```

This script:

- Creates the `phoenix` system user and `/opt/phoenix`
- Provisions a dedicated Python virtual environment and installs `arize-phoenix[server]`
- Writes `/etc/phoenix/phoenix.env` (template: `docs/install/config/phoenix.env`)
- Installs `docs/install/systemd/phoenix.service`

Validate the service:

```bash
sudo systemctl status phoenix
curl http://localhost:6006/health
```

> **Tip:** Update the environment files in `/etc/{weaviate,phoenix}/` if you
> need to change ports or bind addresses. Mirror those hostnames in the backend
> `backend` section inside `/etc/ragcli/config.yaml`.

## 4. Prepare Python Dependencies

`uv` installs backend dependencies directly from `pyproject.toml`:

```bash
uv sync  # creates .venv and synchronizes locked packages
```

All backend invocations use `uv run …`, ensuring the locked environment is
respected.

## 5. Compile the Go CLIs

Build and install the CLI binaries (adjust paths to match your policy):

```bash
go build -o /usr/local/bin/ragman ./cli/ragman
go build -o /usr/local/bin/ragadmin ./cli/ragadmin
```

Confirm they launch:

```bash
ragman --help
ragadmin --help
```

## 6. Seed Runtime Directories and Config

Bootstrap XDG-compliant directories, create the `ragcli` user if required,
and seed configuration defaults:

```bash
sudo docs/install/scripts/setup_ragcli.sh /opt/linux-rag-t2 ragcli
```

Artifacts created by the script:

- `/etc/ragcli/config.yaml` (template: `docs/install/config/ragcli-config.yaml`)
- `/var/lib/ragcli/ragcli/` (state) and `/var/lib/ragcli/ragcli/kiwix`
- `/var/log/ragcli/` and `/run/ragcli/`

## 7. Review Backend Environment

Inspect `/etc/ragcli/config.yaml` and adjust the backend section to match your
deployment. The default installed by the script looks like:

```yaml
ragman:
  confidence_threshold: 0.35
  presenter_default: markdown
ragadmin:
  output_default: table
backend:
  socket: /run/ragcli/backend.sock
  weaviate_url: http://localhost:8080
  weaviate_grpc_port: 50051
  ollama_url: http://localhost:11434
  phoenix_url: localhost:4317  # gRPC OTLP endpoint (UI remains on 6006)
  log_level: INFO
  trace: false
```

Set `log_level` to `DEBUG` when you need verbose diagnostics or leave it at
`INFO` for quieter logs. `weaviate_grpc_port` must match the port exposed by
your Weaviate deployment (the default systemd unit binds gRPC on `50051`).
Toggle `trace: true` only when you need deep tracing; otherwise keep it `false`
to minimize overhead. The `ragman`/`ragadmin` blocks remain available for CLI
defaults (confidence threshold, presenters, etc.).

## 8. Install Systemd Units

If you used the helper scripts, the dependency units are already installed.
Copy the backend unit into `/etc/systemd/system/` and reload systemd:

```bash
sudo cp docs/install/systemd/ragbackend.service /etc/systemd/system/ragbackend.service
sudo systemctl daemon-reload
```

Confirm the dependency unit files (`ollama.service`, `weaviate.service`,
`phoenix.service`) exist in `/etc/systemd/system`; copy them from
`docs/install/systemd/` if necessary.

The `ragbackend.service` unit invokes `PYTHONPATH=backend/src uv run --directory backend python -m main --config /etc/ragcli/config.yaml`;
update the `RAGCLI_CONFIG` environment variable inside the unit file if you relocate the config.

## 9. Enable and Start Services

Enable each service so it starts on boot, then bring them online in order:

```bash
sudo systemctl enable --now ollama.service
sudo systemctl enable --now weaviate.service
sudo systemctl enable --now phoenix.service
sudo systemctl enable --now ragbackend.service
```

Check health:

```bash
sudo systemctl status ragbackend.service
sudo journalctl -u ragbackend.service -f
ls -l /run/ragcli/backend.sock
```

If startup fails, inspect journals for missing dependencies or incorrect
configuration URLs.

## 10. Smoke Test the CLIs

```bash
ragman query "How do I change file permissions?"
ragadmin init
```

Expect an English answer with citations; if confidence falls below the
threshold you will see the “No answer found” guidance.

## 11. Maintenance Tips

- **Upgrade code & dependencies**

  ```bash
  cd /opt/linux-rag-t2
  git pull
  uv sync
  go build -o /usr/local/bin/ragman ./cli/ragman
  go build -o /usr/local/bin/ragadmin ./cli/ragadmin
  sudo systemctl restart ragbackend.service
  ```

- **Monitor services**

  ```bash
  sudo journalctl -u ollama -u weaviate -u phoenix -u ragbackend --since "1 hour ago"
  ```

- **Model updates** (Ollama):

  ```bash
  sudo -u ollama ollama pull gemma3:1b
  sudo -u ollama ollama pull embeddinggemma:latest
  sudo systemctl restart ollama
  ```

Following these steps yields a fully managed installation of the Linux
RAG stack: dependency services run under systemd, directories follow XDG
conventions, and the `ragman`/`ragadmin` CLIs are ready for end users. Refer
back to this guide to provision additional hosts or to audit your current
deployment. !*** End Patch
