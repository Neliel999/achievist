import { PLATFORM_META, PSN_CONSOLE_CHIP, platformLabel, psnConsoleLabel } from "../lib/platforms";

export function PlatformBadge({ platform, console }: { platform: string; console?: string | null }) {
  const meta = PLATFORM_META[platform];
  const cls = meta?.badge ?? "bg-ink-700 text-slate-300 border-ink-600";
  // A console tag stands alone ("PS5", not "PlayStation · PS5"), styled like
  // the PS5 system's trophy-tab tags; a multi-console game gets one chip per
  // console ("PS5", "PS4").
  const consoles = console ? console.split(",").map((t) => t.trim()).filter(Boolean) : [];
  if (consoles.length > 0) {
    return (
      <>
        {consoles.map((token) => (
          <span
            key={token}
            className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-semibold ${PSN_CONSOLE_CHIP[token] ?? cls}`}
          >
            {psnConsoleLabel(token)}
          </span>
        ))}
      </>
    );
  }
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-semibold ${cls}`}
    >
      <span
        className="h-1.5 w-1.5 flex-shrink-0 rounded-full"
        style={{ background: meta?.dot ?? "#9ca3af" }}
      />
      {platformLabel(platform)}
    </span>
  );
}
