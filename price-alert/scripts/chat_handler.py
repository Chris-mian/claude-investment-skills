#!/usr/bin/env python3
"""
chat_handler.py — Natural-language Telegram chat for price alerts.

Polls Telegram for new messages, sends each to Anthropic Claude with
tool definitions, executes whatever tool Claude chooses (add/list/cancel
alert, or just chitchat), and replies to the user via Telegram.

Architecture:
    Telegram bot ← getUpdates → this script ← Anthropic API → tools
                                     │
                                     ↓
                              alerts.json (committed by Actions)

State:
    tg_state.json tracks last processed update_id so we don't replay
    messages on subsequent polls.

ENV required:
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID         # whitelist: only respond to this chat
    ANTHROPIC_API_KEY

Run:
    python chat_handler.py             # one-shot poll, process new msgs
    python chat_handler.py --dry-run   # don't actually call Telegram/API
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
    from anthropic import Anthropic
except ImportError:
    print("ERROR: pip install anthropic requests", file=sys.stderr)
    sys.exit(1)


# ─── Paths ────────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).resolve().parent
SKILL_DIR   = SCRIPT_DIR.parent
STATE_FILE  = SKILL_DIR / "tg_state.json"


# ─── .env loader (shared with check_alerts.py) ────────────────────────────
def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if value and not value.startswith("PASTE_"):
                os.environ.setdefault(key, value)


_load_dotenv(SKILL_DIR / ".env")


# ─── Tool schemas (what Claude can do) ────────────────────────────────────
TOOLS = [
    {
        "name": "add_alert",
        "description": (
            "Create a new price alert on a US-listed stock or ETF. "
            "The alert fires when the trigger condition becomes true. "
            "Use for any user message asking to be notified about a price "
            "level, percentage drop, or percentage rise."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Uppercase ticker symbol (e.g. GLW, NVDA, SPY)"},
                "condition": {
                    "type": "string",
                    "enum": ["below", "above", "drop", "rise"],
                    "description": "below/above for absolute price; drop/rise for % from current price"
                },
                "value": {"type": "number", "description": "Price ($) for below/above; percent number (10 = 10%) for drop/rise"},
                "note": {"type": "string", "description": "Optional one-line context shown in the trigger notification"}
            },
            "required": ["ticker", "condition", "value"]
        }
    },
    {
        "name": "list_alerts",
        "description": "Show all active alerts. Use when user asks 'what alerts do I have', '我的 alerts', 'show my watchlist'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["active", "all", "fired"], "default": "active"}
            }
        }
    },
    {
        "name": "cancel_alert",
        "description": "Cancel a single alert by ticker or id, or cancel all alerts. Use for 'cancel GLW alert', '取消 NVDA'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Ticker (e.g. 'GLW') or alert id, or 'ALL' to cancel everything"}
            },
            "required": ["target"]
        }
    }
]

SYSTEM_PROMPT = """You are a friendly price-alert assistant connected to a US user's investment Telegram bot.

You help the user manage stock price alerts. Capabilities:
- Add alerts (absolute price below/above, or % drop/rise from current)
- List active alerts
- Cancel alerts

Style:
- Reply in the same language the user wrote in (English or Chinese)
- Be concise — 1-3 sentences usually, no long explanations
- When user is ambiguous, pick the most likely interpretation and act, mentioning the assumption
- For price levels: assume USD unless said otherwise
- For "drop 10%" / "跌 10%": that's drop_pct relative to current price, anchored at moment of alert creation

Examples of mapping user intent to tool calls:
- "alert me when GLW hits $140" → add_alert(GLW, below, 140)
- "GLW 跌到 140 通知我" → add_alert(GLW, below, 140)
- "notify if NVDA drops 10%" → add_alert(NVDA, drop, 10)
- "list my alerts" → list_alerts(active)
- "cancel GLW" → cancel_alert(GLW)
- "remove all alerts" → cancel_alert(ALL)

For questions NOT about alerts (e.g. "what's NVDA price?", "should I buy AMD?"):
- Politely say you only handle alert management
- Suggest they ask the same question in Claude Code for full market analysis

Never invent tickers; if the user's ticker looks like a guess, ask for confirmation."""


# ─── State management ─────────────────────────────────────────────────────
def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"last_update_id": 0}
    with open(STATE_FILE) as f:
        return json.load(f)


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ─── Telegram I/O ─────────────────────────────────────────────────────────
def tg_get_updates(token: str, offset: int) -> list:
    r = requests.get(
        f"https://api.telegram.org/bot{token}/getUpdates",
        params={"offset": offset, "timeout": 0},
        timeout=15,
    )
    r.raise_for_status()
    return r.json().get("result", [])


def tg_send(token: str, chat_id: str, text: str, dry: bool = False) -> None:
    if dry:
        print(f"[DRY] would send to {chat_id}: {text}")
        return
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True},
        timeout=10,
    )


# ─── Tool execution (calls existing CLI scripts) ──────────────────────────
def run_script(args: list[str]) -> tuple[bool, str]:
    """Returns (ok, output)."""
    try:
        result = subprocess.run(
            [sys.executable, *args],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=SKILL_DIR,
        )
        out = (result.stdout + "\n" + result.stderr).strip()
        return result.returncode == 0, out
    except Exception as e:
        return False, f"ERROR: {e}"


