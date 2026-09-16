"use client";
import { AlertCircle, LoaderCircle, FolderOpen } from "lucide-react";
import { Button } from "@/components/ui/button";

export function Loading({
  label = "작업실을 불러오는 중",
}: {
  label?: string;
}) {
  return (
    <div
      role="status"
      className="flex min-h-52 items-center justify-center gap-3 text-sm text-zinc-500"
    >
      <LoaderCircle className="size-5 animate-spin text-violet-500" />
      {label}
    </div>
  );
}
export function ErrorState({
  error,
  retry,
}: {
  error: Error | null;
  retry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="my-4 flex flex-wrap items-center gap-3 rounded-xl border border-red-100 bg-red-50 p-4 text-sm text-red-700"
    >
      <AlertCircle className="size-5 shrink-0" />
      <span className="flex-1">{error?.message || "문제가 발생했습니다."}</span>
      {retry && (
        <Button variant="outline" size="sm" onClick={retry}>
          다시 시도
        </Button>
      )}
    </div>
  );
}
export function EmptyState({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex min-h-64 flex-col items-center justify-center rounded-2xl border border-dashed border-zinc-200 bg-white/60 px-6 py-10 text-center">
      <div className="mb-4 rounded-2xl bg-violet-50 p-4 text-violet-500">
        <FolderOpen className="size-7" />
      </div>
      <h3 className="font-semibold text-zinc-800">{title}</h3>
      <p className="mb-5 mt-2 max-w-sm text-sm leading-relaxed text-zinc-500">
        {description}
      </p>
      {children}
    </div>
  );
}
