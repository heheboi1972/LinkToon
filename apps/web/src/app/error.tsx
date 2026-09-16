"use client";
import { ErrorState } from "@/components/states";
export default function ErrorPage({
  error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <main className="mx-auto max-w-2xl p-10">
      <h1 className="text-xl font-bold">화면을 불러오지 못했습니다.</h1>
      <ErrorState error={error} retry={reset} />
    </main>
  );
}
