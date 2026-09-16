import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
export function dateLabel(value: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    month: "short",
    day: "numeric",
  }).format(
    new Date(
      value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`,
    ),
  );
}
export const genres: Record<string, string> = {
  fantasy: "판타지",
  romance: "로맨스",
  drama: "드라마",
  action: "액션",
  comedy: "코미디",
  slice_of_life: "일상",
  thriller: "스릴러",
};
export const statuses: Record<string, string> = {
  draft: "초안",
  active: "제작 중",
  archived: "보관됨",
  empty: "빈 패널",
  static: "이미지",
  animated: "애니메이션",
  generating: "생성 중",
};
