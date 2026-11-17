"""Production Single-URL Packaging Smoke Test.

Verifies:
1. Standalone FastAPI serves compiled React HTML app at http://127.0.0.1:8000/
2. /assets/* loads JS and CSS production bundles with HTTP 200
3. /api/health and /api/analyze return HTTP 200
4. Unknown /api/* routes strictly return JSON 404 rather than HTML
5. Clean server shutdown
"""

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def run_smoke_test():
    dist_dir = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    assets_dir = dist_dir / "assets"

    assert dist_dir.exists(), f"frontend/dist must exist at {dist_dir}"
    assert assets_dir.exists(), f"frontend/dist/assets must exist at {assets_dir}"

    js_files = list(assets_dir.glob("*.js"))
    css_files = list(assets_dir.glob("*.css"))
    assert len(js_files) > 0, "No JS bundle found in frontend/dist/assets"
    assert len(css_files) > 0, "No CSS bundle found in frontend/dist/assets"

    sample_js_name = js_files[0].name
    sample_css_name = css_files[0].name

    python_exe = sys.executable
    port = 8000

    print(f"Starting standalone FastAPI server on port {port}...")
    server_process = subprocess.Popen(
        [
            python_exe,
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    base_url = f"http://127.0.0.1:{port}"
    server_ready = False

    try:
        # Wait for server to bind and respond
        for attempt in range(25):
            try:
                with urllib.request.urlopen(f"{base_url}/api/health", timeout=1.0) as resp:
                    if resp.status == 200:
                        server_ready = True
                        break
            except Exception:
                time.sleep(0.4)

        if not server_ready:
            stdout_text = ""
            stderr_text = ""
            try:
                server_process.terminate()
                stdout_text, stderr_text = server_process.communicate(timeout=2.0)
            except Exception:
                pass
            raise RuntimeError(f"FastAPI server failed to start within timeout.\nSTDOUT:\n{stdout_text}\nSTDERR:\n{stderr_text}")

        print("[OK] FastAPI standalone server is listening.\n")

        # 1. Test Root / serves React HTML
        print(f"Checking GET {base_url}/ ...")
        with urllib.request.urlopen(f"{base_url}/", timeout=5.0) as resp:
            assert resp.status == 200, f"Expected 200, got {resp.status}"
            content_type = resp.headers.get("Content-Type", "")
            assert "text/html" in content_type, f"Expected text/html, got {content_type}"
            html_body = resp.read().decode("utf-8")
            assert '<div id="root"></div>' in html_body or "<title>" in html_body, "index.html missing root or title tag"
            print("  --> [PASSED] Serves React index.html with HTTP 200.")

        # 2. Test JS Asset Bundle
        print(f"Checking GET {base_url}/assets/{sample_js_name} ...")
        with urllib.request.urlopen(f"{base_url}/assets/{sample_js_name}", timeout=5.0) as resp:
            assert resp.status == 200, f"Expected 200, got {resp.status}"
            js_bytes = resp.read()
            assert len(js_bytes) > 1000, f"JS bundle too small: {len(js_bytes)} bytes"
            print(f"  --> [PASSED] JS bundle loaded ({len(js_bytes)} bytes) with HTTP 200.")

        # 3. Test CSS Asset Bundle
        print(f"Checking GET {base_url}/assets/{sample_css_name} ...")
        with urllib.request.urlopen(f"{base_url}/assets/{sample_css_name}", timeout=5.0) as resp:
            assert resp.status == 200, f"Expected 200, got {resp.status}"
            css_bytes = resp.read()
            assert len(css_bytes) > 500, f"CSS bundle too small: {len(css_bytes)} bytes"
            print(f"  --> [PASSED] CSS bundle loaded ({len(css_bytes)} bytes) with HTTP 200.")

        # 4. Test /api/health
        print(f"Checking GET {base_url}/api/health ...")
        with urllib.request.urlopen(f"{base_url}/api/health", timeout=5.0) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "ok"
            assert data["db"] == "connected"
            print("  --> [PASSED] /api/health returned HTTP 200 with DB connected.")

        # 5. Test /api/analyze
        print(f"Checking POST {base_url}/api/analyze ...")
        analyze_payload = json.dumps({
            "location_query": "Belagavi, Karnataka",
            "latitude": 15.8497,
            "longitude": 74.4977,
            "crop_id": "onion",
            "quantity_quintals": 30.0,
            "language": "en",
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/api/analyze",
            data=analyze_payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=25.0) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert "weather" in data
            assert "mandi_comparison" in data
            assert "ai_advisory" in data
            print(f"  --> [PASSED] /api/analyze returned HTTP 200 (Top: {data['mandi_comparison'][0]['market']}).")

        # 6. Test Unknown /api route strictly returns JSON 404 (NOT HTML)
        print(f"Checking GET {base_url}/api/nonexistent_endpoint ...")
        try:
            urllib.request.urlopen(f"{base_url}/api/nonexistent_endpoint", timeout=5.0)
            raise AssertionError("Expected HTTP 404 for unknown API path, but received HTTP 200")
        except urllib.error.HTTPError as err:
            assert err.code == 404, f"Expected HTTP 404, got {err.code}"
            err_body = err.read().decode("utf-8")
            err_json = json.loads(err_body)
            assert "detail" in err_json, "Response must be JSON with 'detail' key"
            print(f"  --> [PASSED] Unknown API path correctly returned JSON 404: {err_json}")

        print("\nALL SMOKE CHECKS PASSED SUCCESSFULLY!")

    finally:
        print("\nTerminating standalone test server process...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            server_process.kill()
        print("[OK] Test server terminated cleanly.")


if __name__ == "__main__":
    run_smoke_test()
