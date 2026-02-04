#!/usr/bin/env python3
"""
Albatross Telegram Module - 2-Way Communication
Part of Phase 4 Core Build

Provides bidirectional communication with user via Telegram bot.
Required for Ralph-Lite orchestrator human-in-the-loop checkpoints.
"""

import os
import time
import logging
import requests
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get credentials from environment
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

# API endpoints
BASE_URL = "https://api.telegram.org/bot{token}"
SEND_MESSAGE_URL = BASE_URL + "/sendMessage"
GET_UPDATES_URL = BASE_URL + "/getUpdates"

# Track last message ID to avoid processing old messages
_last_update_id = 0

def _get_latest_update_id() -> int:
    """Get the latest update ID from Telegram to establish baseline."""
    global _last_update_id
    if not TELEGRAM_BOT_TOKEN:
        return 0
    
    try:
        url = GET_UPDATES_URL.format(token=TELEGRAM_BOT_TOKEN)
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get('ok') and data.get('result'):
            max_id = max((u.get('update_id', 0) for u in data['result']), default=0)
            _last_update_id = max_id
            logger.debug(f"Latest update ID: {_last_update_id}")
    except Exception as e:
        logger.warning(f"Could not get latest update ID: {e}")
    
    return _last_update_id

# Validate credentials on module load
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    logger.warning("Telegram credentials not configured!")
    logger.warning("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables")
else:
    # Initialize update ID on module load
    _get_latest_update_id()


def _make_request(url: str, data: dict = None, timeout: int = 10) -> dict:
    """Make HTTP request to Telegram API with retry logic."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if data:
                response = requests.post(url, json=data, timeout=timeout)
            else:
                response = requests.get(url, timeout=timeout)
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                raise
    
    return {}


def send_message(text: str, parse_mode: str = "HTML") -> bool:
    """
    Send a message to the configured Telegram chat.
    
    Args:
        text: Message text (HTML or Markdown formatted)
        parse_mode: "HTML", "Markdown", or None
    
    Returns:
        True if sent successfully, False otherwise
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("Telegram credentials not configured!")
        return False
    
    # Truncate if too long (Telegram limit is 4096)
    if len(text) > 4000:
        text = text[:3997] + "..."
    
    url = SEND_MESSAGE_URL.format(token=TELEGRAM_BOT_TOKEN)
    data = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': parse_mode
    }
    
    try:
        result = _make_request(url, data)
        if result.get('ok'):
            logger.info("Message sent successfully")
            return True
        else:
            logger.error(f"Telegram API error: {result.get('description')}")
            return False
    except Exception as e:
        logger.error(f"Failed to send message: {e}")
        return False


def send_alert(title: str, body: str, alert_type: str = "info") -> bool:
    """
    Send a formatted alert box.
    
    Args:
        title: Alert title with emoji (e.g., "🎯 STRONG BID")
        body: Alert body text
        alert_type: "info", "warning", "error", "success"
    """
    # Emoji and styling based on type
    styles = {
        'info': ('ℹ️', ''),
        'warning': ('⚠️', ''),
        'error': ('🚨', ''),
        'success': ('✅', '')
    }
    
    emoji, _ = styles.get(alert_type, ('ℹ️', ''))
    
    message = f"""{emoji} <b>{title}</b>
{'═' * 30}

{body}"""
    
    return send_message(message, parse_mode="HTML")


