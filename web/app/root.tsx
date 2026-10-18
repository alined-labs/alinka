import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { isRouteErrorResponse, Links, Meta, NavLink, Outlet, Scripts, ScrollRestoration } from "react-router";

import type { Route } from "./+types/root";
import { FIXTURES } from "./api/client";
import "./app.css";

export function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Alinka · Cuentas por pagar</title>
        {/* No favicon until the brand mark lands; this stops the browser's /favicon.ico 404. */}
        <link rel="icon" href="data:," />
        <Meta />
        <Links />
      </head>
      <body className="min-h-screen bg-bg text-text antialiased">
        {children}
        <ScrollRestoration />
        <Scripts />
      </body>
    </html>
  );
}

const NAV = [{ to: "/", label: "Tablero" }];

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen">
      <a href="#contenido" className="sr-only focus:not-sr-only focus:absolute focus:p-2">
        Saltar al contenido
      </a>
      <nav aria-label="Principal" className="w-sidebar shrink-0 border-r border-border bg-surface p-4">
        <p className="mb-6 text-xl font-semibold">Alinka</p>
        <ul className="space-y-1">
          {NAV.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end
                className={({ isActive }) =>
                  `block rounded-md px-3 py-2 text-sm ${isActive ? "bg-primary text-primary-text" : "hover:bg-surface-muted"}`
                }
              >
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
        {FIXTURES && <p className="mt-6 text-xs text-muted">Modo de muestras: datos de ejemplo, sin API.</p>}
      </nav>
      <main id="contenido" className="min-w-0 flex-1 p-6">
        {children}
      </main>
    </div>
  );
}

export default function App() {
  const [client] = useState(
    () => new QueryClient({ defaultOptions: { queries: { staleTime: 5_000, retry: 1 } } }),
  );
  return (
    <QueryClientProvider client={client}>
      <Shell>
        <Outlet />
      </Shell>
    </QueryClientProvider>
  );
}

export function HydrateFallback() {
  return <p className="p-6 text-muted">Cargando Alinka…</p>;
}

export function ErrorBoundary({ error }: Route.ErrorBoundaryProps) {
  let title = "Algo salió mal";
  let detail = "Ocurrió un error inesperado.";
  if (isRouteErrorResponse(error)) {
    title = error.status === 404 ? "Página no encontrada" : `Error ${error.status}`;
    detail = error.statusText || detail;
  } else if (error instanceof Error) {
    detail = error.message;
  }
  return (
    <main className="p-6">
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="mt-2 text-muted">{detail}</p>
    </main>
  );
}
