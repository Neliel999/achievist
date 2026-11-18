import { describe, expect, it } from "vitest";
import { backgroundSizeFor, bannerArt } from "./art";

const base = {
  portrait_cover_url: null as string | null,
  sgdb_cover_url: "https://cdn/sgdb-cover.jpg",
  igdb_cover_url: "https://cdn/igdb-cover.jpg",
  icon_url: "https://cdn/icon.png",
};

describe("bannerArt (game detail backdrop)", () => {
  it("prefers an explicit portrait override over the SGDB cover", () => {
    expect(bannerArt({ ...base, portrait_cover_url: "https://cdn/portrait.png" })).toBe(
      "https://cdn/portrait.png",
    );
  });

  it("falls back sgdb cover -> igdb -> icon -> null", () => {
    expect(bannerArt(base)).toBe("https://cdn/sgdb-cover.jpg");
    expect(bannerArt({ ...base, sgdb_cover_url: null })).toBe("https://cdn/igdb-cover.jpg");
    expect(bannerArt({ ...base, sgdb_cover_url: null, igdb_cover_url: null })).toBe(
      "https://cdn/icon.png",
    );
    expect(bannerArt({ ...base, sgdb_cover_url: null, igdb_cover_url: null, icon_url: null })).toBeNull();
  });
});

describe("backgroundSizeFor (backdrop fit)", () => {
  it("fits portrait art by height so the whole image stays visible", () => {
    expect(backgroundSizeFor(600, 900)).toBe("auto 100%");
  });

  it("keeps cover for landscape and square art", () => {
    expect(backgroundSizeFor(1920, 620)).toBe("cover");
    expect(backgroundSizeFor(1000, 1000)).toBe("cover");
  });
});
