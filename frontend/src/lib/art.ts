import type { GameDetail } from "../types";

// Full-page backdrop art for the game detail page. An explicit portrait
// override always wins (portrait is the page background); otherwise the
// landscape SGDB cover, then the IGDB portrait box art, then the icon.
export function bannerArt(
  g: Pick<GameDetail, "portrait_cover_url" | "sgdb_cover_url" | "igdb_cover_url" | "icon_url">,
): string | null {
  return g.portrait_cover_url || g.sgdb_cover_url || g.igdb_cover_url || g.icon_url || null;
}

// Backdrop fit for the full-page background: portrait art is fitted by height
// ("auto 100%") so the whole image stays visible on a landscape viewport —
// "cover" would scale a 600x900 portrait up to viewport width, leaving only a
// cropped, upscaled band visible. Landscape art keeps "cover".
export function backgroundSizeFor(naturalWidth: number, naturalHeight: number): string {
  return naturalHeight > naturalWidth ? "auto 100%" : "cover";
}
