# Architecture (C4)

Alinka in four diagrams: the system in its context, the containers inside it, the components of the decision pipeline, and the deployment. The line that matters is the **trust boundary**: only typed `InvoiceFacts` cross from the reading side into the rules, and only the decision core can return PAY.

Legend: dark blue = person, blue = Alinka, light blue = component, grey = external. Solid arrows are calls or data flow; the trust boundary is the dashed box.

## Level 1 · System context

```mermaid
flowchart TB
  supplier["<b>Supplier or contractor</b><br/><i>[Person, external]</i><br/>Sends facturas, cuentas de cobro and invoices by email, PDF, image or chat"]
  operator["<b>AP operator</b><br/><i>[Person]</i><br/>Reviews the board, runs the agent, tunes the rules, tries a document in Probar"]
  approver["<b>Approver</b><br/><i>[Person]</i><br/>Approves or rejects escalations by name"]
  alinka["<b>Alinka</b><br/><i>[Software system]</i><br/>Reads invoices, pays only what the company's rules allow, holds or escalates the rest, and logs why"]
  blinka["<b>Blinka</b><br/><i>[Software system, external]</i><br/>Accounts, balance, beneficiaries on file and payouts. Simulated in the demo: no integration, no money moves"]
  anthropic["<b>Anthropic API</b><br/><i>[External system]</i><br/>Claude Sonnet 5.5 reads; Claude Haiku 5.5 reads again"]
  openrouter["<b>OpenRouter</b><br/><i>[External system]</i><br/>TypeSafe's JEV 1.13 answers escalate-only verification questions"]

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
    edge["<b>Edge</b><br/><i>[Container: Cloudflare Worker]</i><br/>alinka.alinedlabs.co: serves the prerendered pages and the app, forwards /api/* with X-Edge-Secret and X-Client-IP, passes the event stream through unbuffered"]
    web["<b>Web app</b><br/><i>[Container: React Router 7, prerendered public routes, TanStack Query and Table, Tailwind CSS 4, Base UI]</i><br/>Tablero, Probar, Detalle, Reglas, Registro, Evaluación, Cómo funciona"]
    api["<b>API</b><br/><i>[Container: FastAPI, Python 3.12]</i><br/>Read-only canonical run and a 24-hour sandbox per visitor; board, Ejecutar agente, rules, approvals, log, trace; Probar jobs and their event stream; admin settings"]
    reader["<b>Reader jobs</b><br/><i>[Container: Python, alinka.jobs.extract]</i><br/>Sanitize, read, verify; writes InvoiceFacts runs"]
    evals["<b>Evaluation</b><br/><i>[Container: Python CLI, make eval]</i><br/>k of K with the 95% bound, autonomy, risk–coverage, cost and latency"]
    db[("<b>Database</b><br/><i>[Container: PostgreSQL 17 on Neon]</i><br/>Sessions, rule versions, hash-chained decisions, ledger, Probar invoices and uploads, settings with the live_uploads switch")]
    repo[("<b>Repository data</b><br/><i>[Container: files in git]</i><br/>175 fictional documents and labels, recorded runs, cached model responses, eval report")]
  end

  anthropic["<b>Anthropic API</b><br/><i>[External]</i>"]
  openrouter["<b>OpenRouter · JEV</b><br/><i>[External]</i>"]

  user -- "HTTPS" --> edge
  edge -- "Delivers" --> web
  web -- "JSON and server-sent events over /api/*" --> edge
  edge -- "HTTPS + edge secret" --> api
  api -- "SQL, one transaction per decision" --> db
  api -- "Loads runs and recorded readings, renders pages, report" --> repo
  api -- "Uploads only, while switched on: live reading" --> anthropic
  api -- "Uploads only: live JEV questions" --> openrouter
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
  doc["<b>Untrusted document</b><br/>dataset, Probar sample or upload"]

  subgraph reading["Reading side (untrusted input)"]
    ingest["<b>Sanitizer</b><br/><i>[alinka.ingest]</i><br/>PyMuPDF text trace, covered-text render test, Tesseract boxes, Unicode tag and bidi characters, HTML vs plain text"]
    extract["<b>Reader</b><br/><i>[alinka.extract]</i><br/>Claude Sonnet 5.5, structured output, no tools: every field with a quote, plus instructions_seen"]
    verify["<b>Verifier</b><br/><i>[alinka.verify]</i><br/>Normalize amounts and dates, parse words, grounding boxes, regex re-read, totals, Haiku second reading, JEV → risk"]
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

  trace["<b>Trace</b><br/><i>[alinka.trace]</i><br/>seven TraceSteps from a record: Recepción to Registro"]
  routes["<b>HTTP routes</b><br/><i>[alinka.api]</i><br/>sandboxes by cookie, edge-secret check, Ejecutar agente, approve by name, GET /api/invoices/{id}/trace"]
  probar["<b>Probar jobs</b><br/><i>[alinka.api.try_routes]</i><br/>samples replay recorded readings; uploads read live behind live_uploads; limits; step events over SSE"]
  person["<b>Operator or approver</b><br/><i>[Person]</i>"]
  llm["<b>Anthropic · OpenRouter</b><br/><i>[External]</i>"]

  doc --> ingest --> extract --> verify --> facts
  extract <--> cache
  verify <--> cache
  cache <--> llm
  facts --> rules
  world --> rules --> core --> audit --> store
  routes -- "decide / approve" --> core
  routes -- "board, log, chain check" --> store
  routes -- "trace of a stored record" --> trace
  probar -- "runs one document step by step" --> ingest
  probar -- "step events" --> trace
  person -- "approve, reject, try a document" --> routes

  classDef comp fill:#85bbf0,stroke:#5d9bd5,color:#0b2545
  classDef boundary fill:#fff4d6,stroke:#c98a00,color:#5c3d00,stroke-width:2px
  classDef external fill:#8a8a8a,stroke:#6b6b6b,color:#fff
  classDef person fill:#08427b,stroke:#073b6f,color:#fff
  class ingest,extract,verify,cache,world,rules,core,audit,store,routes,probar,trace comp
  class facts boundary
  class doc,llm external
  class person person
  style reading fill:#ffffff00,stroke:#8a8a8a,stroke-dasharray:6 4
  style deciding fill:#ffffff00,stroke:#1168bd,stroke-width:2px
```

