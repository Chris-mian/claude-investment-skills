# Webhook Setup — Real-time Telegram Bot via Cloudflare Workers

> Upgrade from the polling-based `chat_handler.py` (2-15 min latency) to a webhook (< 1 sec latency). Completely free for personal use.

[中文版 / Chinese version](./SETUP-WEBHOOK-zh.md)

---

## Why webhook?

The GitHub Actions polling architecture in `telegram-chat.yml` checks Telegram every 2-5 minutes (sometimes 15 min when GitHub is busy). That's fine for casual use but feels sluggish if you're actively chatting with the bot.

A **Cloudflare Worker webhook** receives Telegram updates **instantly** via HTTPS POST, processes them in 1-3 seconds, and replies — same model, same alert state, just much faster.

**Cost**: Cloudflare Workers free tier = 100,000 requests/day. Personal use ≈ 50-500/day. Free for years.

---

## Prerequisites

- Working `price-alert` skill (you've completed [SETUP.md](./SETUP.md))
- Node.js installed locally (`brew install node` on macOS)
- A Cloudflare account (free, signup at [cloudflare.com](https://cloudflare.com))
- A GitHub fine-grained Personal Access Token with `Contents: Read and write` scoped to your `claude-investment-skills` repo

---

## Part 1 — Local install (5 min)

```bash
# 1. Install wrangler globally
npm install -g wrangler

# 2. Verify
wrangler --version           # should print 4.x

# 3. Authenticate (opens browser for OAuth)
wrangler login

# 4. cd into the webhook folder
cd ~/.claude/skills/price-alert/webhook

# 5. Install local deps (for type checking; not bundled into worker)
npm install
```

If `npm install -g wrangler` fails with permission errors, prefix with `sudo` or use Homebrew: `brew install cloudflare-wrangler`.

---

## Part 2 — Get a GitHub Personal Access Token (5 min)

The worker needs to write to `alerts.json` in your repo, so it needs a token.

1. Go to https://github.com/settings/personal-access-tokens/new
2. Fill in:
   - **Token name**: `price-alert-webhook`
   - **Expiration**: 90 days (or longer if you don't want to rotate)
   - **Repository access**: **Only select repositories** → pick `claude-investment-skills`
   - **Permissions** → **Repository permissions** → find **Contents** → set to **Read and write**

   ⚠️ **The most common mistake here is leaving Contents at "Read-only"**. Read-only lets the worker `GET` alerts.json (which would work even with no token, since the repo is public) but every `PUT` (commit) returns `403 Resource not accessible by personal access token`. Double-check this dropdown shows **Read and write** before clicking Generate.

3. Click **Generate token**
4. **Copy the `github_pat_...` token immediately** — it's shown only once.

⚠️ Treat this token like a password. Don't paste it in chats / screenshots.

---

## Part 3 — Set worker secrets (3 min)

Each `wrangler secret put NAME` opens a prompt; paste the value, hit Enter.

```bash
cd ~/.claude/skills/price-alert/webhook

# Telegram bot token (same one already in your .env)
wrangler secret put TELEGRAM_BOT_TOKEN
# → paste your bot token, Enter

# Telegram chat_id (whitelist — only you can talk to the bot)
wrangler secret put TELEGRAM_CHAT_ID
# → paste your chat_id, Enter

# Anthropic API key (same one already in your .env)
wrangler secret put ANTHROPIC_API_KEY
# → paste sk-ant-api03-..., Enter

# GitHub PAT from Part 2
wrangler secret put GITHUB_TOKEN
# → paste github_pat_..., Enter

# GitHub repo name (NOT a secret — could be in wrangler.toml, but easier as a var here)
wrangler secret put GITHUB_REPO
# → paste "ssurmic/claude-investment-skills" (your fork), Enter
```

Verify:

```bash
wrangler secret list
# Should show 5 secrets
```

Note: the values never appear in your terminal output; wrangler hides them.

---

## Part 4 — Deploy the worker (2-3 min on first deploy)

```bash
cd ~/.claude/skills/price-alert/webhook
wrangler deploy
```

### First-time only: pick your workers.dev subdomain

If this is your first Cloudflare Worker ever, you'll see:

```
✔ Would you like to register a workers.dev subdomain now? … yes
✔ What would you like your workers.dev subdomain to be? …
```

This subdomain is **one-time per Cloudflare account** — it becomes your namespace for ALL future workers (e.g. `my-other-bot.<subdomain>.workers.dev`).

**Tips for picking**:
- Try your GitHub username first (most common pattern). E.g. `ssurmic`.
- Constraints: 3-63 chars, letters/numbers/hyphens only, NOT starting/ending with hyphen, **globally unique** across all Cloudflare Worker users.
- Don't type single letters like `y` or `n` — they're either taken or rejected as invalid.
- Common picks like `john`, `bot`, `worker` are all taken. Use something distinctive.
- Once chosen, the subdomain is **permanent** for your account (you can edit it in the CF dashboard, but it changes ALL your workers' URLs).

After successful registration:

```
✔ Creating a workers.dev subdomain for your account at https://<sub>.workers.dev. Ok to proceed? … yes

Success! It may take a few minutes for DNS records to update.
```

⚠️ **The DNS propagation note matters**. Sometimes the very first deploy succeeds but Telegram can't reach the URL for 1-2 minutes (SSL handshake fails). If `getWebhookInfo` shows `"last_error_message": "SSL error..."`, wait 2 min and Telegram will auto-retry — pending messages are queued.

### Subsequent deploys

After the first deploy, future runs of `wrangler deploy` skip all the subdomain stuff and finish in ~10 sec.

### Final output

```
Deployed price-alert-webhook triggers (3-5 sec on subsequent deploys)
  https://price-alert-webhook.<your-subdomain>.workers.dev
Current Version ID: ...
```

**Copy that URL** — that's your webhook endpoint.

### Benign warnings you may see

```
▲ [WARNING] Because 'workers_dev' is not in your Wrangler file...
▲ [WARNING] Because your 'workers.dev' route is enabled and 'preview_urls' is not in your Wrangler file...
```

These are harmless on first deploy. The `wrangler.toml` in this repo now sets both explicitly (`workers_dev = true`, `preview_urls = false`) to suppress them. If you copied this repo's `wrangler.toml`, you won't see them.

---

## Part 5 — Point Telegram at the webhook (1 min)

Tell Telegram to POST updates to your worker. Replace `<TOKEN>` and `<WORKER_URL>`:

```bash
curl -F "url=https://<WORKER_URL>.workers.dev" \
     "https://api.telegram.org/bot<TOKEN>/setWebhook"
```

Expected response:

```json
{"ok":true,"result":true,"description":"Webhook was set"}
```

**Verify it's set**:

```bash
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

Should return your worker URL in `url` field.

---

## Part 6 — Disable the polling workflow (optional)

Now that webhook is live, the polling `telegram-chat.yml` is redundant — it'll just see no updates (Telegram delivers them all to the webhook instead).

Two options:

**Option A — Disable the polling workflow (recommended)**:
```bash
gh workflow disable telegram-chat.yml --repo <YOUR_USERNAME>/claude-investment-skills
```

**Option B — Keep it as backup** (in case webhook goes down): the polling workflow will silently no-op since Telegram queues nothing.

`price-alerts.yml` (the actual price scanner) stays running — it has nothing to do with chat.

---

## Part 7 — Test

Send your bot a message in Telegram:

```
hello, test webhook latency
```

Expected: bot replies within **1-3 seconds** (no longer 2-15 minutes).

If you don't get a reply within 5 seconds, jump to [Troubleshooting](#troubleshooting) below.

---

## Watching live logs

`wrangler tail` streams every request to your worker in real time:

```bash
cd ~/.claude/skills/price-alert/webhook
wrangler tail
```

Then send a Telegram message — you'll see the worker's `console.log` output instantly. Very useful for debugging.

---

## Troubleshooting

### Bot doesn't reply

1. **Verify webhook is set**:
   ```bash
   curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
   ```
   `url` should point to your worker. If empty, redo Part 5.

2. **Check worker logs**:
   ```bash
   wrangler tail
   ```
   Send a message. If you see no log line, Telegram isn't reaching your worker — wrong URL.

3. **Check secrets are set**:
   ```bash
   wrangler secret list
   ```
   Should show 5 secrets. If missing, redo Part 3.

### Bot replies with `⚠️ Error: ...`

The error message tells you exactly which API failed:
- `Anthropic API error: 401` → ANTHROPIC_API_KEY wrong; redo Part 3 for that secret
- `GitHub fetch failed: 401` → GITHUB_TOKEN wrong or no Contents:write; redo Part 2 + Part 3 for that secret
- `GitHub fetch failed: 404` → GITHUB_REPO wrong; should be `<owner>/<repo>` exactly
- `GitHub commit failed: 403 Resource not accessible by personal access token` → **PAT scope wrong**. The `GET` succeeded (public repo doesn't need auth) but `PUT` failed because the PAT lacks **Contents: Write**. Fix: open https://github.com/settings/personal-access-tokens → click `price-alert-webhook` → Repository permissions → Contents → set to **Read and write** → Update. (Common pitfall: easy to accidentally leave it at "Read-only" — Read-only lets GET work but blocks all commits.)
- `btoa() can only operate on characters in the Latin1 (ISO/IEC 8859-1) range` → outdated worker code. Pull the latest `worker.ts` from this repo (the current version uses `TextEncoder`/`TextDecoder` to round-trip non-ASCII chars like Chinese notes) and redeploy with `wrangler deploy`.
- `Anthropic API error: 400 ... credit balance` → out of Anthropic credits; top up at console.anthropic.com

### Worker logs show "chat_id mismatch"

Your `TELEGRAM_CHAT_ID` secret doesn't match the chat. Get the right one from `https://api.telegram.org/bot<TOKEN>/getUpdates` and redo Part 3.

### Worker is slow (5+ sec response)

- Cold start? CF Workers occasionally cold-start, adding 1-2 sec. After first request, subsequent requests are fast.
- Anthropic API slow? Sometimes Claude API has 5-10 sec response times under load. Not much we can do.

### How to redeploy after code changes

```bash
cd ~/.claude/skills/price-alert/webhook
wrangler deploy
```

That's it — `wrangler deploy` does a full rebuild + push in ~10 seconds.

---

## Architecture comparison

```
BEFORE (polling):
  Telegram → buffered → GH Actions cron (every 2-5 min) → process → reply
  Latency: 2-15 minutes.

AFTER (webhook):
  Telegram → POST to CF Worker (instant) → process → reply
  Latency: 1-3 seconds.
```

Worker code path on each message:
1. Telegram POSTs update JSON (~50ms)
2. Worker parses + calls Anthropic API (~1-2 sec)
3. Worker executes tool (fetches alerts.json from GitHub, edits, commits) (~500ms)
4. Worker calls Anthropic again for final reply text (~500ms)
5. Worker sends Telegram reply (~100ms)

Total: ~2 sec on average. Worst case 5 sec under Anthropic load.

---

## Cost reality check

| Component | Cost | Notes |
|---|---|---|
| Cloudflare Workers | **$0** | Free tier = 100k req/day; you'll use <1k/day |
| Anthropic API | $1-4/mo | Same as polling — same model, same usage pattern |
| GitHub API | $0 | Authenticated rate limit = 5000 req/hour, way more than needed |
| Telegram Bot API | $0 | Always free |
| **Total** | **$1-4/mo** | Identical to polling-based setup |

The webhook is purely an architecture upgrade. Zero new costs.

---

## Reverting to polling

If you want to go back:

```bash
# 1. Tell Telegram to stop sending to webhook
curl "https://api.telegram.org/bot<TOKEN>/deleteWebhook"

# 2. Re-enable the polling workflow
gh workflow enable telegram-chat.yml --repo <YOUR_USERNAME>/claude-investment-skills

# 3. Optional: delete the worker
cd ~/.claude/skills/price-alert/webhook
wrangler delete
```

The worker has no shared state — deleting it is safe and reversible (just redeploy if you change your mind).
