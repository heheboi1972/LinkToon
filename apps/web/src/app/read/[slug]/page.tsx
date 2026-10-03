import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PublicReader } from "@/components/public-reader";
import type { PublicationReader } from "@/lib/types";

async function loadPublication(
  slug: string,
): Promise<PublicationReader | null> {
  const apiOrigin =
    process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") ||
    "http://127.0.0.1:8000";
  try {
    const response = await fetch(
      `${apiOrigin}/api/v1/publications/${encodeURIComponent(slug)}`,
      { cache: "no-store" },
    );
    if (!response.ok) return null;
    return (await response.json()) as PublicationReader;
  } catch {
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const publication = await loadPublication(slug);
  if (!publication)
    return {
      title: "작품을 찾을 수 없습니다",
      robots: { index: false, follow: false },
    };
  const indexable = publication.visibility === "public";
  return {
    title: publication.title,
    description: publication.description.slice(0, 300),
    robots: { index: indexable, follow: indexable },
    openGraph: {
      type: "article",
      title: publication.title,
      description: publication.description.slice(0, 300),
    },
  };
}

export default async function PublicReadPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const publication = await loadPublication(slug);
  if (!publication) notFound();
  return <PublicReader publication={publication} />;
}
