/**
 * price-alert webhook — Cloudflare Worker
 *
 * Receives Telegram bot updates via HTTPS POST, parses the user's natural-
 * language message with Anthropic Claude (Sonnet 4.6), executes the
 * appropriate alert-management action by editing alerts.json via the
 * GitHub Contents API, and replies via Telegram sendMessage.
 *
 * End-to-end latency: typically 1-3 seconds (vs 2-15 minutes for the
 * cron-polling chat_handler.py alternative).
 *
 * Required env vars (set via `wrangler secret put`):
 *   TELEGRAM_BOT_TOKEN     — from @BotFather
 *   TELEGRAM_CHAT_ID       — whitelist; only this chat is allowed to talk
 *   ANTHROPIC_API_KEY      — from console.anthropic.com
 *   GITHUB_TOKEN           — fine-grained PAT, Contents:write on the repo
 *   GITHUB_REPO            — "<owner>/<repo>", e.g. "ssurmic/claude-investment-skills"
 */

export interface Env {
  TELEGRAM_BOT_TOKEN: string;
  TELEGRAM_CHAT_ID: string;
  ANTHROPIC_API_KEY: string;
  GITHUB_TOKEN: string;
  GITHUB_REPO: string;
}

// ─── Tool definitions (mirror of chat_handler.py) ──────────────────────────
const TOOLS = [
  {
    name: "add_alert",
    description:
      "Create a new price alert on a US-listed stock or ETF. The alert fires when the trigger condition becomes true. Use for any user message asking to be notified about a price level, percentage move, or moving-average cross.",
    input_schema: {
      type: "object",
      properties: {
        ticker: { type: "string", description: "Uppercase ticker symbol (e.g. GLW, NVDA, SPY)" },
        condition: {
          type: "string",
          enum: ["below", "above", "drop", "rise", "drop_intraday", "rise_intraday", "below_ma_50", "above_ma_50", "below_ma_200", "above_ma_200"],
          description: "below/above = absolute USD price. drop/rise = % from current price (anchored at creation). drop_intraday/rise_intraday = % move within single trading day vs prev close (re-anchored daily, incl. pre/after-hours). below_ma_*/above_ma_* = price vs moving average. Use MA ops for 'breaks 50DMA' / '跌破 200DMA'.",
        },
        value: { type: "number", description: "Price ($) for below/above; percent number (10 = 10%) for drop/rise/drop_intraday/rise_intraday; pass 0 for MA conditions." },
        note: { type: "string", description: "Optional one-line context shown in the trigger notification" },
      },
      required: ["ticker", "condition", "value"],
    },
  },
  {
    name: "list_alerts",
    description: "Show all active alerts. Use when user asks 'what alerts do I have', '我的 alerts', 'show my watchlist'.",
    input_schema: {
      type: "object",
      properties: {
        scope: { type: "string", enum: ["active", "all", "fired"] },
      },
    },
  },
  {
    name: "cancel_alert",
    description: "Cancel an alert by ticker or id, or cancel all alerts. Use for 'cancel GLW alert', '取消 NVDA'.",
    input_schema: {
      type: "object",
      properties: {
        target: { type: "string", description: "Ticker (e.g. 'GLW'), alert id, or 'ALL' to cancel everything" },
      },
      required: ["target"],
    },
  },
];

const SYSTEM_PROMPT = `You are a friendly price-alert assistant on a personal Telegram bot.

You help the user manage stock price alerts:
- Add alerts (absolute price, % from current, single-day % move, or moving-average cross)
- List active alerts
- Cancel alerts

Reply in the same language the user wrote in (English or Chinese). Be concise — 1-3 sentences. Use emoji sparingly. For ambiguous input, pick the most likely interpretation, act, and mention the assumption.

Mapping examples:
- "alert me when GLW hits $140" → add_alert(GLW, below, 140)
- "GLW 跌到 140 通知我" → add_alert(GLW, below, 140)
- "我想在 NVDA $1000 加仓" → add_alert(NVDA, below, 1000, note="加仓 tier 1")
- "AMD 单日跌 5%" → add_alert(AMD, drop_intraday, 5)
- "VST 跌破 50DMA" → add_alert(VST, below_ma_50, 0)
- "NVDA 突破 200DMA" → add_alert(NVDA, above_ma_200, 0)
- "list my alerts" → list_alerts(active)
- "cancel GLW" → cancel_alert(GLW)

Compound requests (X OR Y, 或者, and also): decompose into multiple add_alert calls in the same turn. Each is a separate alert; any one firing triggers a notification. Mention how many alerts you created in the reply.

After-hours: ALL conditions check the latest quote, including pre-market and after-hours. drop_intraday compares to the previous regular-session close. No special flag needed.

For questions NOT about alerts ("what's NVDA price?", "should I buy AMD?"): politely say you only manage alerts and suggest they ask Claude Code for analysis.`;

