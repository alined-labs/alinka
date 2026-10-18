# Architecture (C4)

Alinka in three C4 levels: the system in its context, the containers inside it, and the components of the decision pipeline. The line that matters is the **trust boundary**: only typed `InvoiceFacts` cross from the reading side into the rules, and only the decision core can return PAY.

Legend: dark blue = person, blue = Alinka, light blue = component, grey = external. Solid arrows are calls or data flow; the trust boundary is the dashed box.

## Level 1 · System context

```mermaid
flowchart TB
  supplier["<b>Supplier or contractor</b><br/><i>[Person, external]</i><br/>Sends facturas, cuentas de cobro and invoices by email, PDF, image or chat"]
  operator["<b>AP operator</b><br/><i>[Person]</i><br/>Reviews the inbox, runs the agent, tunes the rules"]
  approver["<b>Approver</b><br/><i>[Person]</i><br/>Approves or rejects escalations by name"]
  alinka["<b>Alinka</b><br/><i>[Software system]</i><br/>Reads invoices, pays only what the company's rules allow, holds or escalates the rest, and logs why"]
  blinka["<b>Blinka</b><br/><i>[Software system, external]</i><br/>Accounts, balance, beneficiaries on file and payouts. Simulated in the demo: no integration, no money moves"]
  anthropic["<b>Anthropic API</b><br/><i>[External system]</i><br/>Claude Sonnet 5.5 reads; Claude Haiku 5.5 reads again"]
  openrouter["<b>OpenRouter</b><br/><i>[External system]</i><br/>JEV 1.13 answers escalate-only verification questions"]

  supplier -- "Invoices" --> alinka
  operator -- "Uses<br/>[HTTPS]" --> alinka
  approver -- "Approves by name<br/>[HTTPS]" --> alinka
  alinka -- "Beneficiary list, balance, budgets;<br/>payment previews (proposed)" --> blinka
  alinka -- "Page images and visible text<br/>[HTTPS]" --> anthropic
  alinka -- "Short text questions<br/>[HTTPS]" --> openrouter

  classDef person fill:#08427b,stroke:#073b6f,color:#fff
  classDef system fill:#1168bd,stroke:#0b4884,color:#fff
  classDef external fill:#8a8a8a,stroke:#6b6b6b,color:#fff
  class operator,approver person
  class supplier external
  class alinka system
  class blinka,anthropic,openrouter external
```

## Level 2 · Containers

```mermaid
flowchart TB
  user["<b>AP operator / approver</b><br/><i>[Person]</i>"]
  supplier["<b>Supplier</b><br/><i>[Person, external]</i>"]

  subgraph alinka["Alinka [Software system]"]
    direction TB
    edge["<b>Edge</b><br/><i>[Container: Cloudflare Worker]</i><br/>alinka.alinedlabs.co: serves the app, forwards /api/* with X-Edge-Secret and X-Client-IP"]
    web["<b>Web app</b><br/><i>[Container: React Router 7 SPA, TanStack Query and Table, Tailwind CSS 4, Base UI]</i><br/>Bandeja, Tablero, Detalle, Reglas, Registro, Evaluación, Cómo funciona"]
    api["<b>API</b><br/><i>[Container: FastAPI, Python 3.12, Azure Container Apps]</i><br/>Board, Ejecutar agente, rules, approvals, log; runs the decision core per sandbox"]
    reader["<b>Reader jobs</b><br/><i>[Container: Python, alinka.jobs.extract]</i><br/>Sanitize, read, verify; writes InvoiceFacts runs"]
    evals["<b>Evaluation</b><br/><i>[Container: Python CLI, make eval]</i><br/>k of K with the 95% bound, autonomy, risk–coverage, cost and latency"]
    db[("<b>Database</b><br/><i>[Container: PostgreSQL 17 / Neon]</i><br/>Sessions, rule versions, hash-chained decisions, ledger, response cache")]
    repo[("<b>Repository data</b><br/><i>[Container: files in git]</i><br/>175 fictional documents and labels, recorded runs, cached model responses, eval report")]
  end

  anthropic["<b>Anthropic API</b><br/><i>[External]</i>"]
  openrouter["<b>OpenRouter · JEV</b><br/><i>[External]</i>"]

  user -- "HTTPS" --> edge
  edge -- "Delivers" --> web
  web -- "JSON over /api/*" --> edge
  edge -- "HTTPS + edge secret" --> api
  api -- "SQL, one transaction per decision" --> db
  api -- "Loads runs, renders, report" --> repo
  supplier -- "Email, PDF, image, chat" --> reader
  reader -- "Reads documents; writes runs and cache" --> repo
  reader -- "Images + visible text" --> anthropic
  reader -- "Choice and yes/no questions" --> openrouter
  evals -- "Reads labels and runs; writes report" --> repo

  classDef person fill:#08427b,stroke:#073b6f,color:#fff
  classDef container fill:#438dd5,stroke:#2e6295,color:#fff
  classDef external fill:#8a8a8a,stroke:#6b6b6b,color:#fff
  class user person
  class supplier,anthropic,openrouter external
  class edge,web,api,reader,evals,db,repo container
  style alinka fill:#ffffff00,stroke:#1168bd,stroke-width:2px,stroke-dasharray:6 4,color:#1168bd
```

