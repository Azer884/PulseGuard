import type { Metadata } from "next";
import { Geist_Mono, Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "PulseGuard AI Twins",
  description: "AI Scrum Master: team twin simulation, rotation optimization and burnout-aware task allocation.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`dark ${inter.variable} ${geistMono.variable} h-full antialiased`} suppressHydrationWarning>
      <body className="h-full flex flex-col font-sans bg-slate-50 dark:bg-slate-950 text-slate-800 dark:text-slate-100">
        {children}
      </body>
    </html>
  );
}
