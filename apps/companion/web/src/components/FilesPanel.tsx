import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { EditorView } from "@codemirror/view";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, type FilePreview, type TreeNode } from "../api.js";
import { useStore } from "../store.js";
import { isAudioFile, isImageFile, isOfficeFile, isPdfFile, isVideoFile, langForPath, relPath } from "./file-view-utils.js";
import { isWingsightUserMode } from "../wingsight-user-mode.js";

interface FilesPanelProps {
  sessionId: string;
}

interface TreeEntryProps {
  node: TreeNode;
  depth: number;
  cwd: string;
  selectedPaths: Set<string>;
  onSelect: (path: string, event: React.MouseEvent<HTMLButtonElement>) => void;
}

function TreeEntry({ node, depth, cwd, selectedPaths, onSelect }: TreeEntryProps) {
  const [open, setOpen] = useState(isWingsightUserMode ? depth < 1 : depth < 2);

  if (node.type === "directory") {
    return (
      <div className="min-w-0 max-w-full overflow-hidden">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="w-full min-w-0 max-w-full flex items-center gap-1.5 py-2 pr-2 text-left text-xs text-cc-muted hover:text-cc-fg hover:bg-cc-hover rounded cursor-pointer overflow-hidden"
          style={{ paddingLeft: `${8 + depth * 12}px` }}
          aria-label={`Toggle ${relPath(cwd, node.path)}`}
        >
          <span className="w-3 shrink-0 inline-flex justify-center">{open ? "\u25BE" : "\u25B8"}</span>
          <span className="min-w-0 flex-1 truncate">{node.name}</span>
        </button>
        {open && node.children?.map((child) => (
          <TreeEntry
            key={child.path}
            node={child}
            depth={depth + 1}
            cwd={cwd}
            selectedPaths={selectedPaths}
            onSelect={onSelect}
          />
        ))}
      </div>
    );
  }

  const selected = selectedPaths.has(node.path);
  return (
    <button
      type="button"
      onClick={(event) => onSelect(node.path, event)}
      className={`block w-full min-w-0 max-w-full py-2 pr-2 text-left text-xs rounded truncate cursor-pointer overflow-hidden ${
        selected ? "bg-cc-active text-cc-fg" : "text-cc-muted hover:text-cc-fg hover:bg-cc-hover"
      }`}
      style={{ paddingLeft: `${26 + depth * 12}px` }}
      title={relPath(cwd, node.path)}
    >
      {node.name}
    </button>
  );
}

function FileContentViewer({ content, filePath, darkMode }: { content: string; filePath: string; darkMode: boolean }) {
  const extensions = useMemo(() => {
    const exts = [
      EditorView.lineWrapping,
      EditorView.contentAttributes.of({ "aria-label": "File content" }),
    ];
    const lang = langForPath(filePath);
    if (lang) exts.push(lang as never);
    return exts;
  }, [filePath]);

  return (
    <CodeMirror
      value={content}
      readOnly
      editable={false}
      extensions={extensions}
      theme={darkMode ? "dark" : "light"}
      basicSetup={{
        lineNumbers: true,
        foldGutter: true,
        highlightActiveLineGutter: false,
        highlightActiveLine: false,
        dropCursor: false,
        allowMultipleSelections: false,
      }}
      className="h-full text-sm"
      height="100%"
    />
  );
}

function isMarkdownFile(filePath: string): boolean {
  const ext = filePath.split(".").pop()?.toLowerCase() ?? "";
  return ["md", "markdown", "mdx"].includes(ext);
}

function MarkdownPreview({ content }: { content: string }) {
  return (
    <div className="h-full min-h-0 overflow-auto overscroll-contain bg-cc-bg px-5 py-4">
      <div className="prose prose-sm max-w-none dark:prose-invert prose-headings:text-cc-fg prose-p:text-cc-fg prose-li:text-cc-fg prose-strong:text-cc-fg prose-code:text-cc-fg prose-a:text-cc-accent">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>
    </div>
  );
}