## Level 3 · Components of the decision pipeline

```mermaid
flowchart TB
  doc["<b>Untrusted document</b><br/>email, PDF, image, chat"]

  subgraph reading["Reading side (untrusted input)"]
    ingest["<b>Sanitizer</b><br/><i>[alinka.ingest]</i><br/>PyMuPDF text trace, covered-text render test, Tesseract boxes, Unicode tag and bidi characters, HTML vs plain text"]
    extract["<b>Reader</b><br/><i>[alinka.extract]</i><br/>Claude Sonnet 5.5, structured output, no tools: every field with a quote, plus instructions_seen"]
    verify["<b>Verifier</b><br/><i>[alinka.verify]</i><br/>Normalize amounts and dates, parse words, grounding boxes, regex re-read, totals, Haiku second reading, JEV J1 and J2 → risk"]
    cache["<b>Model cache</b><br/><i>[alinka.cache]</i><br/>record / replay / live, pinned models, cost and latency"]
  end

  facts{{"<b>InvoiceFacts</b><br/>typed, verified<br/>the trust boundary"}}

  subgraph deciding["Deciding side (code only)"]
    world["<b>World</b><br/><i>[alinka.world]</i><br/>company, beneficiaries and contracts, rules.yaml, official FX"]
    rules["<b>Rules R01–R16</b><br/><i>[alinka.rules]</i><br/>pure functions"]
    core["<b>Decision core</b><br/><i>[alinka.decide.core]</i><br/>HOLD over ESCALATE over PAY; the only source of PAY; approvals re-check R03, R05, R07, R08"]
    audit["<b>Audit log</b><br/><i>[alinka.audit]</i><br/>RFC 8785 + SHA-256 chain, Spanish reasons citing values, CSV"]
    store["<b>Ledger and records</b><br/><i>[alinka.db]</i><br/>advisory lock per session; unique keys become R03"]
  end

  routes["<b>HTTP routes</b><br/><i>[alinka.api, FastAPI]</i><br/>sandboxes by cookie, edge-secret check, Ejecutar agente, approve by name"]
  person["<b>Approver</b><br/><i>[Person]</i>"]
  llm["<b>Anthropic · OpenRouter</b><br/><i>[External]</i>"]

  doc --> ingest --> extract --> verify --> facts
  extract <--> cache
  verify <--> cache
  cache <--> llm
  facts --> rules
  world --> rules --> core --> audit --> store
  routes -- "decide / approve" --> core
  routes -- "board, log, chain check" --> store
  person -- "approve or reject" --> routes

  classDef comp fill:#85bbf0,stroke:#5d9bd5,color:#0b2545
  classDef boundary fill:#fff4d6,stroke:#c98a00,color:#5c3d00,stroke-width:2px
  classDef external fill:#8a8a8a,stroke:#6b6b6b,color:#fff
  classDef person fill:#08427b,stroke:#073b6f,color:#fff
  class ingest,extract,verify,cache,world,rules,core,audit,store,routes comp
  class facts boundary
  class doc,llm external
  class person person
  style reading fill:#ffffff00,stroke:#8a8a8a,stroke-dasharray:6 4
  style deciding fill:#ffffff00,stroke:#1168bd,stroke-width:2px
```

**What the levels show**
- **Context:** Alinka sits between suppliers and the company's payment platform. It proposes payments to accounts already on file and moves no money.
- **Containers:** one origin, `alinka.alinedlabs.co`; the Worker joins the app and the API. Reading runs as batch jobs whose recordings everything else replays, so the API and the tests need no model keys.
- **Components:** the model sits on the untrusted side and has no tools. Verification can only raise the risk. Sixteen pure rules and one decision core decide, and the log explains every decision in Spanish.
