"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { useAuth } from "@/components/providers";
import { PageHeading } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/states";
export default function Settings() {
  const { user, config, signOut } = useAuth();
  const router = useRouter();
  const [error, setError] = useState<Error | null>(null);
  const [pending, setPending] = useState(false);
  return (
    <>
      <PageHeading
        eyebrow="YOUR WORKSPACE"
        title="계정 설정"
        description="작가 프로필과 로그인 상태를 확인하세요."
      />
      <section className="max-w-xl rounded-2xl border border-zinc-200 bg-white p-7">
        <div className="mb-6 flex items-center gap-4">
          <span className="flex size-14 items-center justify-center rounded-2xl bg-violet-50 text-xl font-bold text-violet-600">
            {user?.display_name[0]}
          </span>
          <div>
            <h2 className="font-bold">{user?.display_name}</h2>
            <p className="mt-1 text-sm text-zinc-400">{user?.email}</p>
          </div>
        </div>
        <dl className="mb-7 space-y-4 border-y border-zinc-100 py-6 text-sm">
          <div className="flex justify-between">
            <dt className="text-zinc-400">로그인 방식</dt>
            <dd>
              {config?.auth_mode === "local"
                ? "로컬 개발 계정"
                : "Supabase Auth"}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-zinc-400">작업실</dt>
            <dd>개인 작업실</dd>
          </div>
        </dl>
        {error && <ErrorState error={error} />}
        <Button
          variant="outline"
          disabled={pending}
          onClick={async () => {
            setPending(true);
            try {
              await signOut();
              router.replace("/login");
            } catch (err) {
              setError(err as Error);
            } finally {
              setPending(false);
            }
          }}
        >
          <LogOut />
          로그아웃
        </Button>
      </section>
    </>
  );
}
