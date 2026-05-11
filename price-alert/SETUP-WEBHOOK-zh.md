# Webhook 设置 —— 用 Cloudflare Workers 实现实时 Telegram bot

> 从 polling 架构（`chat_handler.py`，延迟 2-15 分钟）升级到 webhook（延迟 < 1 秒）。个人用永久免费。

[English / 英文版](./SETUP-WEBHOOK.md)

---

## 为啥 webhook？

GitHub Actions polling 架构（`telegram-chat.yml`）每 2-5 分钟 poll Telegram 一次（GitHub 高峰时段可能 15 分钟）。日常用够，但**真的在聊** bot 时感觉慢。

**Cloudflare Worker webhook** 通过 HTTPS POST **即时**接收 Telegram 推送，1-3 秒内处理 + 回复 —— 模型同、alert 状态同，只是**快很多**。

**费用**: Cloudflare Workers 免费层 = 10 万请求/天。你日常用 ~50-500 条 ≈ 用了 1% 都不到。**用好几年都免费**。

---

## 前提

- 已完成 [SETUP.md](./SETUP-zh.md)（基础 price-alert 已经 work）
- 本地装了 Node.js（macOS: `brew install node`）
- Cloudflare 账号（免费，[cloudflare.com](https://cloudflare.com) 注册）
- GitHub fine-grained PAT，**Contents: Read and write** 权限，scope 到 `claude-investment-skills` repo

---

## Part 1 — 本地装 wrangler（5 分钟）

```bash
# 1. 全局装 wrangler
npm install -g wrangler

# 2. 验证
wrangler --version           # 应该是 4.x

# 3. 认证（开浏览器 OAuth）
wrangler login

# 4. cd 进 webhook 目录
cd ~/.claude/skills/price-alert/webhook

# 5. 装本地依赖（仅类型检查用，不打包进 worker）
npm install
```

如果 `npm install -g wrangler` 报权限错，用 `sudo` 或者 `brew install cloudflare-wrangler`。

---

## Part 2 — 拿 GitHub PAT（5 分钟）

Worker 需要写 `alerts.json` 回你的 repo，所以需要 token。

1. 打开 https://github.com/settings/personal-access-tokens/new
2. 填:
   - **Token name**: `price-alert-webhook`
   - **Expiration**: 90 天（或更长免轮换）
   - **Repository access**: **Only select repositories** → 选 `claude-investment-skills`
   - **Permissions** → **Repository permissions** → 找到 **Contents** → 设为 **Read and write**

   ⚠️ **最容易踩的坑：Contents 留在 "Read-only"**。Read-only 让 worker 能 `GET` alerts.json（其实 public repo 不要 token 也能 GET），但每次 `PUT`（提交）都会 `403 Resource not accessible by personal access token`。Generate 之前**再核对一遍这个下拉框确实是 "Read and write"**。

3. 点 **Generate token**
4. **立刻复制那个 `github_pat_...` token** —— 只显示一次

⚠️ 这个 token 当密码对待。不要发到聊天/截图里。

---

## Part 3 — 设 worker secrets（3 分钟）

每个 `wrangler secret put NAME` 会弹个 prompt；粘贴 value，回车。

```bash
cd ~/.claude/skills/price-alert/webhook

# Telegram bot token（跟 .env 里那个一样）
wrangler secret put TELEGRAM_BOT_TOKEN
# → 粘贴 bot token，回车

# Telegram chat_id（白名单 —— 只有你能跟 bot 说话）
wrangler secret put TELEGRAM_CHAT_ID
# → 粘贴 chat_id，回车

# Anthropic API key（跟 .env 里那个一样）
wrangler secret put ANTHROPIC_API_KEY
# → 粘贴 sk-ant-api03-...，回车

# GitHub PAT（Part 2 拿到的）
wrangler secret put GITHUB_TOKEN
# → 粘贴 github_pat_...，回车

# GitHub repo 名字
wrangler secret put GITHUB_REPO
# → 粘贴 "ssurmic/claude-investment-skills"（你的 fork），回车
```

验证:
```bash
wrangler secret list
# 应该显示 5 个 secrets
```

注意：value 不会出现在终端输出里，wrangler 全程隐藏。

---

## Part 4 — 部署 worker（首次 2-3 分钟）

```bash
cd ~/.claude/skills/price-alert/webhook
wrangler deploy
```

### 第一次部署：选 workers.dev subdomain

第一次跑 Cloudflare Worker 会问:

```
✔ Would you like to register a workers.dev subdomain now? … yes
✔ What would you like your workers.dev subdomain to be? …
```

这个 subdomain **每个 CF 账号一次性绑定** —— 之后所有 worker 都用这个 namespace（比如 `my-other-bot.<subdomain>.workers.dev`）。

**选 subdomain 的 tips**:
- 优先试你的 GitHub 用户名（最常见）。比如 `ssurmic`。
- 限制: 3-63 字符，字母/数字/连字符，**不能**以连字符开头/结尾，**全球唯一**。
- 别打单字母 `y` / `n` —— 要么被占要么报"invalid"。
- 像 `john` / `bot` / `worker` 这种热门词都被占了。选个特别点的。
- 选好之后**永久绑定**账号（CF dashboard 里能改，但改了所有 worker 的 URL 都会变）。

注册成功后:

```
✔ Creating a workers.dev subdomain for your account at https://<sub>.workers.dev. Ok to proceed? … yes

Success! It may take a few minutes for DNS records to update.
```

⚠️ **DNS 传播这个提示要注意**。有时第一次部署成功但 Telegram 1-2 分钟内还连不上 URL（SSL 握手失败）。如果 `getWebhookInfo` 显示 `"last_error_message": "SSL error..."`，等 2 分钟 Telegram 会自动重试 —— pending 的消息会排队等。

### 之后的部署

第一次部署后，下次跑 `wrangler deploy` 跳过 subdomain 那些，~10 秒完事。

### 最终输出

```
Deployed price-alert-webhook triggers (后续部署 3-5 秒)
  https://price-alert-webhook.<你的-subdomain>.workers.dev
Current Version ID: ...
```

**复制这个 URL** —— 你的 webhook 端点。

### 可能看到的无害警告

```
▲ [WARNING] Because 'workers_dev' is not in your Wrangler file...
▲ [WARNING] Because your 'workers.dev' route is enabled and 'preview_urls' is not in your Wrangler file...
```

第一次部署时无害。这个 repo 的 `wrangler.toml` 现在已经显式设置了 (`workers_dev = true`, `preview_urls = false`)，复制这个文件就不会再看到。

---

## Part 5 — 让 Telegram 指向 webhook（1 分钟）

告诉 Telegram POST 到你的 worker。替换 `<TOKEN>` 和 `<WORKER_URL>`:

```bash
curl -F "url=https://<WORKER_URL>.workers.dev" \
     "https://api.telegram.org/bot<TOKEN>/setWebhook"
```

期望回复:

```json
{"ok":true,"result":true,"description":"Webhook was set"}
```

**验证设置了**:

```bash
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

`url` 字段应该指向你的 worker。

---

## Part 6 — 关掉 polling workflow（可选）

Webhook 上线后，polling 的 `telegram-chat.yml` 就**多余**了 —— Telegram 把所有 update 都送到 webhook，poll 永远没东西。

两个选择:

**选项 A — 关掉 polling workflow（推荐）**:
```bash
gh workflow disable telegram-chat.yml --repo <你的用户名>/claude-investment-skills
```

**选项 B — 留着做 backup**（万一 webhook 挂了）:polling workflow 会静默无操作（Telegram 不给它消息）。

`price-alerts.yml`（真正的价格扫描）继续跑 —— 跟 chat 没关系。

---

## Part 7 — 测试

在 Telegram 给 bot 发:

```
hello, test webhook 延迟
```

期望: bot **1-3 秒内**回复（不再是 2-15 分钟）。

如果 5 秒没回，跳到下面 [故障排查](#故障排查)。

---

## 看实时 logs

`wrangler tail` 实时流式显示每个 worker 请求:

```bash
cd ~/.claude/skills/price-alert/webhook
wrangler tail
```

然后发 Telegram 消息 —— 你立刻看到 worker 的 `console.log`。调试神器。

---

## 故障排查

### Bot 不回

1. **验证 webhook 设置了**:
   ```bash
   curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
   ```
   `url` 应该指向你的 worker。如果空，重做 Part 5。

2. **看 worker logs**:
   ```bash
   wrangler tail
   ```
   发消息。如果没 log，Telegram 没在打你的 worker —— URL 错了。

3. **检查 secrets**:
   ```bash
   wrangler secret list
   ```
   应该 5 个。少了就重做 Part 3。

### Bot 回 `⚠️ Error: ...`

错误信息指出是哪个 API 失败:
- `Anthropic API error: 401` → ANTHROPIC_API_KEY 错了；重做那个 secret
- `GitHub fetch failed: 401` → GITHUB_TOKEN 错或没 Contents:write；重做 Part 2 + Part 3
- `GitHub fetch failed: 404` → GITHUB_REPO 错；格式必须是 `<owner>/<repo>`
- `GitHub commit failed: 403 Resource not accessible by personal access token` → **PAT 权限不对**。`GET`（读）成功是因为 repo 是 public 不需要 auth，但 `PUT`（提交）必须有 **Contents: Write**。修复：打开 https://github.com/settings/personal-access-tokens → 点 `price-alert-webhook` → Repository permissions → Contents → 改成 **Read and write** → 点 Update。（**最常见的坑** —— 很容易点成 "Read-only"，Read-only 能读但任何 commit 都 block 掉。）
- `btoa() can only operate on characters in the Latin1 (ISO/IEC 8859-1) range` → worker 代码过时了。从 repo pull 最新 `worker.ts`（新版用 `TextEncoder`/`TextDecoder` 处理中文 note 等非 ASCII 字符），然后 `wrangler deploy` 重新部署。
- `Anthropic API error: 400 ... credit balance` → Anthropic 余额没了；去 console.anthropic.com 充

### Worker logs 显示 "chat_id mismatch"

你的 `TELEGRAM_CHAT_ID` secret 跟实际 chat 不匹配。从 `https://api.telegram.org/bot<TOKEN>/getUpdates` 拿对的，重做 Part 3。

### Worker 慢（5+ 秒响应）

- 冷启动？CF Workers 偶尔冷启动，加 1-2 秒。第一次请求后就快了。
- Anthropic API 慢？高峰时段 Claude API 可能 5-10 秒响应，没办法。

### 代码改了怎么重新部署

```bash
cd ~/.claude/skills/price-alert/webhook
wrangler deploy
```

完事 —— `wrangler deploy` 全量重建 + push，10 秒搞定。

---

## 架构对比

```
之前 (polling):
  Telegram → 缓存 → GH Actions cron (每 2-5 分钟) → 处理 → 回复
  延迟: 2-15 分钟

之后 (webhook):
  Telegram → POST 到 CF Worker (即时) → 处理 → 回复
  延迟: 1-3 秒
```

每条消息的处理流程:
1. Telegram POST update JSON (~50ms)
2. Worker 解析 + 调 Anthropic API (~1-2 秒)
3. Worker 执行 tool（从 GitHub 拉 alerts.json、改、commit）(~500ms)
4. Worker 再调 Anthropic 拿最终回复文本 (~500ms)
5. Worker sendMessage 给 Telegram (~100ms)

平均 ~2 秒。Anthropic 高峰时最差 5 秒。

---

## 费用回顾

| 组件 | 费用 | 备注 |
|---|---|---|
| Cloudflare Workers | **$0** | 免费层 10 万 req/天；你 <1k/天 |
| Anthropic API | $1-4/月 | 跟 polling 一样 —— 同模型同用法 |
| GitHub API | $0 | 认证速率 5000 req/小时，远超所需 |
| Telegram Bot API | $0 | 永久免费 |
| **总计** | **$1-4/月** | 跟 polling 一样 |

Webhook 纯粹是架构升级。**零新增成本**。

---

## 还原到 polling

想退回去:

```bash
# 1. 让 Telegram 别再推 webhook
curl "https://api.telegram.org/bot<TOKEN>/deleteWebhook"

# 2. 重新启用 polling workflow
gh workflow enable telegram-chat.yml --repo <你的用户名>/claude-investment-skills

# 3. 可选：删除 worker
cd ~/.claude/skills/price-alert/webhook
wrangler delete
```

Worker 没存任何状态 —— 删了安全可恢复，想再上随时 redeploy。
