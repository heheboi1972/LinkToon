import { EpisodeReader } from "@/components/episode-reader";

export default async function EpisodeReaderPage({
  params,
}: {
  params: Promise<{ projectId: string; episodeId: string }>;
}) {
  const { projectId, episodeId } = await params;
  return <EpisodeReader projectId={projectId} episodeId={episodeId} />;
}
