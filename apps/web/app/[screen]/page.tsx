import { notFound } from "next/navigation";
import { Suspense } from "react";
import Workspace from "@/components/Workspace";
const screens = [
  "overview",
  "emergency",
  "capacity",
  "trusts",
  "geography",
  "forecasting",
  "analyst",
  "operations",
];
export function generateStaticParams() {
  return screens.map((screen) => ({ screen }));
}
export async function generateMetadata({
  params,
}: {
  params: Promise<{ screen: string }>;
}) {
  const { screen } = await params;
  return { title: screen.charAt(0).toUpperCase() + screen.slice(1) };
}
export default async function Page({
  params,
}: {
  params: Promise<{ screen: string }>;
}) {
  const { screen } = await params;
  if (!screens.includes(screen)) notFound();
  return (
    <Suspense
      fallback={
        <div className="initial-loading" role="status">
          Opening NHS Pulse…
        </div>
      }
    >
      <Workspace screen={screen} />
    </Suspense>
  );
}
