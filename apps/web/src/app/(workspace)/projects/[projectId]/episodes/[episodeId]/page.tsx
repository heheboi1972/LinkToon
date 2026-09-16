import { EpisodeDetail } from "@/components/episode-detail";
export default async function EpisodePage({
  params,
}: {
  params: Promise<{ projectId: string; episodeId: string }>;
}) {
  const { projectId, episodeId } = await params;
  return <EpisodeDetail projectId={projectId} episodeId={episodeId} />;
}
