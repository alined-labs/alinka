/*
 * Everything the showcase page says, in Spanish (/) and English (/en). Both versions live in
 * one file so they cannot drift apart: showcase-copy.test.ts checks that they have the same
 * shape. The figures are never typed into the sentences. They come from FACTS, which cites
 * EVAL_REPORT.md, and are formatted for each language, so a number can only be wrong in one place.
 */

export type Lang = "es" | "en";

/**
 * The evaluation's numbers, from EVAL_REPORT.md: the recorded run of 18 Oct 2026 with rules
 * 2026-10-18.1 on 175 fictional invoices. "Must not pay" counts every invoice whose gold
 * decision is HOLD (47) or ESCALATE (38). The 13 disagreements are all gold PAY invoices that
 * Alinka escalated to a person, which is why none of them overpaid.
 */
export const FACTS = {
  invoices: 175,
  mustNotPay: 85,
  improperPaid: 0,
  improperUpperBound: 0.035,
  autonomous: 124,
  autonomyCeiling: 137,
  attacks: 13,
  attacksAlerted: 13,
  decisionAccuracy: 0.926,
  disagreements: 13,
  costPerInvoiceUsd: 0.02348,
  latencyP50Seconds: 11.44,
  latencyP95Seconds: 16.379,
  rules: 16,
  rulesVersion: "2026-10-18.1",
} as const;

/** Where the page links out: the code and its author are the portfolio's proof. */
export const LINKS = {
  repo: "https://github.com/alined-labs/alinka",
  author: "https://github.com/alinedmooner",
  license: "https://www.gnu.org/licenses/agpl-3.0.html",
} as const;

/** The pitch video and the board screenshots, served as static files from web/public/media. */
export const MEDIA = {
  video: {
    src: "/media/alinka-pitch.mp4",
    poster: "/media/alinka-pitch-poster.webp",
    width: 1920,
    height: 1080,
  },
  /** One capture per theme, at 1x (1136 px) and 2x (2272 px) of the board's width. */
  board: {
    light: { x1: "/media/tablero-light-1x.webp", x2: "/media/tablero-light.webp" },
    dark: { x1: "/media/tablero-dark-1x.webp", x2: "/media/tablero-dark.webp" },
    width: 2272,
    height: 1400,
  },
} as const;

/** A row of the spec sheet: what was measured, the figure, and the caveat that goes with it. */
export interface SpecRow {
  label: string;
  value: string;
  note: string;
}

export interface FooterItem {
  text: string;
  href?: string;
}

export interface ShowcaseCopy {
  meta: { title: string; description: string };
  nav: { skip: string; home: string; switchLabel: string; switchHref: string; switchLang: Lang; cta: string };
  hero: { figure: string; headline: string; qualifier: string; lede: string; primary: string; secondary: string };
  spec: { title: string; rows: SpecRow[]; source: string; link: string };
  steps: { title: string; items: { title: string; text: string }[]; link: string };
  video: { title: string; caption: string; fallback: string };
  demo: { title: string; text: string; cta: string; alt: string; callouts: [string, string, string] };
  foot: { statement: string; items: FooterItem[]; credit: string; author: string; code: string };
}

const LOCALE: Record<Lang, string> = { es: "es-CO", en: "en-US" };

/**
 * Number formatting per language: Colombian Spanish writes a decimal comma ("3,5%", "11,4 s"),
 * English a decimal point ("3.5%", "11.4 s"); neither puts a space before %, like the rest of the
 * site. Seconds get a non-breaking space so the unit never wraps away from its number.
 */
export function formats(lang: Lang) {
  const locale = LOCALE[lang];
  const num = (n: number, digits = 0) =>
    new Intl.NumberFormat(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n);
  const pct = (ratio: number, digits = 0) =>
    new Intl.NumberFormat(locale, { style: "percent", minimumFractionDigits: digits, maximumFractionDigits: digits }).format(ratio);
  const secs = (s: number) => `${num(s, 1)}\u00a0s`;
  const usd = (n: number) => `US$${num(n, 3)}`;
  return { num, pct, secs, usd };
}

const es = formats("es");
const en = formats("en");
const F = FACTS;

