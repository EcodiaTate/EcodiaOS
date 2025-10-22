"use client";

export default function EcodiaLayout({ children }: { children: React.ReactNode }) {
  return (
    <html className="overflow-hidden">
      <body className="m-0 p-0 overflow-hidden bg-black text-black">
        {children}
      </body>
    </html>
  );
}
