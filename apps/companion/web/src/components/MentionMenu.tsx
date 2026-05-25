import type { SavedPrompt } from "../api.js";

interface MentionMenuProps {
  open: boolean;
  loading: boolean;
  prompts: SavedPrompt[];
  selectedIndex: number;
  onSelect: (prompt: SavedPrompt) => void;
  onDelete?: (prompt: SavedPrompt) => void;
  menuRef: React.RefObject<HTMLDivElement | null>;
  className?: string;
}

export function MentionMenu({
  open,
  loading,
  prompts,
  selectedIndex,
  onSelect,
  onDelete,
  menuRef,
  className = "",
}: MentionMenuProps) {
  if (!open) return null;

  return (
    <div
      ref={menuRef}
      className={`max-h-[240px] overflow-y-auto bg-cc-card border border-cc-border rounded-[10px] shadow-lg z-20 py-1 ${className}`}
    >
      {loading ? (
        <div className="px-3 py-2 text-[12px] text-cc-muted">
          Searching prompts...
        </div>
      ) : prompts.length > 0 ? (
        prompts.map((prompt, i) => (
          <div
            key={prompt.id}
            data-prompt-index={i}
            className={`w-full flex items-center gap-1 transition-colors ${
              i === selectedIndex
                ? "bg-cc-hover"
                : "hover:bg-cc-hover/50"
            }`}
          >
            <button
              type="button"
              onClick={() => onSelect(prompt)}
              className="min-w-0 flex-1 px-3 py-2 text-left flex items-center gap-2.5 cursor-pointer"
            >
              <span className="flex items-center justify-center w-6 h-6 rounded-md bg-cc-hover text-cc-muted shrink-0">
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-3.5 h-3.5">
                  <path d="M2.5 8a5.5 5.5 0 1111 0v3a2.5 2.5 0 01-2.5 2.5h-1" strokeLinecap="round" />
                  <circle cx="8" cy="8" r="1.75" fill="currentColor" stroke="none" />
                </svg>
              </span>
              <div className="flex-1 min-w-0">
                <div className="text-[13px] font-medium text-cc-fg truncate">@{prompt.name}</div>
                <div className="text-[11px] text-cc-muted truncate">{prompt.content}</div>
              </div>
              <span className="text-[10px] text-cc-muted shrink-0">
                {prompt.scope === "project" ? "本项目" : "通用"}
              </span>
            </button>
            {onDelete && (
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  onDelete(prompt);
                }}
                className="mr-2 flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-cc-muted hover:bg-cc-error/10 hover:text-cc-error transition-colors cursor-pointer"
                title="删除常用提示词"
                aria-label={`删除常用提示词 ${prompt.name}`}
              >
                <svg viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
                  <path fillRule="evenodd" d="M6 2a1 1 0 011-1h2a1 1 0 011 1h3a.5.5 0 010 1h-.5v10A1.5 1.5 0 0111 14.5H5A1.5 1.5 0 013.5 13V3H3a.5.5 0 010-1h3zm-1.5 1v10A.5.5 0 005 13.5h6a.5.5 0 00.5-.5V3h-7zM6.5 5a.5.5 0 01.5.5v6a.5.5 0 01-1 0v-6a.5.5 0 01.5-.5zm3 0a.5.5 0 01.5.5v6a.5.5 0 01-1 0v-6a.5.5 0 01.5-.5z" clipRule="evenodd" />
                </svg>
              </button>
            )}
          </div>
        ))
      ) : (
        <div className="px-3 py-2 text-[12px] text-cc-muted">
          No prompts found.
        </div>
      )}
    </div>
  );
}