function WordPreview({ preview }: { preview: Extract<FilePreview, { kind: "word" }> }) {
  return (
    <div className="h-full min-h-0 overflow-auto overscroll-contain bg-cc-bg p-4">
      <article
        className="mx-auto max-w-[720px] rounded bg-white px-6 py-5 text-sm leading-6 text-neutral-900 shadow-sm prose prose-sm prose-neutral max-w-none"
        dangerouslySetInnerHTML={{ __html: preview.html || "<p>这个文档没有可预览的文字内容。</p>" }}
      />
    </div>
  );
}

function SpreadsheetPreview({ preview }: { preview: Extract<FilePreview, { kind: "spreadsheet" }> }) {
  const [activeSheetName, setActiveSheetName] = useState(preview.sheets[0]?.name ?? "");
  const activeSheet = preview.sheets.find((sheet) => sheet.name === activeSheetName) ?? preview.sheets[0];

  useEffect(() => {
    setActiveSheetName(preview.sheets[0]?.name ?? "");
  }, [preview]);

  if (!activeSheet) {
    return (
      <div className="h-full flex items-center justify-center text-sm text-cc-muted">
        这个表格没有可预览的数据。
      </div>
    );
  }

  const maxColumns = Math.max(...activeSheet.rows.map((row) => row.length), 1);

  return (
    <div className="h-full min-h-0 flex flex-col bg-cc-bg">
      <div className="shrink-0 px-3 py-2 border-b border-cc-border flex items-center gap-1 overflow-x-auto">
        {preview.sheets.map((sheet) => (
          <button
            key={sheet.name}
            type="button"
            onClick={() => setActiveSheetName(sheet.name)}
            className={`shrink-0 px-2.5 py-1 rounded text-[11px] transition-colors cursor-pointer ${
              sheet.name === activeSheet.name
                ? "bg-cc-active text-cc-fg"
                : "text-cc-muted hover:text-cc-fg hover:bg-cc-hover"
            }`}
            title={`${sheet.rowCount} 行，${sheet.columnCount} 列`}
          >
            {sheet.name}
          </button>
        ))}
      </div>
      {preview.truncated && (
        <div className="shrink-0 px-3 py-1.5 text-[11px] text-cc-muted border-b border-cc-border">
          只显示前 200 行和前 50 列，完整文件请下载查看。
        </div>
      )}
      <div className="flex-1 min-h-0 overflow-auto">
        <table className="min-w-full border-collapse text-xs">
          <tbody>
            {activeSheet.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {Array.from({ length: maxColumns }).map((_, columnIndex) => (
                  <td
                    key={columnIndex}
                    className="max-w-[240px] border border-cc-border px-2 py-1.5 align-top text-cc-fg bg-cc-bg truncate"
                    title={row[columnIndex] ?? ""}
                  >
                    {row[columnIndex] ?? ""}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function OfficePreview({ preview }: { preview: FilePreview }) {
  if (preview.kind === "word") return <WordPreview preview={preview} />;
  return <SpreadsheetPreview preview={preview} />;
}

export function FilesPanel({ sessionId }: FilesPanelProps) {
  const darkMode = useStore((s) => s.darkMode);
  const cwd = useStore((s) =>
    s.sessions.get(sessionId)?.cwd
    || s.sdkSessions.find((sdk) => sdk.sessionId === sessionId)?.cwd
    || null,
  );

  const [tree, setTree] = useState<TreeNode[]>([]);
  const [loadingTree, setLoadingTree] = useState(true);
  const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null);
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
  const [lastSelectedPath, setLastSelectedPath] = useState<string | null>(null);
  const [filesRoot, setFilesRoot] = useState<string | null>(null);
  const [projectCwd, setProjectCwd] = useState<string | null>(null);
  const [uploadsDir, setUploadsDir] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>("");
  const [filePreview, setFilePreview] = useState<FilePreview | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const imageUrlRef = useRef<string | null>(null);
  const [loadingFile, setLoadingFile] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Keep ref in sync so unmount cleanup can access current value
  useEffect(() => { imageUrlRef.current = imageUrl; }, [imageUrl]);

  useEffect(() => {
    api.getProjectRoot().then((res) => {
      setFilesRoot(res.cwd);
      setProjectCwd(res.projectCwd);
      setUploadsDir(res.uploads);
    }).catch(() => {});
  }, []);

  const treeRoot = isWingsightUserMode ? filesRoot : cwd;
  const displayRoot = treeRoot || cwd || "";
  const isRawPreviewFile = useCallback((path: string) => (
    isImageFile(path) || isVideoFile(path) || isAudioFile(path) || isPdfFile(path)
  ), []);

  // Revoke object URL on component unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      if (imageUrlRef.current) URL.revokeObjectURL(imageUrlRef.current);
    };
  }, []);

  // Load the file tree when cwd changes
  useEffect(() => {
    if (!treeRoot) {
      setLoadingTree(false);
      return;
    }
    let cancelled = false;
    setLoadingTree(true);
    setError(null);
    api.getFileTree(treeRoot).then((res) => {
      if (cancelled) return;
      setTree(res.tree);
    }).catch((err) => {
      if (cancelled) return;
      setError(err instanceof Error ? err.message : "Failed to load file tree");
      setTree([]);
    }).finally(() => {
      if (!cancelled) setLoadingTree(false);
    });
    return () => { cancelled = true; };
  }, [treeRoot]);

  // Load file content (or image blob) when a file is selected
  useEffect(() => {
    if (!selectedFilePath) {
      setFileContent("");
      setFilePreview(null);
      setImageUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return null; });
      return;
    }
    let cancelled = false;
    setLoadingFile(true);
    setError(null);

    if (isOfficeFile(selectedFilePath)) {
      setFileContent("");
      setImageUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return null; });
      api.previewFile(selectedFilePath).then((res) => {
        if (cancelled) return;
        setFilePreview(res);
      }).catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to preview file");
        setFilePreview(null);
      }).finally(() => {
        if (!cancelled) setLoadingFile(false);
      });
      return;
    }

    if (isRawPreviewFile(selectedFilePath)) {
      setFileContent("");
      setFilePreview(null);
      api.getFileBlob(selectedFilePath).then((url) => {
        if (cancelled) { URL.revokeObjectURL(url); return; }
        setImageUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return url; });
      }).catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load image");
        setImageUrl(null);
      }).finally(() => {
        if (!cancelled) setLoadingFile(false);
      });
    } else {
      setFilePreview(null);
      setImageUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return null; });
      api.readFile(selectedFilePath).then((res) => {
        if (cancelled) return;
        setFileContent(res.content);
      }).catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to read file");
        setFileContent("");
      }).finally(() => {
        if (!cancelled) setLoadingFile(false);
      });
    }
    return () => {
      cancelled = true;
    };
  }, [isRawPreviewFile, selectedFilePath]);

  const handleBack = useCallback(() => {
    setSelectedFilePath(null);
    setFileContent("");
    setFilePreview(null);
    setImageUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return null; });
    setError(null);
  }, []);

  const handleRefresh = useCallback(() => {
    if (!treeRoot) return;
    setLoadingTree(true);
    setError(null);
    setSelectedFilePath(null);
    setSelectedPaths(new Set());
    setLastSelectedPath(null);
    setFileContent("");
    setFilePreview(null);
    setImageUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return null; });
    api.getFileTree(treeRoot).then((res) => {
      setTree(res.tree);
    }).catch((err) => {
      setError(err instanceof Error ? err.message : "Failed to load file tree");
      setTree([]);
    }).finally(() => {
      setLoadingTree(false);
    });
  }, [treeRoot]);

  const reloadTree = useCallback(() => {
    if (!treeRoot) return;
    setLoadingTree(true);
    setError(null);
    api.getFileTree(treeRoot).then((res) => {
      setTree(res.tree);
    }).catch((err) => {
      setError(err instanceof Error ? err.message : "Failed to load file tree");
      setTree([]);
    }).finally(() => {
      setLoadingTree(false);
    });
  }, [treeRoot]);

  const selectedList = useMemo(() => Array.from(selectedPaths), [selectedPaths]);
  const relSelectedList = useMemo(
    () => selectedList.map((path) => relPath(displayRoot, path)),
    [displayRoot, selectedList],
  );
  const agentPathRoot = isWingsightUserMode ? (projectCwd || cwd || displayRoot) : displayRoot;
  const agentSelectedList = useMemo(
    () => selectedList.map((path) => relPath(agentPathRoot, path)),
    [agentPathRoot, selectedList],
  );
  const fileOrder = useMemo(() => {
    const paths: string[] = [];
    const walk = (nodes: TreeNode[]) => {
      for (const node of nodes) {
        if (node.type === "file") paths.push(node.path);
        else if (node.children) walk(node.children);
      }
    };
    walk(tree);
    return paths;
  }, [tree]);

  const handleSelectPath = useCallback((path: string, event: React.MouseEvent<HTMLButtonElement>) => {
    setSelectedFilePath(path);
    setLastSelectedPath(path);
    setSelectedPaths((prev) => {
      if (event.shiftKey && lastSelectedPath) {
        const start = fileOrder.indexOf(lastSelectedPath);
        const end = fileOrder.indexOf(path);
        if (start !== -1 && end !== -1) {
          const [from, to] = start < end ? [start, end] : [end, start];
          return new Set(fileOrder.slice(from, to + 1));
        }
      }

      if (event.ctrlKey || event.metaKey) {
        const next = new Set(prev);
        if (next.has(path)) next.delete(path);
        else next.add(path);
        return next;
      }

      return new Set([path]);
    });
  }, [fileOrder, lastSelectedPath]);

  const handleMention = useCallback(() => {
    if (!agentSelectedList.length) return;
    window.dispatchEvent(new CustomEvent("companion:insert-text", {
      detail: {
        sessionId,
        text: agentSelectedList.map((path) => `@${path}`).join(" "),
      },
    }));
  }, [agentSelectedList, sessionId]);

  const handleCopy = useCallback(async () => {
    if (!agentSelectedList.length) return;
    await navigator.clipboard.writeText(agentSelectedList.join("\n"));
  }, [agentSelectedList]);

  const handleDownload = useCallback(() => {
    for (const path of selectedList) {
      const a = document.createElement("a");
      a.href = `/api/fs/download?path=${encodeURIComponent(path)}`;
      a.download = path.split("/").pop() || "download";
      document.body.appendChild(a);
      a.click();
      a.remove();
    }
  }, [selectedList]);

  const handleDownloadFile = useCallback((path: string) => {
    const a = document.createElement("a");
    a.href = `/api/fs/download?path=${encodeURIComponent(path)}`;
    a.download = path.split("/").pop() || "download";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }, []);

  const handleUpload = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    if (!files.length || !uploadsDir) return;
    try {
      const res = await api.uploadFiles(uploadsDir, files);
      setSelectedPaths(new Set(res.files.map((file) => file.path)));
      setSelectedFilePath(res.files[0]?.path || null);
      setLastSelectedPath(res.files[0]?.path || null);
      reloadTree();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload files");
    }
  }, [reloadTree, uploadsDir]);

  // No cwd — waiting for session
  if (!treeRoot) {
    return (
      <div className="h-full flex items-center justify-center p-4 text-sm text-cc-muted">
        Loading files...
      </div>
    );
  }

  // ── Desktop layout: side-by-side ──
  // ── Mobile layout: master/detail (tree OR file viewer) ──

  const treePanel = (
    <div className="h-full min-h-0 min-w-0 max-w-full flex flex-col overflow-hidden">
      <div className="shrink-0 min-w-0 px-3 py-2 border-b border-cc-border flex items-center justify-between gap-2 overflow-hidden">
        <span className="min-w-0 truncate text-xs text-cc-muted font-medium">Files <span className="text-[10px]">{selectedPaths.size}</span></span>
        <div className="shrink-0 flex items-center gap-1">
          <label className="w-7 h-7 inline-flex items-center justify-center rounded text-cc-muted hover:text-cc-fg hover:bg-cc-hover cursor-pointer" title="Upload">
            +
            <input type="file" multiple className="hidden" onChange={handleUpload} />
          </label>
          <button type="button" onClick={handleDownload} disabled={!selectedPaths.size} className="w-7 h-7 rounded text-cc-muted hover:text-cc-fg hover:bg-cc-hover disabled:opacity-30 cursor-pointer" title="Download">↓</button>
          <button type="button" onClick={handleMention} disabled={!selectedPaths.size} className="w-7 h-7 rounded text-cc-muted hover:text-cc-fg hover:bg-cc-hover disabled:opacity-30 cursor-pointer" title="@ selected files">@</button>
          <button type="button" onClick={handleCopy} disabled={!selectedPaths.size} className="w-7 h-7 rounded text-cc-muted hover:text-cc-fg hover:bg-cc-hover disabled:opacity-30 cursor-pointer" title="Copy paths">⧉</button>
          <button
            type="button"
            onClick={handleRefresh}
            disabled={loadingTree}
            className="w-7 h-7 rounded text-cc-muted hover:text-cc-fg hover:bg-cc-hover disabled:opacity-50 transition-colors cursor-pointer"
            aria-label="刷新文件列表"
            title="刷新"
          >
            {loadingTree ? (
              <span className="text-[11px] leading-none">...</span>
            ) : (
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" className="w-4 h-4">
                <path d="M13 3.5v3h-3" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M12.1 6.5A4.5 4.5 0 104.2 11" strokeLinecap="round" />
                <path d="M3 12.5v-3h3" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M3.9 9.5A4.5 4.5 0 0011.8 5" strokeLinecap="round" />
              </svg>
            )}
          </button>
        </div>
      </div>
      <div className="flex-1 min-h-0 min-w-0 max-w-full overflow-auto overscroll-contain p-1.5">
        {loadingTree && <div className="px-2 py-2 text-xs text-cc-muted">Loading files...</div>}
        {!loadingTree && tree.length === 0 && !error && (
          <div className="px-2 py-2 text-xs text-cc-muted">No files found.</div>
        )}
        {!loadingTree && error && !selectedFilePath && (
          <div className="m-2 px-3 py-2 rounded-lg bg-cc-error/10 border border-cc-error/30 text-xs text-cc-error">
            {error}
            <button
              type="button"
              onClick={handleRefresh}
              className="ml-2 underline hover:no-underline cursor-pointer"
            >
              Retry
            </button>
          </div>
        )}
        {!loadingTree && tree.map((node) => (
          <TreeEntry
            key={node.path}
            node={node}
            depth={0}
            cwd={displayRoot}
            selectedPaths={selectedPaths}
            onSelect={handleSelectPath}
          />
        ))}
      </div>
    </div>
  );

  const fileViewer = selectedFilePath ? (
    <div className="h-full flex-1 min-h-0 flex flex-col overflow-hidden">
      <div className="shrink-0 px-3 py-2 border-b border-cc-border flex items-center gap-2">
        {/* Back button — always visible on mobile, hidden on desktop */}
        <button
          type="button"
          onClick={handleBack}
          className="sm:hidden flex items-center justify-center w-8 h-8 rounded text-cc-muted hover:text-cc-fg hover:bg-cc-hover transition-colors cursor-pointer shrink-0"
          aria-label="Back to file tree"
        >
          <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
            <path fillRule="evenodd" d="M12.79 5.23a.75.75 0 01-.02 1.06L8.832 10l3.938 3.71a.75.75 0 11-1.04 1.08l-4.5-4.25a.75.75 0 010-1.08l4.5-4.25a.75.75 0 011.06.02z" clipRule="evenodd" />
          </svg>
        </button>
        <p className="text-[11px] text-cc-muted truncate min-w-0 flex-1">{relPath(displayRoot, selectedFilePath)}</p>
        <button
          type="button"
          onClick={() => handleDownloadFile(selectedFilePath)}
          className="shrink-0 px-2 py-1 rounded text-[11px] text-cc-muted hover:text-cc-fg hover:bg-cc-hover transition-colors cursor-pointer"
          title="下载"
        >
          下载
        </button>
      </div>
      {error && (
        <div className="m-3 px-3 py-2 rounded-lg bg-cc-error/10 border border-cc-error/30 text-xs text-cc-error">
          {error}
        </div>
      )}
      <div className="flex-1 min-h-0 overflow-hidden">
        {loadingFile ? (
          <div className="h-full flex items-center justify-center text-sm text-cc-muted">Loading file...</div>
        ) : imageUrl && isImageFile(selectedFilePath) ? (
          <div className="h-full flex items-center justify-center p-4 bg-cc-bg overflow-auto">
            <img
              src={imageUrl}
              alt={relPath(displayRoot, selectedFilePath)}
              className="max-w-full max-h-full object-contain rounded"
            />
          </div>
        ) : imageUrl && isVideoFile(selectedFilePath) ? (
          <div className="h-full flex items-center justify-center p-3 bg-cc-bg overflow-auto">
            <video src={imageUrl} controls className="max-w-full max-h-full rounded" />
          </div>
        ) : imageUrl && isAudioFile(selectedFilePath) ? (
          <div className="h-full flex items-center justify-center p-4 bg-cc-bg">
            <audio src={imageUrl} controls className="w-full" />
          </div>
        ) : imageUrl && isPdfFile(selectedFilePath) ? (
          <iframe
            src={imageUrl}
            title={relPath(displayRoot, selectedFilePath)}
            className="w-full h-full bg-white"
          />
        ) : filePreview && isOfficeFile(selectedFilePath) ? (
          <OfficePreview preview={filePreview} />
        ) : isOfficeFile(selectedFilePath) ? (
          <div className="h-full flex items-center justify-center p-4 bg-cc-bg">
            <div className="max-w-[280px] text-center space-y-3">
              <div className="text-sm font-medium text-cc-fg">预览失败</div>
              <div className="text-xs text-cc-muted leading-relaxed">
                这个文件暂时不能直接预览，可以先下载后用 Word、Excel 或 WPS 打开。
              </div>
              <button
                type="button"
                onClick={() => handleDownloadFile(selectedFilePath)}
                className="px-3 py-1.5 rounded-md bg-cc-primary text-white text-xs hover:bg-cc-primary-hover transition-colors cursor-pointer"
              >
                下载文件
              </button>
            </div>
          </div>
        ) : isMarkdownFile(selectedFilePath) ? (
          <MarkdownPreview content={fileContent} />
        ) : (
          <FileContentViewer content={fileContent} filePath={selectedFilePath} darkMode={darkMode} />
        )}
      </div>
    </div>
  ) : null;

  if (isWingsightUserMode) {
    return (
      <div className="h-full min-h-0 min-w-0 max-w-full flex flex-col bg-cc-bg overflow-hidden">
        <div className={selectedFilePath ? "min-h-0 min-w-0 max-w-full flex-[0_0_52%] overflow-hidden border-b border-cc-border" : "min-h-0 min-w-0 max-w-full flex-1 overflow-hidden"}>
          {treePanel}
        </div>
        {selectedFilePath && (
          <div className="min-h-0 flex-1 flex flex-col overflow-hidden">
            {fileViewer}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="h-full min-h-0 flex bg-cc-bg">
      {/* Desktop: side-by-side */}
      <aside className="hidden sm:flex w-[240px] shrink-0 border-r border-cc-border bg-cc-sidebar/60 flex-col min-h-0">
        {treePanel}
      </aside>
      <div className="hidden sm:flex flex-1 min-h-0 flex-col">
        {fileViewer || (
          <div className="h-full flex items-center justify-center text-sm text-cc-muted">
            Select a file to view its contents.
          </div>
        )}
      </div>

      {/* Mobile: master/detail */}
      <div className="flex sm:hidden flex-1 min-h-0 flex-col">
        {selectedFilePath ? fileViewer : treePanel}
      </div>
    </div>
  );
}