def parse_command(response: str) -> Dict[str, Any]:
    """
    Parse user response into structured command.
    
    Args:
        response: Raw user text
    
    Returns:
        {
            'action': 'CONTINUE' | 'STOP' | 'FIX' | 'ROLLBACK' | 
                      'APPROVE' | 'REJECT' | 'REVISE' | 'YES' | 'NO' | 'UNKNOWN',
            'parameter': str,
            'raw': str
        }
    """
    if not response:
        return {'action': 'UNKNOWN', 'parameter': '', 'raw': ''}
    
    raw = response.strip()
    lower = raw.lower()
    
    # CONTINUE patterns
    if lower in ['continue', 'cont', 'c', 'yes', 'y', 'go', 'proceed']:
        return {'action': 'CONTINUE', 'parameter': '', 'raw': raw}
    
    # STOP patterns
    if lower in ['stop', 'halt', 'cancel', 'abort', 'end', 'quit']:
        return {'action': 'STOP', 'parameter': '', 'raw': raw}
    
    # APPROVE patterns
    if lower in ['approve', 'approved', 'ok', 'good', 'accept']:
        return {'action': 'APPROVE', 'parameter': '', 'raw': raw}
    
    # REJECT patterns
    if lower in ['reject', 'rejected', 'no', 'n', 'bad', 'decline']:
        return {'action': 'REJECT', 'parameter': '', 'raw': raw}
    
    # FIX patterns
    if lower.startswith('fix:') or lower.startswith('fix '):
        parameter = raw[4:].strip() if lower.startswith('fix:') else raw[4:].strip()
        return {'action': 'FIX', 'parameter': parameter, 'raw': raw}
    
    # ROLLBACK patterns
    if lower.startswith('rollback'):
        # Extract number if present
        parts = lower.split()
        parameter = ''
        for part in parts[1:]:
            if part.isdigit():
                parameter = part
                break
        return {'action': 'ROLLBACK', 'parameter': parameter, 'raw': raw}
    
    # REVISE patterns
    if lower.startswith('revise:') or lower.startswith('revise '):
        parameter = raw[7:].strip() if lower.startswith('revise:') else raw[7:].strip()
        return {'action': 'REVISE', 'parameter': parameter, 'raw': raw}
    
    return {'action': 'UNKNOWN', 'parameter': '', 'raw': raw}


def request_user_input(prompt: str, timeout_minutes: int = 30) -> str:
    """
    Send prompt to user and BLOCK until response received.
    CRITICAL FUNCTION for Ralph-Lite orchestration.
    
    Only processes messages received AFTER this function is called.
    
    Args:
        prompt: Message to send (can be multi-line)
        timeout_minutes: Max time to wait (default 30)
    
    Returns:
        User's response text
    
    Raises:
        TimeoutError: If no response within timeout
    """
    global _last_update_id
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Telegram credentials not configured!")
    
    # Get baseline update ID BEFORE sending prompt
    # This ensures we only see messages sent AFTER the prompt
    _get_latest_update_id()
    baseline_update_id = _last_update_id
    logger.debug(f"Baseline update ID: {baseline_update_id}")
    
    # Send the prompt
    if not send_message(prompt):
        raise RuntimeError("Failed to send prompt message")
    
    logger.info(f"Waiting for user response (timeout: {timeout_minutes} min)")
    logger.info(f"Ignoring messages before update ID: {baseline_update_id}")
    
    # Record start time
    start_time = time.time()
    timeout_seconds = timeout_minutes * 60
    
    # Polling loop
    poll_interval = 5  # seconds
    
    while time.time() - start_time < timeout_seconds:
        try:
            # Get updates from Telegram (only NEW messages)
            url = GET_UPDATES_URL.format(token=TELEGRAM_BOT_TOKEN)
            if _last_update_id > 0:
                url += f"?offset={_last_update_id + 1}"
            
            response = requests.get(url, timeout=10)
            data = response.json()
            
            if not data.get('ok'):
                logger.warning(f"Telegram API error: {data.get('description')}")
                time.sleep(poll_interval)
                continue
            
            updates = data.get('result', [])
            
            for update in updates:
                update_id = update.get('update_id')
                
                # Skip old messages (before our baseline)
                if update_id <= baseline_update_id:
                    logger.debug(f"Skipping old message (ID: {update_id})")
                    continue
                
                # Update tracking
                _last_update_id = max(_last_update_id, update_id)
                
                # Check if this is a message
                message = update.get('message')
                if not message:
                    continue
                
                # Check if from correct chat
                chat_id = str(message.get('chat', {}).get('id'))
                if chat_id != str(TELEGRAM_CHAT_ID):
                    continue
                
                # Check if text message
                text = message.get('text')
                if not text:
                    continue
                
                # Got valid response
                logger.info(f"Received user response: {text[:50]}...")
                return text
            
        except Exception as e:
            logger.warning(f"Polling error: {e}")
        
        # Wait before next poll
        time.sleep(poll_interval)
    
    # Timeout reached
    raise TimeoutError(f"No response within {timeout_minutes} minutes")


