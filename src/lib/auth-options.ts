// src/lib/auth-options.ts (ALIVE)
import type { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";
import GoogleProvider from "next-auth/providers/google";

const RAW_API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_BASE = RAW_API_BASE.replace(/\/+$/, "");
const SITE_NAME: "alive" = "alive";

function normalizeEmail(email?: string | null): string | null {
  if (!email) return null;
  const e = String(email).trim().toLowerCase();
  if (!e) return null;
  return e.replace(/\.[lL][oO][cC][aA][lL]$/, ".test");
}

// Matches UpsertAccountIn on the backend
async function upsertAccountToNeo(params: {
  site: "alive";
  uid: string;
  provider?: string | null;
  subject?: string | null;
  email?: string | null;
}) {
  const safe = { ...params, email: normalizeEmail(params.email) };
  try {
    await fetch(`${API_BASE}/link/identity/upsert_account`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      credentials: "include",
      body: JSON.stringify(safe),
    });
  } catch (e) {
    console.warn("[identity.upsert_account] failed", e);
  }
}

export const authOptions: NextAuthOptions = {
  session: { strategy: "jwt" },

  providers: [
    CredentialsProvider({
      name: "Email & Password",
      credentials: { email: {}, password: {} },
      async authorize(creds) {
        try {
          const res = await fetch(`${API_BASE}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              email: creds?.email,
              password: creds?.password,
            }),
            cache: "no-store",
          });
          if (!res.ok) return null;

          const user = await res.json();

          const uid = String(user?.id ?? user?.email ?? "");
          await upsertAccountToNeo({
            site: SITE_NAME,
            uid,
            provider: "credentials",
            subject: uid,
            email: user?.email ? String(user.email) : null,
          });

          return user?.email ? user : null;
        } catch {
          return null;
        }
      },
    }),

    ...(process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET
      ? [
          GoogleProvider({
            clientId: process.env.GOOGLE_CLIENT_ID!,
            clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
          }),
        ]
      : []),
  ],

  callbacks: {
    async signIn({ account, profile }) {
      if (account?.provider === "google") {
        const email = (profile as any)?.email as string | undefined;
        if (!email) return false;

        try {
          let u: any | undefined;

          const r = await fetch(`${API_BASE}/auth/sso-login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email }),
            cache: "no-store",
          });

          if (r.ok) {
            u = await r.json();
            (account as any).__bootstrap = u;
          } else if (r.status === 404) {
            const rr = await fetch(`${API_BASE}/auth/sso-register`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ email }),
              cache: "no-store",
            });
            if (!rr.ok) return false;
            u = await rr.json();
            (account as any).__bootstrap = u;
          } else {
            return false;
          }

          const uid = String(u?.id ?? email);
          const subject = String(
            (account as any)?.providerAccountId ?? u?.id ?? email
          );

          await upsertAccountToNeo({
            site: SITE_NAME,
            uid,
            provider: account.provider,
            subject,
            email,
          });

          return true;
        } catch {
          return false;
        }
      }
      return true;
    },

    async jwt({ token, user, account, trigger, session }) {
      if (user) {
        token.id = (user as any).id ?? token.id;
        token.email = (user as any).email ?? token.email;
        token.role = (user as any).role ?? token.role ?? "user";
        token.caps = (user as any).caps ?? token.caps ?? {};
        token.profile = (user as any).profile ?? token.profile;
        token.user_token = (user as any).user_token ?? token.user_token;
        token.admin_token = (user as any).admin_token ?? token.admin_token;
        token.backendToken =
          (user as any).admin_token ?? (user as any).token ?? token.backendToken;
        (token as any).picture =
          (user as any).picture || (user as any).image || (token as any).picture;
      }

      if (account?.provider === "google" && (account as any).__bootstrap) {
        const u = (account as any).__bootstrap;
        token.id = u.id ?? token.id;
        token.email = u.email ?? token.email;
        token.role = u.role ?? token.role ?? "user";
        token.caps = u.caps ?? token.caps ?? {};
        token.profile = u.profile ?? token.profile;
        token.user_token = u.user_token ?? token.user_token;
        token.admin_token = u.admin_token ?? token.admin_token;
        token.backendToken = u.admin_token ?? u.token ?? token.backendToken;
        (token as any).picture = u.picture || u.image || (token as any).picture;
      }

      if (trigger === "update" && session?.role) token.role = session.role as any;
      return token;
    },

    async session({ session, token }) {
      (session.user as any) = {
        id: token.id,
        email: token.email,
        role: token.role,
        caps: token.caps ?? {},
        profile: token.profile,
        user_token: (token as any).user_token,
        admin_token: (token as any).admin_token,
        token: (token as any).backendToken,
        image: (token as any).picture || (session.user as any).image,
      };
      return session;
    },
  },

  pages: { signIn: "/login" }, // this is fine; you’re opening a modal via mode anyway
};
