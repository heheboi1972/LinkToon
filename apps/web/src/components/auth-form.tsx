"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight } from "lucide-react";
import { Logo } from "@/components/shell";
import { useAuth } from "@/components/providers";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ErrorState, Loading } from "@/components/states";

export function AuthForm({ signup = false }: { signup?: boolean }) {
  const auth = useAuth();
  const router = useRouter();
  const [error, setError] = useState<Error | null>(null);
  const [pending, setPending] = useState(false);
  const [confirmation, setConfirmation] = useState(false);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setPending(true);
    const data = new FormData(event.currentTarget);
    try {
      if (signup) {
        const active = await auth.signUp(
          String(data.get("email")),
          String(data.get("password")),
          String(data.get("name")),
        );
        if (!active) {
          setConfirmation(true);
          return;
        }
      } else
        await auth.signIn(
          String(data.get("email")),
          String(data.get("password")),
        );
      router.push("/dashboard");
    } catch (err) {
      setError(err as Error);
    } finally {
      setPending(false);
    }
  }
  return (
    <main className="grid min-h-screen lg:grid-cols-2">
      <section className="relative hidden overflow-hidden bg-[#221b42] p-12 text-white lg:flex lg:flex-col">
        <Logo light />
        <div className="my-auto">
          <img
            src="/studio-art.svg"
            alt="달빛 도시 웹툰 아트"
            className="mx-auto w-full max-w-xl"
          />
          <div className="mx-auto max-w-md">
            <h2 className="text-3xl font-bold leading-snug">
              모든 멋진 이야기는
              <br />
              작은 상상에서 시작되니까.
            </h2>
            <p className="mt-4 text-sm text-violet-200/60">
              당신만의 세계를 LinkToon에서 펼쳐 보세요.
            </p>
          </div>
        </div>
        <span className="text-xs text-violet-300/50">
          CREATE YOUR WORLD. ONE PANEL AT A TIME.
        </span>
      </section>
      <section className="flex items-center justify-center bg-white px-6 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-12 lg:hidden">
            <Logo />
          </div>
          <p className="mb-3 text-xs font-bold tracking-[.18em] text-violet-500">
            WELCOME TO LINKTOON
          </p>
          <h1 className="text-3xl font-bold tracking-tight">
            {signup ? "새로운 이야기를 시작해요" : "다시 만나서 반가워요"}
          </h1>
          <p className="mb-8 mt-3 text-sm text-zinc-500">
            {signup
              ? "나만의 웹툰 작업실을 만들어 보세요."
              : "이어서 당신의 세계를 만들어 볼까요?"}
          </p>
          {auth.loading ? (
            <Loading label="인증 설정을 확인하는 중" />
          ) : auth.error ? (
            <ErrorState error={auth.error} retry={() => location.reload()} />
          ) : confirmation ? (
            <div
              role="status"
              className="rounded-xl bg-violet-50 p-6 text-sm leading-7 text-violet-800"
            >
              이메일로 인증 링크를 보냈습니다. 메일의 링크를 누른 뒤 로그인해
              주세요.
              <Link className="mt-4 block font-bold underline" href="/login">
                로그인으로 이동
              </Link>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-5">
              {signup && (
                <label className="field-label">
                  작가 이름
                  <Input
                    name="name"
                    placeholder="어떻게 불러드릴까요?"
                    autoComplete="nickname"
                    required
                    maxLength={80}
                  />
                </label>
              )}
              <label className="field-label">
                이메일
                <Input
                  name="email"
                  type="email"
                  placeholder="you@example.com"
                  autoComplete="email"
                  required
                />
              </label>
              <label className="field-label">
                비밀번호
                <Input
                  name="password"
                  type="password"
                  placeholder={
                    signup
                      ? "10자 이상 입력해 주세요"
                      : "비밀번호를 입력해 주세요"
                  }
                  autoComplete={signup ? "new-password" : "current-password"}
                  minLength={signup ? 10 : 1}
                  maxLength={128}
                  required
                />
              </label>
              {error && <ErrorState error={error} />}
              <Button type="submit" className="w-full" disabled={pending}>
                {pending
                  ? "잠시만 기다려 주세요"
                  : signup
                    ? "작업실 만들기"
                    : "로그인"}
                <ArrowRight />
              </Button>
              {auth.config?.auth_mode === "local" && (
                <p className="rounded-lg bg-zinc-50 p-3 text-center text-[11px] leading-5 text-zinc-500">
                  로컬 개발 모드 · 계정과 파일은 이 개발 환경에 저장됩니다.
                </p>
              )}
            </form>
          )}
          <p className="mt-8 text-center text-sm text-zinc-500">
            {signup ? "이미 계정이 있나요? " : "처음 방문하셨나요? "}
            <Link
              className="font-semibold text-violet-600"
              href={signup ? "/login" : "/signup"}
            >
              {signup ? "로그인" : "회원가입"}
            </Link>
          </p>
        </div>
      </section>
    </main>
  );
}
