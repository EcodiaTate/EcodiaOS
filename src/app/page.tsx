// app/route/.../page.tsx
export const dynamic = "force-dynamic";
export const revalidate = 0;

import ClientPage from "./ClientPage";

export default function Page() {
  return <ClientPage />;
}

