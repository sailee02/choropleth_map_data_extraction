# Worktree “Apply to current branch” fix and safe merge guide

## 1) Why `/Downloads` instead of `/Users/sshirodkar/Downloads`?

**What’s going on:**  
Cursor’s “Apply to current branch” is trying to write to:

- **Wrong:** `/Downloads/choropleth_map_data_extraction/...` (root of the disk)
- **Right:** `/Users/sshirodkar/Downloads/choropleth_map_data_extraction/...` (your home Downloads)

So the **main repo path** Cursor uses is missing the `Users/<username>` part. Common causes:

- The **main repo** was opened or registered with a **relative** path (e.g. `Downloads/choropleth_map_data_extraction`) and Cursor later resolves it from the wrong root (e.g. filesystem root).
- A **workspace / folder** setting stores something like `~/Downloads/...` and the `~` is not expanded, or gets replaced with nothing, so it becomes `/Downloads/...`.
- Cursor’s internal “main branch location” or “linked folder” was set from a context where the path was stored without the full home prefix.

**How to fix the workspace path so Apply can work:**

1. **Always open the main repo by full path**
   - Use **File → Open Folder** (or **Open**).
   - Choose the **main** repo, e.g.:
     - `/Users/sshirodkar/Downloads/choropleth_map_data_extraction`
   - Do **not** rely on a path that looks like `Downloads/...` or `~/Downloads/...` unless you’ve confirmed Cursor resolves it to the full path.

2. **If you use a Cursor “workspace” or multi-root**
   - Remove any root that points to `Downloads/...` or `~/Downloads/...`.
   - Add the main repo again using **full path**:  
     `/Users/sshirodkar/Downloads/choropleth_map_data_extraction`.

3. **Reattach so Cursor knows “main” correctly**
   - Open the **main** repo folder (full path above) in Cursor.
   - Then use **File → Add Folder to Workspace** and add your worktree, e.g.:  
     `/Users/sshirodkar/.cursor/worktrees/choropleth_map_data_extraction/wkj`
   - Or the other way: open the worktree first, then add the main repo with its **full path**.
   - The important part is that the “main” folder in the workspace is the real main repo at full path, so Apply writes there instead of `/Downloads/...`.

4. **If Apply still writes to `/Downloads`**
   - Report to Cursor: the app is resolving the main repo path incorrectly (bug). Use the terminal flow below so you don’t depend on Apply.

---

## 2) Exact steps in Cursor so “Apply” can work

Do this so the **target** of Apply is the real main repo, not `/Downloads/...`.

1. **Close any Cursor window** that has only the worktree or a wrong path.
2. **Open the main repo by full path**
   - **File → Open Folder**
   - Navigate to:  
     **`/Users/sshirodkar/Downloads/choropleth_map_data_extraction`**  
   - Click **Open**.
3. **Add the worktree to the same workspace (optional but helpful)**
   - **File → Add Folder to Workspace**
   - Add:  
     **`/Users/sshirodkar/.cursor/worktrees/choropleth_map_data_extraction/wkj`**
   - Save the workspace if you want (File → Save Workspace As).
4. **Do your Apply from the worktree**
   - In the worktree, make sure your changes are as you want (e.g. committed or staged).
   - Use **Apply to current branch** (or equivalent) again.
   - Cursor should now apply **into** `/Users/sshirodkar/Downloads/choropleth_map_data_extraction` because that’s the folder you opened with full path.

If it **still** tries to write to `/Downloads/...`, the bug is in how Cursor stores or resolves the “main” path; use the terminal flow below and report the path bug to Cursor.

---

## 3) Terminal: bring worktree changes into main (even if Apply keeps failing)

All commands assume **macOS** and **git worktrees**. Run from a terminal (e.g. Terminal.app or Cursor’s terminal).

### Step 0: Where things are

- **Main repo:**  
  `/Users/sshirodkar/Downloads/choropleth_map_data_extraction`
- **This worktree:**  
  `/Users/sshirodkar/.cursor/worktrees/choropleth_map_data_extraction/wkj`

### Step 1: Backup (no changes lost)

**Option A – Commit in worktree (recommended)**  
If you’re okay committing in the worktree:

```bash
cd /Users/sshirodkar/.cursor/worktrees/choropleth_map_data_extraction/wkj
git status
git add -A
git commit -m "WIP: worktree changes before applying to main"
git log -1 --oneline
```

**Option B – Patch export (no commit)**  
If you don’t want to commit in the worktree yet:

