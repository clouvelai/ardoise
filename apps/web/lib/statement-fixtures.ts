import type { StatementResponse, UsageStatus } from "./saas-api";

const MONTH = "2026-09";

const emptySummary: UsageStatus = {
  month: MONTH,
  entries: 0,
  month_entries: 0,
  cost_usd: 0,
  estimated_usd: 0,
  billed_usd: 0,
  invoice_grade: false,
  connected: false,
};

export const EMPTY_STATEMENT_FIXTURE: StatementResponse = {
  month: MONTH,
  invoice_grade: false,
  markdown: [
    "# Statement 2026-09",
    "",
    "| Field | Value |",
    "| Truth | Estimate |",
    "",
    "Copy totals into your invoice. Print the HTML → Save as PDF for a portable statement.",
  ].join("\n"),
  csv: "vendor,model,cost_usd\n",
  summary: emptySummary,
  document: {
    title: "Statement",
    number: MONTH,
    invoice_grade: false,
    total_usd: 0,
    groups: [],
    entries: 0,
    month: MONTH,
    statement_date: "Sep 15, 2026",
    period: { label: "Sep 1, 2026 – Sep 30, 2026" },
    from: { name: "Ardoise" },
    prepared_for: { name: "alice", email: "alice@example.com" },
    memo: ["This is a spend statement, not a tax invoice."],
  },
};

export const ESTIMATE_STATEMENT_FIXTURE: StatementResponse = {
  month: MONTH,
  invoice_grade: false,
  markdown: [
    "# Statement 2026-09",
    "",
    "| Field | Value |",
    "| Truth | Estimate |",
    "| Description | Quantity | Rate | Amount |",
    "| Input tokens | 1,000 | $3 / MTok | $0.0030 |",
    "",
    "Copy totals into your invoice.",
  ].join("\n"),
  csv: "vendor,model,cost_usd\nanthropic,claude-sonnet-4-6,0.009\n",
  summary: {
    ...emptySummary,
    entries: 1,
    month_entries: 1,
    cost_usd: 0.009,
    estimated_usd: 0.009,
    connected: true,
  },
  document: {
    title: "Statement",
    number: MONTH,
    statement_date: "Sep 15, 2026",
    period: { label: "Sep 1, 2026 – Sep 30, 2026" },
    from: { name: "Ardoise" },
    prepared_for: { name: "alice", email: "alice@example.com" },
    total_usd: 0.009,
    invoice_grade: false,
    entries: 1,
    month: MONTH,
    totals: {
      list_usd: 0.009,
      adjustment_usd: 0,
      total_usd: 0.009,
      show_reconciliation: false,
    },
    groups: [
      {
        vendor: "anthropic",
        person: "",
        label: "anthropic",
        period_label: "Sep 1, 2026 – Sep 30, 2026",
        subtotal_usd: 0.009,
        tier: "T0",
        invoice_grade: false,
        models: [
          {
            model: "claude-sonnet-4-6",
            subtotal_usd: 0.009,
            lines: [
              {
                description: "Input tokens",
                quantity_label: "1,000",
                rate_label: "$3 / MTok",
                amount_usd: 0.003,
              },
              {
                description: "Output tokens",
                quantity_label: "400",
                rate_label: "$15 / MTok",
                amount_usd: 0.006,
              },
            ],
          },
        ],
      },
    ],
    memo: ["This is a spend statement, not a tax invoice."],
  },
};
