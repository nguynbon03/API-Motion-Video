---
name: kling-automation
description: Expert skill for Kling AI tool automation — web UI automation, multi-account management, proxy rotation, REST API proxy, and MMO-grade video generation pipeline.
trigger: When the user asks about Kling tool automation, account management, video generation pipeline, browser automation, proxy rotation, or REST API proxy for Kling AI.
---

# Kling Automation Expert Skill

## Expertise Areas

1. **Web UI Automation** — Playwright-based automation for Kling AI web interface
2. **Multi-Account Management** — Account pool with credit tracking and rotation
3. **Proxy Rotation** — CLI proxy integration for account farming
4. **REST API Proxy** — Drop-in replacement API that mirrors official Kling API format
5. **Pipeline Design** — End-to-end video generation workflows

## Architecture

### Two Tools

| Tool | Package | Purpose | Auth Method |
|------|---------|---------|-------------|
| `kling-proxy` | `kling_proxy/` | Official API proxy | JWT HS256 (Access Key + Secret Key) |
| `kling-tool` | `kling_tool/` | Web UI automation proxy | Browser cookies (email + password) |

### kling-proxy (API-based)
- Generates JWT tokens from Access Key + Secret Key
- Direct HTTP calls to `https://api-singapore.klingai.com`
- Uses API credits (paid)
- Fast, reliable, no browser needed

### kling-tool (Web UI-based)
- Playwright browser automation of `app.klingai.com`
- Uses web UI credits (free/subscription)
- Multi-account pool with proxy rotation
- Background worker processes task queue
- FastAPI REST API exposes same format as official API
- Network interception discovers internal APIs for optimization

## Key Commands

### kling-tool (Web UI)
```bash
# Account management
kling-tool account add --name "acc1" --email "x@y.com" --proxy "socks5://ip:port"
kling-tool account import accounts.txt --credits 66
kling-tool account list
kling-tool account login-test --name "acc1" --no-headless

# Task management
kling-tool task create --image img.png --video motion.mp4 --mode pro
kling-tool task list
kling-tool task status 123

# REST API server
kling-tool server start --port 8686

# Status
kling-tool status
```

### kling-proxy (API)
```bash
kling-proxy account add --name "api1" --access-key "AK..." --credits 100
kling-proxy task create --image "url" --video "url" --mode pro
```

## Account File Format

For bulk import (`kling-tool account import`):
```
# email:password
user1@mail.com:pass123

# email:password:proxy
user2@mail.com:pass456:socks5://1.2.3.4:1080

# name|email|password|proxy|credits
myacc|user3@mail.com|pass789|http://proxy:8080|100
```

## REST API Endpoints (kling-tool server)

Mirrors official Kling API:
- `POST /v1/videos/motion-control` — Create task
- `GET /v1/videos/motion-control/{id}` — Get task
- `GET /v1/videos/motion-control` — List tasks

Management:
- `GET /v1/pool/status` — Pool summary
- `POST /v1/pool/accounts` — Add account
- `POST /v1/pool/accounts/bulk` — Bulk add
- `GET /v1/pool/accounts` — List accounts

## Workflow Pattern

1. Import accounts with credits → `kling-tool account import`
2. Test logins → `kling-tool account login-test`
3. Start API server → `kling-tool server start`
4. Send tasks via REST API → `POST /v1/videos/motion-control`
5. Worker picks best account, opens browser, creates video
6. Poll status → `GET /v1/videos/motion-control/{id}`
7. Download result video before 30-day expiry

## Optimization Path

Phase 1: Full Playwright automation (current)
Phase 2: Intercept internal web APIs during automation
Phase 3: Switch to direct HTTP calls with session cookies (faster)
Phase 4: Hybrid — HTTP for speed, Playwright fallback for resilience

## Important Notes

- Browser sessions are saved in `~/.kling_tool/sessions/`
- Screenshots captured for debugging in `~/.kling_tool/screenshots/`
- Database at `~/.kling_tool/database.db`
- All secrets stored locally, never in git
- Respect rate limits — 1 concurrent task per account by default
- Video output URLs expire after 30 days
