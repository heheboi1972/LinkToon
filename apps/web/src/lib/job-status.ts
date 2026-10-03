import type { GenerationJobStatus } from "@/lib/types";

const labels: Record<GenerationJobStatus, string> = {
  queued: "생성 준비 중",
  running: "AI가 이야기를 만들고 있어요",
  provider_pending: "AI 응답을 기다리고 있어요",
  saving: "이야기를 저장하고 있어요",
  succeeded: "생성 완료",
  failed: "생성에 실패했습니다",
  canceled: "생성이 취소되었습니다",
};

export function jobStatusLabel(status: string): string {
  return Object.hasOwn(labels, status)
    ? labels[status as GenerationJobStatus]
    : "상태 확인 중";
}
