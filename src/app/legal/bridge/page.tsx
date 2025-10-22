// apps/ecodia-ui/src/app/legal/bridge/page.tsx
"use client";

import { useEffect } from "react";

// Simple cookie helper
function setCookie(name: string, value: string, days = 365) {
  const d = new Date();
  d.setTime(d.getTime() + days * 24 * 60 * 60 * 1000);
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${d.toUTCString()}; path=/; samesite=lax`;
}

export default function PrivacyBridgePage() {
  useEffect(() => {
    try {
      const usp = new URLSearchParams(window.location.search);
      const ver = usp.get("ver") || "v1";
      const to = usp.get("to") || "https://ecodia.au/terms-and-conditions-of-service/";
      // Stamp "opened" time in a versioned cookie
      setCookie(`ecodiaPrivacyOpenAt:${ver}`, String(Date.now()), 365);
      // Immediately redirect to the external policy
      window.location.replace(to);
    } catch {
      window.location.replace("https://ecodia.au/terms-and-conditions-of-service/");
    }
  }, []);

  return null;
}
