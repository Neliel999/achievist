import type { GameDetail } from "../types";

// Full-page backdrop art for the game detail page. An explicit portrait
// override always wins (portrait is the page background); otherwise the
// landscape SGDB cover, then the IGDB portrait box art, then the icon.
export function bannerArt(
  g: Pick<GameDetail, "portrait_cover_url" | "sgdb_cover_url" | "igdb_cover_url" | "icon_url">,
): string | null {
  return g.portrait_cover_url || g.sgdb_cover_url || g.igdb_cover_url || g.icon_url || null;
}
