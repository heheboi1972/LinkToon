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
        description="이야기와 이미지가 만들어지는 과정을 한눈에 확인해요."
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
          description="비동기 AI 생성과 재시도 기능은 Phase 3에서 연결됩니다. 현재는 직접 업로드한 이미지로 패널을 만들 수 있어요."
        />
      )}
    </>
  );
}
