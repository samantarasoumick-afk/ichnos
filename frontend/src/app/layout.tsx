import "./globals.css";
import "reactflow/dist/style.css";

import type { Metadata } from "next";

import { AuthProvider } from "../contexts/AuthContext";

export const metadata: Metadata = {
  title: "Ichnos",
  description: "Metadata intelligence and governance platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
