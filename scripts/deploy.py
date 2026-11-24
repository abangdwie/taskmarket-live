#!/usr/bin/env python3
"""One-command deploy for taskmarket-live (Cloudflare Pages + _worker.js).

Usage:  python3 scripts/deploy.py
Auth:   token comes from the custom.cloudflare-direct connection (Secure Vault
        surrogate). The script passes it to wrangler as CLOUDFLARE_API_TOKEN;
        no token is stored in this file.
Steps:  1. `wrangler pages deploy public` (uploads the static site + the
           Pages worker in public/_worker.js, which serves /api/data)
        2. verify the live site, /api/health and /api/data
        3. print the live URLs
Note: the Cloudflare direct-upload API was tried first (Nov 2026) and silently
dropped every file (deployments reported success but served 404); wrangler is
the reliable path — do not switch back without re-verifying a live file.
"""
import json
import os
import subprocess
import sys
import urllib.request

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import dynamic_credential_entry

ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "b15d3ea349d6597d81ef1b0bd4d08032")
PROJECT = "taskmarket-live"
REPO_URL = "https://github.com/abangdwie/taskmarket-live"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LIVE_URL = f"https://{PROJECT}.pages.dev"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


def verify(url):
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=60) as resp:
            body = resp.read()
        print(f"verify {url} -> HTTP {resp.status}, {len(body)} bytes")
        return resp.status, body
    except urllib.error.HTTPError as e:
        print(f"verify {url} -> HTTP {e.code} (may need a moment to propagate)")
        return e.code, b""


def main():
    entry = dynamic_credential_entry("custom.cloudflare-direct", "access_token")
    env = dict(os.environ)
    env["CLOUDFLARE_API_TOKEN"] = entry["surrogate"]
    env["CLOUDFLARE_ACCOUNT_ID"] = ACCOUNT_ID
    cmd = ["npx", "-y", "wrangler@4", "pages", "deploy", "public",
           "--project-name", PROJECT, "--commit-dirty=true"]
    print("running:", " ".join(cmd))
    r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    sys.stdout.write(r.stdout[-3000:])
    sys.stderr.write(r.stderr[-2000:])
    if r.returncode != 0:
        raise SystemExit(f"wrangler deploy failed (exit {r.returncode})")
    verify(LIVE_URL + "/api/health")
    status, body = verify(LIVE_URL)
    if status != 200:
        print("WARNING: homepage did not return 200 — check the deployment before submitting")
    print(f"\nLIVE_URL={LIVE_URL}")
    print(f"DATA_URL={LIVE_URL}/api/data")
    print(f"REPO_URL={REPO_URL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
