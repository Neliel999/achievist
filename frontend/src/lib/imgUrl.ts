// Rewrites known third-party CDN image URLs to the same-origin proxy
// (GET /api/img?url=…), so covers/icons render even on clients whose network
// cannot reach those hosts directly (issue #15). Mirrors
// DEFAULT_ALLOWED_HOSTS in app/imgproxy.py — keep the two in sync. To proxy
// a custom host (e.g. a self-hosted Nextcloud), add it here AND to
// IMG_PROXY_EXTRA_HOSTS on the backend; anything not listed here is fetched
// directly by the browser, exactly as before.
const KNOWN_HOSTS = [
  "cdn2.steamgriddb.com",
  "cdn.steamgriddb.com",
  "steamgriddb.com",
  "media.steampowered.com",
  "steamstatic.com",
  "steamcdn-a.akamaihd.net",
  "m.exophase.com",
  "images.igdb.com",
  "retroachievements.org",
  "image-ssl.xboxlive.com",
  "thumbnails.roblox.com",
  "render.guildwars2.com",
  "wgcdn.co",
  "wargaming.net",
  "m.np.playstation.com",
];

export function imgUrl(u: string): string;
export function imgUrl(u: string | null | undefined): string | null;
export function imgUrl(u: string | null | undefined): string | null {
  if (!u) return null;
  try {
    const p = new URL(u);
    if (
      (p.protocol === "http:" || p.protocol === "https:") &&
      KNOWN_HOSTS.some((h) => p.hostname === h || p.hostname.endsWith("." + h))
    ) {
      return `/api/img?url=${encodeURIComponent(u)}`;
    }
  } catch {
    // not an absolute URL — a relative path, used as-is
  }
  return u;
}
