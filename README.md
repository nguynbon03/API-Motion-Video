# Kling Motion Control API

REST API proxy for **Kling AI Motion Control** video generation. Upload a character image + motion reference video → get AI-generated motion video back.

Uses web UI accounts with credit pooling — **no API credits needed**.

## How It Works

```
Client sends image + video
        │
        ▼
┌────────────────────────────────────┐
│  Docker Server (runs 24/7)          │
│                                     │
│  POST /api/generate                 │
│    ↓                                │
│  Worker picks best account          │
│    ↓                                │
│  Playwright opens Chrome            │
│    → Login to Kling web UI          │
│    → Upload image + video           │
│    → Click Generate                 │
│    → Wait ~5-10 min                 │
│    → Download result video          │
│    ↓                                │
│  GET /outputs/task_{id}.mp4         │
│    → Return video file              │
└────────────────────────────────────┘
```

## Quick Start

### 1. Setup

```bash
git clone https://github.com/nguynbon03/API-Motion-Video.git
cd API-Motion-Video
pip install -e .
playwright install chromium
```

### 2. Add Accounts

Create `accounts.txt`:

```
user1@gmail.com:password123
user2@gmail.com:password456:socks5://proxy:1080
```

Import:

```bash
kling-tool account import accounts.txt --credits 66
```

### 3. Start Server

```bash
kling-tool server start
```

Server runs at `http://localhost:8686`

- Dashboard: `http://localhost:8686`
- API Docs: `http://localhost:8686/docs`
- Health: `http://localhost:8686/health`

### 4. Create Motion Video (tested & verified)

**Step 1** — Upload image + video, create task:

```bash
curl -X POST http://localhost:8686/api/generate \
  -F "image=@character.png" \
  -F "video=@dance.mp4" \
  -F "mode=pro"
```

Response:

```json
{
  "code": 0,
  "message": "Task queued",
  "data": {
    "task_id": 14,
    "external_task_id": "gen-4598efee",
    "status": "queued"
  }
}
```

**Step 2** — Poll status (repeat every 10-15 seconds):

```bash
curl http://localhost:8686/api/tasks/14
```

Status flow: `queued` → `submitted` → `processing` → `succeed`

```json
{
  "id": 14,
  "status": "succeed",
  "account_name": "b.i.b.jkute116",
  "result_video_url": "/outputs/task_14.mp4",
  "created_at": "2026-03-18T20:55:00",
  "completed_at": "2026-03-18T21:03:00"
}
```

**Step 3** — Download result video:

```bash
curl -O http://localhost:8686/outputs/task_14.mp4
```

Actual test result: **10.8MB video, 720p, ~9 seconds**.

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/generate` | Upload image + video → create task |
| `GET` | `/api/tasks/{id}` | Check task status |
| `GET` | `/api/tasks` | List all tasks |
| `GET` | `/outputs/task_{id}.mp4` | Download result video |
| `POST` | `/api/upload/accounts` | Import accounts file |
| `GET` | `/api/status` | Pool + task summary |
| `GET` | `/health` | Server health check |
| `GET` | `/` | Web dashboard |

### POST /api/generate

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `image` | File | Yes | — | Character image (.jpg/.png) |
| `video` | File | Yes | — | Motion reference video (.mp4/.mov, 3-30s) |
| `prompt` | string | No | `""` | Describe the character |
| `mode` | string | No | `"pro"` | `pro` or `std` |
| `model_name` | string | No | `"kling-v2-6"` | `kling-v2-6` or `kling-v3` |
| `orientation` | string | No | `"image"` | `image` or `video` |
| `keep_sound` | string | No | `"yes"` | `yes` or `no` |

### Task Status

| Status | Meaning |
|--------|---------|
| `queued` | Waiting in queue |
| `submitted` | Account assigned, browser starting |
| `processing` | Kling is generating the video |
| `succeed` | Video ready for download |
| `failed` | Error occurred |

## Docker (24/7 Server)

### docker-compose.yml

```bash
# Add your accounts
echo "user@gmail.com:password" > accounts.txt

