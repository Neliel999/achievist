import { useEffect, useRef, useState } from "react";
import { X, Search, ImageOff, Link } from "lucide-react";
import { api } from "../api";
import type { SgdbSearchResult } from "../types";
import { useToast } from "./Toast";
import { useModal } from "../lib/useModal";

export type ArtField = "cover" | "portrait" | "icon";

const FIELDS: { id: ArtField; label: string; resetLabel: string }[] = [
  { id: "cover", label: "Cover", resetLabel: "Remove custom cover (use default)" },
  { id: "portrait", label: "Portrait", resetLabel: "Remove custom portrait (use IGDB/Steam fallback)" },
  { id: "icon", label: "Icon", resetLabel: "Remove custom icon (use synced icon)" },
];

function assetsFor(field: ArtField, g: SgdbSearchResult): { u: string; cls: string }[] {
  if (field === "portrait") return g.verticals.map((u) => ({ u, cls: "h-24 w-16" }));
  if (field === "icon") return g.icons.map((u) => ({ u, cls: "h-14 w-14" }));
  return [
    ...g.heroes.map((u) => ({ u, cls: "h-20 w-36" })),
    ...g.grids.map((u) => ({ u, cls: "h-20 w-16" })),
  ];
}

export function ChangeCoverModal({
  gameId,
  initialQuery,
  onClose,
  onChanged,
}: {
  gameId: number;
  initialQuery: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [field, setField] = useState<ArtField>("cover");
  const [query, setQuery] = useState(initialQuery);
  const [games, setGames] = useState<SgdbSearchResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [applying, setApplying] = useState<string | null>(null);
  const [customUrl, setCustomUrl] = useState("");
  const toast = useToast();
  const debounceRef = useRef<number>();
  const { titleId, dialogProps } = useModal(onClose);

  function runSearch(q: string) {
    if (!q.trim()) {
      setGames([]);
      return;
    }
    setGames(null);
    setError(null);
    api.sgdbSearch(q)
      .then((r) => {
        if (r.error) {
          setError(r.error);
          setGames([]);
        } else {
          setGames(r.games ?? []);
        }
      })
      .catch((e) => {
        setError(String(e instanceof Error ? e.message : e));
        setGames([]);
      });
  }

  useEffect(() => {
    runSearch(initialQuery);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function onQueryChange(v: string) {
    setQuery(v);
    window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => runSearch(v), 350);
  }

  async function pick(url: string) {
    setApplying(url);
    try {
      await api.artSet(gameId, field, url);
      toast.success(`${FIELDS.find((f) => f.id === field)!.label} updated`);
      onChanged();
      onClose();
    } catch (e) {
      toast.error(String(e instanceof Error ? e.message : e));
    } finally {
      setApplying(null);
    }
  }

  async function applyCustom() {
    const url = customUrl.trim();
    if (!url) return;
    await pick(url);
  }

  async function clear() {
    setApplying("__clear__");
    try {
      await api.artSet(gameId, field, "");
      toast.success(`${FIELDS.find((f) => f.id === field)!.label} reset to default`);
      onChanged();
      onClose();
    } catch (e) {
      toast.error(String(e instanceof Error ? e.message : e));
    } finally {
      setApplying(null);
    }
  }

  const activeField = FIELDS.find((f) => f.id === field)!;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center overflow-y-auto bg-black/70 p-4"
      onClick={(e) => {
        // Stop propagation in case a future caller nests this inside another
        // clickable/backdrop element.
        e.stopPropagation();
        onClose();
      }}
    >
      <div
        {...dialogProps}
        className="my-8 w-full max-w-2xl rounded-card border border-line bg-ink-850 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-line p-4">
          <h2 id={titleId} className="text-base font-semibold text-slate-100">Change Art</h2>
          <button
            onClick={onClose}
            aria-label="Close art picker"
            className="rounded-lg p-1.5 text-muted transition hover:bg-ink-800 hover:text-slate-200"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex gap-1 border-b border-line px-4 pt-2" role="tablist">
          {FIELDS.map((f) => (
            <button
              key={f.id}
              role="tab"
              aria-selected={field === f.id}
              onClick={() => setField(f.id)}
              className={`rounded-t-md px-3 py-1.5 text-sm transition ${
                field === f.id
                  ? "bg-ink-900 font-medium text-slate-100"
                  : "text-muted hover:text-slate-200"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="p-4">
          <div className="flex items-center gap-2 rounded-lg border border-line bg-ink-900 px-3 py-2">
            <Search size={15} className="text-faint" />
            <input
              autoFocus
              value={query}
              onChange={(e) => onQueryChange(e.target.value)}
              placeholder="Search SteamGridDB by name, or paste a numeric game ID…"
              className="w-full bg-transparent text-sm text-slate-100 outline-none placeholder:text-faint"
            />
          </div>

          <div className="mt-3 flex items-center gap-2 rounded-lg border border-line bg-ink-900 px-3 py-2">
            <Link size={15} className="text-faint" />
            <input
              value={customUrl}
              onChange={(e) => setCustomUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && applyCustom()}
              placeholder={`…or paste any image URL for this ${activeField.label.toLowerCase()}…`}
              className="w-full bg-transparent text-sm text-slate-100 outline-none placeholder:text-faint"
            />
            <button
              onClick={applyCustom}
              disabled={applying !== null || !customUrl.trim()}
              className="flex-shrink-0 rounded-md bg-accent px-2.5 py-1 text-xs font-medium text-white transition hover:brightness-110 disabled:opacity-50"
            >
              Use URL
            </button>
          </div>

          <button
            onClick={clear}
            disabled={applying !== null}
            className="mt-3 text-xs text-muted underline decoration-dotted transition hover:text-slate-200 disabled:opacity-50"
          >
            {activeField.resetLabel}
          </button>

          <div className="mt-4 max-h-[50vh] space-y-5 overflow-y-auto">
            {error && (
              <div className="rounded-lg border border-red-900/50 bg-red-950/30 px-3 py-2 text-sm text-red-400">
                {error}
              </div>
            )}

            {games === null ? (
              <div className="py-10 text-center text-sm text-muted">Searching…</div>
            ) : games.length === 0 && !error ? (
              <div className="py-10 text-center text-sm text-muted">
                {query.trim() ? "No results." : "Start typing to search SteamGridDB."}
              </div>
            ) : (
              games.map((g) => {
                const images = assetsFor(field, g);
                return (
                  <div key={g.id}>
                    <div className="mb-2 text-sm font-medium text-slate-200">{g.name}</div>
                    {images.length === 0 ? (
                      <div className="flex items-center gap-2 text-xs text-faint">
                        <ImageOff size={13} /> No {activeField.label.toLowerCase()} art found for this game.
                      </div>
                    ) : (
                      <div className="flex gap-2 overflow-x-auto pb-1">
                        {images.map(({ u, cls }) => (
                          <button
                            key={u}
                            onClick={() => pick(u)}
                            disabled={applying !== null}
                            className="group relative flex-shrink-0 overflow-hidden rounded-md border border-line ring-1 ring-transparent transition hover:ring-accent disabled:opacity-50"
                          >
                            <img
                              src={u}
                              alt=""
                              className={`${cls} object-cover`}
                              loading="lazy"
                            />
                            {applying === u && (
                              <div className="absolute inset-0 flex items-center justify-center bg-black/50 text-[10px] text-slate-100">
                                Applying…
                              </div>
                            )}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