## Level 4 · Deployment

```mermaid
flowchart LR
  dev["<b>Developers</b><br/><i>[Person]</i><br/>one branch per task"]

  subgraph github["GitHub"]
    direction TB
    repo["<b>Repository</b><br/><i>[git]</i><br/>main is merged through pull requests"]
    ci["<b>Actions CI</b><br/><i>[ci.yml]</i><br/>make check-py on Postgres 17, make check-web; replay mode, no keys"]
    ghcr[("<b>GHCR</b><br/><i>[Container registry]</i><br/>alinka-api image, tagged by commit")]
  end

  subgraph cloudflare["Cloudflare"]
    direction TB
    dns["<b>DNS</b><br/>alinka.alinedlabs.co"]
    worker["<b>Worker alinka-edge</b><br/><i>[deploy/edge.sh]</i><br/>static assets from web/build/client, /api/* proxy, health ping every 4 minutes"]
  end

  subgraph azure["Azure · East US 2"]
    aca["<b>Container Apps: alinka-api</b><br/><i>[deploy/azure.sh]</i><br/>1 to 2 replicas, one always warm; secrets as secret references"]
  end

  neon[("<b>Neon</b><br/><i>[PostgreSQL 17]</i><br/>migrated and loaded by deploy/neon.py")]
  anthropic["<b>Anthropic API</b><br/><i>[External]</i>"]
  openrouter["<b>OpenRouter</b><br/><i>[External]</i>"]
  visitor["<b>Visitor</b><br/><i>[Person]</i>"]

  dev -- "git push" --> repo
  repo -- "on push and pull request" --> ci
  repo -- "deploy/image.sh builds docker/Dockerfile.api" --> ghcr
  ghcr -- "image pull" --> aca
  visitor -- "HTTPS" --> dns --> worker
  worker -- "HTTPS + X-Edge-Secret" --> aca
  aca -- "pooled connection" --> neon
  aca -- "uploads only" --> anthropic
  aca -- "uploads only" --> openrouter

  classDef person fill:#08427b,stroke:#073b6f,color:#fff
  classDef container fill:#438dd5,stroke:#2e6295,color:#fff
  classDef external fill:#8a8a8a,stroke:#6b6b6b,color:#fff
  class dev,visitor person
  class repo,ci,ghcr,dns,worker,aca container
  class neon,anthropic,openrouter external
```

**What the diagrams show**
- **Context:** Alinka sits between suppliers and the company's payment platform. It proposes payments to accounts already on file and moves no money.
- **Containers:** one origin, `alinka.alinedlabs.co`; the Worker joins the prerendered app and the API and lets Probar's event stream through unbuffered. Reading runs as batch jobs whose recordings everything else replays, so the API and the tests need no model keys; only Probar uploads, behind the `live_uploads` switch, call the models from the API.
- **Components:** the model sits on the untrusted side and has no tools. Verification can only raise the risk. Sixteen pure rules and one decision core decide, the log explains every decision in Spanish, and `alinka.trace` rebuilds the seven steps of any decision for Probar and "Cómo se decidió".
- **Deployment:** CI checks every push in replay mode. `deploy/image.sh` pushes the API image to GHCR, `deploy/azure.sh` rolls it out to Azure Container Apps with secrets held as secret references, `deploy/neon.py` migrates Neon and loads the canonical run, and `deploy/edge.sh` publishes the Worker on Cloudflare.
