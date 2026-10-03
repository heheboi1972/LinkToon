"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Project } from "@/lib/types";
import { useAuth } from "@/components/providers";
import { PageHeading } from "@/components/shell";
import { ErrorState, Loading } from "@/components/states";
import { ProjectCharacters } from "@/components/project-characters";

export function ProjectCharactersPage({ projectId }: { projectId: string }) {
  const { user } = useAuth();
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api<Project>(`/projects/${projectId}`),
  });
  if (project.isPending) return <Loading />;
  if (project.error || !project.data) {
    return (
      <ErrorState error={project.error} retry={() => void project.refetch()} />
    );
  }
  return (
    <>
      <PageHeading
        eyebrow="CHARACTER BIBLE"
        title="이야기의 인물"
        description={`${project.data.title}의 캐릭터와 기준 이미지를 관리합니다.`}
      />
      <ProjectCharacters projectId={projectId} userId={user?.id || ""} />
    </>
  );
}