def ask_yes_no(question: str, timeout_minutes: int = 30) -> bool:
    """
    Ask a yes/no question and return boolean response.
    
    Args:
        question: Question text
        timeout_minutes: Max wait time
    
    Returns:
        True for yes, False for no or timeout
    """
    full_prompt = f"""{question}

Reply with:
• YES / Y / yes / y
• NO / N / no / n"""
    
    try:
        response = request_user_input(full_prompt, timeout_minutes)
        parsed = parse_command(response)
        
        if parsed['action'] in ['YES', 'CONTINUE', 'APPROVE']:
            return True
        elif parsed['action'] in ['NO', 'STOP', 'REJECT']:
            return False
        else:
            # Default to False for unclear responses
            logger.warning(f"Unclear yes/no response: {response}")
            return False
            
    except TimeoutError:
        logger.warning("Yes/no question timed out, defaulting to NO")
        return False


def send_progress_update(phase: str, iteration: int, total: int,
                         message: str, cost: float = None) -> bool:
    """
    Send progress update during Ralph-Lite build.
    
    Args:
        phase: Current phase name
        iteration: Current iteration number
        total: Total expected iterations
        message: Progress description
        cost: Optional cost info
    """
    cost_str = f"${cost:.2f}" if cost is not None else "N/A"
    
    progress_msg = f"""🔨 <b>BUILD PROGRESS</b>
Phase: {phase} | Iteration {iteration}/{total}
Cost: {cost_str}

{message}"""
    
    return send_message(progress_msg)


def send_iteration_result(iteration: int, max_iter: int,
                         files_changed: list, test_results: str,
                         cost: float) -> str:
    """
    Send build progress after each iteration and wait for command.
    
    Args:
        iteration: Current iteration number
        max_iter: Maximum iterations
        files_changed: List of modified files
        test_results: Test summary string
        cost: Cost of this iteration
    
    Returns:
        User command: "CONTINUE", "STOP", "FIX: ...", or "ROLLBACK: N"
    """
    files_str = '\n'.join([f"• {f}" for f in files_changed[:10]])
    if len(files_changed) > 10:
        files_str += f"\n• ... and {len(files_changed) - 10} more"
    
    message = f"""🔨 <b>ITERATION {iteration}/{max_iter} COMPLETE</b>

<b>Files:</b>
{files_str}

<b>Tests:</b> {test_results}
<b>Cost this iteration:</b> ${cost:.2f}

🎮 <b>YOUR COMMAND:</b>
[CONTINUE] [FIX: issue] [STOP] [ROLLBACK: N]"""
    
    try:
        response = request_user_input(message, timeout_minutes=30)
        parsed = parse_command(response)
        
        # Return action and parameter combined for FIX and ROLLBACK
        if parsed['action'] == 'FIX' and parsed['parameter']:
            return f"FIX: {parsed['parameter']}"
        elif parsed['action'] == 'ROLLBACK' and parsed['parameter']:
            return f"ROLLBACK: {parsed['parameter']}"
        else:
            return parsed['action']
            
    except TimeoutError:
        logger.warning("Iteration checkpoint timed out, defaulting to STOP")
        return "STOP"


def send_plan_for_approval(plan_markdown: str, estimated_cost: float) -> str:
    """
    Send implementation plan and wait for approval decision.
    
    Args:
        plan_markdown: Full plan text (may be truncated if >4000 chars)
        estimated_cost: Estimated total cost
    
    Returns:
        Command: "APPROVE", "REJECT", or "REVISE: feedback"
    """
    # Truncate plan if too long
    max_plan_len = 3000  # Leave room for other text
    if len(plan_markdown) > max_plan_len:
        plan_display = plan_markdown[:max_plan_len] + "\n\n... (truncated)"
    else:
        plan_display = plan_markdown
    
    message = f"""📋 <b>PHASE 2 COMPLETE: Implementation Plan</b>

{plan_display}

<b>Estimated Cost:</b> ${estimated_cost:.2f}

🎮 <b>YOUR DECISION:</b>
[APPROVE] → Start building
[REVISE: feedback] → Fix plan
[REJECT] → Cancel build"""
    
    try:
        response = request_user_input(message, timeout_minutes=30)
        parsed = parse_command(response)
        
        if parsed['action'] == 'REVISE' and parsed['parameter']:
            return f"REVISE: {parsed['parameter']}"
        else:
            return parsed['action']
            
    except TimeoutError:
        logger.warning("Plan approval timed out, defaulting to REJECT")
        return "REJECT"


