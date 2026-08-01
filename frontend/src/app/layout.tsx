import "./globals.css";
import "reactflow/dist/style.css";

import type { Metadata } from "next";

import StoryRecorderWidget from "../components/StoryRecorderWidget";
import TourStepper from "../components/TourStepper";
import { AuthProvider } from "../contexts/AuthContext";
import { StoryRecorderProvider } from "../contexts/StoryRecorderContext";
import { TourProvider } from "../contexts/TourContext";

export const metadata: Metadata = {
  title: "DatFe",
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
            <StoryRecorderProvider>
              {children}
              <TourStepper />
              <StoryRecorderWidget />
            </StoryRecorderProvider>
          </TourProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
