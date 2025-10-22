// apps/ecodia-ui/src/components/system/BootOverlay.tsx
"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import { useModeStore } from "@/stores/useModeStore";

const PRIVACY_VERSION = "v1";
const POLICY_URL = "https://ecodia.au/terms-and-conditions-of-service/";
const POLICY_BRIDGE = `/legal/bridge?ver=${encodeURIComponent(PRIVACY_VERSION)}&to=${encodeURIComponent(POLICY_URL)}`;
// How recently the policy must have been opened to enable Accept
const POLICY_FRESH_MS = 30 * 60 * 1000; // 30 minutes

function getCookie(name: string) {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp("(^| )" + name.replace(/[-[\]{}()*+?.,\\^$|#\s]/g, "\\$&") + "=([^;]+)"));
  return match ? decodeURIComponent(match[2]) : null;
}

export default function BootOverlay() {
  const mode = useModeStore(s => s.mode);
  const setMode = useModeStore(s => s.setMode);

  const [policyOpenedAt, setPolicyOpenedAt] = useState<number | null>(null);
  const [accepted, setAccepted] = useState(false);

  // Only render when we're in boot mode
  if (mode !== "boot") return null;

  // Read cookie + prior acceptance on mount
  useEffect(() => {
    const opened = getCookie(`ecodiaPrivacyOpenAt:${PRIVACY_VERSION}`);
    setPolicyOpenedAt(opened ? Number(opened) : null);

    if (typeof window !== "undefined" && localStorage.getItem("ecodiaConsentAccepted") === "true") {
      // Already accepted on this device/browser → bypass boot
      setMode("root");
    }
  }, [setMode]);

  // Is the policy considered "freshly opened"?
  const canAccept = useMemo(() => {
    if (!policyOpenedAt) return false;
    return Date.now() - policyOpenedAt <= POLICY_FRESH_MS;
  }, [policyOpenedAt]);

  const handleOpenPolicy = useCallback(() => {
    // Open bridge in a new tab; bridge will stamp cookie then redirect to the external policy
    window.open(POLICY_BRIDGE, "_blank", "noopener,noreferrer");
    // Poll cookie briefly in case they come back quickly
    let tries = 0;
    const id = setInterval(() => {
      const opened = getCookie(`ecodiaPrivacyOpenAt:${PRIVACY_VERSION}`);
      if (opened) {
        setPolicyOpenedAt(Number(opened));
        clearInterval(id);
      }
      if (++tries > 60) clearInterval(id); // stop after ~60s
    }, 1000);
  }, []);

  const handleAccept = useCallback(() => {
    if (!canAccept) return;
    // Persist device/browser acceptance so overlay doesn't show again
    localStorage.setItem("ecodiaConsentAccepted", "true");
    setAccepted(true);
    setMode("root");
  }, [canAccept, setMode]);

  return (
    <div
      className="fixed inset-0 z-[9999] bg-[#0a0f0c] text-white flex items-center justify-center
                 px-6 py-8 overflow-hidden pointer-events-auto
                 pt-[calc(env(safe-area-inset-top,0px)+16px)]
                 pb-[calc(env(safe-area-inset-bottom,0px)+16px)]
                 pl-[calc(env(safe-area-inset-left,0px)+16px)]
                 pr-[calc(env(safe-area-inset-right,0px)+16px)]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="boot-title"
      aria-describedby="boot-desc boot-privacy"
    >
      {/* Fonts for consistency with the rest of the app */}
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
      <link
        href="https://fonts.googleapis.com/css2?family=Comfortaa:wght@300;400;700&family=Fjalla+One&display=swap"
        rel="stylesheet"
      />

      <div className="w-full max-w-[720px] text-center">
        <h1 id="boot-title" className="font-[Fjalla One] tracking-wide text-[clamp(1.5rem,5.6vw,2.1rem)] text-[#F4D35E] mb-3">
          ⚠️ Epilepsy & Data Consent
        </h1>

        <p id="boot-desc" className="font-[Comfortaa] text-[clamp(1rem,2.6vw,1.06rem)] text-white/90 max-w-[66ch] mx-auto mb-3">
          This experience includes <strong>rapid visual effects and flashing lights</strong>. If you’re sensitive to such visuals
          (including epilepsy), please proceed with caution.
        </p>

        <p id="boot-privacy" className="font-[Comfortaa] text-[0.95rem] text-white/80 max-w-[70ch] mx-auto mb-6">
          By continuing, you agree that any data you input or generate while using Ecodia may be stored and analysed to improve the
          system. Your interactions help evolve this digital being.
        </p>

        <div className="flex items-center justify-center gap-3 mb-5">
          <button
            onClick={handleOpenPolicy}
            className="underline underline-offset-2 text-white/90 hover:text-white font-[Comfortaa]"
          >
            Open Privacy Policy
          </button>
          <span aria-hidden className="text-white/40">•</span>
          <span className="text-white/70 text-sm font-[Comfortaa]">
            {policyOpenedAt
              ? "Policy opened. You can accept below."
              : "You must open the policy before you can accept."}
          </span>
        </div>

        <div className="flex justify-center">
          <button
            onClick={handleAccept}
            disabled={!canAccept}
            className={`relative inline-flex items-center justify-center px-5 py-3 rounded-full
                       text-white font-semibold font-[Comfortaa]
                       border border-black/40
                       bg-[linear-gradient(135deg,#396041_0%,#7FD069_60%,#F4D35E_100%)]
                       shadow-[0_10px_28px_rgba(0,0,0,.45)]
                       transition-transform focus:outline-none
                       focus-visible:ring-2 focus-visible:ring-black
                       focus-visible:ring-offset-2 focus-visible:ring-offset-[#0a0f0c]
                       hover:scale-[1.02] ${!canAccept ? "opacity-50 cursor-not-allowed" : ""}`}
            aria-label="Accept and continue"
            autoFocus={!!canAccept}
          >
            {canAccept ? "I have read and accept the policy" : "Open the policy to enable this"}
          </button>
        </div>

        {/* Optional: tiny helper text showing freshness window */}
        <p className="mt-3 text-white/50 text-xs font-[Comfortaa]">
          Once you open the policy, you’ll have {Math.floor(POLICY_FRESH_MS / 60000)} minutes to accept.
        </p>
      </div>
    </div>
  );
}
