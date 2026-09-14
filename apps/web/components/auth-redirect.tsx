"use client";

import { useEffect } from "react";
import { hasAuthRedirect } from "@/lib/saas-callback";
import { safeNextPath } from "@/lib/saas-errors";

/**
 * If a magic-link lands on `/` or `/pricing` (Site URL), bounce to `/signup`
 * with the same query + hash so SignupForm can write `ardoise.session`.
 * `/signup` and `/app*` consume the hash themselves — do not drop it.
 */
export function AuthRedirect() {
  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const bounce = () => {
      if (
        window.location.pathname === "/signup" ||
        window.location.pathname.startsWith("/app")
      ) {
        return;
      }
      if (!hasAuthRedirect(window.location.search, window.location.hash)) {
        return;
      }
      const url = new URL("/signup", window.location.origin);
      const incoming = new URLSearchParams(window.location.search);
      incoming.forEach((value, key) => {
        url.searchParams.set(key, value);
      });
      if (!safeNextPath(url.searchParams.get("next"))) {
        url.searchParams.set("next", "/app");
      }
      window.location.replace(
        `${url.pathname}${url.search}${window.location.hash}`,
      );
    };

    bounce();
    window.addEventListener("hashchange", bounce);
    const retry = window.setTimeout(bounce, 0);
    return () => {
      window.removeEventListener("hashchange", bounce);
      window.clearTimeout(retry);
    };
  }, []);

  return null;
}
