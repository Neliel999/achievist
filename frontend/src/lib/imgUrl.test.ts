import { describe, expect, it } from "vitest";
import { imgUrl } from "./imgUrl";

describe("imgUrl", () => {
  it("rewrites known CDN hosts to the same-origin proxy", () => {
    const u = "https://cdn2.steamgriddb.com/grid/abc.png";
    expect(imgUrl(u)).toBe(`/api/img?url=${encodeURIComponent(u)}`);
  });

  it("rewrites subdomains of allowlisted suffixes", () => {
    const u = "https://avatars.steamstatic.com/abc.jpg";
    expect(imgUrl(u)).toBe(`/api/img?url=${encodeURIComponent(u)}`);
  });

  it("matches hosts case-insensitively", () => {
    const u = "https://CDN2.SteamGridDB.com/x.png";
    expect(imgUrl(u)).toBe(`/api/img?url=${encodeURIComponent(u)}`);
  });

  it("passes unknown absolute hosts through unchanged (direct fetch)", () => {
    expect(imgUrl("https://nextcloud.example.com/s/x.png")).toBe(
      "https://nextcloud.example.com/s/x.png",
    );
    expect(imgUrl("https://steamstatic.com.evil.com/x.png")).toBe(
      "https://steamstatic.com.evil.com/x.png",
    );
  });

  it("passes relative paths and non-http schemes through unchanged", () => {
    expect(imgUrl("/static/icon.png")).toBe("/static/icon.png");
    expect(imgUrl("data:image/png;base64,AAAA")).toBe("data:image/png;base64,AAAA");
  });

  it("is null for missing input", () => {
    expect(imgUrl(null)).toBeNull();
    expect(imgUrl(undefined)).toBeNull();
    expect(imgUrl("")).toBeNull();
  });
});
