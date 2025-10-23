export interface PermalinkState {
  lat: number;
  lon: number;
  zoom: number;
  layers: string[];
}

function encode(str: string): string {
  return btoa(encodeURIComponent(str));
}

function decode(str: string): string {
  return decodeURIComponent(atob(str));
}

export function encodePermalink(state: PermalinkState): string {
  const payload = encode(JSON.stringify(state));
  window.location.hash = payload;
  return payload;
}

export function decodePermalink(): PermalinkState | null {
  const hash = window.location.hash.startsWith("#")
    ? window.location.hash.substring(1)
    : window.location.hash;

  if (!hash) {
    return null;
  }

  try {
    const json = decode(hash);
    return JSON.parse(json) as PermalinkState;
  } catch (error) {
    console.warn("Permalink decode failed", error);
    return null;
  }
}
