# HDFC Sky Trade APIs client

A small Python client for the HDFC Sky Open API, covering:

- **Login** — the 6-step auth flow (`hdfc_sky/auth.py`)
- **Normal orders** — place / modify / cancel
- **Cover orders** — place / modify / cancel
- **Bracket orders** — place / modify / cancel

(`hdfc_sky/orders.py`, 9 methods total)

## ⚠️ Before you go live

This project was built without network access to `developer.hdfcsky.com`
(it's blocked from this sandbox), so **every endpoint path, HTTP method,
and payload field in `config/endpoints.yaml` and in the docstrings of
`hdfc_sky/auth.py` is a placeholder**, not a verified value. The
architecture (login orchestration, retry/error handling, dry-run safety
switch, config-driven endpoints) is solid and ready to use — but you must:

1. Log into https://developer.hdfcsky.com with your own credentials.
2. Open the Open API reference for Login and for Order Management.
3. Replace every `# TODO` in `config/endpoints.yaml` with the real
   method/path, and fix up the payload field names in `auth.py` /
   `orders.py` call sites if they differ (e.g. the checksum HDFC requires
   when exchanging `request_token` for `access_token`).
4. Only then flip `DRY_RUN=false` in your `.env`.

Until you do that, every order method just returns the request it *would*
have sent — see `DRY_RUN` below.

## Project layout

```
hdfc_sky/            the client library
  config.py           loads .env + config/endpoints.yaml into a Settings object
  http_client.py       requests.Session wrapper: retries, timeouts, auth header, error handling
  auth.py              the 6-step login flow
  orders.py            place/modify/cancel for normal/cover/bracket orders
  session_store.py     caches the access token locally so you don't re-login every run
config/endpoints.yaml  every endpoint's method+path in one place (not secret, committed)
examples/quickstart.py login + place one sample order
tests/                 unit tests (mocked HTTP, no real credentials needed)
deploy/                systemd unit + shell scripts for running this on EC2
.github/workflows/     CI (tests) and an optional SSH-deploy-to-EC2 workflow
```

## Local setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your real API key/secret/client id/password
pytest -q              # sanity check, no real credentials needed
python -m examples.quickstart   # runs with DRY_RUN=true by default
```

Secrets (`HDFC_SKY_API_KEY`, `HDFC_SKY_API_SECRET`, `HDFC_SKY_CLIENT_ID`,
`HDFC_SKY_PASSWORD`, `HDFC_SKY_TOTP_SECRET`) live only in `.env`, which is
git-ignored. Never commit it.

## Why this needs to run on a server, not your laptop

HDFC Sky's Open API only accepts order-placement calls from an IP address
you've pre-registered/whitelisted with them. Home/mobile internet
connections almost never have a static IP, so the standard fix is to run
the bot on a small cloud VM that **has** a fixed IP, and whitelist that
IP with HDFC Sky instead.

## Recommended hosting approach: EC2 + an Elastic IP

**Use an AWS EC2 free-tier instance with an Elastic IP attached.** This is
the simplest way to get a static outbound IP for a small always-on
process, and it costs nothing at free-tier volumes.

Why this over the alternatives:
- A plain EC2 public IP **changes** every time you stop/start the
  instance — an **Elastic IP** is what actually stays fixed. It's free
  as long as it stays attached to a *running* instance (AWS charges for
  Elastic IPs that are allocated but idle/unattached).
- AWS Lightsail also gives a static IP, but its "free tier" is a 3-month
  trial, not ongoing — EC2's free tier (check current terms in your AWS
  console/account, they vary by when the account was created) is the
  better fit for a long-running personal bot.
- You don't need a NAT Gateway, load balancer, or container platform for
  a single lightweight process placing orders — that's added cost and
  complexity for no benefit here.

### Steps (run these yourself in the AWS console — this session has no AWS
access, so nothing here was provisioned for you)

1. **Launch the instance**: `t2.micro` or `t3.micro`, Ubuntu 22.04/24.04
   LTS, in a free-tier-eligible region. Create/download a new SSH key
   pair.
2. **Allocate an Elastic IP** (EC2 → Network & Security → Elastic IPs →
   Allocate), then **associate** it with the instance. This IP is what
   you'll whitelist with HDFC Sky and put in DNS/config — it will not
   change even if you reboot the instance.
3. **Security group**: allow inbound SSH (22) from your own IP only.
   Nothing else needs to be open — this bot only makes outbound calls to
   HDFC Sky.
4. **Whitelist the Elastic IP** with HDFC Sky, in the same developer
   portal where you got your API key (static-IP whitelisting section).
5. **Clone and set up the app**:
   ```bash
   ssh ubuntu@<ELASTIC_IP>
   git clone https://github.com/priyanka15802/hdfc-sky-tradeapis.git
   cd hdfc-sky-tradeapis
   bash deploy/setup_ec2.sh
   cp .env.example .env && nano .env    # fill in real secrets
   chmod 600 .env
   sudo cp deploy/hdfc-sky-bot.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now hdfc-sky-bot
   journalctl -u hdfc-sky-bot -f        # watch logs
   ```
6. **Ongoing deploys** — two options:
   - Manual: `ssh` in, `bash deploy/deploy.sh` (git pull + restart).
   - Automatic: fill in the `EC2_HOST` / `EC2_USER` / `EC2_SSH_KEY`
     secrets in the GitHub repo settings, then either run the
     `Deploy to EC2` workflow manually from the Actions tab, or uncomment
     its `push` trigger in `.github/workflows/deploy.yml` to deploy on
     every merge to `main`.

### Secret handling on the server

- `.env` lives only on the EC2 instance, `chmod 600`, never committed.
- For a bit more rigor than a flat file, consider migrating secrets to
  AWS Systems Manager **Parameter Store** (SecureString, free tier
  covers this) and reading them at startup instead of a `.env` file —
  the code changes needed are limited to `hdfc_sky/config.py`.
- Set a small AWS Billing budget/alarm so you get notified if usage ever
  exceeds free-tier limits.

## Extending

- `hdfc_sky/orders.py`'s `_action()` is generic — add a new order type or
  action by adding an entry to `config/endpoints.yaml`, no new Python
  method required unless you want a named convenience wrapper.
- `AuthClient.login()` caches the access token via `SessionStore`; call
  `AuthClient.logout()` (step 6) to force a fresh login next run.
