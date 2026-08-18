# Daily usage cheat sheet

Your EC2 details (fill in / already set):
- Elastic IP: `3.6.125.49`
- SSH key (on your phone/Termux): `~/hdfc-sky-vm-pair.pem`
- The app auto-starts on boot (systemd `enable`d), so you never start it by hand.

---

## Every day: open the app

**Step 1 — make sure the instance is running.**
- If you leave the instance ON 24/7: skip this, it's already running.
- If you stop it to save cost: AWS Console → EC2 → Instances → select
  `hdfc-sky` → Instance state → **Start instance**. Wait ~1 min for
  "Running" + status checks. The Elastic IP stays the same, and the app
  auto-starts, so nothing to reconfigure.

**Step 2 — open the tunnel** (in Termux). This is the command you reuse
every day:
```bash
ssh -i ~/hdfc-sky-vm-pair.pem -L 5000:localhost:5000 ubuntu@3.6.125.49
```
Leave this session open while you trade.

**Step 3 — open the UI.** Phone browser → http://localhost:5000 → log in
(Client ID → OTP → MPIN).

That's the whole daily flow.

---

## Optional: watch the server logs while you trade

In a SECOND Termux session (swipe from the left edge → New session):
```bash
ssh -i ~/hdfc-sky-vm-pair.pem ubuntu@3.6.125.49
```
then on the server:
```bash
journalctl -u hdfc-sky-bot -f
```
Every browser action prints a line with its status code (200 ok, 401 not
logged in, 502 HDFC rejected). Ctrl+C stops the log view (not the app).

---

## Handy server commands (run after SSH-ing in)

Check the app is running:
```bash
systemctl is-active hdfc-sky-bot
```

Restart the app (e.g. after changing .env):
```bash
sudo systemctl restart hdfc-sky-bot
```

See the last 30 log lines without following:
```bash
journalctl -u hdfc-sky-bot -n 30 --no-pager
```

Pull the latest code and restart (after new changes are pushed to the
branch):
```bash
bash ~/hdfc-sky-tradeapis/deploy/deploy.sh
```

---

## Dry run vs live

- The app opens in **dry run** each launch (safe — no real orders).
- To place real orders: use the toggle at the top-right of the UI, confirm
  the warning. It stays live only for that browser session.
- To make it default to live permanently, change `DRY_RUN=false` in
  `~/hdfc-sky-tradeapis/.env` on the server, then
  `sudo systemctl restart hdfc-sky-bot`.

---

## Saving cost (optional)

Two AWS instances running 24/7 exceed the 750 free-tier hours, so a second
always-on instance costs roughly $8–9/month plus ~$3.60/month for the
public IPv4. If you only trade during market hours, stopping the instance
when done (AWS Console → Instance state → Stop) reduces the instance-hour
cost. The Elastic IP and whitelisting survive stop/start unchanged.
