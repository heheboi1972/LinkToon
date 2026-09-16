import Link from "next/link";
import { Button } from "@/components/ui/button";
export default function NotFound() {
  return (
    <main className="mx-auto max-w-lg px-6 py-32 text-center">
      <p className="text-sm font-bold text-violet-600">404</p>
      <h1 className="my-4 text-2xl font-bold">
        아직 그려지지 않은 페이지예요.
      </h1>
      <p className="mb-8 text-sm text-zinc-500">
        주소를 확인하거나 작업실로 돌아가 주세요.
      </p>
      <Button asChild>
        <Link href="/dashboard">작업실로 돌아가기</Link>
      </Button>
    </main>
  );
}
