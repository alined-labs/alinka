import { QueryClient } from "@tanstack/react-query";

/** One client for the app, so route clientLoaders can warm the same cache the screens read. */
export const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 5_000, retry: 1 } } });
