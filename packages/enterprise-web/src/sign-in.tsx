"use client";

import { SignIn, useClerk, useSignIn } from "@clerk/nextjs";
import { isClerkAPIResponseError } from "@clerk/nextjs/errors";
import { useRef, useState, type FormEvent } from "react";

const FIELD_STYLE = { display: "block", inlineSize: "100%", minBlockSize: 44 };
const BUTTON_STYLE = { minBlockSize: 44 };

function destination() {
  const current = new URL(window.location.href);
  const redirect = current.searchParams.get("redirect_url");
  if (redirect) {
    try {
      const target = new URL(redirect, current);
      if (target.origin === current.origin && !target.pathname.startsWith("/sign-in")) return target.href;
    } catch { /* Use the dashboard for malformed redirect URLs. */ }
  }
  return "/dashboard";
}

export function WorkspaceSignIn({ managedFlow = false }: { managedFlow?: boolean }) {
  const clerk = useClerk();
  const { signIn, fetchStatus } = useSignIn();
  const [managed, setManaged] = useState(false);
  const [verifyDevice, setVerifyDevice] = useState(false);
  const [message, setMessage] = useState("");
  const [invalid, setInvalid] = useState(false);
  const submitting = useRef(false);
  const disabled = !clerk.loaded || fetchStatus === "fetching";

  if (managed || managedFlow || clerk.user) return <SignIn />;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (disabled || submitting.current) return;
    submitting.current = true;
    setMessage("");
    setInvalid(false);
    const values = new FormData(event.currentTarget);
    try {
      const result = verifyDevice
        ? await signIn.mfa.verifyEmailCode({ code: String(values.get("code")) })
        : await signIn.password({ emailAddress: String(values.get("email")), password: String(values.get("password")) });
      if (result.error) {
        if (isClerkAPIResponseError(result.error)) {
          if (result.error.status === 429) {
            setMessage("Too many attempts. Wait a moment and try again.");
            return;
          }
          if (result.error.status === 400 || result.error.status === 422) {
            setInvalid(true);
            setMessage(verifyDevice ? "The code could not be verified. Try again." : "Incorrect email or password. Try again.");
            return;
          }
        }
        setMessage("Sign-in is temporarily unavailable. Try again.");
        return;
      }
      if (signIn.status === "complete") {
        const finalized = await signIn.finalize({ navigate: async ({ session, decorateUrl }) => {
          if (session?.currentTask) await clerk.redirectToTasks();
          else window.location.assign(decorateUrl(destination()));
        } });
        if (finalized.error) setMessage("Sign-in could not be completed. Try again.");
        return;
      }
      if (!verifyDevice && signIn.status === "needs_client_trust" && signIn.supportedSecondFactors.some(factor => factor.strategy === "email_code")) {
        const sent = await signIn.mfa.sendEmailCode();
        if (sent.error) setMessage("Could not send a verification code. Try again.");
        else setVerifyDevice(true);
        return;
      }
      // Leave the remaining methods and challenges with Clerk's managed interface.
      setManaged(true);
    } catch {
      setMessage("Sign-in is temporarily unavailable. Try again.");
    } finally {
      submitting.current = false;
    }
  }

  return <section className="card" style={{ inlineSize: "100%", maxInlineSize: "28rem", marginInline: "auto" }}>
    <h1>{verifyDevice ? "Verify your device" : "Sign in"}</h1>
    {verifyDevice && <p>Enter the verification code sent to your email.</p>}
    <form method="post" onSubmit={submit} className="workspace-form">
      {verifyDevice ? <label>Verification code
        <input name="code" type="text" autoComplete="one-time-code" inputMode="numeric" required
          aria-invalid={invalid} aria-describedby={invalid ? "workspace-sign-in-error" : undefined} style={FIELD_STYLE} />
      </label> : <>
        <label>Email address
          <input name="email" type="email" autoComplete="username" autoCapitalize="none" spellCheck={false} required style={FIELD_STYLE} />
        </label>
        <label>Password
          <input name="password" type="password" autoComplete="current-password" required aria-invalid={invalid}
            aria-describedby={invalid ? "workspace-sign-in-error" : undefined} style={FIELD_STYLE} />
        </label>
      </>}
      <p id="workspace-sign-in-error" role="alert" aria-atomic="true">{message}</p>
      <button type="submit" className="btn primary" style={BUTTON_STYLE} disabled={disabled}>{verifyDevice ? "Verify" : "Continue"}</button>
      <button type="button" className="btn" style={BUTTON_STYLE} disabled={disabled} onClick={() => setManaged(true)}>Other sign-in options</button>
    </form>
  </section>;
}
