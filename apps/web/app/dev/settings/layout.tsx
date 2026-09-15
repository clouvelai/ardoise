import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Settings mint preview",
  robots: { index: false, follow: false },
};

export default function SettingsPreviewLayout({
  children,
}: {
  children: ReactNode;
}) {
  return children;
}