# Start (runs forever, auto-restart)
docker-compose up -d

# Check logs
docker-compose logs -f

# Stop
docker-compose down
```

Volumes:

| Host Path | Container Path | Purpose |
|-----------|---------------|---------|
| `./accounts.txt` | `/data/accounts/accounts.txt` | Account list (auto-imported) |
| `./inputs/` | `/data/inputs/` | Uploaded images + videos |
| `./outputs/` | `/data/outputs/` | Generated result videos |

### Public Access with ngrok

```bash
ngrok http 8686
```

Then use the ngrok URL from any website:

```javascript
const API = 'https://your-url.ngrok-free.dev';

// Create video
const form = new FormData();
form.append('image', imageFile);
form.append('video', videoFile);
form.append('mode', 'pro');

const res = await fetch(`${API}/api/generate`, {
  method: 'POST',
  headers: { 'ngrok-skip-browser-warning': 'true' },
  body: form
});
const { data } = await res.json();

// Poll until done
const poll = setInterval(async () => {
  const r = await fetch(`${API}/api/tasks/${data.task_id}`, {
    headers: { 'ngrok-skip-browser-warning': 'true' }
  });
  const task = await r.json();
  if (task.status === 'succeed') {
    clearInterval(poll);
    window.open(`${API}${task.result_video_url}`);
  }
}, 10000);
```

## Web Frontend

Deploy `web/` folder to Vercel:

- `https://your-site.vercel.app/` — Video generator UI
- `https://your-site.vercel.app/docs.html` — API documentation

Live docs: [https://api-motion-video.vercel.app/docs.html](https://api-motion-video.vercel.app/docs.html)

## Account Management

### Account File Format

```
# email:password
user1@gmail.com:MyPass123

# email:password:proxy
user2@gmail.com:MyPass456:socks5://1.2.3.4:1080

# name|email|password|proxy|credits
acc-01|user3@gmail.com|MyPass789|http://proxy:8080|100
```

### Auto-Rotation

- Accounts are selected by highest credits remaining
- When one account runs out → automatically switches to next
- Each account uses its assigned proxy
- Failed logins auto-disable the account

### CLI Commands

```bash
kling-tool account list              # Show all accounts
kling-tool account add -n "acc1" -e "user@mail.com"
kling-tool account import file.txt   # Bulk import
kling-tool account set-credits -n "acc1" -c 100
kling-tool status                    # Pool summary
```

## Project Structure

```
├── kling_tool/
│   ├── server.py        # Unified FastAPI app (main entry)
│   ├── api.py           # /v1/ REST API routes
│   ├── dashboard.py     # Web dashboard + /api/ routes
│   ├── browser.py       # Playwright automation for Kling web UI
│   ├── worker.py        # Background task processor
│   ├── accounts.py      # Account pool + rotation
│   ├── database.py      # SQLite persistence
│   ├── watcher.py       # Auto-import accounts.txt
│   ├── config.py        # Configuration (env var support)
│   └── models.py        # Data models
├── web/
│   ├── index.html       # Video generator frontend
│   └── docs.html        # API documentation page
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── accounts.txt         # Your accounts (gitignored)
```

## Tested Workflow (2026-03-19)

Full end-to-end test verified:

1. `POST /api/generate` — uploaded `test_character.png` + `test_dance.mp4`
2. Task #14 queued → submitted → processing (worker used account `b.i.b.jkute116`)
3. Playwright logged in via saved session cookies
4. Navigated to Motion Control page, uploaded files, clicked Generate
5. Kling created video in ~8 minutes, credits deducted on web UI
6. CDN video URL intercepted from Kling internal API response
7. Video downloaded: **10.8MB, 720p, 9 seconds**
8. `GET /outputs/task_14.mp4` → HTTP 200, file served successfully
