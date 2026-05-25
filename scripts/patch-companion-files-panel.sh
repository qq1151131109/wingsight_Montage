#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

export BUN_INSTALL="${BUN_INSTALL:-$HOME/.bun}"
export PATH="$BUN_INSTALL/bin:$PATH"

PACKAGE_DIRS=()
if [ -n "${WINGSIGHT_MONTAGE_COMPANION_PACKAGE_DIR:-}" ]; then
  PACKAGE_DIRS+=("$WINGSIGHT_MONTAGE_COMPANION_PACKAGE_DIR")
else
  while IFS= read -r dir; do
    PACKAGE_DIRS+=("$dir")
  done < <(find "$HOME/.bun/install/cache" -maxdepth 1 -type d -name 'the-companion@*' | sort -V)
  while IFS= read -r dir; do
    PACKAGE_DIRS+=("$dir")
  done < <(find /tmp -path '*/node_modules/the-companion/package.json' 2>/dev/null | sed 's#/package.json$##' | sort -u)
fi

if [ "${#PACKAGE_DIRS[@]}" -eq 0 ]; then
  echo "Cannot find installed the-companion package under ~/.bun/install/cache" >&2
  exit 1
fi

python_bin="$PROJECT_DIR/.venv/bin/python"
if [ ! -x "$python_bin" ]; then
  python_bin="python3"
fi

patched=0
for PACKAGE_DIR in "${PACKAGE_DIRS[@]}"; do
  FS_ROUTES="$PACKAGE_DIR/server/routes/fs-routes.ts"
  ROUTES_TS="$PACKAGE_DIR/server/routes.ts"
  INDEX_HTML="$PACKAGE_DIR/dist/index.html"
  PANEL_JS="$PACKAGE_DIR/dist/wingsight-files-panel.js"

  if [ ! -f "$FS_ROUTES" ] || [ ! -f "$ROUTES_TS" ] || [ ! -f "$INDEX_HTML" ]; then
    continue
  fi

  "$python_bin" - "$FS_ROUTES" "$ROUTES_TS" "$INDEX_HTML" "$PANEL_JS" "$PROJECT_DIR" <<'PY'
from pathlib import Path
import sys
import re
import json

fs_routes = Path(sys.argv[1])
routes_ts = Path(sys.argv[2])
index_html = Path(sys.argv[3])
panel_js = Path(sys.argv[4])
project_dir = Path(sys.argv[5]).resolve()
prompt_path = project_dir / "docs" / "WINGSIGHT_MONTAGE_USER_MODE_PROMPT.md"
user_prompt = prompt_path.read_text() if prompt_path.exists() else "你现在是 wingsight_montage 的非技术用户视频助手。"

fs_text = fs_routes.read_text()
fs_text = fs_text.replace('import { existsSync, createReadStream } from "node:fs";\n', "")

if "WINGSIGHT_MONTAGE_FILES_PANEL_IMPORTS" not in fs_text:
    fs_text = fs_text.replace(
        'import { readdir, readFile, stat, writeFile, mkdir } from "node:fs/promises";',
        'import { readdir, readFile, stat, writeFile, mkdir } from "node:fs/promises";\n'
        '// WINGSIGHT_MONTAGE_FILES_PANEL_IMPORTS\n'
        'import { basename, relative } from "node:path";',
    )

