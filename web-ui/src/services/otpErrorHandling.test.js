import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const authServiceUrl = new URL("./authService.js", import.meta.url);

test("OTP exchange maps Firebase and server failures to safe distinct messages", async () => {
  const source = await readFile(authServiceUrl, "utf8");

  assert.match(source, /Invalid verification code\./);
  assert.match(source, /Verification code expired\. Please request a new code\./);
  assert.match(source, /resp\.status >= 500/);
  assert.match(source, /Unable to complete sign-in right now\. Please try again\./);
  assert.doesNotMatch(source, /parseBackendDetail\(txt\) \|\| txt/);
});
