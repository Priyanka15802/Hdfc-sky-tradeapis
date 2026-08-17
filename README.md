# HDFC Sky — Lite Trade Tool

A small Flask backend + single-page HTML/JS frontend for the HDFC Sky Open
API: login (7-call flow: token id → username → OTP → PIN → authorise →
access token, plus a resend-OTP utility), a 5-second-polling LTP
watchlist, and place/modify/cancel for Regular, AMO, Cover, and Bracket
orders, plus place/cancel/fetch for GTT orders (23 of the 24 APIs in
HDFC's doc — see "What's not implemented" below).

Every request this tool sends mirrors an exact curl from HDFC's own API
doc — same host, path, method, and body — nothing was guessed. Where the
doc didn't show something (mainly response shapes, and the `consent`
value for Authorise), the tool doesn't invent it: it shows you the raw
response and gives you an editable field instead.

## Project layout

```
app.py               Flask routes: session handling, dry-run gate, field extraction
hdfc_client.py        one function per HDFC Sky endpoint, matching their curls exactly
static/index.html     the whole UI (login wizard, LTP watchlist, order tabs)
static/app.js         vanilla JS: fetch() calls to the Flask backend, 5s LTP polling
static/style.css
tests/                 unit tests (HTTP calls mocked, no real credentials/network needed)
deploy/                systemd unit + EC2 setup/deploy scripts
.github/workflows/     CI (tests)
```

No frontend build step, no framework beyond Flask — kept deliberately
small so there's one Python file and one JS file to reason about.

## What's not implemented

**Modify GTT Orders.** HDFC's doc (`PUT /oapi/v1/event/gtt`) shows only
headers — no request body and no way to identify which GTT order you're
modifying. There's nothing to build against. The button is disabled in
the UI. Once you have the real request shape, add a `modify_gtt_order()`
function to `hdfc_client.py` (mirroring the others) and a route in
`app.py`.

## Local setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in HDFC_SKY_API_KEY, HDFC_SKY_API_SECRET, HDFC_SKY_CLIENT_ID, FLASK_SECRET_KEY
pytest -q          # sanity check, all HTTP calls mocked, no real credentials needed
python app.py       # http://127.0.0.1:5000, Flask dev server
```

`DRY_RUN=true` (the `.env.example` default) makes every place/modify/cancel
order call return the exact request it *would* send instead of sending
it — verify payloads look right before flipping it to `false`.

## How the login flow works in the UI

Each of the 7 steps is its own button because HDFC's docs never show what
the responses look like, so the tool can't reliably auto-chain them:

1. **Start login** → gets a `token_id`.
2. **Submit username**.
3. **Validate OTP** (there's also a Resend OTP button).
4. **Validate PIN**.
5. **Authorise** — needs a `request_token` (auto-filled if step 3 or 4's
   response contained one under a common key name; otherwise check the
   raw response shown on screen and paste it in yourself) and a
   `consent` value (HDFC's doc shows this parameter but never says what
   value it expects — enter whatever your account requires).
6. **Get access token** — exchanges the request_token + your API secret
   for the access_token that every subsequent call uses.

The raw JSON from every step is shown on screen specifically so you can
see what HDFC actually sent back and correct any auto-filled field that
guessed wrong.

## Why this needs to run on a server, not your laptop

HDFC Sky's Open API only accepts calls from an IP you've
pre-registered/whitelisted with them. Home/mobile connections essentially
never have a static IP, so the fix is running this on a small cloud VM
that has one, and whitelisting that IP with HDFC Sky instead.

## Recommended hosting: EC2 + an Elastic IP, reached over SSH tunnel

**Use an AWS EC2 free-tier instance with an Elastic IP attached**, and
reach the tool's web UI through an SSH tunnel rather than opening a port
for it.

- A plain EC2 public IP changes on every stop/start — an **Elastic IP**
  stays fixed as long as it's attached to a *running* instance (and it's
  free under that condition; AWS charges for an idle/unattached one).
- This is a login-and-order UI for your own trading account — it
  shouldn't be reachable from the open internet. Run it bound to
  `127.0.0.1` on the instance (already set up that way in
  `deploy/hdfc-sky-bot.service`, via gunicorn) and access it from your
  browser with:
  ```bash
  ssh -L 5000:localhost:5000 ubuntu@<ELASTIC_IP>
  ```
  then browse to `http://localhost:5000`. The security group only ever
  needs port 22 open, from your own IP.

### Steps (run these yourself in the AWS console — this session has no AWS access)

1. Launch `t2.micro`/`t3.micro`, Ubuntu 22.04/24.04, free-tier-eligible
   region. Create/download an SSH key pair.
2. Allocate an **Elastic IP** and associate it with the instance.
3. Security group: inbound SSH (22) from your own IP only.
4. Whitelist the Elastic IP with HDFC Sky in the developer portal.
5. Set up the app:
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
   journalctl -u hdfc-sky-bot -f         # watch logs
   ```
6. From your laptop: `ssh -L 5000:localhost:5000 ubuntu@<ELASTIC_IP>`,
   then open `http://localhost:5000`.
7. **Ongoing deploys** — `ssh` in and run `bash deploy/deploy.sh` (git
   pull + restart), or wire up `.github/workflows/deploy.yml` with
   `EC2_HOST`/`EC2_USER`/`EC2_SSH_KEY` repo secrets to do it from GitHub
   Actions (manual trigger by default, see comments in that file).

### Secrets

`.env` lives only on the EC2 instance, `chmod 600`, never committed. For
more rigor than a flat file, consider AWS Systems Manager Parameter
Store (SecureString, free tier covers this) — the only code change
needed is in the small `os.environ.get(...)` block at the top of
`app.py`.
