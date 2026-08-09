const ACCESS_KEY = "landsense_access";
const REFRESH_KEY = "landsense_refresh";

export function saveTokens({ access_token, refresh_token, expires_in }) {
  localStorage.setItem(ACCESS_KEY, access_token || "");
  localStorage.setItem(REFRESH_KEY, refresh_token || "");
}

export function getTokens() {
  const access_token = localStorage.getItem(ACCESS_KEY) || null;
  const refresh_token = localStorage.getItem(REFRESH_KEY) || null;
  if (!access_token) return null;
  return { access_token, refresh_token };
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}
