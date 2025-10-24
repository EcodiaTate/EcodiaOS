"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import type { Route } from "next";
import { useModeStore } from "@/stores/useModeStore";

export default function ClientPage() {
  const setMode = useModeStore((s) => s.setMode);
  const router = useRouter();
  const params = useSearchParams();

  useEffect(() => {
    const desiredMode = (params.get("mode") || "hub") as any;
    const rawNext = params.get("next") || "/";

    // Persist + set mode
    try {
      // Set localStorage first, just in case
      localStorage.setItem("alive_mode", desiredMode);
    } catch {}
    
    // Set the in-memory store state. This is the crucial part.
    // Any component listening to the store (like your main layout)
    // will react to this *immediately*, before any navigation.
    setMode(desiredMode);

    // --- The Elegant Fix ---
    // We navigate *after* setting the state.
    // The `setTimeout(..., 0)` pushes this navigation to the next
    // event loop tick. This gives React time to re-render
    // any components that depend on the store's 'mode'
    // *before* the URL changes.
    //
    // This avoids the hard reload (window.location) and lets
    // React's router handle it, which is much cleaner.
    const target: Route =
      rawNext.startsWith("/") ? (rawNext as unknown as Route) : ("/" as Route);

    // Navigate after mode is stored
    const t = setTimeout(() => {
      router.replace(target);
    }, 0); // This 0ms timeout is the key

    return () => clearTimeout(t);
  }, [params, router, setMode]);

  return (
    <main className="grid min-h-[50vh] place-items-center text-white/80">
      <p>Preparing your workspace…</p>
    </main>
  );
}

