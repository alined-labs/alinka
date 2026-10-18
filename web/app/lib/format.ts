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

/** 310000000, "COP" -> "COP 3.100.000,00" */
export function formatMoney(minor: number | null | undefined, currency: string | null | undefined): string {
  if (minor == null || !currency) return "—";
  const digits = exponent(currency);
  const sign = minor < 0 ? "-" : "";
  const abs = Math.abs(minor);
  const scale = 10 ** digits;
  const whole = Math.floor(abs / scale);
  const fraction = abs % scale;
  const grouped = whole.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const tail = digits > 0 ? `,${fraction.toString().padStart(digits, "0")}` : "";
  return `${sign}${currency} ${grouped}${tail}`;
}

/** usd_minor -> "USD 1.180,00" */
export function formatUsd(minor: number | null | undefined): string {
  return formatMoney(minor, "USD");
}

const dateTime = new Intl.DateTimeFormat("es-CO", {
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "UTC",
});

export function formatReceived(iso: string): string {
  return `${dateTime.format(new Date(iso))} UTC`;
}
