import type { Metadata } from "next";
import { Analytics } from "@vercel/analytics/next"
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from './providers'

// Initialize the Geist Sans font with specific options.
// The `variable` property assigns a CSS variable name for this font.
// The `subsets` property specifies the character subsets to include.
const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

// Initialize the Geist Mono font with specific options.
// The `variable` property assigns a CSS variable name for this font.
// The `subsets` property specifies the character subsets to include.
const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Defines the metadata for the application.
// This includes the title and description that will be used in the HTML head.
export const metadata: Metadata = {
  title: "Jarvis-AI",
  description: "AI Agent Communication Platform",
};

/**
 * Root layout component for the application.
 * This component wraps all pages and provides a consistent structure.
 * It sets up the HTML lang, body classes for fonts, and includes Providers and Analytics.
 *
 * @param {object} props - The component's props.
 * @param {React.ReactNode} props.children - The child components to be rendered within this layout.
 * @returns {JSX.Element} The HTML structure for the root layout.
 */
export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <Providers>
          {children}
        </Providers>
        <Analytics />
      </body>
    </html>
  );
}
