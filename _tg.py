"""Shared Telegram fan-out helper for the public skills repo.

All firehose scripts use this so a single message reaches every configured
chat — the @DuckyduckyTradeBot DM *and* the duckyduckyChannel.

Environment variables
─────────────────────
  TELEGRAM_BOT_TOKEN          @DuckyduckyTradeBot token (also admin in channel)
  TELEGRAM_CHAT_ID            primary chat (the DM with the bot)
  TELEGRAM_CHAT_ID_CHANNEL    duckyduckyChannel id (-100... format)

If either chat env is empty it's silently skipped, so a single secret missing
never blocks the other route.  Markdown is the default; we retry plain text
on parse failure so messages always land.
"""
from __future__ import annotations

import os
import sys


def routes() -> list[tuple[str, str, str]]:
    """Return list of (label, token, chat_id) to send to.  Deduped."""
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for label, env in (("DM", "TELEGRAM_CHAT_ID"),
                       ("Channel", "TELEGRAM_CHAT_ID_CHANNEL")):
        chat = (os.environ.get(env) or "").strip()
        if token and chat and chat not in seen:
            seen.add(chat)
            out.append((label, token, chat))
    return out


def send(msg, test_mode: bool = False, parse_mode: str = "Markdown") -> bool:
    """Fan-out send.  Returns True iff at least one route succeeded."""
    msg = str(msg)
    rs = routes()

    if test_mode:
        names = ", ".join(f"{lbl}:{c}" for lbl, _, c in rs) or "<no-route>"
        print(f"─── TEST_MODE ({len(rs)} routes: {names}) ───\n{msg}\n─── end ───",
              file=sys.stderr)
        return True

    if not rs:
        print("[WARN] no Telegram routes configured (TELEGRAM_CHAT_ID and "
              "TELEGRAM_CHAT_ID_CHANNEL both empty)", file=sys.stderr)
        return False

    try:
        import requests
    except ImportError:
        print("[WARN] requests not installed", file=sys.stderr)
        return False

    any_ok = False
    for label, token, chat in rs:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat,
            "text": msg,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            r = requests.post(url, json=payload, timeout=20)
            if r.status_code == 200:
                any_ok = True
                continue
            if parse_mode:  # Markdown parse failures → retry plain text
                payload.pop("parse_mode", None)
                r2 = requests.post(url, json=payload, timeout=20)
                if r2.status_code == 200:
                    any_ok = True
                    continue
            print(f"[WARN] telegram {label} chat={chat} → "
                  f"{r.status_code} {r.text[:120]}", file=sys.stderr)
        except Exception as exc:
            print(f"[WARN] telegram {label} chat={chat}: {exc}", file=sys.stderr)
    return any_ok
