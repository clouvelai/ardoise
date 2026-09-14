import type { Metadata, Viewport } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";
import { AuthRedirect } from "@/components/auth-redirect";
import "./globals.css";

const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-jakarta",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Ardoise — Know where every token went",
  description:
    "Local AI spend ledger for Claude Code and Cursor. Prompts never leave the machine.",
  applicationName: "Ardoise",
  authors: [{ name: "clouvelai" }],
  keywords: [
    "AI spend",
    "Claude Code",
    "Cursor",
    "local ledger",
    "token usage",
  ],
  openGraph: {
    title: "Ardoise — Know where every token went",
    description:
      "Turn Claude Code and Cursor usage into a local ledger. Nothing leaves the machine.",
    type: "website",
  },
};

export const viewport: Viewport = {
  themeColor: "#f4f0fb",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${jakarta.variable} h-full antialiased`}>
      <body className="min-h-full font-sans">
        <AuthRedirect />
        {children}
      </body>
    </html>
  );
}
