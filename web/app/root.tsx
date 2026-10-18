import { QueryClientProvider } from "@tanstack/react-query";
import { Info } from "lucide-react";
import { isRouteErrorResponse, Links, Meta, NavLink, Outlet, Scripts, ScrollRestoration } from "react-router";

import type { Route } from "./+types/root";
import { FIXTURES } from "./api/client";
import { queryClient } from "./api/query";
import { AlinkaLogo } from "./components/brand/AlinkaLogo";
import { Segmented } from "./components/segmented";
import { useMotionOK } from "./lib/motion";
import { seo } from "./lib/seo";
import { useView } from "./lib/view";
import "./app.css";
import "./styles/motion.css";

export const links: Route.LinksFunction = () => [
  { rel: "icon", href: "/favicon.svg", type: "image/svg+xml" },
  { rel: "preconnect", href: "https://fonts.googleapis.com" },
  { rel: "preconnect", href: "https://fonts.gstatic.com", crossOrigin: "anonymous" },
  {
    rel: "stylesheet",
    href: "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Manrope:wght@400;500;600;700&display=swap",
  },
];

// The defaults, also in __spa-fallback.html. Every route returns its own full set from seo();
// here the canonical URL and og:url are left out, since the fallback serves many paths.
export const meta: Route.MetaFunction = () =>
  seo({ path: "/" }).filter((d) => !("rel" in d && d.rel === "canonical") && !("property" in d && d.property === "og:url"));

export function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="theme-color" media="(prefers-color-scheme: light)" content="#F7F7F4" />
        <meta name="theme-color" media="(prefers-color-scheme: dark)" content="#131B2B" />
        <Meta />
        <Links />
      </head>
      <body className="min-h-screen">
        {children}
        <ScrollRestoration />
        <Scripts />
      </body>
    </html>
  );
}

const NAV = [
  { to: "/", label: "Tablero" },
  { to: "/reglas", label: "Reglas" },
  { to: "/registro", label: "Registro" },
  { to: "/evaluacion", label: "Evaluación" },
  { to: "/como-funciona", label: "Cómo funciona" },
];

function Shell({ children }: { children: React.ReactNode }) {
  const [view, setView] = useView();
  const motion = useMotionOK();
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#contenido" className="ak-sr focus:not-sr-only focus:absolute focus:z-10 focus:bg-surface focus:p-2">
        Saltar al contenido
      </a>
      <header className="ak-header">
        <NavLink to="/" className="ak-header__brand" aria-label="Alinka, ir al tablero" viewTransition={motion}>
          <AlinkaLogo />
        </NavLink>
        <nav aria-label="Principal" className="ak-nav">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={{ pathname: item.to, search: view === "canonical" ? "?vista=canonica" : "" }}
              end
              viewTransition={motion}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <Segmented
          label="Ejecución"
          value={view}
          onChange={setView}
          options={[
            { value: "canonical", label: "Ejecución canónica" },
            { value: "sandbox", label: "Mi sandbox" },
          ]}
        />
      </header>
      <main id="contenido" className="mx-auto w-full max-w-6xl flex-1 space-y-4 px-6 py-6">
        <p className="ak-banner ak-banner--demo">
          <Info aria-hidden className="ak-icon" />
          <span>
            Datos 100% ficticios.{" "}
            {view === "canonical"
              ? "Estás viendo la ejecución canónica: es de solo lectura y la misma para todos."
              : "Estás en tu sandbox: tus cambios no tocan la ejecución canónica."}
            {FIXTURES && " Modo de muestras: respuestas de ejemplo, sin API."}
          </span>
        </p>
        {children}
      </main>
      <footer className="px-6 pb-6">
        <p className="ak-footer mx-auto max-w-6xl">
          Alinka · La IA lee, las reglas deciden, el registro explica. Ceiba Demo Labs, Inc. (empresa ficticia).
        </p>
      </footer>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Shell>
        <Outlet />
      </Shell>
    </QueryClientProvider>
  );
}

export function HydrateFallback() {
  return (
    <div className="ak-skel mx-auto max-w-6xl p-6" aria-label="Cargando Alinka">
      <span />
      <span />
      <span />
    </div>
  );
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
    <main className="mx-auto max-w-6xl space-y-3 p-6">
      <h1 className="ak-h1">{title}</h1>
      <p className="ak-banner ak-banner--error" role="alert">
        {detail}
      </p>
    </main>
  );
}
