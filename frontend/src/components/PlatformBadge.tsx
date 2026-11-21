import { PLATFORM_META, platformLabel, psnConsoleLabel } from "../lib/platforms";

export function PlatformBadge({ platform, console }: { platform: string; console?: string | null }) {
  const meta = PLATFORM_META[platform];
  const cls = meta?.badge ?? "bg-ink-700 text-slate-300 border-ink-600";
  // A console tag stands alone ("PS5", not "PlayStation · PS5"), and a
  // multi-console game gets one chip per console ("PS5", "PS4").
  const labels = console
    ? console.split(",").map((t) => psnConsoleLabel(t.trim())).filter((l) => l !== "")
    : [platformLabel(platform)];
  return (
    <>
      {labels.map((label) => (
        <span
          key={label}
          className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-semibold ${cls}`}
        >
          <span
            className="h-1.5 w-1.5 flex-shrink-0 rounded-full"
            style={{ background: meta?.dot ?? "#9ca3af" }}
          />
          {label}
        </span>
      ))}
    </>
  );
}
