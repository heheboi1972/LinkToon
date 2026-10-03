import { PublicationManager } from "@/components/publication-manager";

export default async function PublishPage({
  params,
}: {
  params: Promise<{ projectId: string; episodeId: string }>;
}) {
  const { projectId, episodeId } = await params;
  return <PublicationManager projectId={projectId} episodeId={episodeId} />;
}
