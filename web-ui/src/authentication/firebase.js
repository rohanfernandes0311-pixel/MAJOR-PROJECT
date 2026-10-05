import { initializeApp } from "firebase/app";
import { getAuth, RecaptchaVerifier } from "firebase/auth";

const firebaseConfig = {
  apiKey: String(import.meta.env.VITE_FIREBASE_API_KEY || "").trim(),
  authDomain: String(import.meta.env.VITE_FIREBASE_AUTH_DOMAIN || "").trim(),
  projectId: String(import.meta.env.VITE_FIREBASE_PROJECT_ID || "").trim(),
  storageBucket: String(import.meta.env.VITE_FIREBASE_STORAGE_BUCKET || "").trim(),
  messagingSenderId: String(import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID || "").trim(),
  appId: String(import.meta.env.VITE_FIREBASE_APP_ID || "").trim(),
};

let appInstance = null;
let authInstance = null;

function validateFirebaseConfig() {
  const required = ["apiKey", "authDomain", "projectId", "appId"];
  const missing = required.filter((key) => !firebaseConfig[key]);
  if (missing.length) {
    console.error("[firebase] Missing Firebase configuration keys", missing);
    throw new Error(`Missing Firebase configuration: ${missing.join(", ")}`);
  }
}

function getFirebaseAuth() {
  if (authInstance) return authInstance;
  validateFirebaseConfig();
  if (!appInstance) {
    console.debug("[firebase] Initializing Firebase app");
    appInstance = initializeApp(firebaseConfig);
  }
  authInstance = getAuth(appInstance);
  console.debug("[firebase] Firebase auth initialized");
  return authInstance;
}

function createRecaptcha(container) {
  if (typeof window === "undefined") return null;
  if (!container?.isConnected) {
    throw new Error("reCAPTCHA container is not mounted");
  }
  const auth = getFirebaseAuth();
  console.debug("[firebase] Creating page-scoped reCAPTCHA verifier");
  return new RecaptchaVerifier(container, { size: "invisible" }, auth);
}

export { createRecaptcha, getFirebaseAuth };