def send_interview_question(q_num: int, total: int, question: str) -> str:
    """
    Send single interview question and wait for answer.
    
    Args:
        q_num: Current question number
        total: Total questions
        question: Question text
    
    Returns:
        User's answer text
    """
    prompt = f"""📋 <b>Question {q_num}/{total}</b>

{question}

<i>Reply with your answer...</i>"""
    
    return request_user_input(prompt, timeout_minutes=30)


def send_build_complete(project_path: str, total_cost: float,
                       iterations: int, file_list: list) -> bool:
    """
    Notify build completion.
    
    Args:
        project_path: Path to FINAL/ directory
        total_cost: Total token cost
        iterations: Number of iterations completed
        file_list: List of files created
    """
    files_str = '\n'.join([f"• {f}" for f in file_list[:15]])
    if len(file_list) > 15:
        files_str += f"\n• ... and {len(file_list) - 15} more files"
    
    message = f"""✅ <b>BUILD COMPLETE</b>

<b>Location:</b> <code>{project_path}</code>
<b>Total Cost:</b> ${total_cost:.2f}
<b>Iterations:</b> {iterations}

<b>Files:</b>
{files_str}

📋 <b>NEXT STEPS:</b>
1. Review code in FINAL/ directory
2. Run tests: <code>cd FINAL && python -m pytest tests/</code>
3. Deploy when ready (manual)

[RALPH_DONE]"""
    
    return send_message(message)


def send_daily_briefing(system_status: dict, leads_summary: dict,
                       content_status: dict) -> bool:
    """
    Send daily morning briefing (cron job uses this).
    
    Args:
        system_status: Dict with system health info
        leads_summary: Dict with lead generation stats
        content_status: Dict with content status
    """
    date_str = datetime.now().strftime('%A, %B %d, %Y')
    
    # System status
    guardian = system_status.get('token_guardian', 'N/A')
    t490 = system_status.get('t490_status', 'unknown')
    vps = system_status.get('vps_status', 'unknown')
    sync = system_status.get('last_sync', 'unknown')
    
    # Leads
    new_leads = leads_summary.get('new_leads', 0)
    qualified = leads_summary.get('qualified', 0)
    needs_action = leads_summary.get('needs_action', 0)
    
    # Content
    monday = content_status.get('monday_roundup', 'pending')
    wednesday = content_status.get('wednesday_preview', 'pending')
    
    message = f"""═══════════════════════════════════════
🎯 <b>ALBATROSS DAILY BRIEFING</b>
{date_str}
═══════════════════════════════════════

📊 <b>SYSTEM HEALTH</b>
• Token Guardian: {guardian} {'✅' if '✅' in guardian else '⚠️'}
• T490: {t490} {'✅' if t490 == 'online' else '⚠️'}
• VPS: {vps} {'✅' if vps == 'online' else '⚠️'}
• Last sync: {sync} {'✅' if sync != 'unknown' else '⚠️'}

💰 <b>LEAD GENERATION</b>
• New leads: {new_leads}
• Qualified: {qualified}
• Needs action: {needs_action}

📝 <b>NGN CONTENT</b>
• Monday Roundup: {monday.upper()}
• Wednesday Preview: {wednesday.upper()}

═══════════════════════════════════════"""
    
    return send_message(message)


# Convenience aliases for backward compatibility
notify = send_message
alert = send_alert
ask = request_user_input
confirm = ask_yes_no


if __name__ == "__main__":
    # Simple test when run directly
    print("Testing Telegram module...")
    
    # Test send
    if send_message("<b>Test</b> from Albatross Telegram module"):
        print("✓ send_message works")
    else:
        print("✗ send_message failed")
    
    # Test parse_command
    test_cases = ["continue", "fix: error handling", "rollback 3", "yes"]
    for cmd in test_cases:
        parsed = parse_command(cmd)
        print(f"✓ parse_command('{cmd}') = {parsed['action']}")
    
    print("\nTo test request_user_input, run:")
    print("from src.utils.telegram import request_user_input")
    print("response = request_user_input('Test question', timeout_minutes=2)")