// ─── Helpers ──────────────────────────────────────────────────────────────
function maskedId(): string {
  return Math.random().toString(36).slice(2, 8);
}

function todayDate(): string {
  return new Date().toISOString().split("T")[0];
}

// Yahoo Finance chart endpoint — public, no API key.
async function getCurrentPrice(ticker: string): Promise<number | null> {
  try {
    const r = await fetch(
      `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}?interval=1m&range=1d`,
      { headers: { "User-Agent": "Mozilla/5.0" } },
    );
    if (!r.ok) return null;
    const json = (await r.json()) as any;
    return json?.chart?.result?.[0]?.meta?.regularMarketPrice ?? null;
  } catch {
    return null;
  }
}

// ─── GitHub Contents API ──────────────────────────────────────────────────
const ALERTS_PATH = "price-alert/alerts.json";

// btoa/atob only handle Latin1. alerts.json may contain Chinese in `note` —
// round-trip through TextEncoder/TextDecoder so non-ASCII survives.
function base64EncodeUtf8(str: string): string {
  const bytes = new TextEncoder().encode(str);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

function base64DecodeUtf8(b64: string): string {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new TextDecoder("utf-8").decode(bytes);
}

async function fetchAlerts(env: Env): Promise<{ data: any; sha: string }> {
  const r = await fetch(
    `https://api.github.com/repos/${env.GITHUB_REPO}/contents/${ALERTS_PATH}`,
    {
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        "User-Agent": "price-alert-webhook/1.0",
        Accept: "application/vnd.github+json",
      },
    },
  );
  if (!r.ok) throw new Error(`GitHub fetch failed: ${r.status} ${await r.text()}`);
  const meta = (await r.json()) as any;
  const content = base64DecodeUtf8(meta.content.replace(/\n/g, ""));
  return { data: JSON.parse(content), sha: meta.sha };
}

async function commitAlerts(env: Env, alertsObj: any, sha: string, message: string): Promise<void> {
  const content = base64EncodeUtf8(JSON.stringify(alertsObj, null, 2) + "\n");
  const r = await fetch(
    `https://api.github.com/repos/${env.GITHUB_REPO}/contents/${ALERTS_PATH}`,
    {
      method: "PUT",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        "User-Agent": "price-alert-webhook/1.0",
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ message, content, sha, branch: "main" }),
    },
  );
  if (!r.ok) throw new Error(`GitHub commit failed: ${r.status} ${await r.text()}`);
}

// ─── Build a condition object from Claude's tool input ────────────────────
async function buildCondition(op: string, value: number, ticker: string): Promise<any> {
  if (op === "below") return { op: "below", threshold: value };
  if (op === "above") return { op: "above", threshold: value };
  if (op === "drop" || op === "rise") {
    const price = await getCurrentPrice(ticker);
    if (price == null) throw new Error(`Could not fetch current price for ${ticker}`);
    return op === "drop"
      ? { op: "drop_pct", pct: value, anchor_price: price }
      : { op: "rise_pct", pct: value, anchor_price: price };
  }
  if (op === "drop_intraday") return { op: "drop_intraday", pct: value };
  if (op === "rise_intraday") return { op: "rise_intraday", pct: value };
  if (["below_ma_50", "above_ma_50", "below_ma_200", "above_ma_200"].includes(op)) {
    return { op };
  }
  throw new Error(`Unknown op: ${op}`);
}

function fmtCondition(c: any): string {
  const op = c.op;
  if (op === "below") return `≤ $${c.threshold.toFixed(2)}`;
  if (op === "above") return `≥ $${c.threshold.toFixed(2)}`;
  if (op === "drop_pct") {
    const t = c.anchor_price * (1 - c.pct / 100);
    return `-${c.pct}% from $${c.anchor_price.toFixed(2)} (≤ $${t.toFixed(2)})`;
  }
  if (op === "rise_pct") {
    const t = c.anchor_price * (1 + c.pct / 100);
    return `+${c.pct}% from $${c.anchor_price.toFixed(2)} (≥ $${t.toFixed(2)})`;
  }
  if (op === "drop_intraday") return `single-day -${c.pct}% vs prev close`;
  if (op === "rise_intraday") return `single-day +${c.pct}% vs prev close`;
  if (op === "below_ma_50") return "≤ 50DMA";
  if (op === "above_ma_50") return "≥ 50DMA";
  if (op === "below_ma_200") return "≤ 200DMA";
  if (op === "above_ma_200") return "≥ 200DMA";
  return JSON.stringify(c);
}

