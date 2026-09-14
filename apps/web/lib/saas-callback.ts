/**
 * Parse a Supabase Auth redirect on the marketing origin.
 * Implicit magic links arrive as `#access_token=…`; PKCE / custom
 * templates use `?token_hash=` or `?code=`. Never persist the raw URL.
 */

const AUTH_QUERY_KEYS = [
  "access_token",
  "refresh_token",
  "expires_in",
  "expires_at",
  "token_type",
  "type",
  "token_hash",
  "code",
  "error",
  "error_code",
  "error_description",
  "provider_token",
  "provider_refresh_token",
] as const;

export type AuthRedirect =
  | { kind: "none" }
  | { kind: "access_token"; accessToken: string }
  | { kind: "token_hash"; tokenHash: string; type: string }
  | { kind: "code"; code: string }
  | { kind: "error"; message: string };

function paramsOf(raw: string, prefix: "?" | "#"): URLSearchParams {
  const trimmed = raw.startsWith(prefix) ? raw.slice(1) : raw;
  return new URLSearchParams(trimmed);
}

export function parseAuthRedirect(
  search: string,
  hash: string,
): AuthRedirect {
  const query = paramsOf(search, "?");
  const frag = paramsOf(hash, "#");

  const error =
    query.get("error_description") ||
    frag.get("error_description") ||
    query.get("error") ||
    frag.get("error");
  if (error) {
    return { kind: "error", message: error };
  }

  const accessToken = frag.get("access_token") || query.get("access_token");
  if (accessToken) {
    return { kind: "access_token", accessToken };
  }

  const tokenHash = query.get("token_hash") || frag.get("token_hash");
  if (tokenHash) {
    return {
      kind: "token_hash",
      tokenHash,
      type: query.get("type") || frag.get("type") || "email",
    };
  }

  const code = query.get("code") || frag.get("code");
  if (code) {
    return { kind: "code", code };
  }

  return { kind: "none" };
}

export function hasAuthRedirect(search: string, hash: string): boolean {
  return parseAuthRedirect(search, hash).kind !== "none";
}

export function stripAuthRedirect(url: URL): string {
  for (const key of AUTH_QUERY_KEYS) {
    url.searchParams.delete(key);
  }
  url.hash = "";
  return `${url.pathname}${url.search}`;
}