def execute_tool(name: str, args: dict) -> str:
    """Run the right CLI script and return a Telegram-friendly summary."""
    scripts = SCRIPT_DIR

    if name == "add_alert":
        ticker = args["ticker"].upper()
        cond = args["condition"]
        val = args["value"]
        note = args.get("note", "Set via Telegram chat")
        ok, out = run_script([
            str(scripts / "add_alert.py"),
            ticker, cond, str(val),
            "--note", note
        ])
        if not ok:
            return f"❌ Failed to add alert:\n```\n{out[:500]}\n```"
        # Pull the "Alert added" line
        for line in out.splitlines():
            if "Alert added:" in line or "Trigger:" in line:
                return f"✅ Alert added: {ticker} {cond} {val}\n_{note}_"
        return f"✅ {ticker} {cond} {val} alert added."

    elif name == "list_alerts":
        scope = args.get("scope", "active")
        flag = f"--{scope}" if scope != "all" else ""
        ok, out = run_script([str(scripts / "list_alerts.py"), flag] if flag else [str(scripts / "list_alerts.py")])
        if not ok:
            return f"❌ list_alerts failed:\n```\n{out[:500]}\n```"
        # Keep first 20 lines, truncate the rest
        lines = out.splitlines()[:25]
        return "📋 *Your alerts:*\n```\n" + "\n".join(lines) + "\n```"

    elif name == "cancel_alert":
        target = args["target"]
        flag = "--all" if target.upper() == "ALL" else target
        ok, out = run_script([
            str(scripts / "cancel_alert.py"),
            *(["--all"] if target.upper() == "ALL" else [target])
        ])
        if not ok:
            return f"❌ Cancel failed:\n```\n{out[:500]}\n```"
        return f"✅ Cancelled: {target}\n```\n{out[:400]}\n```"

    return f"❌ Unknown tool: {name}"


# ─── Main message handler ─────────────────────────────────────────────────
def handle_message(message: dict, anthropic_client: Anthropic, tg_token: str, allowed_chat_id: str, dry: bool) -> None:
    chat_id = str(message.get("chat", {}).get("id", ""))
    text = message.get("text", "").strip()
    if not text:
        return

    # Security: whitelist only the configured chat
    if chat_id != allowed_chat_id:
        print(f"  ✗ Ignoring message from non-whitelisted chat_id={chat_id}")
        return

    print(f"  📥 [{chat_id}] {text[:80]}")

    # Send to Claude
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        messages=[{"role": "user", "content": text}],
    )

    # Process response — may have text + tool_use blocks
    reply_chunks = []

    if response.stop_reason == "tool_use":
        # Loop: execute tool, send result back, get final reply
        tool_results = []
        for block in response.content:
            if block.type == "text":
                reply_chunks.append(block.text)
            elif block.type == "tool_use":
                print(f"  🔧 Tool: {block.name}({block.input})")
                tool_output = execute_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": tool_output,
                })

        # Send tool results back for final natural-language summary
        if tool_results:
            follow_up = anthropic_client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=512,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=[
                    {"role": "user", "content": text},
                    {"role": "assistant", "content": response.content},
                    {"role": "user", "content": tool_results},
                ],
            )
            for block in follow_up.content:
                if block.type == "text":
                    reply_chunks.append(block.text)
    else:
        # No tool — direct text reply
        for block in response.content:
            if block.type == "text":
                reply_chunks.append(block.text)

    reply_text = "\n\n".join(c for c in reply_chunks if c).strip() or "✓"
    print(f"  📤 Reply: {reply_text[:80]}")
    tg_send(tg_token, chat_id, reply_text, dry=dry)


# ─── Main ─────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    allowed_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    ant_key = os.environ.get("ANTHROPIC_API_KEY")

    if not (tg_token and allowed_chat_id and ant_key):
        print("ERROR: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ANTHROPIC_API_KEY all required", file=sys.stderr)
        return 1

    client = Anthropic()
    state = load_state()
    offset = state["last_update_id"] + 1

    print(f"Polling Telegram (offset {offset}) at {datetime.now(timezone.utc).isoformat()}")
    try:
        updates = tg_get_updates(tg_token, offset)
    except Exception as e:
        print(f"ERROR polling Telegram: {e}", file=sys.stderr)
        return 2

    print(f"  {len(updates)} new update(s)")
    max_seen = state["last_update_id"]
    for update in updates:
        max_seen = max(max_seen, update.get("update_id", 0))
        message = update.get("message") or update.get("edited_message")
        if not message:
            continue
        try:
            handle_message(message, client, tg_token, allowed_chat_id, dry=args.dry_run)
        except Exception as e:
            print(f"  ERROR handling message: {e}", file=sys.stderr)
            # Send a friendly error reply
            chat_id = str(message.get("chat", {}).get("id", ""))
            if chat_id == allowed_chat_id:
                tg_send(tg_token, chat_id, f"⚠️ Error processing your message:\n`{str(e)[:200]}`", dry=args.dry_run)

    if max_seen > state["last_update_id"]:
        state["last_update_id"] = max_seen
        save_state(state)
        print(f"  Updated last_update_id to {max_seen}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
