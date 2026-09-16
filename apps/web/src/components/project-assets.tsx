"use client";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Upload } from "lucide-react";
import { api, mediaUrl, remove, uploadImage } from "@/lib/api";
import type { Asset, Project } from "@/lib/types";
import { ConfirmDelete, PageHeading } from "@/components/shell";
import { EmptyState, ErrorState, Loading } from "@/components/states";

export function ProjectAssets({ projectId }: { projectId: string }) {
  const client = useQueryClient();
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api<Project>(`/projects/${projectId}`),
  });
  const assets = useQuery({
    queryKey: ["assets", projectId],
    queryFn: () => api<Asset[]>(`/projects/${projectId}/assets?limit=200`),
    refetchInterval: 600_000,
  });
  const upload = useMutation({
    mutationFn: (file: File) => uploadImage(projectId, file, "reference"),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ["assets", projectId] }),
  });
  const deletion = useMutation({
    mutationFn: (id: string) => remove(`/assets/${id}`),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ["assets", projectId] }),
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
        eyebrow={project.data?.title || "PROJECT ASSETS"}
        title="이미지 보관함"
        description="직접 그린 장면, 캐릭터 참고 이미지, 영감을 주는 이미지를 모아 두세요."
      />
      <label className="mb-7 flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed border-violet-200 bg-violet-50/40 p-10 text-center">
        <Upload className="mb-3 size-7 text-violet-500" />
        <span className="text-sm font-semibold text-violet-700">
          {upload.isPending
            ? "이미지를 업로드하는 중…"
            : "클릭해서 이미지 업로드"}
        </span>
        <span className="mt-2 text-xs text-zinc-400">
          PNG, JPG, WebP · 최대 10 MB · 정적 이미지
        </span>
        <input
          aria-label="참고 이미지 업로드"
          className="sr-only"
          type="file"
          accept="image/png,image/jpeg,image/webp"
          disabled={upload.isPending || !project.data}
          onChange={(e) => {
            if (e.target.files?.[0]) upload.mutate(e.target.files[0]);
            e.target.value = "";
          }}
        />
      </label>
      {(upload.error || deletion.error || project.error) && (
        <ErrorState error={upload.error || deletion.error || project.error} />
      )}
      {assets.isPending ? (
        <Loading />
      ) : assets.error ? (
        <ErrorState error={assets.error} retry={() => void assets.refetch()} />
      ) : !assets.data?.length ? (
        <EmptyState
          title="아직 보관된 이미지가 없어요"
          description="프로젝트의 표지, 패널 이미지, 참고 이미지는 모두 여기에 모입니다."
        />
      ) : (
        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
          {assets.data.map((asset) => (
            <article
              key={asset.id}
              className="overflow-hidden rounded-2xl border border-zinc-200 bg-white"
            >
              <img
                src={mediaUrl(asset.public_url)}
                alt={asset.metadata.filename || "프로젝트 이미지"}
                className="aspect-square w-full bg-zinc-50 object-contain"
              />
              <div className="p-4">
                <p className="truncate text-xs font-semibold">
                  {asset.metadata.filename || asset.id}
                </p>
                <p className="mb-3 mt-1 text-[10px] text-zinc-400">
                  {asset.width} × {asset.height} ·{" "}
                  {(asset.file_size / 1024).toFixed(0)} KB
                </p>
                <ConfirmDelete
                  label="이 이미지를"
                  pending={deletion.isPending}
                  onDelete={() => deletion.mutate(asset.id)}
                />
              </div>
            </article>
          ))}
        </div>
      )}
    </>
  );
}
