import type { Metadata } from "next";
import { DocsClient } from "@/components/docs/DocsClient";

export const metadata: Metadata = {
  title: "Documentation — Meridian AI",
  description:
    "The complete Meridian AI product guide: concepts, the seven-stage investigation pipeline, evidence and verification, security, and reference.",
};

export default function DocsPage() {
  return <DocsClient />;
}
