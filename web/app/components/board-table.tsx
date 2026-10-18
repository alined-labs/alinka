import {
  columnFilteringFeature,
  type ColumnFiltersState,
  createColumnHelper,
  createFilteredRowModel,
  createSortedRowModel,
  filterFn_equals,
  functionalUpdate,
  rowSortingFeature,
  type SortingState,
  sortFn_alphanumeric,
  sortFn_basic,
  tableFeatures,
  useTable,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp } from "lucide-react";
import { useMemo, useState } from "react";

import type { Card } from "~/api/client";
import { STATE_LABEL } from "~/lib/board";
import { formatMoney, formatUsd } from "~/lib/format";

import { AlertBadge, ChannelIcon, StateBadge } from "./badges";
import { BeneficiaryName } from "./invoice-card";

const features = tableFeatures({
  columnFilteringFeature,
  rowSortingFeature,
  filteredRowModel: createFilteredRowModel(),
  sortedRowModel: createSortedRowModel(),
  filterFns: { equals: filterFn_equals },
  sortFns: { alphanumeric: sortFn_alphanumeric, basic: sortFn_basic },
});

const col = createColumnHelper<typeof features, Card>();
const NO_BENEFICIARY = "__none__";
const NO_RULE = "__none__";

const columns = col.columns([
  col.accessor("invoice_id", {
    header: "Factura",
    cell: (info) => <span className="font-mono">{info.getValue()}</span>,
  }),
  col.accessor("channel", { header: "Canal", cell: (info) => <ChannelIcon channel={info.getValue()} withLabel /> }),
  col.accessor((c) => c.beneficiary_id ?? NO_BENEFICIARY, {
    id: "beneficiary",
    header: "Beneficiario",
    filterFn: "equals",
    cell: (info) => <BeneficiaryName card={info.row.original} />,
  }),
  col.accessor("amount_minor", {
    header: "Monto",
    sortFn: "basic",
    cell: (info) => formatMoney(info.getValue(), info.row.original.currency),
  }),
  col.accessor("usd_minor", { header: "USD", sortFn: "basic", cell: (info) => formatUsd(info.getValue()) }),
  col.accessor("state", { header: "Estado", filterFn: "equals", cell: (info) => <StateBadge state={info.getValue()} /> }),
  col.accessor((c) => c.determining_rule ?? NO_RULE, {
    id: "rule",
    header: "Regla",
    filterFn: "equals",
    cell: (info) => {
      const c = info.row.original;
      return c.determining_rule ? `${c.determining_rule} · ${c.determining_rule_es ?? ""}` : "—";
    },
  }),
  col.accessor((c) => c.alerts.join(","), {
    id: "alerts",
    header: "Alertas",
    enableSorting: false,
    cell: (info) => <AlertBadge rules={info.row.original.alerts} />,
  }),
  col.accessor("reason_es", { header: "Motivo", enableSorting: false }),
]);

function Filter({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm" htmlFor={id}>
      {label}
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-border bg-surface px-2 py-1.5"
      >
        <option value="">Todas</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function BoardTable({ cards }: { cards: Card[] }) {
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [sorting, setSorting] = useState<SortingState>([]);
  const table = useTable({
    features,
    columns,
    data: cards,
    getRowId: (row) => row.invoice_id,
    state: { columnFilters, sorting },
    onColumnFiltersChange: (u) => setColumnFilters((prev) => functionalUpdate(u, prev)),
    onSortingChange: (u) => setSorting((prev) => functionalUpdate(u, prev)),
  });

  const options = useMemo(() => {
    const states = [...new Set(cards.map((c) => c.state))].map((s) => ({ value: s, label: STATE_LABEL[s] }));
    const rules = new Map<string, string>();
    const beneficiaries = new Map<string, string>();
    for (const c of cards) {
      rules.set(c.determining_rule ?? NO_RULE, c.determining_rule ? `${c.determining_rule} · ${c.determining_rule_es ?? ""}` : "Ninguna regla");
      beneficiaries.set(c.beneficiary_id ?? NO_BENEFICIARY, c.beneficiary_id ? (c.beneficiary_name ?? c.beneficiary_id) : "No está en la lista");
    }
    const sorted = (m: Map<string, string>) =>
      [...m].map(([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label, "es"));
    return { states, rules: sorted(rules), beneficiaries: sorted(beneficiaries) };
  }, [cards]);

  const filterValue = (id: string) => String(columnFilters.find((f) => f.id === id)?.value ?? "");
  const setFilter = (id: string) => (value: string) =>
    setColumnFilters((prev) => [...prev.filter((f) => f.id !== id), ...(value ? [{ id, value }] : [])]);

  const rows = table.getRowModel().rows;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-4" role="group" aria-label="Filtros">
        <Filter id="f-state" label="Decisión" value={filterValue("state")} options={options.states} onChange={setFilter("state")} />
        <Filter id="f-rule" label="Regla" value={filterValue("rule")} options={options.rules} onChange={setFilter("rule")} />
        <Filter
          id="f-beneficiary"
          label="Beneficiario"
          value={filterValue("beneficiary")}
          options={options.beneficiaries}
          onChange={setFilter("beneficiary")}
        />
      </div>
      <p className="text-sm text-muted" aria-live="polite">
        {rows.length} de {cards.length} facturas
      </p>
      <div className="overflow-x-auto rounded-lg border border-border bg-surface">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Facturas del tablero</caption>
          <thead className="bg-surface-muted">
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id}>
                {group.headers.map((header) => {
                  const sorted = header.column.getIsSorted();
                  const canSort = header.column.getCanSort();
                  return (
                    <th
                      key={header.id}
                      scope="col"
                      className="px-3 py-2 font-semibold"
                      aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : undefined}
                    >
                      {canSort ? (
                        <button
                          type="button"
                          onClick={header.column.getToggleSortingHandler()}
                          className="inline-flex items-center gap-1 hover:underline"
                        >
                          <table.FlexRender header={header} />
                          {sorted === "asc" && <ArrowUp aria-hidden size={14} />}
                          {sorted === "desc" && <ArrowDown aria-hidden size={14} />}
                        </button>
                      ) : (
                        <table.FlexRender header={header} />
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-t border-border align-top">
                {row.getAllCells().map((cell) => (
                  <td key={cell.id} className="px-3 py-2">
                    <table.FlexRender cell={cell} />
                  </td>
                ))}
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="px-3 py-6 text-center text-muted">
                  Ninguna factura coincide con los filtros.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
