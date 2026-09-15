import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { safeNextPath, signupHref } from "./saas-errors.ts";

describe("safeNextPath", () => {
  it("allows app destinations including statement", () => {
    assert.equal(safeNextPath("/app"), "/app");
    assert.equal(safeNextPath("/app/settings"), "/app/settings");
    assert.equal(safeNextPath("/app/statement"), "/app/statement");
    assert.equal(safeNextPath("/pricing"), "/pricing");
  });

  it("rejects open redirects", () => {
    assert.equal(safeNextPath("https://evil.example"), null);
    assert.equal(safeNextPath("//evil.example"), null);
    assert.equal(safeNextPath("/app/../evil"), null);
    assert.equal(safeNextPath("/elsewhere"), null);
  });
});

describe("signupHref", () => {
  it("preserves an unauthenticated statement visit", () => {
    assert.equal(signupHref("/app/statement"), "/signup?next=/app/statement");
  });

  it("falls back to the ledger when the path is not allow-listed", () => {
    assert.equal(signupHref("/unknown"), "/signup?next=/app");
    assert.equal(signupHref(null), "/signup?next=/app");
  });
});
