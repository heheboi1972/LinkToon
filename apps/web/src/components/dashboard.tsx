"use client";
import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  ArrowUpRight,
  Clock3,
  ImagePlus,
  LayoutGrid,
  List,
  Plus,
  Search,
  Sparkles,
} from "lucide-react";
import { api } from "@/lib/api";
import type { Project, Job } from "@/lib/types";
import { useAuth } from "@/components/providers";
import { PageHeading } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState, Loading } from "@/components/states";
import { AssetImage } from "@/components/asset-image";
import { cn, dateLabel, genres, statuses } from "@/lib/utils";
import { useUI } from "@/lib/store";

export function Dashboard({ allProjects = false }: { allProjects?: boolean }) {
  const { user } = useAuth();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const { projectView, setProjectView } = useUI();
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<Project[]>("/projects?limit=200"),
  });
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api<Job[]>("/jobs"),
    refetchInterval: 30_000,
  });
  const visible = projects.data?.filter(
    (p) =>
      (filter === "all" || p.status === filter) &&
      `${p.title} ${p.description}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  return (
    <>
      <PageHeading
        eyebrow={allProjects ? "YOUR COLLECTION" : "LET’S MAKE SOMETHING GREAT"}
        title={
          allProjects
            ? "내 프로젝트"
            : `${user?.display_name}님, 어떤 이야기를 만들어 볼까요?`
        }
        description="상상을 꺼내 놓는 곳. 당신의 다음 장면이 여기서 시작됩니다."
      />
      {!allProjects && (
        <>
          <section className="hero-grid relative mb-6 grid min-h-[260px] overflow-hidden rounded-[22px] bg-[#251d43] text-white sm:grid-cols-[1.1fr_1fr]">
            <div className="relative z-10 px-7 py-8 sm:p-9">
              <span className="rounded-full border border-violet-300/20 bg-violet-300/10 px-2.5 py-1 text-[9px] font-semibold tracking-[.14em] text-violet-200">
                FROM A SPARK TO A STORY
              </span>
              <h2 className="mb-3 mt-5 text-[28px] font-bold leading-[1.4] tracking-tight">
                상상했던 세계를,
                <br />
                이제 웹툰으로.
              </h2>
              <p className="text-xs leading-6 text-violet-100/60">
                당신의 아이디어에 첫 번째 장면을 더해 보세요.
              </p>
              <Button
                asChild
                size="sm"
                className="mt-6 bg-white text-violet-950 hover:bg-violet-100"
              >
                <Link href="/projects/new">
                  새 웹툰 만들기 <ArrowUpRight />
                </Link>
              </Button>
            </div>
            <img
              src="/studio-art.svg"
              alt="새로운 이야기의 영감이 되는 달빛 도시"
              className="pointer-events-none hidden h-full max-h-[320px] w-full scale-110 object-contain sm:block"
            />
          </section>
          <div className="mb-10 grid gap-4 sm:grid-cols-2">
            <Link
              href="/projects/new"
              className="group flex items-center gap-4 rounded-2xl border border-zinc-200/80 bg-white p-5 transition hover:border-violet-300 hover:shadow-sm"
            >
              <span className="rounded-xl bg-violet-50 p-3 text-violet-600">
                <Plus className="size-5" />
              </span>
              <div className="flex-1">
                <h3 className="text-sm font-bold">새 웹툰 만들기</h3>
                <p className="mt-1 text-xs text-zinc-400">
                  작은 아이디어에서 시작하는 새로운 세계
                </p>
              </div>
              <ArrowRight className="size-4 text-zinc-400 group-hover:text-violet-500" />
            </Link>
            <Link
              href="/generate"
              className="group flex items-center gap-4 rounded-2xl border border-zinc-200/80 bg-white p-5 transition hover:border-violet-300"
            >
              <span className="rounded-xl bg-orange-50 p-3 text-orange-500">
                <ImagePlus className="size-5" />
              </span>
              <div className="flex-1">
                <h3 className="text-sm font-bold">
                  이미지 만들기{" "}
                  <span className="ml-1 text-[9px] font-medium text-violet-500">
                    AI
                  </span>
                </h3>
                <p className="mt-1 text-xs text-zinc-400">
                  이미지 생성은 Phase 3에서 연결됩니다
                </p>
              </div>
              <ArrowRight className="size-4 text-zinc-400" />
            </Link>
          </div>
        </>
      )}
      <section>
        <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
          <h2 className="text-lg font-bold">
            {allProjects ? "모든 프로젝트" : "최근 프로젝트"}{" "}
            <span className="ml-2 text-sm font-medium text-zinc-400">
              {projects.data?.length || 0}
            </span>
          </h2>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="absolute left-3 top-3 size-3.5 text-zinc-400" />
              <Input
                aria-label="프로젝트 검색"
                placeholder="프로젝트 검색"
                className="h-9 w-44 rounded-lg pl-9 text-xs sm:w-52"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div className="flex rounded-lg border border-zinc-200 bg-white p-0.5">
              <Button
                size="icon"
                variant="ghost"
                className={cn(
                  "size-7 rounded-md",
                  projectView === "grid" && "bg-zinc-100 text-violet-600",
                )}
                aria-label="카드 보기"
                aria-pressed={projectView === "grid"}
                onClick={() => setProjectView("grid")}
              >
                <LayoutGrid className="!size-3.5" />
              </Button>
              <Button
                size="icon"
                variant="ghost"
                className={cn(
                  "size-7 rounded-md",
                  projectView === "list" && "bg-zinc-100 text-violet-600",
                )}
                aria-label="목록 보기"
                aria-pressed={projectView === "list"}
                onClick={() => setProjectView("list")}
              >
                <List className="!size-3.5" />
              </Button>
            </div>
          </div>
        </div>
        <div
          className="mb-5 flex gap-5 border-b border-zinc-200"
          role="group"
          aria-label="프로젝트 상태 필터"
        >
          {[
            ["all", "전체"],
            ["active", "제작 중"],
            ["draft", "초안"],
            ["archived", "보관됨"],
          ].map(([value, label]) => (
            <button
              key={value}
              onClick={() => setFilter(value)}
              aria-pressed={filter === value}
              className={cn(
                "border-b-2 pb-3 text-xs font-medium",
                filter === value
                  ? "border-violet-600 text-violet-600"
                  : "border-transparent text-zinc-400",
              )}
            >
              {label}
            </button>
          ))}
        </div>
        {projects.isPending ? (
          <Loading />
        ) : projects.error ? (
          <ErrorState
            error={projects.error}
            retry={() => void projects.refetch()}
          />
        ) : !visible?.length ? (
          <EmptyState
            title={
              search || filter !== "all"
                ? "조건에 맞는 프로젝트가 없어요"
                : "첫 번째 이야기를 기다리고 있어요"
            }
            description="새 프로젝트를 만들고 제목과 스타일을 정해 보세요. 에피소드와 패널은 그다음에 차근차근 채워 나갈 수 있어요."
          >
            <Button asChild size="sm">
              <Link href="/projects/new">
                <Plus />새 프로젝트 만들기
              </Link>
            </Button>
          </EmptyState>
        ) : (
          <div
            className={cn(
              "grid gap-5",
              projectView === "grid"
                ? "sm:grid-cols-2 xl:grid-cols-3"
                : "grid-cols-1",
            )}
          >
            {visible.map((project) => (
              <Link
                key={project.id}
                href={`/projects/${project.id}`}
                className={cn(
                  "group overflow-hidden rounded-2xl border border-zinc-200/80 bg-white transition hover:-translate-y-0.5 hover:border-violet-200 hover:shadow-md",
                  projectView === "list" && "flex",
                )}
              >
                <div
                  className={cn(
                    "relative",
                    projectView === "list" ? "w-32 shrink-0" : "aspect-[1.85]",
                  )}
                >
                  {project.thumbnail_asset_id ? (
                    <AssetImage
                      id={project.thumbnail_asset_id}
                      alt={`${project.title} 표지`}
                      className="size-full"
                    />
                  ) : (
                    <div className="flex size-full min-h-24 items-center justify-center bg-gradient-to-br from-[#e8e3f5] to-[#f5e5e4]">
                      <span className="text-5xl font-black text-violet-300/70">
                        {project.title[0]}
                      </span>
                    </div>
                  )}
                  <span className="absolute left-3 top-3 rounded-md bg-white/95 px-2 py-1 text-[9px] font-semibold text-zinc-600">
                    {statuses[project.status]}
                  </span>
                </div>
                <div className="min-w-0 flex-1 p-5">
                  <p className="mb-2 text-[10px] text-violet-500">
                    {genres[project.genre] || project.genre} ·{" "}
                    {project.orientation === "vertical"
                      ? "세로 스크롤"
                      : "가로형"}
                  </p>
                  <h3 className="truncate text-sm font-bold group-hover:text-violet-600">
                    {project.title}
                  </h3>
                  <p className="mt-2 truncate text-xs text-zinc-400">
                    {project.description || "아직 소개가 작성되지 않았어요."}
                  </p>
                  <p className="mt-4 flex items-center gap-1.5 text-[10px] text-zinc-400">
                    <Clock3 className="size-3" />
                    {dateLabel(project.updated_at)} 수정
                  </p>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>
      {!allProjects && (
        <section className="mt-10">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-bold">최근 생성 작업</h2>
            <Link
              href="/jobs"
              className="flex items-center gap-1 text-xs text-zinc-400"
            >
              모두 보기 <ArrowRight className="size-3" />
            </Link>
          </div>
          {jobs.error ? (
            <ErrorState error={jobs.error} retry={() => void jobs.refetch()} />
          ) : jobs.isPending ? (
            <Loading label="생성 작업을 확인하는 중" />
          ) : jobs.data?.length ? (
            <JobList jobs={jobs.data.slice(0, 3)} />
          ) : (
            <div className="flex items-center gap-4 rounded-2xl border border-zinc-200/70 bg-white p-5">
              <span className="rounded-xl bg-zinc-50 p-3 text-zinc-400">
                <Sparkles className="size-5" />
              </span>
              <div>
                <p className="text-xs font-medium text-zinc-600">
                  진행 중인 생성 작업이 없어요
                </p>
                <p className="mt-1 text-[11px] text-zinc-400">
                  AI 생성 기능이 연결되면 작업 진행 상황을 여기에서 확인할 수
                  있어요.
                </p>
              </div>
            </div>
          )}
        </section>
      )}
    </>
  );
}

export function JobList({ jobs }: { jobs: Job[] }) {
  return (
    <div className="space-y-3">
      {jobs.map((job) => (
        <div
          key={job.id}
          className="rounded-xl border border-zinc-200 bg-white p-5"
        >
          <div className="flex justify-between text-sm">
            <span>{job.job_type}</span>
            <span>
              {job.status} · {job.progress}%
            </span>
          </div>
          <progress
            value={job.progress}
            max="100"
            aria-label={`${job.job_type} 진행률`}
            className="mt-3 h-1.5 w-full accent-violet-600"
          />
          {job.error_message && (
            <p className="mt-2 text-xs text-red-600">{job.error_message}</p>
          )}
        </div>
      ))}
    </div>
  );
}