export const COPY: Record<Lang, ShowcaseCopy> = {
  es: {
    meta: {
      title: "Alinka · Cuentas por pagar con reglas y registro",
      description: `Agente de cuentas por pagar del hackathon HackRadar 30X: la IA lee la factura, ${F.rules} reglas deciden y un registro encadenado explica. ${F.improperPaid} de ${F.mustNotPay} facturas que no debían pagarse se pagaron. Demo congelada con datos ficticios.`,
    },
    nav: {
      skip: "Saltar al contenido",
      home: "Alinka, inicio",
      switchLabel: "English",
      switchHref: "/en",
      switchLang: "en",
      cta: "Abrir la demo",
    },
    hero: {
      figure: String(F.improperPaid),
      headline: `de ${F.mustNotPay} facturas que no debían pagarse se pagaron.`,
      qualifier: `Evaluación grabada sobre ${F.invoices} facturas ficticias en cinco monedas · cota superior del ${es.pct(0.95)}: ${es.pct(F.improperUpperBound, 1)}.`,
      lede: "Alinka es un agente de cuentas por pagar para el reto Blinka de HackRadar 30X. La IA solo lee la factura; dieciséis reglas escritas en código deciden si se paga, se frena o pasa a una persona, y cada decisión queda en un registro encadenado que explica por qué.",
      primary: "Abrir la demo",
      secondary: "Ver el código",
    },
    spec: {
      title: "Lo que midió la evaluación",
      rows: [
        {
          label: "Pagos indebidos",
          value: `${F.improperPaid} de ${F.mustNotPay}`,
          note: `cota superior del ${es.pct(0.95)} (Clopper–Pearson): ${es.pct(F.improperUpperBound, 1)}`,
        },
        {
          label: "Decididas sin una persona",
          value: `${es.num(F.autonomous)} de ${F.invoices} (${es.pct(F.autonomous / F.invoices)})`,
          note: `techo posible: ${F.autonomyCeiling} (${es.pct(F.autonomyCeiling / F.invoices)})`,
        },
        {
          label: "Alertas de seguridad en ataques",
          value: `${F.attacksAlerted} de ${F.attacks}`,
          note: "cada ataque del conjunto levantó su alerta",
        },
        {
          label: "Exactitud de la decisión",
          value: es.pct(F.decisionAccuracy, 1),
          note: `los ${F.disagreements} desacuerdos escalaron facturas pagables; ninguno pagó de más`,
        },
        { label: "Costo por factura", value: es.usd(F.costPerInvoiceUsd), note: "en llamadas a modelos, medido al grabar" },
        {
          label: "Latencia por factura",
          value: `p50 ${es.secs(F.latencyP50Seconds)} · p95 ${es.secs(F.latencyP95Seconds)}`,
          note: "medida en la ejecución grabada",
        },
        { label: "Reglas", value: String(F.rules), note: "deterministas, en código; solo ellas aprueban un pago" },
        { label: "Monedas", value: "5", note: "COP, MXN, BRL, EUR y USD, con la tasa oficial del día" },
      ],
      source: `Fuente: EVAL_REPORT.md, ejecución grabada del 18 de octubre de 2026 (reglas ${F.rulesVersion}). Datos ${es.pct(1)} ficticios.`,
      link: "Ver la evaluación",
    },
    steps: {
      title: "Cómo decide una factura",
      items: [
        {
          title: "Revisa antes de leer",
          text: "El código busca texto blanco, capas ocultas, caracteres invisibles e instrucciones escondidas antes de que la IA vea el documento.",
        },
        {
          title: "Lee con evidencia",
          text: "Claude Sonnet lee cada página sin herramientas ni acceso a las reglas y devuelve cada dato con su cita; Claude Haiku hace una segunda lectura.",
        },
        {
          title: "Verifica en código",
          text: "Cada cita debe aparecer en la página, los montos se convierten con la tasa oficial del día y el total debe cuadrar; JEV pregunta si algo se leyó mal.",
        },
        {
          title: "Decide y registra",
          text: "Dieciséis reglas deciden: Frenada gana sobre Pendiente y Pendiente sobre Pagada. La decisión entra en un registro encadenado con su motivo en español.",
        },
      ],
      link: "Cómo funciona, en detalle",
    },
    video: {
      title: "El pitch, en 2:55",
      caption: "Video de la entrega final en HackRadar 30X, 18 de octubre de 2026.",
      fallback: "Tu navegador no reproduce este video. Descárgalo (MP4, 6,7 MB).",
    },
    demo: {
      title: "La demo sigue abierta",
      text: "El 22 de octubre de 2026 la API se retiró y la demo quedó congelada: reproduce las respuestas que grabó. Puedes ejecutar el agente, abrir cada factura con su página y su traza, verificar la cadena y correr las muestras de Probar. Editar reglas, aprobar y subir facturas quedó desactivado.",
      cta: "Abrir el tablero",
      alt: "El tablero de Alinka con las 30 facturas de octubre decididas: 16 pagadas, 7 frenadas y 7 pendientes de aprobación, cada una con su motivo.",
      callouts: [
        "Tres decisiones: Pagada, Frenada y Pendiente de aprobación.",
        "Cada tarjeta dice por qué, con la regla y sus valores.",
        "Lo que viene del documento se muestra aparte, como cita, nunca como interfaz.",
      ],
    },
    foot: {
      statement: "La IA lee, las reglas deciden, el registro explica.",
      items: [
        { text: "HackRadar 30X · reto Blinka · octubre de 2026" },
        { text: "Proyecto cerrado" },
        { text: "Código abierto (AGPL-3.0)", href: LINKS.license },
        { text: `Datos ${es.pct(1)} ficticios` },
      ],
      credit: "Hecho por",
      author: "Daniel M.C.",
      code: "Código en GitHub",
    },
  },
  en: {
    meta: {
      title: "Alinka · Accounts payable with rules and a log",
      description: `An accounts-payable agent from the HackRadar 30X hackathon: the AI reads the invoice, ${F.rules} rules decide and a hash-chained log explains. ${F.improperPaid} of ${F.mustNotPay} invoices that should not have been paid were paid. A frozen demo with fictional data.`,
    },
    nav: {
      skip: "Skip to content",
      home: "Alinka, home",
      switchLabel: "Español",
      switchHref: "/",
      switchLang: "es",
      cta: "Open the demo",
    },
    hero: {
      figure: String(F.improperPaid),
      headline: `of ${F.mustNotPay} invoices that should not have been paid were paid.`,
      qualifier: `Recorded evaluation on ${F.invoices} fictional invoices in five currencies · ${en.pct(0.95)} upper bound: ${en.pct(F.improperUpperBound, 1)}.`,
      lede: "Alinka is an accounts-payable agent built for the Blinka challenge at HackRadar 30X. The AI only reads the invoice; sixteen rules written in code decide whether it is paid, held or sent to a person, and every decision lands in a hash-chained log that explains why.",
      primary: "Open the demo",
      secondary: "Read the code",
    },
    spec: {
      title: "What the evaluation measured",
      rows: [
        {
          label: "Improper payments",
          value: `${F.improperPaid} of ${F.mustNotPay}`,
          note: `${en.pct(0.95)} upper bound (Clopper–Pearson): ${en.pct(F.improperUpperBound, 1)}`,
        },
        {
          label: "Decided without a person",
          value: `${en.num(F.autonomous)} of ${F.invoices} (${en.pct(F.autonomous / F.invoices)})`,
          note: `possible ceiling: ${F.autonomyCeiling} (${en.pct(F.autonomyCeiling / F.invoices)})`,
        },
        {
          label: "Security alerts on attacks",
          value: `${F.attacksAlerted} of ${F.attacks}`,
          note: "every attack in the set raised its alert",
        },
        {
          label: "Decision accuracy",
          value: en.pct(F.decisionAccuracy, 1),
          note: `all ${F.disagreements} disagreements escalated payable invoices; none overpaid`,
        },
        { label: "Cost per invoice", value: en.usd(F.costPerInvoiceUsd), note: "in model calls, measured while recording" },
        {
          label: "Latency per invoice",
          value: `p50 ${en.secs(F.latencyP50Seconds)} · p95 ${en.secs(F.latencyP95Seconds)}`,
          note: "measured on the recorded run",
        },
        { label: "Rules", value: String(F.rules), note: "deterministic, in code; only they approve a payment" },
        { label: "Currencies", value: "5", note: "COP, MXN, BRL, EUR and USD, at the day's official rate" },
      ],
      source: `Source: EVAL_REPORT.md, recorded run of October 18, 2026 (rules ${F.rulesVersion}). 100% fictional data.`,
      link: "See the evaluation (in Spanish)",
    },
    steps: {
      title: "How an invoice gets decided",
      items: [
        {
          title: "Check before reading",
          text: "Code looks for white text, hidden layers, invisible characters and planted instructions before the AI sees the document.",
        },
        {
          title: "Read with evidence",
          text: "Claude Sonnet reads each page with no tools and no access to the rules, returning every field with its quote; Claude Haiku reads it a second time.",
        },
        {
          title: "Verify in code",
          text: "Every quote must appear on the page, amounts convert at the day's official rate and the total must add up; JEV asks whether anything was misread.",
        },
        {
          title: "Decide and record",
          text: "Sixteen rules decide: Held beats Pending, and Pending beats Paid. The decision enters a hash-chained log with its reason in Spanish.",
        },
      ],
      link: "How it works, in detail (in Spanish)",
    },
    video: {
      title: "The pitch, in 2:55",
      caption: "Final submission video for HackRadar 30X, October 18, 2026. In Spanish.",
      fallback: "Your browser can't play this video. Download it (MP4, 6.7 MB).",
    },
    demo: {
      title: "The demo is still open",
      text: "On October 22, 2026 the API was retired and the demo was frozen: it replays the responses it recorded. You can run the agent, open every invoice with its page and trace, verify the chain and run Probar's samples. Editing rules, approving and uploading invoices are switched off.",
      cta: "Open the board",
      alt: "Alinka's board with October's 30 invoices decided: 16 paid, 7 held and 7 pending approval, each with its reason.",
      callouts: [
        "Three decisions: Paid, Held and Pending approval (Pagada, Frenada, Pendiente).",
        "Every card says why, naming the rule and its values.",
        "Text from the document is shown apart, as a quote, never as interface.",
      ],
    },
    foot: {
      statement: "The AI reads, the rules decide, the log explains.",
      items: [
        { text: "HackRadar 30X · Blinka challenge · October 2026" },
        { text: "Project closed" },
        { text: "Open source (AGPL-3.0)", href: LINKS.license },
        { text: "100% fictional data" },
      ],
      credit: "Made by",
      author: "Daniel M.C.",
      code: "Code on GitHub",
    },
  },
};
