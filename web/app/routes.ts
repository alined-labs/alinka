import { type RouteConfig, index, route } from "@react-router/dev/routes";

export default [index("routes/tablero.tsx"), route("facturas/:invoiceId", "routes/factura.tsx")] satisfies RouteConfig;
