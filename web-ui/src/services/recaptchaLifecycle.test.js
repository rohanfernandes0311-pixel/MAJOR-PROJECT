import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  discardRecaptchaVerifier,
  ensureRecaptchaVerifier,
  isStaleRecaptchaError,
} from "../authentication/recaptchaLifecycle.js";

test("page-scoped verifier is created once across rerenders, phone changes, and role changes", () => {
  const verifierRef = { current: null };
  const container = { isConnected: true };
  let creations = 0;
  const factory = () => ({ id: ++creations, clear() {} });

  const first = ensureRecaptchaVerifier(verifierRef, container, factory);
  const afterRerender = ensureRecaptchaVerifier(verifierRef, container, factory);
  const afterStateChanges = ensureRecaptchaVerifier(
    verifierRef,
    { isConnected: true },
    factory,
  );

  assert.equal(creations, 1);
  assert.equal(afterRerender, first);
  assert.equal(afterStateChanges, first);
});

test("unmount cleanup clears the verifier and a remount creates a fresh one", () => {
  const verifierRef = { current: null };
  const container = { isConnected: true };
  let creations = 0;
  let clears = 0;
  const factory = () => ({ id: ++creations, clear: () => { clears += 1; } });

  const first = ensureRecaptchaVerifier(verifierRef, container, factory);
  discardRecaptchaVerifier(verifierRef);
  const second = ensureRecaptchaVerifier(verifierRef, container, factory);

  assert.equal(clears, 1);
  assert.equal(verifierRef.current, second);
  assert.notEqual(second, first);
});

test("removed-client errors are recoverable without an automatic retry", () => {
  const verifierRef = { current: { clear() {} } };
  const stale = new Error("reCAPTCHA client element has been removed: 0");

  assert.equal(isStaleRecaptchaError(stale), true);
  discardRecaptchaVerifier(verifierRef);
  assert.equal(verifierRef.current, null);

  let creations = 0;
  ensureRecaptchaVerifier(
    verifierRef,
    { isConnected: true },
    () => ({ id: ++creations, clear() {} }),
  );
  assert.equal(creations, 1);
});

test("Login and OTP own stable containers and pass exactly one verifier to Firebase", async () => {
  const [login, otp, authService] = await Promise.all([
    readFile(new URL("../pages/Login.jsx", import.meta.url), "utf8"),
    readFile(new URL("../pages/OTP.jsx", import.meta.url), "utf8"),
    readFile(new URL("./authService.js", import.meta.url), "utf8"),
  ]);

  assert.match(login, /const recaptchaContainerRef = useRef\(null\)/);
  assert.match(login, /ref=\{recaptchaContainerRef\}/);
  assert.match(login, /await startPhoneSignIn\(normalized, verifier\)/);
  assert.match(login, /discardRecaptchaVerifier\(recaptchaVerifierRef\)/);
  assert.ok(login.indexOf("isValidIndianMobileNumber") < login.indexOf("ensureRecaptchaVerifier("));

  assert.match(otp, /const recaptchaContainerRef = useRef\(null\)/);
  assert.match(otp, /await startPhoneSignIn\(phoneNumber, verifier\)/);
  assert.match(authService, /signInWithPhoneNumber\(auth, phoneNumber, verifier\)/);
  assert.match(authService, /Verification security check expired\. Please try again\./);
});
