#!/usr/bin/env bash
# Run on the EC2 instance (by hand, or via the deploy.yml GitHub Action)
# to pull the latest code and restart the service.
set -euo pipefail

APP_DIR="$HOME/hdfc-sky-tradeapis"
BRANCH="claude/hdfc-sky-api-integration-jv7ab8"
cd "$APP_DIR"

git fetch origin
git reset --hard "origin/$BRANCH"

source venv/bin/activate
pip install -r requirements.txt

sudo systemctl restart hdfc-sky-bot
sudo systemctl --no-pager status hdfc-sky-bot
