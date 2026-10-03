import { ProjectCharactersPage } from "@/components/project-characters-page";

export default async function CharactersPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <ProjectCharactersPage projectId={projectId} />;
}
