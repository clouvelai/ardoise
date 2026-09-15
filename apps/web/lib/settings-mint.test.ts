import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { loginCommand, SETTINGS_COPY } from "./settings-mint.ts";

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = join(here, "..");

describe("settings mint copy", () => {
  it("prefills the login command with the minted token", () => {
    assert.equal(
      loginCommand("ard_preview_once"),
      "ardoise login --token ard_preview_once",
    );
  });

  it("keeps mint copy controls on the settings voice", () => {
    const files = [
      "components/settings-view.tsx",
      "lib/settings-mint.ts",
    ];
    const forbidden = ["Invoice client", "Amount due"];
    for (const rel of files) {
      const src = readFileSync(join(webRoot, rel), "utf8");
      for (const needle of forbidden) {
        assert.equal(src.includes(needle), false, `${rel} must not say ${needle}`);
      }
    }
    const view = readFileSync(join(webRoot, "components/settings-view.tsx"), "utf8");
    assert.equal(view.includes("SETTINGS_COPY.copyToken"), true);
    assert.equal(view.includes("SETTINGS_COPY.copyLogin"), true);
    assert.equal(view.includes("loginCommand"), true);
    assert.equal(view.includes("ardoise sync"), true);
    const chrome = readFileSync(join(webRoot, "lib/settings-mint.ts"), "utf8");
    assert.equal(chrome.includes(SETTINGS_COPY.copyToken), true);
    assert.equal(chrome.includes(SETTINGS_COPY.copyLogin), true);
  });
});
