"use client";

import { Fragment } from "react";

type Party = {
  name?: string;
  email?: string;
  address?: string[];
};

type Meter = {
  description?: string;
  quantity_label?: string;
  rate_label?: string;
  amount_usd?: number;
};

type ModelGroup = {
  model?: string;
  subtotal_usd?: number;
  lines?: Meter[];
};

type StatementGroup = {
  vendor?: string;
  person?: string;
  label?: string;
  period_label?: string;
  subtotal_usd?: number;
  tier?: string;
  invoice_grade?: boolean;
  models?: ModelGroup[];
  adjustment?: Meter & { description?: string };
};

type StatementTotals = {
  list_usd?: number;
  adjustment_usd?: number;
  total_usd?: number;
  show_reconciliation?: boolean;
};

export type StatementDocument = {
  title?: string;
  number?: string;
  statement_date?: string;
  period?: { label?: string };
  from?: Party;
  prepared_for?: Party;
  total_usd?: number;
  invoice_grade?: boolean;
  totals?: StatementTotals;
  groups?: StatementGroup[];
  memo?: string[];
  notes?: string[];
  month?: string;
  entries?: number;
};

export function money(value: number | undefined, places = 2): string {
  const n = Number(value || 0);
  return `$${n.toLocaleString("en-US", {
    minimumFractionDigits: places,
    maximumFractionDigits: places,
  })}`;
}

export function GradeBadge({ billed }: { billed: boolean }) {
  return (
    <span
      className={
        billed
          ? "inline-flex items-center rounded-full bg-grape px-2.5 py-[3px] text-[10px] font-semibold tracking-[0.14em] text-white uppercase"
          : "inline-flex items-center rounded-full bg-lavender px-2.5 py-[3px] text-[10px] font-semibold tracking-[0.14em] text-grape-ink uppercase"
      }
    >
      {billed ? "Billed" : "Estimate"}
    </span>
  );
}

function PartyBlock({ label, party }: { label: string; party?: Party }) {
  const lines = [
    party?.name,
    ...(party?.address || []),
    party?.email,
  ].filter(Boolean) as string[];
  return (
    <div>
      <p className="m-0 mb-1 text-[11px] font-semibold tracking-[0.08em] text-muted uppercase">
        {label}
      </p>
      {lines.length ? (
        lines.map((line, index) => (
          <p
            key={`${label}-${line}`}
            className={
              index === 0
                ? "m-0 font-semibold text-ink"
                : "m-0 mt-0.5 text-[13px] text-muted"
            }
          >
            {line}
          </p>
        ))
      ) : (
        <p className="m-0 text-[13px] text-muted">—</p>
      )}
    </div>
  );
}

