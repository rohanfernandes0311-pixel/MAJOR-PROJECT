const STALE_RECAPTCHA_CODE = "landsense/recaptcha-stale";

function ensureRecaptchaVerifier(verifierRef, container, createVerifier) {
  if (verifierRef.current) return verifierRef.current;
  if (!container?.isConnected) {
    throw new Error("Verification security check is not ready. Please try again.");
  }
  verifierRef.current = createVerifier(container);
  return verifierRef.current;
}

function discardRecaptchaVerifier(verifierRef) {
  const verifier = verifierRef.current;
  verifierRef.current = null;
  try {
    verifier?.clear?.();
  } catch {
    // Firebase may already have detached a stale reCAPTCHA client.
  }
}

function isStaleRecaptchaError(error) {
  const code = String(error?.code || "").toLowerCase();
  const message = String(error?.message || "").toLowerCase();
  return (
    code === STALE_RECAPTCHA_CODE ||
    message.includes("recaptcha client element has been removed") ||
    message.includes("recaptcha container is not mounted")
  );
}

export {
  STALE_RECAPTCHA_CODE,
  discardRecaptchaVerifier,
  ensureRecaptchaVerifier,
  isStaleRecaptchaError,
};
