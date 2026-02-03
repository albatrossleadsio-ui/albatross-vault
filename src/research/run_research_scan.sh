#!/bin/bash
# ============================================================
# Research Scanner Cron Wrapper
# Part of Albatross Phase 3.4 - VPS Research Agent
#
# Purpose: Activates venv and runs all research scanners
# Usage: Called by cron or manually: ./run_research_scan.sh
#
# Cron example (daily at 8am):
#   0 8 * * * /home/albatross/research/run_research_scan.sh
# ============================================================

# Log start time
echo "========================================" >> ~/research/cron.log
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting research scan" >> ~/research/cron.log

# Activate virtual environment
source ~/research-env/bin/activate

# Run Reddit scanner
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running Reddit scanner..." >> ~/research/cron.log
python ~/research/reddit_scanner.py >> ~/research/cron.log 2>&1

# Run LPGA monitor
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running LPGA monitor..." >> ~/research/cron.log
python ~/research/lpga_monitor.py >> ~/research/cron.log 2>&1

# Deactivate virtual environment
deactivate

# Log completion
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Research scan complete" >> ~/research/cron.log
echo "========================================" >> ~/research/cron.log
