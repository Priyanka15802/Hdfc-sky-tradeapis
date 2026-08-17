#!/usr/bin/env bash
# One-time provisioning script — run this BY HAND over SSH on a fresh
# EC2 instance (tested against Ubuntu 22.04/24.04). It is not executed
# automatically by anything; it is meant to be read and then run.
#
# Usage (from your laptop):
#   scp deploy/setup_ec2.sh ubuntu@<ELASTIC_IP>:~/
#   ssh ubuntu@<ELASTIC_IP> 'bash setup_ec2.sh'
set -euo pipefail

REPO_URL="git@github.com:priyanka15802/hdfc-sky-tradeapis.git"
APP_DIR="$HOME/hdfc-sky-tradeapis"

sudo apt-get update
sudo apt-get install -y python3-venv python3-pip git

if [ ! -d "$APP_DIR" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn   # production WSGI server; not in requirements.txt so local/Windows dev isn't forced to install it

echo
echo "Now create $APP_DIR/.env (copy from .env.example) with real secrets,"
echo "then: chmod 600 $APP_DIR/.env"
echo
echo "Then install the systemd unit:"
echo "  sudo cp deploy/hdfc-sky-bot.service /etc/systemd/system/"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable --now hdfc-sky-bot"
echo
echo "Access the UI from your laptop via an SSH tunnel (nothing is opened"
echo "in the security group beyond port 22):"
echo "  ssh -L 5000:localhost:5000 ubuntu@<ELASTIC_IP>"
echo "  then browse http://localhost:5000"
