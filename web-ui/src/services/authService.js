import { getFirebaseAuth } from "../authentication/firebase";
import { STALE_RECAPTCHA_CODE, isStaleRecaptchaError } from "../authentication/recaptchaLifecycle";
import { signInWithPhoneNumber } from "firebase/auth";

const FIREBASE_SIGNIN_KEY = "landsense_firebase_signin_active";
let confirmationResultRef = null;
let confirmInFlight = false;

function setPendingFirebaseSignIn(phoneNumber) {
  sessionStorage.setItem(FIREBASE_SIGNIN_KEY, JSON.stringify({ phoneNumber, startedAt: Date.now() }));
}

function clearPendingFirebaseSignIn() {
  sessionStorage.removeItem(FIREBASE_SIGNIN_KEY);
}

function getPendingFirebaseSignIn() {
  try {
    return JSON.parse(sessionStorage.getItem(FIREBASE_SIGNIN_KEY) || "null");
  } catch {
    return null;
  }
}

function parseBackendDetail(text) {
  try {
    const parsed = JSON.parse(text);
    if (typeof parsed?.detail === "string") return parsed.detail;
  } catch {
    return "";
  }
  return "";
}

function toFriendlyAuthError(err, fallbackMessage) {
  const code = String(err?.code || "");
  const message = String(err?.message || "");
  if (code.includes("auth/invalid-verification-code")) return "Invalid verification code.";
  if (code.includes("auth/code-expired")) return "Verification code expired. Please request a new code.";
  if (code.includes("auth/too-many-requests")) return "Too many attempts. Please wait and try again.";
  if (code.includes("auth/missing-phone-number")) return "Phone number is missing. Please enter it again.";
  if (code.includes("auth/invalid-phone-number")) return "Invalid phone number format.";
  if (code.includes("auth/captcha-check-failed")) return "reCAPTCHA verification failed. Please try again.";
  if (code.includes("auth/network-request-failed")) return "Network error. Please check your connection and retry.";
  if (message.startsWith("{") && message.includes('"detail"')) {
    const detail = parseBackendDetail(message);
    if (detail) return detail;
  }
  return message || fallbackMessage;
}

async function startPhoneSignIn(phoneNumber, verifier) {
  try {
    if (!verifier) throw new Error("reCAPTCHA container is not mounted");
    const auth = getFirebaseAuth();
    console.debug("[authService] Firebase auth instance ready");
    console.debug("[authService] Calling signInWithPhoneNumber");
    const result = await signInWithPhoneNumber(auth, phoneNumber, verifier);
    confirmationResultRef = result;
    confirmInFlight = false;
    setPendingFirebaseSignIn(phoneNumber);
    window.__confirmationResult = result;
    console.debug("[authService] signInWithPhoneNumber completed");
    return true;
  } catch (err) {
    console.error("[authService] startPhoneSignIn failed", err);
    const friendly = new Error(
      isStaleRecaptchaError(err)
        ? "Verification security check expired. Please try again."
        : toFriendlyAuthError(err, "Unable to send OTP right now.")
    );
    if (isStaleRecaptchaError(err)) friendly.code = STALE_RECAPTCHA_CODE;
    throw friendly;
  }
}

function resetPhoneSignIn() {
  confirmationResultRef = null;
  confirmInFlight = false;
  if (typeof window !== "undefined") window.__confirmationResult = null;
  clearPendingFirebaseSignIn();
}

async function confirmOtpAndExchange(otp) {
  if (confirmInFlight) {
    throw new Error("Verification is already in progress.");
  }
  const pending = getPendingFirebaseSignIn();
  const confirmation = confirmationResultRef || window.__confirmationResult;
  if (!pending || !confirmation) {
    throw new Error("OTP session expired. Please resend OTP.");
  }
  try {
    confirmInFlight = true;
    const credential = await confirmation.confirm(otp);
    const idToken = await credential.user.getIdToken();
    // Send idToken to backend for exchange
    const resp = await fetch(`/auth/firebase/exchange`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: idToken }),
    });
    if (!resp.ok) {
      const txt = await resp.text();
      const detail = parseBackendDetail(txt);
      if (resp.status >= 500) {
        throw new Error("Unable to complete sign-in right now. Please try again.");
      }
      if (resp.status === 401) {
        throw new Error("Firebase authentication could not be verified. Please sign in again.");
      }
      throw new Error(detail || "Unable to complete sign-in right now. Please try again.");
    }
    const data = await resp.json();
    try {
      const profileResponse = await getProfile(data.access_token);
      if (profileResponse?.profile) {
        data.profile = { ...(data.profile || {}), ...profileResponse.profile };
      }
    } catch {
      // Keep the exchange response even if profile hydration fails.
    }
    confirmationResultRef = null;
    window.__confirmationResult = null;
    clearPendingFirebaseSignIn();
    return data;
  } catch (err) {
    throw new Error(toFriendlyAuthError(err, "Verification failed."));
  } finally {
    confirmInFlight = false;
  }
}

async function refreshTokens(refreshToken) {
  const resp = await fetch(`/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!resp.ok) throw new Error("Refresh failed");
  return resp.json();
}

async function logout(accessToken) {
  const resp = await fetch(`/auth/logout`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  return resp.ok;
}

async function getProfile(accessToken) {
  const resp = await fetch(`/auth/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!resp.ok) throw new Error("Unauthorized");
  return resp.json();
}

function isFirebaseSignInPending() {
  return Boolean(getPendingFirebaseSignIn()) && Boolean(confirmationResultRef || window.__confirmationResult);
}

export { startPhoneSignIn, confirmOtpAndExchange, refreshTokens, logout, getProfile, isFirebaseSignInPending, resetPhoneSignIn };
