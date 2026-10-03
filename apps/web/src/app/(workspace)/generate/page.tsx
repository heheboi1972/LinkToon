import Link from "next/link";
import { ImagePlus } from "lucide-react";
import { PageHeading } from "@/components/shell";
import { Button } from "@/components/ui/button";
export default function GeneratePage() {
  return (
    <>
      <PageHeading
        eyebrow="IMAGE STUDIO"
        title="머릿속 장면을 꺼내는 곳"
        description="AI 이미지는 프로젝트 Story의 각 Scene에서 생성하고 다시 만들 수 있습니다."
      />
      <div className="grid overflow-hidden rounded-2xl border border-zinc-200 bg-white md:grid-cols-2">
        <img
          src="/studio-art.svg"
          alt="웹툰 장면 예시 일러스트"
          className="w-full bg-[#ede8f5]"
        />
        <div className="flex flex-col items-start justify-center p-8">
          <ImagePlus className="mb-5 size-8 text-violet-500" />
          <h2 className="text-xl font-bold">Story Scene에서 이미지 만들기</h2>
          <p className="mb-6 mt-4 text-sm leading-7 text-zinc-500">
            프로젝트의 Story를 생성한 뒤 각 Scene에서 AI 이미지를 만들거나
            다시 생성할 수 있어요. 직접 만든 이미지는 보관함에 업로드하세요.
          </p>
          <Button asChild>
            <Link href="/projects">내 프로젝트 열기</Link>
          </Button>
        </div>
      </div>
    </>
  );
}
