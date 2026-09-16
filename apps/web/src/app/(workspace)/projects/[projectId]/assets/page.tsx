import { ProjectAssets } from "@/components/project-assets";
export default async function AssetsPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <ProjectAssets projectId={projectId} />;
}
