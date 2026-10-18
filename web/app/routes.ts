import { type RouteConfig, index, route } from "@react-router/dev/routes";

export default [
  index("routes/tablero.tsx"),
  route("facturas/:invoiceId", "routes/factura.tsx"),
  route("reglas", "routes/reglas.tsx"),
] satisfies RouteConfig;
