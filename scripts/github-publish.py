#!/usr/bin/env python3
"""Publish taskmarket-live to a public GitHub repo via the custom.github
connection (PAT, public_repo scope). Creates the repo if missing, then uploads
every project file through the Contents API (base64 PUT).
Usage: python3 scripts/github-publish.py
"""
import base64
import json
import os
import sys
import urllib.request

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import add_surrogate_to_request

OWNER = "abangdwie"
REPO = "taskmarket-live"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FILES = [
    "public/index.html", "public/favicon.svg", "public/_headers", "public/og.png",
    "public/_worker.js", "scripts/deploy.py", "scripts/og-card.py",
    "scripts/github-publish.py",
    "package.json", "README.md", "LICENSE",
]
# Files removed from the repo (deleted via API after upload pass).
DELETE_FILES = ["worker/data-worker.mjs"]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


def call(method, path, data=None):
    req = urllib.request.Request("https://api.github.com" + path, data=data, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    if data:
        req.add_header("Content-Type", "application/json")
    add_surrogate_to_request(req, "custom.github", allowed_hosts=["api.github.com"])
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def main():
    status, body = call("GET", f"/repos/{OWNER}/{REPO}")
    if status == 200:
        print(f"repo exists: {body['full_name']} ({body['html_url']})")
    elif status == 404:
        status, body = call("POST", "/user/repos", json.dumps({
            "name": REPO,
            "description": "A public, live dashboard of Taskmarket's market data (Tempo + Base).",
            "public": True, "license_template": "mit", "auto_init": False,
        }).encode())
        if status not in (200, 201):
            raise SystemExit(f"repo create failed HTTP {status}: {json.dumps(body)[:500]}")
        print(f"repo created: {body['html_url']}")
    else:
        raise SystemExit(f"repo check failed HTTP {status}: {json.dumps(body)[:500]}")

    for rel in FILES:
        with open(os.path.join(ROOT, rel), "rb") as f:
            content = base64.b64encode(f.read()).decode()
        # get current sha if the file already exists (update instead of create)
        status, cur = call("GET", f"/repos/{OWNER}/{REPO}/contents/{rel}")
        sha = cur.get("sha") if status == 200 else None
        payload = {"message": f"taskmarket-live: {rel}", "content": content, "branch": "main"}
        if sha:
            payload["sha"] = sha
        status, body = call("PUT", f"/repos/{OWNER}/{REPO}/contents/{rel}", json.dumps(payload).encode())
        if status not in (200, 201):
            raise SystemExit(f"upload {rel} failed HTTP {status}: {json.dumps(body)[:500]}")
        print(f"uploaded {rel} ({body['content']['size']} bytes, {body['commit']['sha'][:7]})")
    for rel in DELETE_FILES:
        status, cur = call("GET", f"/repos/{OWNER}/{REPO}/contents/{rel}")
        if status != 200:
            print(f"delete skipped (not in repo): {rel}")
            continue
        status, body = call("DELETE", f"/repos/{OWNER}/{REPO}/contents/{rel}", json.dumps({
            "message": f"taskmarket-live: remove superseded {rel}",
            "sha": cur["sha"], "branch": "main",
        }).encode())
        print(f"deleted {rel} (HTTP {status})")
    print(f"REPO_URL=https://github.com/{OWNER}/{REPO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
