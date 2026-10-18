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

import { CHANNEL, ChannelIcon, DecisionChip, ReasonText, RuleChip, SecurityTag } from "./badges";
import { Amount, BeneficiaryName } from "./invoice-card";

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
    cell: (info) => <span className="font-mono whitespace-nowrap">{info.getValue()}</span>,
  }),
  col.accessor("channel", {
    header: "Canal",
    cell: (info) => (
      <span className="inline-flex items-center gap-1.5">
        <ChannelIcon channel={info.getValue()} />
        {CHANNEL[info.getValue()].label}
      </span>
    ),
  }),
  col.accessor((c) => c.beneficiary_id ?? NO_BENEFICIARY, {
    id: "beneficiary",
    header: "Beneficiario",
    filterFn: "equals",
    cell: (info) => <BeneficiaryName card={info.row.original} />,
  }),
  col.accessor("amount_minor", {
    header: "Monto",
    sortFn: "basic",
    cell: (info) => (
      <span className="ak-card__amount">
        <Amount minor={info.getValue()} currency={info.row.original.currency} />
      </span>
    ),
  }),
  col.accessor("usd_minor", {
    header: "USD",
    sortFn: "basic",
    cell: (info) => (
      <span className="ak-card__amount">
        <Amount minor={info.getValue()} currency="USD" />
      </span>
    ),
  }),
  col.accessor("state", {
    header: "Estado",
    cell: (info) => {
      const state = info.getValue();
      return state === "inbox" ? <span className="ak-muted">{STATE_LABEL.inbox}</span> : <DecisionChip decision={state} />;
    },
  }),
  col.accessor((c) => c.determining_rule ?? NO_RULE, {
    id: "rule",
    header: "Regla",
    filterFn: "equals",
    cell: (info) => {
      const c = info.row.original;
      if (!c.determining_rule) return <span className="ak-muted">—</span>;
      return (
        <RuleChip rule={c.determining_rule} name={c.determining_rule_es} decision={c.state === "inbox" ? undefined : c.state} />
      );
    },
  }),
  col.accessor((c) => c.alerts.join(","), {
    id: "alerts",
    header: "Alertas",
    enableSorting: false,
    cell: (info) => <SecurityTag rules={info.row.original.alerts} />,
  }),
  col.accessor("reason_es", {
    header: "Motivo",
    enableSorting: false,
    cell: (info) => (
      <div className="min-w-80">
        <ReasonText text={info.getValue()} className="ak-muted" />
      </div>
    ),
  }),
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
    <label className="grid min-w-56 gap-1 text-small text-ink-muted" htmlFor={id}>
      {label}
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)} className="ak-input ak-input--text">
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
    const rules = new Map<string, string>();
    const beneficiaries = new Map<string, string>();
    for (const c of cards) {
      rules.set(c.determining_rule ?? NO_RULE, c.determining_rule ? `${c.determining_rule} · ${c.determining_rule_es ?? ""}` : "Ninguna regla");
      beneficiaries.set(c.beneficiary_id ?? NO_BENEFICIARY, c.beneficiary_id ? (c.beneficiary_name ?? c.beneficiary_id) : "No está en la lista");
    }
    const sorted = (m: Map<string, string>) =>
      [...m].map(([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label, "es"));
    return { rules: sorted(rules), beneficiaries: sorted(beneficiaries) };
  }, [cards]);

  const filterValue = (id: string) => String(columnFilters.find((f) => f.id === id)?.value ?? "");
  const setFilter = (id: string) => (value: string) =>
    setColumnFilters((prev) => [...prev.filter((f) => f.id !== id), ...(value ? [{ id, value }] : [])]);

  const rows = table.getRowModel().rows;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-4" role="group" aria-label="Filtros">
        <Filter id="f-rule" label="Regla" value={filterValue("rule")} options={options.rules} onChange={setFilter("rule")} />
        <Filter
          id="f-beneficiary"
          label="Beneficiario"
          value={filterValue("beneficiary")}
          options={options.beneficiaries}
          onChange={setFilter("beneficiary")}
        />
      </div>
      <p className="text-small text-ink-muted" aria-live="polite">
        {rows.length} de {cards.length} facturas
      </p>
      <div className="overflow-x-auto rounded-xl border border-line bg-surface">
        <table className="ak-log">
          <caption className="ak-sr">Facturas del tablero</caption>
          <thead>
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id}>
                {group.headers.map((header) => {
                  const sorted = header.column.getIsSorted();
                  const canSort = header.column.getCanSort();
                  return (
                    <th
                      key={header.id}
                      scope="col"
                      aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : undefined}
                    >
                      {canSort ? (
                        <button
                          type="button"
                          onClick={header.column.getToggleSortingHandler()}
                          className="inline-flex items-center gap-1 font-semibold hover:text-ink"
                        >
                          <table.FlexRender header={header} />
                          {sorted === "asc" && <ArrowUp aria-hidden className="ak-icon" />}
                          {sorted === "desc" && <ArrowDown aria-hidden className="ak-icon" />}
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
              <tr key={row.id}>
                {row.getAllCells().map((cell) => (
                  <td key={cell.id}>
                    <table.FlexRender cell={cell} />
                  </td>
                ))}
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="ak-empty">
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
