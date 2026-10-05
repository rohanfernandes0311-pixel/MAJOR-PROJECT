import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readSource = (relativePath) =>
  readFile(new URL(relativePath, import.meta.url), "utf8");

test("OTP UI preserves six-digit entry, paste, resend cooldown, and edit-phone reset", async () => {
  const [input, otpPage] = await Promise.all([
    readSource("../components/OTPInput.jsx"),
    readSource("../pages/OTP.jsx"),
  ]);

  assert.match(input, /Array\.from\(\{ length: 6 \}/);
  assert.match(input, /onPaste=\{handlePaste\}/);
  assert.match(input, /slice\(0, 6\)/);
  assert.match(input, /autoComplete="one-time-code"/);
  assert.match(otpPage, /setCooldown\(30\)/);
  assert.match(otpPage, /disabled=\{cooldown > 0 \|\| resending\}/);
  assert.match(otpPage, /await startPhoneSignIn\(phoneNumber, verifier\)/);
  assert.match(otpPage, /resetPhoneSignIn\(\)/);
  assert.match(otpPage, /editPhoneNumber: phoneToEdit/);
});
