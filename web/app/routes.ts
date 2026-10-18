import { type RouteConfig, index, route } from "@react-router/dev/routes";

export default [
  index("routes/tablero.tsx"),
  route("facturas/:invoiceId", "routes/factura.tsx"),
  route("reglas", "routes/reglas.tsx"),
  route("registro", "routes/registro.tsx"),
  route("evaluacion", "routes/evaluacion.tsx"),
  route("como-funciona", "routes/como-funciona.tsx"),
] satisfies RouteConfig;
