"""Quick test: does Playwright work with system Edge?"""
import os, pathlib
from playwright.sync_api import sync_playwright

edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
print("Edge path:", edge_path, "exists:", pathlib.Path(edge_path).exists())

HTML = """<!DOCTYPE html>
<html>
<head>
<style>
  body { margin:0; background:#1A0A00; display:flex; align-items:center; justify-content:center; }
  h1 { color:#C8961E; font-size:80px; font-family:Georgia,serif; text-align:center; }
  p { color:white; font-size:30px; font-family:Arial,sans-serif; text-align:center; }
</style>
</head>
<body>
  <div>
    <h1>VB Exports</h1>
    <p>Premium Indian Coffee — Playwright Test</p>
    <p style="color:#C8961E">vb-exports.com | +91 9449522395</p>
  </div>
</body>
</html>"""

with sync_playwright() as p:
    try:
        browser = p.chromium.launch(executable_path=edge_path, channel="msedge")
        page = browser.new_page()
        page.set_viewport_size({"width": 1080, "height": 1350})
        page.set_content(HTML, wait_until="domcontentloaded")
        page.screenshot(path="output/test_edge.png", type="png")
        browser.close()
        print("SUCCESS — output/test_edge.png created")
    except Exception as e:
        print("FAILED:", e)
