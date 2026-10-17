import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: {
    default: "NHS Pulse · Published hospital intelligence",
    template: "%s · NHS Pulse",
  },
  icons: { icon: "/icon.svg" },
  description:
    "Independent analysis of published NHS England A&E, diagnostics and quarterly bed statistics, with source versions and release-aware operations.",
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-GB">
      <body>
        <a className="skip-link" href="#workspace">
          Skip to workspace
        </a>
        {children}
      </body>
    </html>
  );
}
