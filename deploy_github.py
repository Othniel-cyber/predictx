import os
import base64
import requests
import fnmatch
import sys

import os
TOKEN = os.environ.get("GITHUB_TOKEN") or open("prompt.txt", "r").read().strip()
OWNER = "Othniel-cyber"
REPO = "predictx"
HEADERS = {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github+json"}
API = "https://api.github.com"

ROOT = os.path.dirname(os.path.abspath(__file__))

GITIGNORE_PATTERNS = []
gitignore_path = os.path.join(ROOT, ".gitignore")
if os.path.exists(gitignore_path):
    for line in open(gitignore_path):
        line = line.strip()
        if line and not line.startswith("#"):
            GITIGNORE_PATTERNS.append(line)

def is_ignored(path):
    rel = os.path.relpath(path, ROOT).replace("\\", "/")
    parts = rel.split("/")
    for pat in GITIGNORE_PATTERNS:
        p = pat.rstrip("/")
        # Match basename (e.g. "venv" matches "backend/venv")
        if fnmatch.fnmatch(os.path.basename(path), p):
            return True
        # Match any path segment (e.g. "venv" matches "backend/venv/Scripts")
        if any(fnmatch.fnmatch(part, p) for part in parts):
            return True
        # Match relative path
        if fnmatch.fnmatch(rel, p):
            return True
        # Match directory prefix
        if rel.startswith(p + "/") or rel == p:
            return True
        # Match wildcard patterns like "*.json", "*.pyc"
        if fnmatch.fnmatch(rel, pat):
            return True
    return False

# 1. Create repo or get base SHA
print("Setting up repository...", flush=True)
r = requests.post(f"{API}/user/repos", json={"name": REPO, "private": False, "auto_init": True}, headers=HEADERS, timeout=30)
if r.status_code == 201:
    print("Repository created", flush=True)
elif r.status_code == 422:
    print("Repository already exists", flush=True)

# 2. Get default branch SHA
r = requests.get(f"{API}/repos/{OWNER}/{REPO}/git/refs/heads/main", headers=HEADERS, timeout=30)
if r.status_code != 200:
    r = requests.get(f"{API}/repos/{OWNER}/{REPO}/git/refs/heads/master", headers=HEADERS, timeout=30)
if r.status_code != 200:
    print("Could not get branch ref", flush=True)
    exit(1)
base_sha = r.json()["object"]["sha"]
print(f"Base SHA: {base_sha[:8]}", flush=True)

# 3. Collect files
files = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    if ".git" in dirnames:
        dirnames.remove(".git")
    dirnames[:] = [d for d in dirnames if not is_ignored(os.path.join(dirpath, d))]
    for f in filenames:
        full = os.path.join(dirpath, f)
        if not is_ignored(full):
            rel = os.path.relpath(full, ROOT).replace("\\", "/")
            files.append((rel, full))

print(f"Uploading {len(files)} files...", flush=True)

# 4. Create blobs for all files
blobs = []
count = 0
for rel, full in files:
    with open(full, "rb") as fh:
        content = fh.read()
    if len(content) > 1024 * 1024:
        print(f"  Skipping {rel} (too large)", flush=True)
        continue
    try:
        text = content.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        encoding = "base64"
        text = base64.b64encode(content).decode("ascii")
    
    r = requests.post(f"{API}/repos/{OWNER}/{REPO}/git/blobs", json={"content": text, "encoding": encoding}, headers=HEADERS, timeout=30)
    if r.status_code == 201:
        blobs.append({"path": rel, "mode": "100644", "type": "blob", "sha": r.json()["sha"]})
        count += 1
        if count % 20 == 0:
            print(f"  {count}/{len(files)} blobs created", flush=True)
    else:
        print(f"  FAIL {rel}: {r.status_code}", flush=True)
print(f"  {count} blobs total", flush=True)

# 5. Create tree
print("Creating tree...", flush=True)
r = requests.post(f"{API}/repos/{OWNER}/{REPO}/git/trees", json={"base_tree": base_sha, "tree": blobs}, headers=HEADERS, timeout=30)
if r.status_code != 201:
    print(f"Error creating tree: {r.status_code} {r.text[:200]}", flush=True)
    exit(1)
tree_sha = r.json()["sha"]

# 6. Create commit
print("Creating commit...", flush=True)
r = requests.post(f"{API}/repos/{OWNER}/{REPO}/git/commits", json={
    "message": "Initial commit - PredictX",
    "tree": tree_sha,
    "parents": [base_sha]
}, headers=HEADERS, timeout=30)
if r.status_code != 201:
    print(f"Error creating commit: {r.status_code} {r.text[:200]}", flush=True)
    exit(1)
commit_sha = r.json()["sha"]

# 7. Update branch
print("Updating main branch...", flush=True)
r = requests.patch(f"{API}/repos/{OWNER}/{REPO}/git/refs/heads/main", json={"sha": commit_sha, "force": True}, headers=HEADERS, timeout=30)
if r.status_code == 200:
    print(f"SUCCESS! https://github.com/{OWNER}/{REPO}", flush=True)
else:
    print(f"Error updating branch: {r.status_code} {r.text[:200]}", flush=True)