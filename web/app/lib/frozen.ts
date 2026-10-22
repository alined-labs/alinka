/*
 * Production builds are served by the edge Worker (edge/src), which answers /api from responses
 * recorded from the API, so production builds say so in the demo banner; dev servers and tests,
 * which talk to a local API or to fixtures, do not.
 */

/** True in production builds, the only ones the frozen Worker serves. */
export const FROZEN: boolean = import.meta.env.PROD;
