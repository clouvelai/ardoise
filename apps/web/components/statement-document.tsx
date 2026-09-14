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
  models?: ModelGroup[];
  adjustment?: Meter & { description?: string };
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
  groups?: StatementGroup[];
  memo?: string[];
  notes?: string[];
  month?: string;
};

function money(value: number | undefined, places = 2): string {
  const n = Number(value || 0);
  return `$${n.toLocaleString("en-US", {
    minimumFractionDigits: places,
    maximumFractionDigits: places,
  })}`;
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

  return (
    <article className="stmt-doc mt-6 rounded-[24px] border border-black/[0.06] bg-white px-6 py-7 text-ink sm:px-8">
      <p className="m-0 mb-3 text-[11px] font-semibold tracking-[0.14em] text-muted uppercase">
        Ardoise · spend statement
      </p>
      <h2 className="m-0 mb-5 text-[1.7rem] font-bold tracking-[-0.03em]">
        Statement
      </h2>
      <div className="grid gap-6 md:grid-cols-[1.2fr_0.9fr]">
        <div className="space-y-4">
          <PartyBlock label="From" party={document.from} />
          <PartyBlock label="Prepared for" party={document.prepared_for} />
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
                <span className="text-[13px] font-medium text-muted">
                  ({grade ? "invoice-grade" : "estimate"})
                </span>
              </th>
              <td className="pt-3 text-right text-[1.05rem] font-bold tabular-nums">
                {money(document.total_usd, totalPlaces)}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <table className="mt-7 w-full border-collapse text-[13px]">
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
        <tbody>
          {groups.length === 0 ? (
            <tr>
              <td colSpan={4} className="px-1.5 py-4 text-muted">
                No usage this period.
              </td>
            </tr>
          ) : (
            groups.map((group) => (
              <Fragment key={`${group.vendor}-${group.person || ""}`}>
                <tr>
                  <td
                    colSpan={3}
                    className="border-b border-black/10 px-1.5 pt-3.5 pb-1.5"
                  >
                    <strong>{group.label || group.vendor}</strong>
                    <span className="font-normal text-muted">
                      {" "}
                      · {group.period_label}
                      {group.tier ? ` · ${group.tier}` : ""}
                    </span>
                  </td>
                  <td className="border-b border-black/10 px-1.5 pt-3.5 pb-1.5 text-right font-semibold tabular-nums">
                    {money(group.subtotal_usd)}
                  </td>
                </tr>
                {(group.models || []).map((model) => (
                  <Fragment key={`${group.vendor}-${model.model}`}>
                    <tr>
                      <td
                        colSpan={3}
                        className="border-b border-black/[0.04] px-1.5 py-1.5 font-medium"
                      >
                        {model.model}
                      </td>
                      <td className="border-b border-black/[0.04] px-1.5 py-1.5 text-right tabular-nums">
                        {money(model.subtotal_usd, 4)}
                      </td>
                    </tr>
                    {(model.lines || []).map((meter) => (
                      <tr
                        key={`${group.vendor}-${model.model}-${meter.description}`}
                      >
                        <td className="border-b border-black/[0.04] py-1.5 pr-1.5 pl-5 text-ink/80">
                          {meter.description}
                        </td>
                        <td className="border-b border-black/[0.04] px-1.5 py-1.5 text-right tabular-nums">
                          {meter.quantity_label || "—"}
                        </td>
                        <td className="border-b border-black/[0.04] px-1.5 py-1.5 text-right tabular-nums">
                          {meter.rate_label || "—"}
                        </td>
                        <td className="border-b border-black/[0.04] px-1.5 py-1.5 text-right tabular-nums">
                          {money(meter.amount_usd, 4)}
                        </td>
                      </tr>
                    ))}
                  </Fragment>
                ))}
                {group.adjustment ? (
                  <tr>
                    <td
                      colSpan={3}
                      className="border-b border-black/[0.04] px-1.5 py-1.5 text-muted italic"
                    >
                      {group.adjustment.description}
                    </td>
                    <td className="border-b border-black/[0.04] px-1.5 py-1.5 text-right text-muted italic tabular-nums">
                      {money(group.adjustment.amount_usd, 4)}
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            ))
          )}
        </tbody>
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
        <section className="mt-5 rounded-[14px] border border-[#f1e4c8] bg-[#fffbeb] px-4 py-3.5 text-[13px] text-[#92400e]">
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
