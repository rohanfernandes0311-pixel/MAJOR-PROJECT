import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { confirmOtpAndExchange } from "../services/authService";
import * as tokenStorage from "../utils/tokenStorage";

function OTPInput({ length = 6, onChange }) {
  const refs = useRef([]);
  const [values, setValues] = useState(Array(length).fill(""));

  useEffect(() => {
    refs.current[0]?.focus();
  }, []);

  function handleChange(i, v) {
    if (!/^[0-9]?$/.test(v)) return;
    const next = [...values];
    next[i] = v;
    setValues(next);
    onChange(next.join(""));
    if (v && i < length - 1) refs.current[i + 1]?.focus();
  }

  function handleKeyDown(e, i) {
    if (e.key === "Backspace" && !values[i] && i > 0) {
      refs.current[i - 1]?.focus();
    }
  }

  return (
    <div className="flex gap-2">
      {Array.from({ length }).map((_, i) => (
        <input
          key={i}
          ref={(el) => (refs.current[i] = el)}
          value={values[i]}
          onChange={(e) => handleChange(i, e.target.value)}
          onKeyDown={(e) => handleKeyDown(e, i)}
          className="w-12 h-12 text-center border rounded"
          inputMode="numeric"
          maxLength={1}
        />
      ))}
    </div>
  );
}

export default function OTPVerification() {
  const [otp, setOtp] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  async function handleConfirm(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const data = await confirmOtpAndExchange(otp);
      tokenStorage.saveTokens({ access_token: data.access_token, refresh_token: data.refresh_token });
      // gently wait then redirect
      navigate("/");
    } catch (err) {
      setError(err.message || "Invalid code");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="max-w-md w-full p-8 bg-white dark:bg-slate-900 rounded-lg shadow">
        <h2 className="text-2xl font-semibold mb-4">Enter verification code</h2>
        <form onSubmit={handleConfirm}>
          <OTPInput length={6} onChange={setOtp} />
          <button type="submit" className="mt-6 w-full bg-sky-600 text-white py-2 rounded">{loading ? "Verifying..." : "Verify"}</button>
          {error && <p className="mt-2 text-red-600">{error}</p>}
        </form>
      </div>
    </div>
  );
}
