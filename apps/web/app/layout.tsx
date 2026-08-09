import type { Metadata } from "next";
import { Inter, Fira_Code } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const firaCode = Fira_Code({
  subsets: ["latin"],
  variable: "--font-fira-code",
  display: "swap",
});

export const metadata: Metadata = {
  title: "RepoLens — AI Codebase Intelligence Platform",
  description: "Enterprise codebase intelligence, AST parsing, dependency graphs, security SAST, and grounded AI context.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} ${firaCode.variable} dark`}>
      <body className="bg-obsidian-base text-gray-100 antialiased min-h-screen selection:bg-electric-indigo selection:text-white">
        {children}
      </body>
    </html>
  );
}
