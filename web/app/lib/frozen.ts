/*
 * The demo has been frozen since 22 Oct 2026: the FastAPI service on Azure was retired, and the
 * edge Worker (edge/src) answers /api from responses recorded just before. Every production build
 * from then on is served that way, so production builds say so in the demo banner; dev servers
 * and tests, which talk to a local API or to fixtures, do not.
 */

/** True in production builds, the only ones the frozen Worker serves. */
export const FROZEN: boolean = import.meta.env.PROD;