route_block = r'''

  // WINGSIGHT_MONTAGE_FILES_PANEL_ROUTES_START
  api.post("/fs/upload", async (c) => {
    const uploadDirRaw = c.req.query("dir") || join(process.cwd(), "projects", "uploads");
    const uploadDir = guardPath(uploadDirRaw, allowedBases());
    if (!uploadDir) return c.json({ error: "Path outside allowed directories" }, 403);
    try {
      await mkdir(uploadDir, { recursive: true });
      const form = await c.req.formData();
      const files = form.getAll("files").filter((item): item is File => item instanceof File);
      if (files.length === 0) return c.json({ error: "files required" }, 400);
      const saved: { name: string; path: string; relPath: string; size: number }[] = [];
      for (const file of files) {
        const safeName = basename(file.name).replace(/[\/\\]/g, "_");
        const target = join(uploadDir, safeName);
        const guardedTarget = guardPath(target, [uploadDir]);
        if (!guardedTarget) return c.json({ error: "Invalid file name" }, 400);
        const buffer = Buffer.from(await file.arrayBuffer());
        await writeFile(guardedTarget, buffer);
        saved.push({
          name: safeName,
          path: guardedTarget,
          relPath: relative(process.cwd(), guardedTarget) || safeName,
          size: buffer.length,
        });
      }
      return c.json({ ok: true, files: saved });
    } catch (e: unknown) {
      return c.json({ error: e instanceof Error ? e.message : "Cannot upload file" }, 500);
    }
  });

  api.get("/fs/download", async (c) => {
    const filePath = c.req.query("path");
    if (!filePath) return c.json({ error: "path required" }, 400);
    const absPath = guardPath(filePath, allowedBases());
    if (!absPath) return c.json({ error: "Path outside allowed directories" }, 403);
    try {
      const info = await stat(absPath);
      if (!info.isFile()) return c.json({ error: "Not a file" }, 400);
      const file = Bun.file(absPath);
      return new Response(file, {
        headers: {
          "Content-Type": file.type || "application/octet-stream",
          "Content-Disposition": `attachment; filename="${basename(absPath).replace(/"/g, "")}"`,
          "Cache-Control": "private, max-age=60",
        },
      });
    } catch (e: unknown) {
      return c.json({ error: e instanceof Error ? e.message : "File not found" }, 404);
    }
  });

  api.get("/fs/project-root", (c) => {
    return c.json({ cwd: process.cwd(), uploads: join(process.cwd(), "projects", "uploads") });
  });
  // WINGSIGHT_MONTAGE_FILES_PANEL_ROUTES_END
'''

if "WINGSIGHT_MONTAGE_FILES_PANEL_ROUTES_START" not in fs_text:
    marker = '  api.get("/fs/diff", (c) => {'
    fs_text = fs_text.replace(marker, route_block + "\n" + marker)

fs_routes.write_text(fs_text)

routes_text = routes_ts.read_text()
session_route = f'''  api.get("/sessions", (c) => {{
    const sessions = launcher.listSessions();
    const names = sessionNames.getAllNames();
    const bridgeStates = wsBridge.getAllSessions();
    const bridgeMap = new Map(bridgeStates.map((s) => [s.session_id, s]));
    const enriched = sessions.map((s) => {{
      const bridge = bridgeMap.get(s.sessionId);
      return {{
        ...s,
        // Bridge state is the source of truth for runtime cwd updates
        // (notably containerized sessions mapped back to host paths).
        cwd: bridge?.cwd || s.cwd,
        name: names[s.sessionId] ?? s.name,
        gitBranch: bridge?.git_branch || "",
        gitAhead: bridge?.git_ahead || 0,
        gitBehind: bridge?.git_behind || 0,
        totalLinesAdded: bridge?.total_lines_added || 0,
        totalLinesRemoved: bridge?.total_lines_removed || 0,
      }};
    }});
    // WINGSIGHT_MONTAGE_SESSION_FILTER_START
    const wingsightProjectRoot = {json.dumps(str(project_dir))};
    const wingsightVisibleSessions = enriched.filter((session) => {{
      const cwd = String(session.cwd || "").replace(/\\/+$/, "");
      return cwd === wingsightProjectRoot;
    }});
    return c.json(wingsightVisibleSessions);
    // WINGSIGHT_MONTAGE_SESSION_FILTER_END
  }});

  api.get("/sessions/:id",'''
routes_text, session_route_replacements = re.subn(
    r'  api\.get\("/sessions", \(c\) => \{.*?\n  api\.get\("/sessions/:id",',
    session_route,
    routes_text,
    count=1,
    flags=re.S,
)
if session_route_replacements != 1:
    raise RuntimeError("Could not patch /api/sessions route")
routes_ts.write_text(routes_text)

