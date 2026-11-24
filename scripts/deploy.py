#!/usr/bin/env python3
"""One-command deploy for taskmarket-live (Cloudflare Pages + Worker).

Usage:  python3 scripts/deploy.py [--repo-url https://github.com/abangdwie/taskmarket-live]
Auth:   token comes from the custom.cloudflare-direct connection (Secure Vault
        surrogate, same pattern as deploy-pages.py). No token in this file.
        CLOUDFLARE_ACCOUNT_ID defaults to the account used by that connection.
Steps:  1. deploy the data worker (server-side API fetch + 600s cache)
        2. create the Pages project if missing
        3. upload public/ (index.html gets __WORKER_URL__ / __REPO_URL__ replaced)
        4. print the live URLs and verify both endpoints
"""
import hashlib
import json
import os
import sys
import urllib.request
import uuid

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import add_surrogate_to_request

ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "b15d3ea349d6597d81ef1b0bd4d08032")
PROJECT = "taskmarket-live"
WORKER_NAME = "taskmarket-live-data"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PUBLIC = os.path.join(ROOT, "public")
WORKER_FILE = os.path.join(ROOT, "worker", "data-worker.mjs")
REPO_URL = "https://github.com/abangdwie/taskmarket-live"
if "--repo-url" in sys.argv:
    REPO_URL = sys.argv[sys.argv.index("--repo-url") + 1]
API = "https://api.cloudflare.com/client/v4"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


def call(method, path, data=None, content_type=None):
    req = urllib.request.Request(API + path, data=data, method=method)
    if content_type:
        req.add_header("Content-Type", content_type)
    add_surrogate_to_request(req, "custom.cloudflare-direct", allowed_hosts=["api.cloudflare.com"])
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def multipart(parts):
    """parts: list of (name, filename_or_None, content_type, bytes)."""
    boundary = "----cfdeploy" + uuid.uuid4().hex
    body = b""
    for name, filename, ctype, data in parts:
        disp = f'Content-Disposition: form-data; name="{name}"'
        if filename:
            disp += f'; filename="{filename}"'
        body += f"--{boundary}\r\n{disp}\r\nContent-Type: {ctype}\r\n\r\n".encode() + data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def deploy_worker():
    sub = call("GET", f"/accounts/{ACCOUNT_ID}/workers/subdomain")
    if not sub.get("success"):
        raise SystemExit("subdomain lookup failed: " + json.dumps(sub)[:500])
    subdomain = sub["result"]["subdomain"]
    with open(WORKER_FILE, "rb") as f:
        script = f.read()
    meta = json.dumps({
        "main_module": "data-worker.mjs",
        "compatibility_date": "2024-01-01",
    }).encode()
    body, ctype = multipart([
        ("metadata", None, "application/json", meta),
        ("data-worker.mjs", "data-worker.mjs", "application/javascript+module", script),
    ])
    res = call("PUT", f"/accounts/{ACCOUNT_ID}/workers/scripts/{WORKER_NAME}", body, ctype)
    if not res.get("success"):
        raise SystemExit("worker deploy failed: " + json.dumps(res)[:800])
    url = f"https://{WORKER_NAME}.{subdomain}.workers.dev"
    print(f"worker live: {url}")
    return url


def ensure_pages_project():
    res = call("GET", f"/accounts/{ACCOUNT_ID}/pages/projects/{PROJECT}")
    if res.get("success"):
        print(f"pages project exists: {PROJECT}")
        return
    res = call("POST", f"/accounts/{ACCOUNT_ID}/pages/projects",
               json.dumps({"name": PROJECT, "production_branch": "main"}).encode(),
               "application/json")
    if not res.get("success"):
        raise SystemExit("pages project create failed: " + json.dumps(res)[:800])
    print(f"pages project created: {PROJECT}")


def deploy_pages(worker_url):
    files = {}
    for name in sorted(os.listdir(PUBLIC)):
        p = os.path.join(PUBLIC, name)
        if not os.path.isfile(p):
            continue
        with open(p, "rb") as f:
            data = f.read()
        if name == "index.html":
            data = (data.decode()
                    .replace("__WORKER_URL__", worker_url)
                    .replace("__REPO_URL__", REPO_URL).encode())
        files["/" + name] = data
    manifest = {k: hashlib.sha256(v).hexdigest() for k, v in files.items()}
    parts = [("manifest", None, "application/json", json.dumps(manifest).encode())]
    for path, data in files.items():
        ctype = {"index.html": "text/html", "og.png": "image/png",
                 "favicon.svg": "image/svg+xml", "_headers": "text/plain"}.get(
                     os.path.basename(path), "application/octet-stream")
        parts.append((path, os.path.basename(path), ctype, data))
    body, ctype = multipart(parts)
    res = call("POST", f"/accounts/{ACCOUNT_ID}/pages/projects/{PROJECT}/deployments", body, ctype)
    if not res.get("success"):
        raise SystemExit("pages deploy failed: " + json.dumps(res)[:800])
    d = res["result"]
    print(f"pages live: {d['url']} (deployment {d['id']}, stage {d['latest_stage']['name']}:{d['latest_stage']['status']})")
    return d["url"]


def verify(url):
    req = urllib.request.Request(url, method="GET")
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=30) as resp:
        body = resp.read()
    print(f"verify {url} -> HTTP {resp.status}, {len(body)} bytes")
    return resp.status


def main():
    worker_url = deploy_worker()
    ensure_pages_project()
    pages_url = deploy_pages(worker_url)
    verify(worker_url + "/api/health")
    verify(pages_url)
    print(f"\nLIVE_URL={pages_url}")
    print(f"WORKER_URL={worker_url}")
    print(f"REPO_URL={REPO_URL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
