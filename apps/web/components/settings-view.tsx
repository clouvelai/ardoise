"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { Install } from "@/components/install";
import { apiGet, apiPost, type CliTokenResponse, type MeResponse } from "@/lib/saas-api";
import { getSession } from "@/lib/saas-session";
import { sparseMessage } from "@/lib/saas-errors";

export function SettingsView() {
  const [plan, setPlan] = useState("free");
  const [token, setToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    const session = getSession();
    if (!session) {
      return;
    }
    apiGet<MeResponse>("/v1/me", session.accessToken)
      .then((me) => setPlan(me.account.plan || "free"))
      .catch((caught) => setError(sparseMessage(caught)));
  }, []);

  async function mintToken() {
    const session = getSession();
    if (!session) {
      return;
    }
    setPending(true);
    setError(null);
    try {
      const created = await apiPost<CliTokenResponse>(
        "/v1/cli/tokens",
        session.accessToken,
      );
      setToken(created.token);
    } catch (caught) {
      setError(sparseMessage(caught));
    } finally {
      setPending(false);
    }
  }

  return (
    <AppShell>
      <p className="text-[11px] font-semibold tracking-[0.22em] text-muted/80 uppercase">
        Settings
      </p>
      <h1 className="mt-2 text-[2.1rem] font-bold tracking-[-0.04em] text-ink">
        Connect the CLI
      </h1>
      <p className="mt-2 text-[15px] text-muted">
        Plan: {plan}. Token is shown once. It is never stored in the ledger.
      </p>

      <section className="mt-8 rounded-[28px] bg-white px-7 py-8 ring-1 ring-black/[0.04]">
        <h2 className="text-[1.2rem] font-semibold">CLI token</h2>
        <p className="mt-2 text-[14px] text-muted">
          After install: <code>ardoise login --token …</code> then{" "}
          <code>ardoise sync</code>.
        </p>
        <button
          type="button"
          onClick={mintToken}
          disabled={pending}
          className="mt-5 rounded-full bg-grape px-5 py-2.5 text-[14px] font-semibold text-white disabled:opacity-70"
        >
          {pending ? "Creating…" : "Create CLI token"}
        </button>
        {token ? (
          <pre className="mt-4 overflow-x-auto whitespace-pre-wrap break-all rounded-xl bg-mist px-4 py-3 text-[12px]">
            {token}
          </pre>
        ) : null}
        {error ? (
          <p role="alert" className="mt-4 text-[13px] text-grape-ink">
            {error}
          </p>
        ) : null}
      </section>

      <Install className="mt-10 w-full max-w-3xl" />
    </AppShell>
  );
}
