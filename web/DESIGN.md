# Alinka design system: integration into web/

Adapted from `alinka-ui` for React Router 7 (SPA), Tailwind CSS 4, Base UI and Lucide. Compiled and checked with Tailwind 4.3: `preview/light.png` and `preview/dark.png` show the kit applied to Alinka's own content.

## Files

| From this folder | To the repo | What it is |
| --- | --- | --- |
| `web/app/styles/tokens.css` | `web/app/styles/tokens.css` (replaces the neutral one) | Colours (light and dark), `--space-*`, radii, fonts, `--doc-*` |
| `web/app/styles/theme.css` | `web/app/styles/theme.css` | Tailwind 4 `@theme` mapped to the tokens |
| `web/app/styles/alinka.css` | `web/app/styles/alinka.css` | Base styles plus every `ak-` component, in `@layer components` |
| `web/app/components/brand/*.tsx` | same path | `AlinkaLogo` and `AlinkaMark`, with strokes in `currentColor` |
| `web/public/favicon.svg`, `web/public/brand/*.svg` | same paths | Favicon and logo files |

`web/app/app.css` starts with, in this order:

```css
@import "tailwindcss";
@import "./styles/tokens.css";
@import "./styles/theme.css";
@import "./styles/alinka.css";
```

`root.tsx` `links` adds the favicon (`/favicon.svg`, `image/svg+xml`), preconnects to `fonts.googleapis.com` and `fonts.gstatic.com` (crossOrigin), and this stylesheet:
`https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Manrope:wght@400;500;600;700&display=swap`.
Remove any other font, such as Inter from the template. No Pico.css: the kit was written for it, and this adaptation drops it.

## Tokens and utilities

- **Colours as utilities:**
  - surfaces and text: `bg-paper`, `bg-surface`, `bg-desk`, `text-ink`, `text-ink-muted`, `text-ink-subtle`;
  - borders: `border-line`, `border-line-strong`;
  - decisions: `text-pagada` with `bg-pagada-tint`, `text-frenada` with `bg-frenada-tint`, `text-pendiente` with `bg-pendiente-tint`;
  - on dark ink: `text-on-ink`.
- **Type:** `text-caption` 12, `text-small` 13, `text-body` 15 (the base), `text-lead` 17, `text-title` 20, `text-stat` 24, `text-h1` 28, `text-display` 40.
- **Radii:** `rounded-lg` 8 for controls, `rounded-xl` 12 for containers, `rounded-full` for pills, `rounded-none` for document sheets. Tailwind's default 4px spacing scale already matches `--space-*`.
- **Dark mode:** automatic from the system preference. `data-theme="light"` or `"dark"` on `<html>` forces one. Document sheets and page images stay paper-white in both themes.

## Rules that keep it right

1. **Vocabulary:** the tokens are named `--retenida`, but the UI always says **Frenada**. The three states read "Pagada", "Frenada" and "Pendiente de aprobación".
2. **Colour is never the only signal.** Each decision chip has an icon:
   - Pagada `CircleCheck`;
   - Frenada `CirclePause`;
   - Pendiente `Clock`.

   A security alert is `ak-sec` or `ak-sec-box` with `ShieldAlert`, outlined in ink, with no colour of its own.
3. **Document text crosses the trust boundary visibly.** Anything read from a document goes in `ak-slip` (quotes) or `ak-docsheet` (emails and chats), escaped and never styled like the interface:
   - `<mark>` for the quote that grounds a value;
   - `<del>` for hidden text that was dropped;
   - `ak-hidden-char` for invisible characters (show the code point, for example `U+200B`).
4. **Contrast:** every text pair passes WCAG AA, except `--ink-subtle` on `--desk`. Use `text-ink-muted` there. Controls and inputs use `border-line-strong`; `border-line` is only for dividers and card outlines.
5. **Icons:** Lucide, with `className="ak-icon"`. The kit sizes it to 16px and sets the stroke width to 1.75.
6. **Motion:** `ak-moved` on cards that change column when the sandbox re-decides, `ak-progress` while "Ejecutar agente" runs, and `ak-skel` while a detail loads. Each one stops under `prefers-reduced-motion`.

## Components by screen

| Screen | Components |
| --- | --- |
| Shell | `ak-header` with `AlinkaLogo` (22px high) · `ak-nav`, with `aria-current="page"` on the active link · `ak-seg` for "Ejecución canónica / Mi sandbox" · `ak-banner--demo` ("Datos 100% ficticios…") · `ak-footer` |
| Tablero | `ak-counts`, four `ak-count` toggle buttons with `aria-pressed`: Bandeja, Pagadas, Frenadas, Pendientes de aprobación · `ak-btn--primary` "Ejecutar agente" with `ak-progress` · `ak-board` and `ak-column` · `ak-card`: beneficiary, amount with currency in `<small>`, meta line with the channel icon (`Mail`, `FileText`, `Image`, `MessageSquare`), reason, tags (decision `ak-chip`, `ak-rule` for the determining rule, `ak-sec` when alerted) · table view: TanStack Table with `ak-log` styles · empty state: `ak-empty` and `ak-schema` |
| Detalle | `ak-detail`, two columns: `ak-detail__data` and `ak-detail__doc`<br>Data column:<br>• `ak-h1` and `ak-detail__amount`<br>• `ak-sec-box` first, when alerted<br>• `ak-fields` and `ak-field`: label; value; quote as `ak-slip ak-slip--inline`; `ak-checks` with "Cita en la página", "Segunda lectura coincide" and "JEV", using `ok` or `warn`<br>• fired rules as `ak-rule` (`--retiene` or `--escala`, passes as `--pasa`), each with its sentence<br>• `ak-account`: the account on file, masked, with the source "Lista de beneficiarios"<br>• `ak-timeline`: received, read, verified, decided, approved<br>• approve and reject: `ak-btn--primary` and `ak-btn--secondary`, the name in `ak-input ak-input--text`, a Base UI Dialog styled with `ak-backdrop` and `ak-dialog`, buttons shown only where allowed<br>Document column:<br>• `ak-doctools`<br>• `ak-page` (the page PNG) with an `ak-box` per `Field.boxes`, and `is-active` while its field is hovered or focused<br>• emails and chats as `ak-docsheet` |
| Reglas | One `ak-sentence` per editable rule, for example "R06 · Escalar si el monto supera [2000] USD o queda a menos del [5] % por debajo", with `ak-input` (`ak-input--short` for percentages) · `ak-impact` under the form ("Con este cambio, 3 facturas pasan a Pendientes de aprobación") · "Añadir beneficiario" as a form in `ak-sentence` · "Restablecer sandbox" as `ak-btn--secondary` |
| Registro | `ak-log` table · `ak-hash` (short hash with `Link2`) · `ak-verify ak-verify--ok` "Cadena verificada" (`ShieldCheck`) or `ak-verify--roto` (`ShieldX`) · CSV export as `ak-btn--secondary` |
| Evaluación | `ak-stats` and `ak-stat` tiles: improper approvals "0 de K" with the 95% bound, autonomy "X% de un máximo de Y%", cost per invoice, p95 · `ak-chart` for the risk–coverage curve: JEV on is `series-a` (ink, solid), JEV off is `series-b` (muted, dashed), the grid is `.grid`; never decision colours |
| Cómo funciona | `ak-h1` and `ak-h2` · `ak-steps` for the pipeline (Lee · Verifica · Decide · Registra) · `ak-sec-box` for each guarantee · `ak-slip` for one example of document text |
