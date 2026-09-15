import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  copyPayload,
  hasPrintableRows,
  isBilledGrade,
  isEmptyStatement,
  STATEMENT_COPY,
} from "./statement-chrome.ts";
import {
  EMPTY_STATEMENT_FIXTURE,
  ESTIMATE_STATEMENT_FIXTURE,
} from "./statement-fixtures.ts";

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = join(here, "..");

describe("statement chrome lock", () => {
  it("treats Free/estimate with no synced rows as empty", () => {
    assert.equal(isEmptyStatement(EMPTY_STATEMENT_FIXTURE), true);
    assert.equal(hasPrintableRows(EMPTY_STATEMENT_FIXTURE), false);
    assert.equal(isBilledGrade(EMPTY_STATEMENT_FIXTURE), false);
    assert.equal(isEmptyStatement(null), false);
  });

  it("treats an estimate with groups as printable", () => {
    assert.equal(isEmptyStatement(ESTIMATE_STATEMENT_FIXTURE), false);
    assert.equal(hasPrintableRows(ESTIMATE_STATEMENT_FIXTURE), true);
    assert.equal(isBilledGrade(ESTIMATE_STATEMENT_FIXTURE), false);
  });

  it("prefers document billed truth over the plan flag", () => {
    const proEmpty = {
      ...EMPTY_STATEMENT_FIXTURE,
      invoice_grade: true,
    };
    assert.equal(isBilledGrade(proEmpty), false);
    assert.equal(isEmptyStatement(proEmpty), true);

    const billed = {
      ...ESTIMATE_STATEMENT_FIXTURE,
      invoice_grade: true,
      document: {
        ...ESTIMATE_STATEMENT_FIXTURE.document,
        invoice_grade: true,
      },
    };
    assert.equal(isBilledGrade(billed), true);
  });

  it("copies totals without inventing rows or billed copy", () => {
    assert.equal(
      copyPayload(EMPTY_STATEMENT_FIXTURE, "2026-09"),
      "Statement 2026-09 · Estimate · Total $0.0000",
    );
    assert.equal(
      copyPayload(ESTIMATE_STATEMENT_FIXTURE, "2026-09"),
      "Statement 2026-09 · Estimate · Total $0.0090",
    );
  });

  it("keeps hosted statement files on the #58 voice", () => {
    const files = [
      "components/statement-view.tsx",
      "components/statement-document.tsx",
      "lib/statement-chrome.ts",
      "lib/statement-fixtures.ts",
    ];
    const forbidden = ["Invoice client", "Amount due"];
    const required = [
      STATEMENT_COPY.print,
      STATEMENT_COPY.copyTotals,
      STATEMENT_COPY.estimate,
    ];
    for (const rel of files) {
      const src = readFileSync(join(webRoot, rel), "utf8");
      for (const needle of forbidden) {
        assert.equal(src.includes(needle), false, `${rel} must not say ${needle}`);
      }
    }
    const chrome = readFileSync(join(webRoot, "lib/statement-chrome.ts"), "utf8");
    const view = readFileSync(join(webRoot, "components/statement-view.tsx"), "utf8");
    for (const needle of required) {
      assert.equal(chrome.includes(needle), true, `statement-chrome must include ${needle}`);
    }
    assert.equal(view.includes("STATEMENT_COPY.print"), true);
    assert.equal(view.includes("STATEMENT_COPY.copyTotals"), true);
    assert.equal(view.includes("STATEMENT_COPY.emptyTitle"), true);
    assert.equal(view.includes("ConnectLaptopSteps"), true);
  });
});
