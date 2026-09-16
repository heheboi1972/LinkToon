import Link from "next/link";
import { ArrowRight, Layers, ImagePlus, BookOpen } from "lucide-react";
import { Logo } from "@/components/shell";
import { Button } from "@/components/ui/button";
export default function Landing() {
  return (
    <main className="min-h-screen bg-[#faf9fe]">
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-6 py-7">
        <Logo />
        <div className="flex items-center gap-2">
          <Button asChild variant="ghost">
            <Link href="/login">로그인</Link>
          </Button>
          <Button asChild>
            <Link href="/signup">무료로 시작하기</Link>
          </Button>
        </div>
      </nav>
      <section className="mx-auto grid max-w-6xl items-center gap-4 px-6 pb-16 pt-12 lg:grid-cols-2 lg:pt-20">
        <div>
          <span className="rounded-full border border-violet-200 bg-violet-50 px-3 py-1.5 text-[11px] font-semibold text-violet-600">
            A NEW CHAPTER OF CREATIVITY
          </span>
          <h1 className="mb-6 mt-7 text-5xl font-extrabold leading-[1.25] tracking-tight sm:text-6xl">
            당신의 이야기,
            <br />
            <span className="text-violet-600">장면이 되다.</span>
          </h1>
          <p className="max-w-md text-base leading-8 text-zinc-500">
            작은 아이디어부터 나만의 세계까지.
            <br />
            이야기를 정리하고, 이미지를 모으고, 웹툰의 첫 장면을 만들어 보세요.
          </p>
          <Button asChild size="lg" className="mt-8">
            <Link href="/signup">
              나의 첫 웹툰 만들기 <ArrowRight />
            </Link>
          </Button>
          <p className="mt-4 text-xs text-zinc-400">
            당신의 상상에서 시작하는 나만의 작업실
          </p>
        </div>
        <img
          src="/studio-art.svg"
          alt="달빛 아래 도시를 바라보는 인물이 담긴 웹툰 일러스트"
          className="w-full"
        />
      </section>
      <section className="mx-auto grid max-w-6xl gap-5 px-6 pb-20 md:grid-cols-3">
        {[
          {
            icon: BookOpen,
            title: "이야기를 위한 공간",
            text: "프로젝트마다 장르와 스타일을 정하고, 나만의 이야기 설정을 보관하세요.",
          },
          {
            icon: Layers,
            title: "한 장면씩, 차근차근",
            text: "에피소드를 나누고 패널을 더하며 머릿속 이야기를 구체화하세요.",
          },
          {
            icon: ImagePlus,
            title: "흩어진 영감을 한곳에",
            text: "직접 그린 이미지와 레퍼런스를 업로드하고 패널에 연결하세요.",
          },
        ].map(({ icon: Icon, title, text }) => (
          <div
            key={title}
            className="rounded-2xl border border-zinc-200/80 bg-white p-7"
          >
            <Icon className="mb-5 size-6 text-violet-500" />
            <h2 className="mb-2 font-bold">{title}</h2>
            <p className="text-sm leading-6 text-zinc-500">{text}</p>
          </div>
        ))}
      </section>
    </main>
  );
}
