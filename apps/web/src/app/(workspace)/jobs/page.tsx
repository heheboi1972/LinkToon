"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Job } from "@/lib/types";
import { PageHeading } from "@/components/shell";
import { EmptyState, ErrorState, Loading } from "@/components/states";
import { JobList } from "@/components/dashboard";
export default function JobsPage() {
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api<Job[]>("/jobs"),
    refetchInterval: 30_000,
  });
  return (
    <>
      <PageHeading
        eyebrow="GENERATION HISTORY"
        title="생성 작업"
        description="AI Story 생성 작업의 현재 상태를 확인해요."
      />
      {jobs.isPending ? (
        <Loading />
      ) : jobs.error ? (
        <ErrorState error={jobs.error} retry={() => void jobs.refetch()} />
      ) : jobs.data?.length ? (
        <JobList jobs={jobs.data} />
      ) : (
        <EmptyState
          title="아직 생성 작업이 없어요"
          description="프로젝트의 이야기 설정에서 AI Story를 만들면 작업이 여기에 표시됩니다."
        />
      )}
    </>
  );
}
