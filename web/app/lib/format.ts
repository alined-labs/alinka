/*
 * Display formatting only. Every amount arrives from the API already computed, in integer
 * minor units with its ISO 4217 code; this file only places the decimal point and separators.
 */

// ISO 4217 minor-unit exponents that differ from 2. Intl follows CLDR, which disagrees with
// ISO for some currencies (COP), so the exponent comes from here, not from Intl.
const EXPONENT: Record<string, number> = { CLP: 0, JPY: 0, KRW: 0, PYG: 0, BHD: 3, KWD: 3 };

export function exponent(currency: string): number {
  return EXPONENT[currency] ?? 2;
}

/** 310000000, "COP" -> { number: "3.100.000,00", currency: "COP" }; null when unknown. */
export function amountParts(
  minor: number | null | undefined,
  currency: string | null | undefined,
): { number: string; currency: string } | null {
  if (minor == null || !currency) return null;
  const digits = exponent(currency);
  const sign = minor < 0 ? "-" : "";
  const abs = Math.abs(minor);
  const scale = 10 ** digits;
  const whole = Math.floor(abs / scale);
  const fraction = abs % scale;
  const grouped = whole.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const tail = digits > 0 ? `,${fraction.toString().padStart(digits, "0")}` : "";
  return { number: `${sign}${grouped}${tail}`, currency };
}

/** 310000000, "COP" -> "3.100.000,00 COP" */
export function formatMoney(minor: number | null | undefined, currency: string | null | undefined): string {
  const parts = amountParts(minor, currency);
  return parts ? `${parts.number} ${parts.currency}` : "—";
}

/** usd_minor -> "1.180,00 USD" */
export function formatUsd(minor: number | null | undefined): string {
  return formatMoney(minor, "USD");
}

const day = new Intl.DateTimeFormat("es", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

/** "2026-10-03T09:30:00Z" -> "3 oct 2026" */
export function formatDay(iso: string): string {
  return day.format(new Date(iso));
}

const dayTime = new Intl.DateTimeFormat("es", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "UTC",
});

/** "2026-10-06T13:45:00Z" -> "6 oct 2026, 13:45 UTC" */
export function formatDateTime(iso: string): string {
  return `${dayTime.format(new Date(iso))} UTC`;
}

/**
 * "5.200.000,50" or "5200000.50" in major units -> integer minor units, without floating point.
 * The last "," or "." followed by up to the currency's decimals is the decimal mark. Null if invalid.
 */
export function parseMajor(text: string, currency: string): number | null {
  const digits = exponent(currency);
  const t = text.trim().replace(/\s/g, "");
  if (!/^\d[\d.,]*$/.test(t)) return null;
  const m = t.match(/^(.*?)[.,](\d+)$/);
  let whole = t;
  let frac = "";
  if (m && m[2]!.length <= digits && m[2]!.length !== 3) {
    whole = m[1]!;
    frac = m[2]!;
  }
  whole = whole.replace(/[.,]/g, "");
  if (!/^\d+$/.test(whole)) return null;
  const minor = BigInt(whole) * 10n ** BigInt(digits) + BigInt((frac + "0".repeat(digits)).slice(0, digits) || "0");
  return minor <= BigInt(Number.MAX_SAFE_INTEGER) ? Number(minor) : null;
}

/** data/fx.yaml names each official rate in its publisher's words; the page says them in Spanish. */
const FX_SOURCE_ES: Record<string, string> = {
  "Banco de la República TRM": "TRM del Banco de la República",
  "Banxico FIX (DOF)": "FIX de Banxico (DOF)",
  "BCB PTAX venda": "PTAX de venta del Banco Central do Brasil",
  "ECB reference rate": "tasa de referencia del BCE",
};

export const fxSourceEs = (source: string) => FX_SOURCE_ES[source] ?? source;

/** "tasa 5,08260 (PTAX de venta del Banco Central do Brasil, 16 oct 2026)": the rate keeps its digits. */
export function formatFxLine(fx: { rate: string | number; source: string; date: string }): string {
  return `tasa ${String(fx.rate).replace(".", ",")} (${fxSourceEs(fx.source)}, ${formatDay(fx.date)})`;
}
