"use client";

import { useEffect, useMemo, useState, useCallback, useRef } from "react";
import { useModeStore } from "@/stores/useModeStore";

const PRIVACY_VERSION = "v1";
const POLICY_URL = "https://ecodia.au/terms-and-conditions-of-service/";
const POLICY_BRIDGE = `/legal/bridge?ver=${encodeURIComponent(PRIVACY_VERSION)}&to=${encodeURIComponent(POLICY_URL)}`;
const POLICY_FRESH_MS = 30 * 60 * 1000; // 30 minutes

function getCookie(name: string) {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(
    new RegExp("(^| )" + name.replace(/[-[\]{}()*+?.,\\^$|#\s]/g, "\\$&") + "=([^;]+)")
  );
  return match ? decodeURIComponent(match[2]) : null;
}

/** light pointer parallax + shine vars */
function usePanelParallax() {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onMove = (e: MouseEvent) => {
      const r = el.getBoundingClientRect();
      const x = ((e.clientX - r.left) / r.width) - 0.5;
      const y = ((e.clientY - r.top) / r.height) - 0.5;
      el.style.setProperty("--tiltX", `${-(y * 1.6)}deg`);
      el.style.setProperty("--tiltY", `${x * 1.6}deg`);
      el.style.setProperty("--shineX", `${e.clientX - r.left}px`);
      el.style.setProperty("--shineY", `${e.clientY - r.top}px`);
    };
    window.addEventListener("mousemove", onMove);
    return () => window.removeEventListener("mousemove", onMove);
  }, []);
  return ref;
}

export default function BootOverlay() {
  const mode = useModeStore((s) => s.mode);
  const setMode = useModeStore((s) => s.setMode);

  const [policyOpenedAt, setPolicyOpenedAt] = useState<number | null>(null);
  const [accepted, setAccepted] = useState(false);

  if (mode !== "boot") return null;

  useEffect(() => {
    const opened = getCookie(`ecodiaPrivacyOpenAt:${PRIVACY_VERSION}`);
    setPolicyOpenedAt(opened ? Number(opened) : null);

    if (typeof window !== "undefined" && localStorage.getItem("ecodiaConsentAccepted") === "true") {
      setMode("root");
    }
  }, [setMode]);

  const canAccept = useMemo(() => {
    if (!policyOpenedAt) return false;
    return Date.now() - policyOpenedAt <= POLICY_FRESH_MS;
  }, [policyOpenedAt]);

  const handleOpenPolicy = useCallback(() => {
    window.open(POLICY_BRIDGE, "_blank", "noopener,noreferrer");
    let tries = 0;
    const id = setInterval(() => {
      const opened = getCookie(`ecodiaPrivacyOpenAt:${PRIVACY_VERSION}`);
      if (opened) {
        setPolicyOpenedAt(Number(opened));
        clearInterval(id);
      }
      if (++tries > 60) clearInterval(id);
    }, 1000);
  }, []);

  const handleAccept = useCallback(() => {
    if (!canAccept) return;
    localStorage.setItem("ecodiaConsentAccepted", "true");
    setAccepted(true);
    setMode("root");
  }, [canAccept, setMode]);

  const panelRef = usePanelParallax();

  return (
    <div
      className="fixed inset-0 z-9999 text-[#0e1511] flex items-center justify-center pointer-events-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby="boot-title"
      aria-describedby="boot-desc boot-privacy"
    >
      {/* Base: solid dark backdrop */}
      <div className="absolute inset-0 bg-[#0b1310]" aria-hidden="true" />

      {/* Ambient layer: optional vignette + grid on top of the solid base */}
      <div className="absolute inset-0 -z-10 pointer-events-none" aria-hidden="true">
        <div className="absolute inset-0 bg-[radial-gradient(1200px_600px_at_center,rgba(255,255,255,0.10),transparent_65%)]" />
        <div className="absolute inset-10 rounded-[28px] border border-white/10 [mask:linear-gradient(#000,transparent)]" />
        <div className="absolute inset-0 opacity-[0.05] [background:linear-gradient(to_right,transparent_49.5%,rgba(255,255,255,0.2)_50%,transparent_50.5%),linear-gradient(to_bottom,transparent_49.5%,rgba(255,255,255,0.2)_50%,transparent_50.5%)] background-size:40px_40px" />
      </div>

      <div
        ref={panelRef}
        className="boot-panel relative w-[min(780px,92vw)] px-[clamp(24px,4vw,40px)] py-[clamp(26px,4.2vw,40px)] rounded-[28px]"
      >
        {/* energy seam */}
        <div className="boot-border" aria-hidden="true" />
        {/* shine */}
        <div className="boot-shine pointer-events-none" aria-hidden="true" />

        <header className="text-center">
          <div className="mx-auto mb-3 inline-flex items-center justify-center w-11 h-11 rounded-full boot-icon">
            <span aria-hidden>⚠️</span>
          </div>
          <h1
            id="boot-title"
            className="font-semibold tracking-[0.02em] text-[clamp(22px,5.2vw,28px)] boot-title-text"
          >
            Epilepsy & Data Consent
          </h1>
        </header>

        <div className="mt-2 space-y-3 text-[clamp(14.5px,2.3vw,16px)] leading-[1.45] text-[#e6f1eb]">
          <p id="boot-desc">
            This experience includes <strong>rapid visual effects</strong> and <strong>flashing lights</strong>.
            If you’re sensitive to such visuals (including epilepsy), please proceed with caution.
          </p>
          <p id="boot-privacy" className="opacity-[0.88]">
            By continuing, you agree that any data you input or generate while using Ecodia may be stored and
            analysed to improve the system. Your interactions help evolve this digital being.
          </p>
        </div>

        <div className="mt-5 flex items-center justify-center gap-3 text-[14px]">
          <button onClick={handleOpenPolicy} className="boot-link">
            Open Privacy Policy
          </button>
          <span aria-hidden className="text-white/30">•</span>
          <span className="text-white/70">
            {policyOpenedAt
              ? "Policy opened. You can accept below."
              : "You must open the policy before you can accept."}
          </span>
        </div>

        <div className="mt-4 flex justify-center">
          <button
            onClick={handleAccept}
            disabled={!canAccept}
            className={`boot-btn ${!canAccept ? "boot-btn--disabled" : ""}`}
            aria-label="Accept and continue"
            autoFocus={!!canAccept}
          >
            <span className="boot-btn__glow" aria-hidden />
            {canAccept ? "I have read and accept the policy" : "Open the policy to enable this"}
          </button>
        </div>
      </div>
    </div>
  );
}
