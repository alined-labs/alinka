import { type RouteConfig, index, route } from "@react-router/dev/routes";

/*
 * "/" and "/en" are the showcase page (Spanish and English); the app screens follow. The board
 * was the index route until 22 Oct 2026 and now lives at /tablero (see lib/view.ts BOARD_PATH).
 */
export default [
  index("routes/inicio.tsx"),
  route("en", "routes/en.tsx"),
  route("tablero", "routes/tablero.tsx"),
  route("facturas/:invoiceId", "routes/factura.tsx"),
  route("probar", "routes/probar.tsx"),
  route("reglas", "routes/reglas.tsx"),
  route("registro", "routes/registro.tsx"),
  route("evaluacion", "routes/evaluacion.tsx"),
  route("como-funciona", "routes/como-funciona.tsx"),
] satisfies RouteConfig;