// ─── Tool execution ───────────────────────────────────────────────────────
async function executeTool(env: Env, name: string, input: any): Promise<string> {
  if (name === "add_alert") {
    const { data, sha } = await fetchAlerts(env);
    const ticker = input.ticker.toUpperCase();
    const condition = await buildCondition(input.condition, input.value, ticker);
    const id = `${ticker.toLowerCase()}-${input.condition}-${maskedId()}`;
    const alert = {
      id,
      ticker,
      condition,
      note: input.note || "Set via Telegram bot",
      created: todayDate(),
      active: true,
      fired: false,
    };
    data.alerts = data.alerts || [];
    data.alerts.push(alert);
    await commitAlerts(env, data, sha, `webhook: add_alert ${id}`);
    return `✅ ${ticker} ${fmtCondition(condition)}${input.note ? `\n_${input.note}_` : ""}`;
  }

  if (name === "list_alerts") {
    const { data } = await fetchAlerts(env);
    const scope = input.scope || "active";
    let alerts = data.alerts || [];
    if (scope === "active") alerts = alerts.filter((a: any) => a.active && !a.fired);
    else if (scope === "fired") alerts = alerts.filter((a: any) => a.fired);
    if (alerts.length === 0) return "📋 No active alerts.";
    const lines = alerts.slice(0, 20).map(
      (a: any) => `• \`${a.ticker}\` ${fmtCondition(a.condition)}${a.note ? ` _${a.note}_` : ""}`,
    );
    return `📋 *Your alerts (${alerts.length}):*\n${lines.join("\n")}`;
  }

  if (name === "cancel_alert") {
    const { data, sha } = await fetchAlerts(env);
    const target = input.target;
    const before = (data.alerts || []).filter((a: any) => a.active && !a.fired).length;
    let n = 0;
    for (const a of data.alerts || []) {
      const match = target.toUpperCase() === "ALL" ||
        a.id === target ||
        a.ticker?.toUpperCase() === target.toUpperCase();
      if (match && a.active) {
        a.active = false;
        n++;
      }
    }
    if (n === 0) return `🤷 Nothing matched \`${target}\`.`;
    await commitAlerts(env, data, sha, `webhook: cancel_alert ${target} (${n} cancelled)`);
    return `✅ Cancelled ${n} alert${n > 1 ? "s" : ""} (${before - n} still active).`;
  }

  return `❌ Unknown tool: ${name}`;
}

// ─── Claude API ───────────────────────────────────────────────────────────
async function callClaude(env: Env, userText: string, conversation?: any[]): Promise<any> {
  const messages = conversation || [{ role: "user", content: userText }];
  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "x-api-key": env.ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "claude-sonnet-4-6",
      max_tokens: 1024,
      system: SYSTEM_PROMPT,
      tools: TOOLS,
      messages,
    }),
  });
  if (!r.ok) throw new Error(`Anthropic API error: ${r.status} ${await r.text()}`);
  return r.json();
}

// ─── Telegram ─────────────────────────────────────────────────────────────
async function sendTelegram(env: Env, chatId: string, text: string): Promise<void> {
  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: chatId,
      text,
      parse_mode: "Markdown",
      disable_web_page_preview: true,
    }),
  });
}

// ─── Main handler ─────────────────────────────────────────────────────────
async function handleMessage(env: Env, message: any): Promise<void> {
  const chatId = String(message.chat?.id ?? "");
  const text = message.text?.trim();
  if (!text) return;

  // Whitelist check
  if (chatId !== env.TELEGRAM_CHAT_ID) {
    console.log(`Ignoring message from non-whitelisted chat ${chatId}`);
    return;
  }

  try {
    const response = await callClaude(env, text);
    const replyChunks: string[] = [];

    if (response.stop_reason === "tool_use") {
      const toolResults = [];
      for (const block of response.content) {
        if (block.type === "text") replyChunks.push(block.text);
        if (block.type === "tool_use") {
          const out = await executeTool(env, block.name, block.input);
          toolResults.push({ type: "tool_result", tool_use_id: block.id, content: out });
        }
      }
      if (toolResults.length > 0) {
        const followUp = await callClaude(env, text, [
          { role: "user", content: text },
          { role: "assistant", content: response.content },
          { role: "user", content: toolResults },
        ]);
        for (const block of followUp.content) {
          if (block.type === "text") replyChunks.push(block.text);
        }
      }
    } else {
      for (const block of response.content) {
        if (block.type === "text") replyChunks.push(block.text);
      }
    }

    const reply = replyChunks.filter(Boolean).join("\n\n").trim() || "✓";
    await sendTelegram(env, chatId, reply);
  } catch (e: any) {
    console.error("Error handling message:", e);
    await sendTelegram(env, chatId, `⚠️ Error: ${String(e.message || e).slice(0, 200)}`);
  }
}

// ─── Worker entry point ───────────────────────────────────────────────────
export default {
  async fetch(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("price-alert webhook — POST only", { status: 200 });
    }

    let update: any;
    try {
      update = await request.json();
    } catch {
      return new Response("invalid json", { status: 400 });
    }

    const message = update.message || update.edited_message;
    if (message) {
      // Process async; respond to Telegram immediately so it doesn't retry
      _ctx.waitUntil(handleMessage(env, message));
    }

    return new Response("ok", { status: 200 });
  },
};