panel_js.write_text(f'''(() => {{
  const PROJECT_ROOT = {str(project_dir)!r};
  const REL_ROOT = "projects";
  const UPLOAD_DIR = PROJECT_ROOT + "/projects/uploads";
  const USER_PROMPT = {json.dumps(user_prompt, ensure_ascii=False)};
  const STYLE_ID = "wingsight-files-panel-style";
  const PANEL_ID = "wingsight-files-panel";
  const HIDDEN_CLASS = "wingsight-user-hidden";
  const MAX_DEPTH = 8;
  const state = {{
    tree: [],
    selected: new Set(),
    activeAbs: "",
    contextPanel: null,
  }};

  const api = {{
    async json(url, options) {{
      const res = await fetch(url, options);
      const data = await res.json().catch(() => ({{}}));
      if (!res.ok) throw new Error(data.error || res.statusText);
      return data;
    }},
  }};

  function injectStyle() {{
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      #${{PANEL_ID}} {{
        border: 1px solid var(--color-cc-border, #2a2a2a);
        border-radius: 12px;
        overflow: hidden;
        margin: 10px 10px 12px;
        background: var(--color-cc-card, #171717);
        color: var(--color-cc-fg, #e5e5e5);
        font-family: var(--font-sans-ui, ui-sans-serif, system-ui, sans-serif);
      }}
      #${{PANEL_ID}} .wf-head {{
        height: 38px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        padding: 0 8px 0 10px;
        border-bottom: 1px solid var(--color-cc-border, #2a2a2a);
        font-size: 12px;
        font-weight: 600;
      }}
      #${{PANEL_ID}} .wf-count {{
        color: var(--color-cc-muted, #8b8b8b);
        font-size: 11px;
        font-weight: 500;
        margin-left: 4px;
      }}
      #${{PANEL_ID}} .wf-actions {{
        display: flex;
        align-items: center;
        gap: 4px;
      }}
      #${{PANEL_ID}} .wf-btn {{
        width: 26px;
        height: 26px;
        display: inline-grid;
        place-items: center;
        border-radius: 7px;
        border: 1px solid var(--color-cc-border, #333);
        background: var(--color-cc-bg, #111);
        color: var(--color-cc-muted, #aaa);
        cursor: pointer;
        font-size: 12px;
        line-height: 1;
      }}
      #${{PANEL_ID}} .wf-btn:hover {{
        background: var(--color-cc-hover, #252525);
        color: var(--color-cc-fg, #fff);
      }}
      #${{PANEL_ID}} .wf-tree {{
        min-height: 340px;
        max-height: 52vh;
        overflow: auto;
        padding: 6px;
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        font-size: 11px;
      }}
      #${{PANEL_ID}} .wf-node {{
        width: 100%;
        min-height: 27px;
        display: grid;
        grid-template-columns: 16px minmax(0, 1fr) auto;
        align-items: center;
        gap: 6px;
        border: 0;
        border-radius: 7px;
        background: transparent;
        color: var(--color-cc-fg, #e5e5e5);
        text-align: left;
        cursor: pointer;
        padding: 0 6px;
      }}
      #${{PANEL_ID}} .wf-node:hover {{
        background: var(--color-cc-hover, #252525);
      }}
      #${{PANEL_ID}} .wf-node.wf-selected {{
        background: color-mix(in srgb, var(--color-cc-primary, #d97757) 18%, transparent);
        color: var(--color-cc-fg, #fff);
      }}
      #${{PANEL_ID}} .wf-name {{
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }}
      #${{PANEL_ID}} .wf-tag {{
        color: var(--color-cc-muted, #8b8b8b);
        font-family: var(--font-sans-ui, ui-sans-serif, system-ui, sans-serif);
        font-size: 10px;
      }}
      #${{PANEL_ID}} .wf-empty {{
        color: var(--color-cc-muted, #8b8b8b);
        padding: 12px 8px;
        font-size: 12px;
        line-height: 1.4;
      }}
      .${{HIDDEN_CLASS}} {{
        display: none !important;
      }}
    `;
    document.head.appendChild(style);
  }}

  function relPath(abs) {{
    if (!abs) return "";
    if (abs === PROJECT_ROOT) return ".";
    if (abs.startsWith(PROJECT_ROOT + "/")) return abs.slice(PROJECT_ROOT.length + 1);
    return abs;
  }}

  function extTag(name, type) {{
    if (type === "directory") return "dir";
    const ext = name.includes(".") ? name.split(".").pop() : "file";
    return (ext || "file").slice(0, 5);
  }}

  function iconFor(node) {{
    if (node.type === "directory") return "▾";
    const name = node.name.toLowerCase();
    if (name.match(/\\.(mp4|mov|webm|mkv)$/)) return "▶";
    if (name.match(/\\.(png|jpe?g|webp|gif|svg)$/)) return "◼";
    if (name.match(/\\.(mp3|wav|m4a|aac|flac)$/)) return "♪";
    return "◇";
  }}

  function flatten(nodes, depth = 0, out = []) {{
    for (const node of nodes || []) {{
      out.push({{ ...node, depth }});
      if (node.type === "directory" && depth < MAX_DEPTH) flatten(node.children || [], depth + 1, out);
    }}
    return out;
  }}

  function selectedPaths() {{
    return state.selected.size ? Array.from(state.selected) : (state.activeAbs ? [state.activeAbs] : []);
  }}

  function renderTree(container) {{
    const tree = container.querySelector(".wf-tree");
    const count = container.querySelector(".wf-count");
    count.textContent = String(state.selected.size);
    const flat = flatten(state.tree);
    if (!flat.length) {{
      tree.innerHTML = `<div class="wf-empty">No files yet. Use + to upload into projects/uploads.</div>`;
      return;
    }}
    tree.innerHTML = "";
    for (const node of flat) {{
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "wf-node" + (state.selected.has(node.path) ? " wf-selected" : "");
      btn.style.paddingLeft = `${{6 + node.depth * 15}}px`;
      btn.dataset.path = node.path;
      btn.dataset.type = node.type;
      btn.title = relPath(node.path);
      btn.innerHTML = `<span>${{iconFor(node)}}</span><span class="wf-name">${{node.name}}</span><span class="wf-tag">${{extTag(node.name, node.type)}}</span>`;
      tree.appendChild(btn);
    }}
  }}

  async function refresh(container) {{
    try {{
      const data = await api.json(`/api/fs/tree?path=${{encodeURIComponent(PROJECT_ROOT + "/projects")}}`);
      state.tree = [{{ name: "projects", path: PROJECT_ROOT + "/projects", type: "directory", children: data.tree || [] }}];
      renderTree(container);
    }} catch (error) {{
      container.querySelector(".wf-tree").innerHTML = `<div class="wf-empty">${{String(error.message || error)}}</div>`;
    }}
  }}

  function toast(text) {{
    let el = document.getElementById("wingsight-files-toast");
    if (!el) {{
      el = document.createElement("div");
      el.id = "wingsight-files-toast";
      el.style.cssText = "position:fixed;left:50%;bottom:18px;transform:translateX(-50%);z-index:99999;background:#111;color:white;padding:8px 12px;border-radius:8px;font:12px system-ui;box-shadow:0 8px 20px rgba(0,0,0,.2)";
      document.body.appendChild(el);
    }}
    el.textContent = text;
    el.style.opacity = "1";
    clearTimeout(el._timer);
    el._timer = setTimeout(() => (el.style.opacity = "0"), 1200);
  }}

  async function createUserSession() {{
    try {{
      toast("Creating session...");
      const session = await api.json("/api/sessions/create", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{
          backend: "codex",
          backendType: "codex",
          cwd: PROJECT_ROOT,
          permissionMode: "bypassPermissions",
        }}),
      }});
      const sessionId = session.sessionId;
      if (!sessionId) throw new Error("No session id returned");
      const name = `wingsight_montage 视频助手 ${{new Date().toLocaleString("zh-CN", {{ hour12: false }})}}`;
      await fetch(`/api/sessions/${{sessionId}}/name`, {{
        method: "PATCH",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ name }}),
      }}).catch(() => null);
      location.hash = `#/session/${{sessionId}}`;
      toast("Session created");
    }} catch (error) {{
      toast(String(error.message || error));
    }}
  }}

  function findComposer() {{
    const textareas = Array.from(document.querySelectorAll("textarea"));
    return textareas.find((el) => el.offsetParent !== null) || textareas[textareas.length - 1] || null;
  }}

  function insertMentions() {{
    const paths = selectedPaths().map((p) => "@" + relPath(p)).join(" ");
    if (!paths) return toast("No file selected");
    const input = findComposer();
    if (!input) return toast("Composer not found");
    const start = input.selectionStart ?? input.value.length;
    const end = input.selectionEnd ?? input.value.length;
    const prefix = input.value && start > 0 && !/\\s$/.test(input.value.slice(0, start)) ? " " : "";
    const next = input.value.slice(0, start) + prefix + paths + input.value.slice(end);
    input.value = next;
    input.dispatchEvent(new Event("input", {{ bubbles: true }}));
    input.focus();
    toast("Inserted @files");
  }}

  async function copyPaths() {{
    const paths = selectedPaths().map(relPath).join("\\n");
    if (!paths) return toast("No file selected");
    await navigator.clipboard.writeText(paths);
    toast("Paths copied");
  }}

  function downloadSelected() {{
    const paths = selectedPaths();
    if (!paths.length) return toast("No file selected");
    for (const path of paths) {{
      const a = document.createElement("a");
      a.href = `/api/fs/download?path=${{encodeURIComponent(path)}}`;
      a.download = path.split("/").pop() || "download";
      document.body.appendChild(a);
      a.click();
      a.remove();
    }}
    toast(paths.length > 1 ? "Downloading files" : "Downloading file");
  }}

  async function uploadFiles(input, container) {{
    if (!input.files || input.files.length === 0) return;
    const form = new FormData();
    for (const file of input.files) form.append("files", file);
    try {{
      const data = await api.json(`/api/fs/upload?dir=${{encodeURIComponent(UPLOAD_DIR)}}`, {{
        method: "POST",
        body: form,
      }});
      state.selected = new Set((data.files || []).map((file) => file.path));
      state.activeAbs = Array.from(state.selected)[0] || "";
      input.value = "";
      await refresh(container);
      toast("Uploaded");
    }} catch (error) {{
      toast(String(error.message || error));
    }}
  }}

  function createPanel() {{
    const panel = document.createElement("section");
    panel.id = PANEL_ID;
    panel.innerHTML = `
      <div class="wf-head">
        <span>Files <span class="wf-count">0</span></span>
        <div class="wf-actions">
          <button class="wf-btn" data-action="upload" title="Upload">+</button>
          <button class="wf-btn" data-action="download" title="Download">↓</button>
          <button class="wf-btn" data-action="mention" title="@ selected files">@</button>
          <button class="wf-btn" data-action="copy" title="Copy paths">⧉</button>
          <button class="wf-btn" data-action="refresh" title="Refresh">R</button>
          <input type="file" multiple accept="image/*,video/*,audio/*" hidden />
        </div>
      </div>
      <div class="wf-tree"><div class="wf-empty">Loading files...</div></div>
    `;
    const fileInput = panel.querySelector("input[type=file]");
    panel.addEventListener("click", (event) => {{
      const action = event.target.closest("[data-action]")?.dataset.action;
      if (action === "upload") fileInput.click();
      if (action === "download") downloadSelected();
      if (action === "mention") insertMentions();
      if (action === "copy") void copyPaths();
      if (action === "refresh") void refresh(panel);
      const node = event.target.closest(".wf-node");
      if (node) {{
        const path = node.dataset.path;
        state.activeAbs = path;
        if (node.dataset.type === "file") {{
          if (state.selected.has(path)) state.selected.delete(path);
          else state.selected.add(path);
        }}
        renderTree(panel);
      }}
    }});
    fileInput.addEventListener("change", () => void uploadFiles(fileInput, panel));
    void refresh(panel);
    return panel;
  }}

  function findContextPanel() {{
    const buttons = Array.from(document.querySelectorAll("button, [role=button]"));
    const contextButton = buttons.find((el) => (el.textContent || "").trim() === "Context");
    const fixedPanels = Array.from(document.querySelectorAll("div[class*='fixed'][class*='right'], aside, [aria-label*='Context']"));
    if (contextButton && !fixedPanels.length) contextButton.click();
    const candidates = Array.from(document.querySelectorAll("aside, div"));
    return candidates.find((el) => {{
      const text = (el.textContent || "").slice(0, 400);
      return text.includes("Project") && text.includes("Usage Limits") && text.includes("MCP Servers");
    }});
  }}

  function hideTechnicalContext(context) {{
    if (!context) return;
    const hideLabels = ["Usage Limits", "Git Branch", "GitHub PR", "Linear Issue", "Link Linear issue", "MCP Servers", "Customize panel"];
    const nodes = Array.from(context.querySelectorAll("button, [role=button]"));
    for (const node of nodes) {{
      const text = (node.textContent || "").trim();
      if (hideLabels.some((label) => text === label || text.startsWith(label + " "))) {{
        const target = node.closest(".border-t, [class*='border-t']") || node.closest("section") || node;
        if (!target.closest(`#${{PANEL_ID}}`)) target.classList.add(HIDDEN_CLASS);
      }}
    }}
  }}

  function hideTechnicalNavigation() {{
    for (const nav of Array.from(document.querySelectorAll("nav[aria-label='Navigation']"))) {{
      nav.classList.add(HIDDEN_CLASS);
    }}
    const labels = ["Prompts", "Integrations", "Environments", "Sandboxes", "Agents", "Settings", "Diffs"];
    for (const el of Array.from(document.querySelectorAll("button, a, [role=button]"))) {{
      const text = (el.textContent || "").trim();
      const aria = (el.getAttribute("aria-label") || "").trim();
      if (labels.some((label) => text === label || text.startsWith(label + " ") || aria === `${{label}} tab`)) {{
        el.classList.add(HIDDEN_CLASS);
        const row = el.closest("li, div");
        if (row && (row.textContent || "").length < 80) row.classList.add(HIDDEN_CLASS);
      }}
    }}
    for (const link of Array.from(document.querySelectorAll("a[href*='thecompanion'], a[href*='github.com/The-Vibe-Company']"))) {{
      const row = link.closest("div");
      if (row && (row.textContent || "").length < 80) row.classList.add(HIDDEN_CLASS);
      else link.classList.add(HIDDEN_CLASS);
    }}
    for (const el of Array.from(document.querySelectorAll("button, div"))) {{
      const text = (el.textContent || "").replace(/\\s+/g, " ").trim().toLowerCase();
      const aria = (el.getAttribute("aria-label") || "").trim();
      if (["resources", "workbench", "workspace"].includes(text)) {{
        el.classList.add(HIDDEN_CLASS);
      }}
      if (aria === "Toggle AI validation settings" || text === "auto") el.classList.add(HIDDEN_CLASS);
      if (text.startsWith("terminal /bin/") || text.startsWith("terminal/bin/")) el.classList.add(HIDDEN_CLASS);
      const isProtocolNoise =
        text.includes("codex protocol drift") ||
        text.includes("companion may need an update") ||
        text.includes("codex initialization failed") ||
        text.includes("unsupported incoming notification");
      if (isProtocolNoise && text.length < 500 && !el.closest("#root > div")) {{
        el.classList.add(HIDDEN_CLASS);
      }}
    }}
    for (const span of Array.from(document.querySelectorAll("span"))) {{
      const text = (span.textContent || "").trim();
      if (text === PROJECT_ROOT || text === "CX" || text === "CC") span.classList.add(HIDDEN_CLASS);
      if (text === "WORKBENCH" || text === "WORKSPACE" || text === "RESOURCES") {{
        const section = span.closest("section") || span;
        section.classList.add(HIDDEN_CLASS);
      }}
    }}
  }}

  function filterProjectSessions() {{
    for (const el of Array.from(document.querySelectorAll("button"))) {{
      const text = el.textContent || "";
      if (text.includes("/home/") && !text.includes(PROJECT_ROOT)) {{
        const row = el.parentElement;
        if (row && (row.textContent || "").length < 300) row.classList.add(HIDDEN_CLASS);
      }}
      const normalized = text.replace(/\\s+/g, " ").trim();
      if (/^SHENGLIN\\b/i.test(normalized)) {{
        const group = el.parentElement;
        if (group && (group.textContent || "").length < 120) group.classList.add(HIDDEN_CLASS);
      }}
    }}
  }}

  function wireNewSession() {{
    for (const button of Array.from(document.querySelectorAll("button"))) {{
      const text = (button.textContent || "").trim();
      const aria = (button.getAttribute("aria-label") || "").trim();
      if ((text === "New Session" || aria === "New Session") && !button.dataset.wingsightNewSession) {{
        button.dataset.wingsightNewSession = "1";
        button.addEventListener("click", (event) => {{
          event.preventDefault();
          event.stopPropagation();
          void createUserSession();
        }}, true);
      }}
    }}
  }}

  function applyUserMode(context) {{
    hideTechnicalNavigation();
    filterProjectSessions();
    wireNewSession();
    hideTechnicalContext(context);
  }}

  function mount() {{
    injectStyle();
    hideTechnicalNavigation();
    filterProjectSessions();
    wireNewSession();
    const context = findContextPanel();
    applyUserMode(context);
    if (context && !document.getElementById(PANEL_ID)) {{
      const panel = createPanel();
      const firstSection = Array.from(context.children).find((child) => (child.textContent || "").includes("Project"));
      if (firstSection) context.insertBefore(panel, firstSection);
      else context.prepend(panel);
    }}
  }}

  setInterval(mount, 1500);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();
}})();
''')

html = index_html.read_text()
html = re.sub(r"\s*<script src=\"/wingsight-files-panel\.js(?:\?v=\d+)?\"></script>\s*", "\n", html)
script_tag = '<script src="/wingsight-files-panel.js?v=4"></script>'
html = html.replace("</body>", f"    {script_tag}\n  </body>")
index_html.write_text(html)
PY

  patched=$((patched + 1))
  printf 'Patched Companion files panel in %s\n' "$PACKAGE_DIR"
done

if [ "$patched" -eq 0 ]; then
  echo "No patchable the-companion package layouts found" >&2
  exit 1
fi
