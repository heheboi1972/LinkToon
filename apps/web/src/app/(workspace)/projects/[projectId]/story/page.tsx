import { ProjectBible } from "@/components/project-bible";
export default async function StoryPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <ProjectBible projectId={projectId} />;
}
