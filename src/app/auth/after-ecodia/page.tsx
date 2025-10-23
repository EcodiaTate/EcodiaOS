// app/auth/after/page.tsx
export const dynamic = "force-dynamic";
export const revalidate = 0;
export const fetchCache = "force-no-store";

import ClientPage from "./ClientPage";

export default function AfterAuthPage() {
  return <ClientPage />;
}
