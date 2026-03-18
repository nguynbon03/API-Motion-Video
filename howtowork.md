# How To Work — Kling Motion Control API

Quy trình tạo motion video hoàn chỉnh chỉ cần **3 API calls**.

## Server

```
Public URL: https://regardless-philologic-martin.ngrok-free.dev
Dashboard:  https://regardless-philologic-martin.ngrok-free.dev
API Docs:   https://regardless-philologic-martin.ngrok-free.dev/docs
Swagger:    https://regardless-philologic-martin.ngrok-free.dev/docs
Vercel:     https://api-motion-video.vercel.app/docs.html
```

> Tất cả request cần header: `ngrok-skip-browser-warning: true`

---

## Quy trình 3 bước

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  STEP 1          │     │  STEP 2           │     │  STEP 3           │
│  POST            │     │  GET              │     │  GET              │
│  /api/generate   │────▶│  /api/tasks/{id}  │────▶│  /outputs/*.mp4   │
│                  │     │                   │     │                   │
│  Upload ảnh      │     │  Loop mỗi 15s     │     │  Download video   │
│  Upload video    │     │  đến khi succeed  │     │  kết quả          │
│  → nhận task_id  │     │  → nhận video URL │     │  → file .mp4      │
└─────────────────┘     └──────────────────┘     └──────────────────┘
```

---

## Step 1: Tạo task — Upload ảnh + video

**Endpoint:**

```
POST /api/generate
Content-Type: multipart/form-data
```

**Request:**

```bash
curl -X POST https://YOUR_SERVER/api/generate \
  -H "ngrok-skip-browser-warning: true" \
  -F "image=@character.png" \
  -F "video=@dance.mp4" \
  -F "mode=pro"
```

**Tham số:**

| Field | Type | Bắt buộc | Default | Mô tả |
|-------|------|----------|---------|-------|
| `image` | File | ✅ | — | Ảnh nhân vật (.jpg, .png). Max 10MB |
| `video` | File | ✅ | — | Video motion mẫu (.mp4, .mov). 3-30 giây, max 100MB |
| `prompt` | string | ❌ | `""` | Mô tả nhân vật (ví dụ: "A girl in gray T-shirt") |
| `mode` | string | ❌ | `"pro"` | `"pro"` = chất lượng cao, `"std"` = nhanh hơn |
| `model_name` | string | ❌ | `"kling-v2-6"` | `"kling-v2-6"` hoặc `"kling-v3"` |
| `orientation` | string | ❌ | `"image"` | `"image"` = theo dáng ảnh, `"video"` = theo dáng video |
| `keep_sound` | string | ❌ | `"yes"` | `"yes"` = giữ âm thanh gốc, `"no"` = tắt tiếng |

**Response:**

```json
{
  "code": 0,
  "message": "Task queued",
  "data": {
    "task_id": 14,
    "external_task_id": "gen-4598efee",
    "status": "queued",
    "image": "0698ca87_character.png",
    "video": "78d31bbf_dance.mp4"
  }
}
```

**Lưu lại:** `data.task_id` → dùng cho Step 2.

---

## Step 2: Poll status — Chờ video hoàn thành

**Endpoint:**

```
GET /api/tasks/{task_id}
```

**Request:**

```bash
curl https://YOUR_SERVER/api/tasks/14 \
  -H "ngrok-skip-browser-warning: true"
```

**Logic:** Gọi API này **mỗi 15 giây** cho đến khi `status` = `"succeed"` hoặc `"failed"`.

**Response khi đang xử lý:**

```json
{
  "id": 14,
  "status": "processing",
  "account_name": "b.i.b.jkute116",
  "mode": "pro",
  "created_at": "2026-03-18T20:55:00"
}
```

**Response khi hoàn thành:**

```json
{
  "id": 14,
  "status": "succeed",
  "account_name": "b.i.b.jkute116",
  "mode": "pro",
  "result_video_url": "/outputs/task_14.mp4",
  "created_at": "2026-03-18T20:55:00",
  "completed_at": "2026-03-18T21:03:00"
}
```

**Status flow:**

```
queued → submitted → processing → succeed
                                → failed
```

| Status | Nghĩa | Hành động |
|--------|--------|-----------|
| `queued` | Đang chờ trong hàng đợi | Tiếp tục poll |
| `submitted` | Đã chọn account, đang mở browser | Tiếp tục poll |
| `processing` | Kling đang tạo video (~5-10 phút) | Tiếp tục poll |
| `succeed` | Video xong, sẵn sàng download | → Sang Step 3 |
| `failed` | Lỗi xảy ra | Dừng, xem `error_message` |

**Lưu lại:** `result_video_url` → dùng cho Step 3.

---

## Step 3: Download video kết quả

**Endpoint:**

```
GET /outputs/task_{id}.mp4
```

**Request:**

```bash
curl -O https://YOUR_SERVER/outputs/task_14.mp4 \
  -H "ngrok-skip-browser-warning: true"
```

**URL đầy đủ** = `YOUR_SERVER` + `result_video_url` từ Step 2.

Ví dụ: `https://regardless-philologic-martin.ngrok-free.dev/outputs/task_14.mp4`

**Response:** File binary `.mp4` (khoảng 10-15MB, 720p, 5-10 giây).

---

## Kết quả test thực tế (2026-03-19)

```
Input:
  - Ảnh: test_character.png (776KB)
  - Video: test_dance.mp4 (2.6MB, 10 giây)
  - Mode: pro

Timeline:
  00:00  POST /api/generate → task_id: 14, status: queued
  00:05  GET /api/tasks/14 → status: submitted
  00:15  GET /api/tasks/14 → status: processing
  03:45  GET /api/tasks/14 → status: processing (Kling đang tạo...)
  08:00  GET /api/tasks/14 → status: succeed ✅

Output:
  - File: task_14.mp4
  - Size: 10.8MB
  - Resolution: 720p
  - Duration: ~9 giây
  - Credits tiêu tốn: ~90 (trên web UI)
```

---

## n8n Workflow Setup

### Node 1: HTTP Request — Tạo task

```
Method:     POST
URL:        https://YOUR_SERVER/api/generate
Auth:       None
Headers:    ngrok-skip-browser-warning = true
Body Type:  Form-Data (Multipart)
Parameters:
  - image    = {{ $binary.image }}      (Binary Data)
  - video    = {{ $binary.video }}      (Binary Data)
  - mode     = pro                      (String)
  - prompt   = [optional description]   (String)
```

Output: `{{ $json.data.task_id }}`

### Node 2: Wait

```
Wait Time: 15 seconds
```

### Node 3: HTTP Request — Check status

```
Method:     GET
URL:        https://YOUR_SERVER/api/tasks/{{ $json.data.task_id }}
Headers:    ngrok-skip-browser-warning = true
```

### Node 4: IF

```
Condition: {{ $json.status }} equals "succeed"
  True  → Node 5 (Download)
  False → Check if "failed"
    Yes → Stop
    No  → Back to Node 2 (Wait + Poll again)
```

### Node 5: HTTP Request — Download video

```
Method:     GET
URL:        https://YOUR_SERVER{{ $json.result_video_url }}
Headers:    ngrok-skip-browser-warning = true
Response:   Binary File

→ Save to Google Drive / S3 / Send to Telegram / v.v.
```

### n8n Flow Diagram

```
[Trigger]
    ↓
[HTTP: POST /api/generate]  ← upload image + video
    ↓
[Wait 15s]
    ↓
[HTTP: GET /api/tasks/{id}]  ← check status
    ↓
[IF status == "succeed"]
   YES → [HTTP: GET /outputs/task.mp4]  ← download
   NO  → [IF status == "failed"]
            YES → [Stop/Error]
            NO  → [Back to Wait 15s]  ← loop
```

---

## JavaScript (cho Website)

```javascript
const API = 'https://YOUR_SERVER';
const H = { 'ngrok-skip-browser-warning': 'true' };

async function createMotionVideo(imageFile, videoFile) {
  // Step 1: Upload + create task
  const form = new FormData();
  form.append('image', imageFile);
  form.append('video', videoFile);
  form.append('mode', 'pro');

  const res = await fetch(`${API}/api/generate`, {
    method: 'POST', headers: H, body: form
  });
  const { data } = await res.json();
  const taskId = data.task_id;

  // Step 2: Poll until done
  while (true) {
    await new Promise(r => setTimeout(r, 15000)); // wait 15s

    const r = await fetch(`${API}/api/tasks/${taskId}`, { headers: H });
    const task = await r.json();

    if (task.status === 'succeed') {
      // Step 3: Return download URL
      return `${API}${task.result_video_url}`;
    }
    if (task.status === 'failed') {
      throw new Error(task.error_message || 'Video generation failed');
    }
  }
}

// Usage:
const videoUrl = await createMotionVideo(imageFile, videoFile);
window.open(videoUrl); // download video
```

---

## Python

```python
import httpx
import time

API = "https://YOUR_SERVER"

# Step 1: Upload + create task
files = {
    "image": open("character.png", "rb"),
    "video": open("dance.mp4", "rb"),
}
data = {"mode": "pro"}

r = httpx.post(f"{API}/api/generate", files=files, data=data)
task_id = r.json()["data"]["task_id"]
print(f"Task #{task_id} created")

# Step 2: Poll until done
while True:
    time.sleep(15)
    r = httpx.get(f"{API}/api/tasks/{task_id}")
    task = r.json()
    print(f"Status: {task['status']}")

    if task["status"] == "succeed":
        video_url = f"{API}{task['result_video_url']}"
        break
    if task["status"] == "failed":
        raise Exception(task.get("error_message", "Failed"))

# Step 3: Download video
r = httpx.get(video_url)
with open("output.mp4", "wb") as f:
    f.write(r.content)
print(f"Downloaded: output.mp4 ({len(r.content)} bytes)")
```

---

## API phụ trợ (không bắt buộc)

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `GET` | `/api/status` | Xem số account, credits, tasks |
| `GET` | `/health` | Kiểm tra server còn sống không |
| `POST` | `/api/upload/accounts` | Import file accounts.txt |
| `GET` | `/api/tasks?status=succeed` | Liệt kê tasks đã hoàn thành |
| `GET` | `/` | Web dashboard (giao diện upload) |

---

## Tips

- **Thời gian tạo video:** Khoảng 5-10 phút cho mỗi video
- **Poll interval:** 15 giây là hợp lý, không nên thấp hơn 10 giây
- **Video input tốt nhất:** 1 người, thấy rõ đầu + tay chân, ít cắt cảnh, động tác vừa phải
- **Ảnh input tốt nhất:** Rõ mặt, rõ thân, ratio 1:2.5 đến 2.5:1
- **Credits:** ~90 credits cho 1 video pro mode 720p
- **Server 24/7:** Dùng Docker + ngrok, hoặc VPS với domain riêng
