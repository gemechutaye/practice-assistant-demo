import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Practice Assistant — A working demonstration by Gemechu",
  description:
    "A personal assistant that prepares the day, coordinates the team, and follows work through. Independent demonstration with fictional office records.",
  robots: { index: false, follow: false },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
