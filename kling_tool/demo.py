"""Full E2E workflow demo for Kling Tool."""

import json
import logging
import time
import uuid
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

from kling_tool.accounts import AccountManager
from kling_tool.browser import KlingBrowser
from kling_tool.database import Database
from kling_tool.models import Task, TaskStatus

IMAGE_PATH = r"C:\Users\Admin\.kling_tool\downloads\test_character.png"
VIDEO_PATH = r"C:\Users\Admin\.kling_tool\downloads\test_motion.mp4"


def main():
    db = Database()
    mgr = AccountManager(db)

    print("\n" + "=" * 62)
    print("  KLING TOOL - COMPLETE E2E WORKFLOW DEMO")
    print("=" * 62)

    # ── STEP 1: Pool Status ──
    print("\n[STEP 1] Account Pool Status")
    print("-" * 40)
    stats = mgr.pool_stats()
    print(f"  Accounts: {stats['total_accounts']} total, {stats['active_accounts']} active")
    print(f"  Credits:  {stats['total_credits_remaining']:.0f} remaining")
    for a in stats["accounts"]:
        print(f"    > {a['name']} ({a['email']}) | {a['status']} | {a['credits_remaining']:.0f} credits")

    # ── STEP 2: Queue task ──
    print(f"\n[STEP 2] Create Task (REST API format)")
    print("-" * 40)
    ext_id = f"demo-{uuid.uuid4().hex[:8]}"
    task = Task(
        external_task_id=ext_id,
        image_url=IMAGE_PATH,
        video_url=VIDEO_PATH,
        prompt="The girl is wearing a loose gray T-shirt",
        model_name="kling-v2-6",
        mode="pro",
        character_orientation="image",
        keep_original_sound="yes",
    )
    task_id = db.add_task(task)
    print(f"  Queued task #{task_id} (ext: {ext_id})")
    print(f'  Response: {{"code": 0, "task_id": "{task_id}", "status": "queued"}}')

    # ── STEP 3: Worker processes ──
    print(f"\n[STEP 3] Worker picks best account")
    print("-" * 40)
    account = mgr.select_best()
    print(f"  Selected: {account['name']} ({account['email']})")
    print(f"  Credits: {account['credits_remaining']:.0f}")
    db.update_task(task_id, status=TaskStatus.SUBMITTED.value, account_name=account["name"])
    print(f"  Task #{task_id} -> SUBMITTED")

    print(f"\n[STEP 3b] Browser automation")
    print("-" * 40)
    browser = KlingBrowser(account_name=account["name"], headless=True)

    with browser:
        page = browser._page

        print("  Navigating to Motion Control...")
        page.goto(
            "https://app.klingai.com/global/video-motion-control/new",
            timeout=20000,
            wait_until="domcontentloaded",
        )
        time.sleep(5)
        db.update_task(task_id, status=TaskStatus.PROCESSING.value)
        print(f"  Task #{task_id} -> PROCESSING")

        # Upload video
        print("  Uploading motion video...")
        vi = page.query_selector('input[type="file"][accept=".mp4,.mov"]')
        if vi:
            vi.set_input_files(VIDEO_PATH)
            time.sleep(5)
            print("  Video uploaded")

        # Upload image
        print("  Uploading character image...")
        ii = page.query_selector('input[type="file"][accept=".jpg,.jpeg,.png"]')
        if ii:
            ii.set_input_files(IMAGE_PATH)
            time.sleep(5)
            print("  Image uploaded")

        browser._screenshot("demo_e2e_ready")

        # Generate
        print("  Clicking Generate...")
        gen = page.query_selector('button:has-text("Generate")')
        if gen:
            gen.click()
            time.sleep(8)
            print("  Generate clicked!")
            browser._screenshot("demo_e2e_submitted")

        # Capture submit response
        kling_task_id = ""
        if browser._task_submit_response:
            td = browser._task_submit_response.get("data", {}).get("task", {})
            kling_task_id = str(td.get("id", ""))
            print(f"  Kling task ID: {kling_task_id}")
            print(f"  Type: {td.get('type', '')}")
            db.update_task(task_id, kling_task_id=kling_task_id)

        mgr.mark_used(account["name"], cost=19.0)
        print("  Credits deducted: 19")

        # ── STEP 4: Poll ──
        print(f"\n[STEP 4] Polling for completion (every 20s)")
        print("-" * 40)
        video_url = ""
        for i in range(30):
            time.sleep(20)
            page.reload(wait_until="domcontentloaded")
            time.sleep(5)

            body = page.inner_text("body")
            if "Creating..." in body or "Queueing..." in body:
                print(f"  Poll #{i+1}: Still processing...")
                continue

            vel = page.query_selector("video[src], video source[src]")
            if vel:
                video_url = vel.get_attribute("src") or "completed"
                print(f"  Poll #{i+1}: VIDEO COMPLETED!")
                browser._screenshot("demo_e2e_complete")
                db.update_task(
                    task_id,
                    status=TaskStatus.SUCCEED.value,
                    result_video_url=video_url,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
                break
            else:
                print(f"  Poll #{i+1}: Checking...")

    # ── STEP 5: Result ──
    print(f"\n[STEP 5] Final Result")
    print("-" * 40)
    ft = db.get_task(task_id)
    print(f"  Task ID:       {ft['id']}")
    print(f"  External ID:   {ft['external_task_id']}")
    print(f"  Status:        {ft['status']}")
    print(f"  Account:       {ft['account_name']}")
    print(f"  Kling ID:      {ft['kling_task_id']}")
    print(f"  Created:       {ft['created_at'][:19]}")
    print(f"  Completed:     {(ft.get('completed_at') or '')[:19]}")

    resp = {
        "code": 0,
        "message": "success",
        "data": {
            "task_id": str(ft["id"]),
            "external_task_id": ft["external_task_id"],
            "task_status": ft["status"],
        },
    }
    if ft["status"] == "succeed":
        resp["data"]["task_result"] = {"videos": [{"url": ft.get("result_video_url", ""), "duration": 9.0}]}

    print(f"\n  GET /v1/videos/motion-control/{task_id}")
    print(f"  {json.dumps(resp, indent=2, ensure_ascii=False)}")

    # Final stats
    print(f"\n[FINAL] Pool Status After Demo")
    print("-" * 40)
    s2 = mgr.pool_stats()
    print(f"  Credits remaining: {s2['total_credits_remaining']:.0f}")
    print(f"  Credits used:      {s2['total_credits_used']:.0f}")
    print(f"\n{'=' * 62}")
    print("  DEMO COMPLETE!")
    print(f"{'=' * 62}\n")


if __name__ == "__main__":
    main()
