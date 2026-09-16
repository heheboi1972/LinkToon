"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, BookOpen, Palette } from "lucide-react";
import { api } from "@/lib/api";
import type { Project } from "@/lib/types";
import { PageHeading } from "@/components/shell";
import { ErrorState, Loading } from "@/components/states";
interface Bible {
  story_bible: { idea?: string };
  visual_bible: { preset?: string };
  world_bible: Record<string, unknown>;
  prompt_rules: string[];
  negative_rules: string[];
}
export function ProjectBible({ projectId }: { projectId: string }) {
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api<Project>(`/projects/${projectId}`),
  });
  const bible = useQuery({
    queryKey: ["bible", projectId],
    queryFn: () => api<Bible>(`/projects/${projectId}/bible`),
  });
  return (
    <>
      <Link
        href={`/projects/${projectId}`}
        className="mb-5 inline-flex items-center gap-2 text-xs text-zinc-500"
      >
        <ArrowLeft className="size-3" />
        프로젝트로 돌아가기
      </Link>
      <PageHeading
        eyebrow="PROJECT BIBLE"
        title="이야기의 시작점"
        description={`${project.data?.title || "프로젝트"}를 만들 때 정한 아이디어와 스타일입니다.`}
      />
      {bible.isPending ? (
        <Loading />
      ) : bible.error ? (
        <ErrorState error={bible.error} retry={() => void bible.refetch()} />
      ) : (
        <div className="grid gap-5 md:grid-cols-2">
          <div className="rounded-2xl border border-zinc-200 bg-white p-7">
            <BookOpen className="mb-5 size-6 text-violet-500" />
            <h2 className="font-bold">처음의 아이디어</h2>
            <p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-zinc-500">
              {bible.data.story_bible.idea ||
                "프로젝트를 만들 때 입력한 아이디어가 없습니다."}
            </p>
          </div>
          <div className="rounded-2xl border border-zinc-200 bg-white p-7">
            <Palette className="mb-5 size-6 text-violet-500" />
            <h2 className="font-bold">비주얼 스타일</h2>
            <p className="mt-4 text-sm text-zinc-500">
              {{
                cinematic: "시네마틱",
                soft_webtoon: "소프트 웹툰",
                ink: "잉크 & 모노",
              }[bible.data.visual_bible.preset || ""] ||
                bible.data.visual_bible.preset}
            </p>
          </div>
        </div>
      )}
      <p className="mt-6 text-xs leading-6 text-zinc-400">
        Story Studio의 AI 작성·확장·버전 관리는 Phase 3에서 연결됩니다.
      </p>
    </>
  );
}
