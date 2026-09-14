import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  hasAuthRedirect,
  parseAuthRedirect,
  stripAuthRedirect,
} from "./saas-callback.ts";

describe("parseAuthRedirect", () => {
  it("reads implicit magic-link tokens from the hash", () => {
    const parsed = parseAuthRedirect(
      "?next=/app",
      "#access_token=eyJhbGciOiJIUzI1NiJ9.payload.sig&refresh_token=rt&token_type=bearer&type=magiclink",
    );
    assert.deepEqual(parsed, {
      kind: "access_token",
      accessToken: "eyJhbGciOiJIUzI1NiJ9.payload.sig",
    });
  });

  it("reads access_token from the query (some Gotrue configs)", () => {
    const parsed = parseAuthRedirect(
      "?access_token=tok_query&next=/app",
      "",
    );
    assert.equal(parsed.kind, "access_token");
    if (parsed.kind === "access_token") {
      assert.equal(parsed.accessToken, "tok_query");
    }
  });

  it("reads token_hash + type from the query", () => {
    const parsed = parseAuthRedirect(
      "?token_hash=abc123&type=signup&next=/app",
      "",
    );
    assert.deepEqual(parsed, {
      kind: "token_hash",
      tokenHash: "abc123",
      type: "signup",
    });
  });

  it("defaults token_hash type to email", () => {
    const parsed = parseAuthRedirect("?token_hash=xyz", "");
    assert.deepEqual(parsed, {
      kind: "token_hash",
      tokenHash: "xyz",
      type: "email",
    });
  });

  it("reads a PKCE code", () => {
    const parsed = parseAuthRedirect("?code=pkce-one&next=/pricing", "");
    assert.deepEqual(parsed, { kind: "code", code: "pkce-one" });
  });

  it("prefers Gotrue error params over tokens", () => {
    const parsed = parseAuthRedirect(
      "?error=access_denied&error_description=otp_expired",
      "#access_token=should-not-win",
    );
    assert.deepEqual(parsed, { kind: "error", message: "otp_expired" });
  });

  it("returns none for a plain signup URL", () => {
    assert.deepEqual(parseAuthRedirect("?next=/app", ""), { kind: "none" });
    assert.equal(hasAuthRedirect("?next=/app", ""), false);
    assert.equal(hasAuthRedirect("", "#access_token=tok"), true);
  });
});

describe("stripAuthRedirect", () => {
  it("drops auth query/hash and keeps next", () => {
    const url = new URL(
      "https://web.example/signup?next=/app&code=pkce&type=email#access_token=tok",
    );
    assert.equal(stripAuthRedirect(url), "/signup?next=%2Fapp");
  });
});
