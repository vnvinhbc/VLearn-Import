# VLearn Importer — AWS EC2 bootstrap

A small Python 3.12+ skeleton (tested with Python 3.14 on EC2) for Ubuntu 26.04 / AWS `t2.micro` (1 vCPU, ~1 GiB RAM).

**SAFETY:** On first deployment the service runs in `WORKER_MODE=idle` only. It does not consume Cloudflare Queues, change D1, or acknowledge messages. Add Queue/R2/Main API business logic before enabling processing.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m pip install ruff
ruff check .
python -m unittest discover -s tests -v
python -m vlearn_importer check
python -m vlearn_importer worker  # Ctrl+C to stop
```

To try text extraction with a document you have permission to use:

```bash
python -m pip install -e '.[extract]'
python -m vlearn_importer extract ./example.docx --output ./extracted.txt
python -m vlearn_importer extract ./example.pdf --output ./extracted.txt
```

The extractor is a starting point. It does not extract scanned PDFs, TOEIC answer keys, image associations, or question groups yet.

## EC2 one-time setup (SSH as ubuntu)

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip rsync
sudo useradd -m -s /bin/bash vdeploy
sudo useradd --system --home /var/lib/vlearn-importer --shell /usr/sbin/nologin vlearn
sudo install -d -m 2750 -o vdeploy -g vlearn /opt/vlearn-importer
sudo install -d -m 2750 -o vdeploy -g vlearn /opt/vlearn-importer/current
sudo install -d -m 0750 -o vlearn -g vlearn /var/lib/vlearn-importer
sudo install -d -m 0700 -o root -g root /etc/vlearn-importer
sudo install -d -m 0700 -o vdeploy -g vdeploy /home/vdeploy/.ssh
sudo install -m 0600 -o root -g root /dev/null /etc/vlearn-importer/worker.env
printf 'WORKER_MODE=idle\nHEARTBEAT_SECONDS=60\n' | sudo tee /etc/vlearn-importer/worker.env >/dev/null
```

Add only the *public* deploy SSH key to `/home/vdeploy/.ssh/authorized_keys` and set `vdeploy:vdeploy`, mode 0600. Verify SSH host key fingerprint before storing `VPS_KNOWN_HOSTS` in GitHub.

Install the service unit from this repository (after first copying the file to EC2):

```bash
sudo cp deploy/vlearn-importer.service /etc/systemd/system/vlearn-importer.service
sudo systemctl daemon-reload
sudo systemctl enable vlearn-importer.service
```

Give the deploy user permission to restart this *one* service:

```bash
printf '%s\n' 'vdeploy ALL=(root) NOPASSWD: /usr/bin/systemctl restart vlearn-importer.service' | sudo tee /etc/sudoers.d/vlearn-importer-deploy >/dev/null
sudo chmod 440 /etc/sudoers.d/vlearn-importer-deploy
sudo visudo -cf /etc/sudoers.d/vlearn-importer-deploy
```

The CI/CD workflow creates `.venv`, installs the application, restarts the service and checks status. The service should stay disabled/not running until the first deploy installs the Python package.

## Required GitHub Action secrets

- `VPS_HOST` — EC2 stable public IP or DNS.
- `VPS_USER` — `vdeploy`.
- `VPS_SSH_KEY` — contents of private deploy key (no passphrase for noninteractive SSH runner). **Never commit.**
- `VPS_KNOWN_HOSTS` — `ssh-keyscan` output **after comparing fingerprint** with the fingerprint from EC2.

In GitHub repository Settings → Environments, create an environment named `production`. Use branch protection to restrict production deploys to `main`. No Cloudflare credentials are required in GitHub Actions for the bootstrap.

## Verify

```bash
sudo systemctl status vlearn-importer --no-pager
sudo journalctl -u vlearn-importer -n 50 --no-pager
sudo journalctl -u vlearn-importer -f
```

## Next stage (not implemented yet)

1. Cloudflare Queue HTTP Pull consumer with one message at a time.
2. R2 S3-compatible reads/writes for source documents and extracted artifacts.
3. Parsing answer key, question groups, TOEIC Parts 1–7.
4. Main API callback that validates result contract and records durable state in D1.
5. ACK messages only after result is persistently recorded. Use job idempotency and safe retries.

See official docs: https://developers.cloudflare.com/queues/configuration/pull-consumers/ and https://developers.cloudflare.com/r2/examples/aws/boto3/.