```bash
cd /Users/sshirodkar/.cursor/worktrees/choropleth_map_data_extraction/wkj
git status
git diff > /tmp/wkj-worktree-changes.patch
git diff --cached >> /tmp/wkj-worktree-changes.patch
# Optional: also capture untracked files (list them)
git status --short > /tmp/wkj-worktree-status.txt
```

**Optional extra – branch in main that mirrors worktree**

```bash
cd /Users/sshirodkar/Downloads/choropleth_map_data_extraction
git fetch . d16ae918:refs/heads/backup-wkj-$(date +%Y%m%d) 2>/dev/null || true
```

(Only works if worktree’s HEAD is a commit; if detached, use Step 1 Option A first so you have a commit to merge.)

### Step 2: See worktree list and status

```bash
cd /Users/sshirodkar/.cursor/worktrees/choropleth_map_data_extraction/wkj
git worktree list
git status -sb
git branch -a
git log -1 --oneline
```

### Step 3: Commit in worktree (if you didn’t in Step 1)

```bash
cd /Users/sshirodkar/.cursor/worktrees/choropleth_map_data_extraction/wkj
git add backend/utils/overlay_preview.py frontend/src/components/AlaskaCountySelector.jsx frontend/src/components/ConusCountySelector.jsx
# Add any other files you care about (omit __pycache__, large data, secrets)
git status
git commit -m "Apply overlay and selector fixes from worktree"
WORKTREE_COMMIT=$(git rev-parse HEAD)
echo "Worktree commit: $WORKTREE_COMMIT"
```

If you already committed in Step 1, just run:

```bash
WORKTREE_COMMIT=$(git rev-parse HEAD)
echo "Worktree commit: $WORKTREE_COMMIT"
```

### Step 4: Merge worktree commit into main

```bash
cd /Users/sshirodkar/Downloads/choropleth_map_data_extraction
git status
git checkout main
git pull origin main   # if you use a remote
git merge $WORKTREE_COMMIT -m "Merge worktree wkj changes into main"
# If you didn’t set WORKTREE_COMMIT in this shell:
# git merge <paste the commit hash from worktree>
```

**If merge has conflicts:** resolve in main, then:

```bash
git add -A
git commit -m "Merge worktree wkj: resolve conflicts"
```

### Alternative: Cherry-pick instead of merge

If you prefer to bring only the worktree commit(s) into main:

```bash
cd /Users/sshirodkar/Downloads/choropleth_map_data_extraction
git checkout main
git pull origin main   # if you use a remote
git cherry-pick $WORKTREE_COMMIT
# If conflicts:
# Fix files, then: git add -A && git cherry-pick --continue
```

### Step 5: Confirm

```bash
cd /Users/sshirodkar/Downloads/choropleth_map_data_extraction
git log -3 --oneline
git status
```

---

## 4) One-shot copy-paste flow (with backup)

Run these in order. Uses **commit** as backup and **merge** into main.

```bash
# --- Worktree: backup and commit ---
cd /Users/sshirodkar/.cursor/worktrees/choropleth_map_data_extraction/wkj
git add backend/utils/overlay_preview.py frontend/src/components/AlaskaCountySelector.jsx frontend/src/components/ConusCountySelector.jsx frontend/src/pages/Upload.jsx
git status
git commit -m "WIP: apply worktree changes for main" || true
WORKTREE_COMMIT=$(git rev-parse HEAD)
echo "Backup commit: $WORKTREE_COMMIT"

# --- Main: merge ---
cd /Users/sshirodkar/Downloads/choropleth_map_data_extraction
git checkout main
git merge $WORKTREE_COMMIT -m "Merge worktree wkj into main"

# --- Verify ---
git log -2 --oneline
```

Adjust the `git add` list to match the files you actually changed. Add other paths as needed; omit `__pycache__`, `node_modules`, and large/generated data.

---

## Summary

| Goal | Action |
|------|--------|
| Fix Cursor writing to `/Downloads` | Open main repo with **full path** `/Users/sshirodkar/Downloads/choropleth_map_data_extraction` and (if needed) add worktree to same workspace. |
| Make “Apply to current branch” work | Same: main repo opened by full path, then use Apply from worktree. |
| Don’t rely on Apply | Use terminal: commit in worktree → in main run `git merge <worktree-commit>`. |
| No changes lost | Commit in worktree and/or save a patch with `git diff > /tmp/wkj-worktree-changes.patch` before switching/merging. |
