"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  PencilLine,
  Sparkles,
  WandSparkles,
} from "lucide-react";
import { post } from "@/lib/api";
import type { Project } from "@/lib/types";
import { cn, genres } from "@/lib/utils";
import { PageHeading } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { ErrorState } from "@/components/states";

export function ProjectWizard() {
  const [step, setStep] = useState(0);
  const router = useRouter();
  const client = useQueryClient();
  const [form, setForm] = useState({
    title: "",
    description: "",
    genre: "fantasy",
    orientation: "vertical",
    creation_mode: "manual",
    visual_style: "cinematic",
  });
  const create = useMutation({
    mutationFn: () => post<Project>("/projects", form),
    onSuccess: async (project) => {
      await client.invalidateQueries({ queryKey: ["projects"] });
      router.push(`/projects/${project.id}`);
    },
  });
  function set(name: keyof typeof form, value: string) {
    setForm((state) => ({ ...state, [name]: value }));
  }
  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (step < 2) setStep(step + 1);
    else create.mutate();
  }
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeading
        eyebrow="A NEW BEGINNING"
        title="새로운 세계를 만들어 볼까요?"
        description="이야기의 이름과 방향을 정하는 것부터 시작해요."
      />
      <ol className="mb-8 flex items-center">
        {["프로젝트 소개", "제작 방식", "비주얼 스타일"].map((label, index) => (
          <li key={label} className="flex flex-1 items-center gap-2 text-xs">
            <span
              className={cn(
                "flex size-7 shrink-0 items-center justify-center rounded-full text-[11px] font-bold",
                index <= step
                  ? "bg-violet-600 text-white"
                  : "bg-zinc-200 text-zinc-500",
              )}
            >
              {index < step ? <Check className="size-4" /> : index + 1}
            </span>
            <span
              className={cn(
                index === step
                  ? "font-semibold text-zinc-800"
                  : "text-zinc-400",
              )}
            >
              {label}
            </span>
            {index < 2 && (
              <span className="mx-2 hidden h-px flex-1 bg-zinc-200 sm:block" />
            )}
          </li>
        ))}
      </ol>
      <form
        onSubmit={submit}
        className="rounded-2xl border border-zinc-200 bg-white p-6 sm:p-9"
      >
        {step === 0 && (
          <div className="space-y-6">
            <label className="field-label">
              프로젝트 제목
              <Input
                value={form.title}
                onChange={(e) => set("title", e.target.value)}
                placeholder="예: 달빛이 머무는 도시"
                required
                maxLength={120}
                autoFocus
              />
            </label>
            <label className="field-label">
              어떤 이야기인가요?
              <Textarea
                value={form.description}
                onChange={(e) => set("description", e.target.value)}
                placeholder="주인공, 세계관, 떠오르는 장면을 자유롭게 적어 주세요."
                maxLength={5000}
              />
            </label>
            <div className="grid gap-5 sm:grid-cols-2">
              <label className="field-label">
                장르
                <select
                  value={form.genre}
                  onChange={(e) => set("genre", e.target.value)}
                >
                  {Object.entries(genres).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field-label">
                화면 방향
                <select
                  value={form.orientation}
                  onChange={(e) => set("orientation", e.target.value)}
                >
                  <option value="vertical">세로 스크롤</option>
                  <option value="horizontal">가로형</option>
                </select>
              </label>
            </div>
          </div>
        )}
        {step === 1 && (
          <fieldset>
            <legend className="mb-2 text-lg font-bold">
              어떤 방식으로 만들고 싶나요?
            </legend>
            <p className="mb-6 text-sm text-zinc-500">
              선택한 제작 방식은 프로젝트 설정에 저장됩니다.
            </p>
            <div className="space-y-3">
              {[
                {
                  value: "manual",
                  label: "직접 만들기",
                  description: "직접 그린 이미지와 대사로 장면을 채워요.",
                  icon: PencilLine,
                },
                {
                  value: "assisted",
                  label: "AI와 함께 만들기",
                  description:
                    "이야기는 내가, 아이디어는 AI와 함께. AI 연결은 Phase 3 예정.",
                  icon: Sparkles,
                },
                {
                  value: "ai_first",
                  label: "AI로 시작하기",
                  description:
                    "아이디어에서 장면까지 생성으로 시작해요. AI 연결은 Phase 3 예정.",
                  icon: WandSparkles,
                },
              ].map(({ value, label, description, icon: Icon }) => (
                <label
                  key={value}
                  className={cn(
                    "flex cursor-pointer items-center gap-4 rounded-xl border p-5",
                    form.creation_mode === value
                      ? "border-violet-500 bg-violet-50/50"
                      : "border-zinc-200",
                  )}
                >
                  <input
                    type="radio"
                    name="mode"
                    value={value}
                    checked={form.creation_mode === value}
                    onChange={() => set("creation_mode", value)}
                    className="accent-violet-600"
                  />
                  <Icon className="size-5 shrink-0 text-violet-500" />
                  <span>
                    <span className="block text-sm font-semibold">{label}</span>
                    <span className="mt-1 block text-xs leading-5 text-zinc-500">
                      {description}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
        )}
        {step === 2 && (
          <fieldset>
            <legend className="mb-2 text-lg font-bold">
              이야기에 어울리는 색을 골라 주세요
            </legend>
            <p className="mb-6 text-sm text-zinc-500">
              스타일 프리셋은 Project Bible에 저장됩니다.
            </p>
            <div className="grid gap-4 sm:grid-cols-3">
              {[
                {
                  value: "cinematic",
                  label: "시네마틱",
                  bg: "from-indigo-950 via-violet-800 to-orange-200",
                  caption: "깊은 빛과 영화 같은 장면",
                },
                {
                  value: "soft_webtoon",
                  label: "소프트 웹툰",
                  bg: "from-rose-200 via-orange-100 to-violet-200",
                  caption: "부드럽고 따뜻한 분위기",
                },
                {
                  value: "ink",
                  label: "잉크 & 모노",
                  bg: "from-zinc-800 via-zinc-500 to-zinc-200",
                  caption: "강렬한 선과 명암",
                },
              ].map(({ value, label, bg, caption }) => (
                <label
                  key={value}
                  className={cn(
                    "cursor-pointer overflow-hidden rounded-xl border-2",
                    form.visual_style === value
                      ? "border-violet-500"
                      : "border-zinc-100",
                  )}
                >
                  <div
                    className={cn(
                      "flex h-32 items-center justify-center bg-gradient-to-br",
                      bg,
                    )}
                  >
                    <span className="text-4xl font-black text-white/60">
                      Aa
                    </span>
                  </div>
                  <div className="p-3">
                    <span className="flex items-center justify-between text-sm font-semibold">
                      {label}
                      <input
                        aria-label={label}
                        type="radio"
                        name="style"
                        value={value}
                        checked={form.visual_style === value}
                        onChange={() => set("visual_style", value)}
                        className="accent-violet-600"
                      />
                    </span>
                    <span className="mt-2 block text-[10px] text-zinc-400">
                      {caption}
                    </span>
                  </div>
                </label>
              ))}
            </div>
          </fieldset>
        )}
        {create.error && <ErrorState error={create.error} />}
        <div className="mt-9 flex justify-between border-t border-zinc-100 pt-6">
          <Button
            type="button"
            variant="ghost"
            disabled={create.isPending}
            onClick={() =>
              step ? setStep(step - 1) : router.push("/dashboard")
            }
          >
            <ArrowLeft />
            {step ? "이전" : "취소"}
          </Button>
          <Button
            type="submit"
            disabled={create.isPending || !form.title.trim()}
          >
            {create.isPending
              ? "만드는 중…"
              : step === 2
                ? "프로젝트 만들기"
                : "다음"}
            <ArrowRight />
          </Button>
        </div>
      </form>
    </div>
  );
}