export function StatementDocumentView({
  document,
}: {
  document: StatementDocument;
}) {
  const grade = Boolean(document.invoice_grade);
  const totalPlaces = grade ? 2 : 4;
  const groups = document.groups || [];
  const totals = document.totals || {};
  const showReconciliation = Boolean(totals.show_reconciliation);
  const total = money(document.total_usd, totalPlaces);

  return (
    <article className="stmt-doc mt-6 rounded-[24px] border border-black/[0.06] bg-white px-6 py-7 text-ink sm:px-8">
      <header className="mb-5 grid grid-cols-[1fr_auto] items-start gap-x-8 gap-y-3">
        <div>
          <p className="m-0 text-[1.15rem] font-semibold tracking-[-0.03em]">
            Ardoise
          </p>
          <p className="m-0 mt-0.5 text-[11px] font-semibold tracking-[0.14em] text-muted uppercase">
            Spend statement
          </p>
        </div>
        <div className="text-right">
          <h2 className="m-0 text-[1.85rem] font-semibold tracking-[0.14em] uppercase leading-none">
            Statement
          </h2>
          <p className="mt-2.5">
            <GradeBadge billed={grade} />
          </p>
        </div>
      </header>
      <div className="grid gap-6 md:grid-cols-[1.15fr_0.95fr]">
        <div>
          <PartyBlock label="From" party={document.from} />
          <div className="mt-4">
            <PartyBlock label="Prepared for" party={document.prepared_for} />
          </div>
        </div>
        <table className="w-full border-collapse text-[14px]">
          <tbody>
            <tr>
              <th className="py-0.5 pr-3 text-left font-medium text-muted">
                Statement number
              </th>
              <td className="py-0.5 text-right tabular-nums">
                {document.number || "—"}
              </td>
            </tr>
            <tr>
              <th className="py-0.5 pr-3 text-left font-medium text-muted">
                Statement date
              </th>
              <td className="py-0.5 text-right tabular-nums">
                {document.statement_date || "—"}
              </td>
            </tr>
            <tr>
              <th className="py-0.5 pr-3 text-left font-medium text-muted">
                Usage period
              </th>
              <td className="py-0.5 text-right tabular-nums">
                {document.period?.label || "—"}
              </td>
            </tr>
            <tr>
              <th className="pt-3 pr-3 text-left text-[1.05rem] font-bold text-ink">
                Total{" "}
                <span className="align-middle font-medium">
                  <GradeBadge billed={grade} />
                </span>
              </th>
              <td className="pt-3 text-right text-[1.05rem] font-bold tabular-nums">
                {total}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <table className="stmt-lines mt-7 w-full border-collapse text-[13px]">
        <colgroup>
          <col className="w-[52%]" />
          <col className="w-[16%]" />
          <col className="w-[16%]" />
          <col className="w-[16%]" />
        </colgroup>
        <thead>
          <tr>
            <th className="border-b border-ink px-1.5 py-1.5 text-left text-[11px] font-semibold tracking-[0.06em] text-muted uppercase">
              Description
            </th>
            <th className="border-b border-ink px-1.5 py-1.5 text-right text-[11px] font-semibold tracking-[0.06em] text-muted uppercase">
              Quantity
            </th>
            <th className="border-b border-ink px-1.5 py-1.5 text-right text-[11px] font-semibold tracking-[0.06em] text-muted uppercase">
              Rate
            </th>
            <th className="border-b border-ink px-1.5 py-1.5 text-right text-[11px] font-semibold tracking-[0.06em] text-muted uppercase">
              Amount
            </th>
          </tr>
        </thead>
        {groups.length === 0 ? (
          <tbody>
            <tr>
              <td colSpan={4} className="px-1.5 py-4 text-muted">
                No usage this period.
              </td>
            </tr>
          </tbody>
        ) : (
          groups.map((group) => (
            <tbody
              key={`${group.vendor}-${group.person || ""}`}
              className="stmt-section"
            >
              <tr>
                <td colSpan={3} className="px-1.5 pt-3.5 pb-0">
                  <strong>{group.label || group.vendor}</strong>
                </td>
                <td className="px-1.5 pt-3.5 pb-0 text-right font-semibold tabular-nums">
                  {money(group.subtotal_usd, group.invoice_grade ? 2 : 4)}
                </td>
              </tr>
              <tr>
                <td
                  colSpan={4}
                  className="border-b border-black/10 px-1.5 pt-0 pb-1.5 text-[12px] text-muted"
                >
                  {group.period_label}
                  {group.tier ? ` · ${group.tier}` : ""}
                </td>
              </tr>
              {(group.models || []).map((model) => (
                <Fragment key={`${group.vendor}-${model.model}`}>
                  <tr>
                    <td colSpan={3} className="px-1.5 py-1 font-medium">
                      {model.model}
                    </td>
                    <td className="px-1.5 py-1 text-right tabular-nums">
                      {money(model.subtotal_usd, 4)}
                    </td>
                  </tr>
                  {(model.lines || []).map((meter) => (
                    <tr
                      key={`${group.vendor}-${model.model}-${meter.description}`}
                    >
                      <td className="border-b border-lavender py-1 pr-1.5 pl-5 text-ink/80">
                        {meter.description}
                      </td>
                      <td className="border-b border-lavender px-1.5 py-1 text-right tabular-nums">
                        {meter.quantity_label || "—"}
                      </td>
                      <td className="border-b border-lavender px-1.5 py-1 text-right tabular-nums">
                        {meter.rate_label || "—"}
                      </td>
                      <td className="border-b border-lavender px-1.5 py-1 text-right tabular-nums">
                        {money(meter.amount_usd, 4)}
                      </td>
                    </tr>
                  ))}
                </Fragment>
              ))}
              {group.adjustment ? (
                <tr>
                  <td className="border-b border-lavender py-1 pr-1.5 pl-5 text-muted">
                    {group.adjustment.description}
                  </td>
                  <td className="border-b border-lavender px-1.5 py-1 text-right text-muted tabular-nums">
                    —
                  </td>
                  <td className="border-b border-lavender px-1.5 py-1 text-right text-muted tabular-nums">
                    —
                  </td>
                  <td className="border-b border-lavender px-1.5 py-1 text-right text-muted tabular-nums">
                    {money(group.adjustment.amount_usd, 4)}
                  </td>
                </tr>
              ) : null}
            </tbody>
          ))
        )}
        <tfoot>
          {showReconciliation ? (
            <>
              <tr>
                <td colSpan={3} className="px-1.5 pt-3 text-muted">
                  List price
                </td>
                <td className="px-1.5 pt-3 text-right text-muted tabular-nums">
                  {money(totals.list_usd, 4)}
                </td>
              </tr>
              <tr>
                <td colSpan={3} className="px-1.5 py-1 text-muted">
                  Reconciling adjustment
                </td>
                <td className="px-1.5 py-1 text-right text-muted tabular-nums">
                  {money(totals.adjustment_usd, 4)}
                </td>
              </tr>
            </>
          ) : null}
          <tr>
            <td
              colSpan={3}
              className="border-t border-ink px-1.5 pt-2.5 font-semibold"
            >
              Total
            </td>
            <td className="border-t border-ink px-1.5 pt-2.5 text-right font-semibold tabular-nums">
              {total}
            </td>
          </tr>
        </tfoot>
      </table>

      {(document.memo || []).length ? (
        <section className="mt-6 text-[13px] text-muted">
          <h3 className="m-0 mb-2 text-[11px] font-semibold tracking-[0.1em] uppercase">
            Memo
          </h3>
          <ul className="m-0 list-disc space-y-1 pl-4">
            {(document.memo || []).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {(document.notes || []).length ? (
        <section className="mt-5 rounded-[14px] border border-[#e9e1f6] bg-mist px-4 py-3.5 text-[13px] text-grape-ink">
          <h3 className="m-0 mb-2 text-[11px] font-semibold tracking-[0.1em] uppercase">
            Notes (soft)
          </h3>
          <ul className="m-0 list-disc space-y-1 pl-4">
            {(document.notes || []).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </article>
  );
}
