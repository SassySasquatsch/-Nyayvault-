// Runtime data is loaded from the FastAPI backend after authentication.
let NV_CASES = [];
let NV_AUDIT_LOG = [];
let NV_USERS = [];
let NV_RECENT = [];   // IO dashboard: latest activity across the IO's own cases
let NV_OVERVIEW = null;  // GET /api/cases/overview/summary (ABAC-scoped counts) for non-admin roles
