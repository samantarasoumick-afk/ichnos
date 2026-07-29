import "./globals.css";
import "reactflow/dist/style.css";

import type { Metadata } from "next";

import TourStepper from "../components/TourStepper";
import { AuthProvider } from "../contexts/AuthContext";
import { TourProvider } from "../contexts/TourContext";

export const metadata: Metadata = {
  title: "DataFe",
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
        <AuthProvider>
          <TourProvider>
            {children}
            <TourStepper />
          </TourProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
