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
let recaptchaVerifierInstance = null;
let recaptchaContainerId = "";

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

function createRecaptcha(containerId = "recaptcha-container") {
  if (typeof window === "undefined") return null;
  if (recaptchaVerifierInstance && recaptchaContainerId === containerId) {
    console.debug("[firebase] Reusing existing reCAPTCHA verifier");
    return recaptchaVerifierInstance;
  }
  const container = document.getElementById(containerId);
  if (!container) {
    throw new Error(`reCAPTCHA container "${containerId}" was not found`);
  }
  const auth = getFirebaseAuth();
  if (recaptchaVerifierInstance && recaptchaContainerId !== containerId) {
    recaptchaVerifierInstance.clear();
  }
  // Returns an invisible recaptcha instance attached to the DOM container id
  recaptchaVerifierInstance = new RecaptchaVerifier(containerId, { size: "invisible" }, auth);
  recaptchaContainerId = containerId;
  console.debug("[firebase] reCAPTCHA verifier created", { containerId });
  return recaptchaVerifierInstance;
}

export { createRecaptcha, getFirebaseAuth };
