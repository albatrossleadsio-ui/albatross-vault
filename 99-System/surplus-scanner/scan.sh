#!/bin/bash
# Albatross Surplus Scanner - Cron Wrapper
# Schedule: 0 6 * * 1,3 (Monday & Wednesday 6:00 AM MT)

# Change to script directory
cd ~/albatross/src/surplus || exit 1

# Activate virtual environment
source ~/albatross/venv/bin/activate

# Verify activation
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "ERROR: Virtual environment not activated" >&2
    exit 1
fi

# Log start
echo "[$(date)] Starting surplus scan"

# Run scanner (production mode)
python ~/albatross/src/surplus/surplus_scanner.py >> ~/albatross/surplus_scan.log 2>&1

# Sync vault to GitHub
cd ~/albatross-vault || exit 1
git add 04-Patterns/Surplus-Leads/
git commit -m "Surplus scan: $(date '+%Y-%m-%d %H:%M')" || true
git push origin main || echo "Git push failed, will retry next run"

# Log completion
echo "[$(date)] Surplus scan complete"

# Deactivate
deactivate
