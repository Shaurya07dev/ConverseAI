"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { authClient } from "@/lib/auth/client";

const inputClass =
  "w-full bg-white/[0.03] border border-white/10 rounded-lg px-4 py-3 focus:outline-none focus:border-saffron transition-colors";

// Sign-in / sign-up with a mandatory email-code check, so each free account
// is tied to an inbox the person controls.
export default function AuthForm({ mode }) {
  const router = useRouter();
  const next = useSearchParams().get("next") || "/analysis";
  const [step, setStep] = useState("form"); // "form" | "verify"
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  const run = async (fn) => {
    setPending(true);
    setError("");
    try {
      await fn();
    } catch (err) {
      setError(err?.message || "Something went wrong. Please try again.");
    } finally {
      setPending(false);
    }
  };

  const sendCode = async () => {
    const { error } = await authClient.emailOtp.sendVerificationOtp({ email, type: "email-verification" });
    if (error) throw error;
    setMessage(`We sent a 6-digit code to ${email}.`);
  };

  const signIn = async () => {
    const { error } = await authClient.signIn.email({ email, password });
    if (error?.status === 403) {
      // Account exists but the email isn't verified yet
      setStep("verify");
      await sendCode();
      return;
    }
    if (error) throw error;
    router.push(next);
    router.refresh();
  };

  const onSubmit = (e) => {
    e.preventDefault();
    run(async () => {
      if (mode === "sign-in") return signIn();
      const { data, error } = await authClient.signUp.email({ name: name || email.split("@")[0], email, password });
      if (error) throw error;
      if (data?.user?.emailVerified) return signIn();
      setStep("verify");
      await sendCode();
    });
  };

  const onVerify = (e) => {
    e.preventDefault();
    run(async () => {
      const { error } = await authClient.emailOtp.verifyEmail({ email, otp: code.trim() });
      if (error) throw error;
      await signIn();
    });
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-6 py-24">
      <div className="w-full max-w-md space-y-8">
        <div className="text-center space-y-2">
          <Link href="/" className="text-saffron font-mono text-xs uppercase tracking-[0.3em]">VaakSetu</Link>
          <h1 className="text-4xl font-display">
            {step === "verify" ? "Check your email" : mode === "sign-in" ? "Welcome back" : "Create your account"}
          </h1>
          {message && <p className="text-sm text-muted">{message}</p>}
        </div>

        {step === "form" ? (
          <form onSubmit={onSubmit} className="space-y-4">
            {mode === "sign-up" && (
              <input className={inputClass} placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
            )}
            <input className={inputClass} type="email" required autoComplete="email" placeholder="Email"
              value={email} onChange={(e) => setEmail(e.target.value)} />
            <input className={inputClass} type="password" required minLength={8}
              autoComplete={mode === "sign-in" ? "current-password" : "new-password"}
              placeholder="Password (min 8 characters)" value={password} onChange={(e) => setPassword(e.target.value)} />
            {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
            <button type="submit" disabled={pending} className="btn-primary w-full justify-center py-3 disabled:opacity-60">
              {pending && <Loader2 size={16} className="animate-spin" />}
              {mode === "sign-in" ? "Sign in" : "Create account"}
            </button>
            <p className="text-center text-sm text-muted">
              {mode === "sign-in" ? (
                <>New here? <Link href={`/auth/sign-up?next=${encodeURIComponent(next)}`} className="text-saffron hover:underline">Create an account</Link></>
              ) : (
                <>Already have an account? <Link href={`/auth/sign-in?next=${encodeURIComponent(next)}`} className="text-saffron hover:underline">Sign in</Link></>
              )}
            </p>
          </form>
        ) : (
          <form onSubmit={onVerify} className="space-y-4">
            <input className={`${inputClass} text-center text-2xl tracking-[0.5em] font-mono`} inputMode="numeric"
              autoComplete="one-time-code" required maxLength={6} placeholder="------" aria-label="Verification code"
              value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
            {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
            <button type="submit" disabled={pending || code.length < 6} className="btn-primary w-full justify-center py-3 disabled:opacity-60">
              {pending && <Loader2 size={16} className="animate-spin" />}
              Verify email
            </button>
            <button type="button" disabled={pending} onClick={() => run(sendCode)}
              className="w-full text-sm text-muted hover:text-saffron transition-colors">
              Didn&apos;t get it? Send a new code
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
