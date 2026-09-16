"use client";
import { useQuery } from "@tanstack/react-query";
import { ImageIcon } from "lucide-react";
import { api, mediaUrl } from "@/lib/api";
import type { Asset } from "@/lib/types";
import { cn } from "@/lib/utils";
export function AssetImage({
  id,
  alt,
  className,
}: {
  id: string | null;
  alt: string;
  className?: string;
}) {
  const result = useQuery({
    queryKey: ["asset", id],
    queryFn: () => api<Asset>(`/assets/${id}`),
    enabled: Boolean(id),
    staleTime: 300_000,
    refetchInterval: 600_000,
  });
  return (
    <div
      className={cn(
        "flex items-center justify-center overflow-hidden bg-zinc-100",
        className,
      )}
    >
      {result.data?.public_url ? (
        <img
          src={mediaUrl(result.data.public_url)}
          alt={alt}
          className="size-full object-cover"
        />
      ) : (
        <span className="flex flex-col items-center gap-2 text-zinc-400">
          <ImageIcon className="size-8" />
          {result.isError && (
            <span className="text-xs">이미지를 불러올 수 없습니다</span>
          )}
        </span>
      )}
    </div>
  );
}
