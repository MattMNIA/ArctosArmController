// Small helper to centralize build-time flags coming from Vite env vars.
// Set VITE_PRIVATE_BUILD=true for your private/dev build.
export const isPrivateBuild =
  (import.meta.env.VITE_PRIVATE_BUILD === 'true' || import.meta.env.VITE_PRIVATE_BUILD === '1');

export default {
  isPrivateBuild,
};
