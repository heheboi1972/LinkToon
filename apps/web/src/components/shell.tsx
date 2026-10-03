"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  BookOpen,
  ChevronsUpDown,
  Clapperboard,
  Eye,
  FolderOpen,
  LayoutGrid,
  Menu,
  Plus,
  Send,
  Settings,
  Sparkles,
  Users,
  Waypoints,
  X,
} from "lucide-react";
import { useAuth } from "@/components/providers";
import { ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { useUI } from "@/lib/store";
import { cn } from "@/lib/utils";

export function Logo({ light = false }: { light?: boolean }) {
  return (
    <Link
      href="/dashboard"
      className={cn(
        "flex items-center gap-2.5 text-xl font-extrabold tracking-tight",
        light && "text-white",
      )}
      aria-label="LinkToon 대시보드"
    >
      <span className="flex size-9 items-center justify-center rounded-xl bg-violet-600 text-white">
        <Clapperboard className="size-5" />
      </span>
      LinkToon<span className="self-start text-violet-500">.</span>
    </Link>
  );
}

const navigation = [
  { href: "/dashboard", label: "내 작업실", icon: LayoutGrid },
  { href: "/projects", label: "프로젝트", icon: FolderOpen },
  { href: "/generate", label: "이미지 스튜디오", icon: Sparkles },
  { href: "/jobs", label: "생성 작업", icon: Activity },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const { user, loading, error } = useAuth();
  const router = useRouter();
  const path = usePathname();
  const { sidebarOpen, setSidebarOpen } = useUI();
  useEffect(() => {
    if (!loading && !user && !error) router.replace("/login");
  }, [loading, user, error, router]);
  if (loading) return <Loading />;
  if (error)
    return (
      <main className="mx-auto max-w-xl p-8">
        <Logo />
        <ErrorState error={error} retry={() => location.reload()} />
      </main>
    );
  if (!user) return <Loading label="로그인 화면으로 이동 중" />;
  return (
    <div className="min-h-screen bg-[#f8f9fc]">
      {sidebarOpen && (
        <button
          aria-label="메뉴 닫기"
          className="fixed inset-0 z-30 bg-black/30 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <aside
        id="workspace-sidebar"
        aria-label="작업실 메뉴"
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-zinc-200/70 bg-white px-5 py-7 transition-transform lg:visible lg:translate-x-0",
          sidebarOpen ? "visible translate-x-0" : "invisible -translate-x-full",
        )}
      >
        <div className="flex items-center justify-between px-2">
          <Logo />
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            aria-label="메뉴 닫기"
            onClick={() => setSidebarOpen(false)}
          >
            <X />
          </Button>
        </div>
        <div className="mb-7 mt-9 flex items-center gap-3 rounded-xl border border-zinc-200 p-3">
          <span className="flex size-8 items-center justify-center rounded-lg bg-orange-100 text-xs font-bold text-orange-700">
            {user.display_name[0]}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-semibold">
              {user.display_name}의 작업실
            </p>
            <p className="mt-0.5 text-[10px] text-zinc-400">
              Personal workspace
            </p>
          </div>
          <ChevronsUpDown className="size-3 text-zinc-400" />
        </div>
        <p className="mb-3 px-3 text-[10px] font-semibold tracking-[.15em] text-zinc-400">
          WORKSPACE
        </p>
        <nav aria-label="주 메뉴" className="space-y-1.5">
          {navigation.map(({ href, label, icon: Icon }) => (
            <Link
              onClick={() => setSidebarOpen(false)}
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-xl px-3 py-3 text-[13px] font-medium transition-colors",
                (href === "/projects" ? path.startsWith(href) : path === href)
                  ? "bg-violet-50 text-violet-700"
                  : "text-zinc-500 hover:bg-zinc-50 hover:text-zinc-900",
              )}
            >
              <Icon className="size-[18px]" />
              {label}
              {href === "/generate" && (
                <span className="ml-auto rounded bg-violet-100 px-1 text-[9px] text-violet-500">
                  AI
                </span>
              )}
            </Link>
          ))}
        </nav>
        <div className="mt-auto space-y-5 pt-10">
          <div className="rounded-2xl bg-[#f6f4fd] p-4">
            <span className="text-[10px] font-bold tracking-wider text-violet-600">
              YOUR STORY STARTS HERE
            </span>
            <p className="mb-3 mt-2 text-xs leading-5 text-zinc-600">
              머릿속 이야기를
              <br />첫 번째 장면으로 만들어 보세요.
            </p>
            <Link
              href="/projects/new"
              onClick={() => setSidebarOpen(false)}
              className="flex items-center gap-1 text-xs font-semibold text-violet-700"
            >
              새 프로젝트 만들기 <ArrowUpRight className="size-3.5" />
            </Link>
          </div>
          <Link
            href="/settings"
            onClick={() => setSidebarOpen(false)}
            className="flex items-center gap-3 px-3 text-sm text-zinc-500"
          >
            <Settings className="size-4" />
            설정
          </Link>
          <div className="border-t border-zinc-100 pt-4">
            <Link href="/settings" className="flex items-center gap-3 px-2">
              <span className="flex size-9 items-center justify-center rounded-full bg-zinc-100 text-sm font-semibold">
                {user.display_name[0]}
              </span>
              <div className="min-w-0">
                <p className="truncate text-xs font-semibold">
                  {user.display_name}
                </p>
                <p className="mt-1 truncate text-[10px] text-zinc-400">
                  {user.email}
                </p>
              </div>
            </Link>
          </div>
        </div>
      </aside>
      <div className="lg:pl-60">
        <header className="flex h-[76px] items-center justify-between border-b border-zinc-200/60 bg-white/80 px-5 sm:px-9">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              className="lg:hidden"
              aria-label="메뉴 열기"
              aria-expanded={sidebarOpen}
              aria-controls="workspace-sidebar"
              onClick={() => setSidebarOpen(true)}
            >
              <Menu />
            </Button>
            <span className="text-xs text-zinc-400">
              Workspace <span className="mx-3 text-zinc-300">/</span>
              <span className="font-medium text-zinc-700">
                {navigation.find((item) => path.startsWith(item.href))?.label ||
                  "프로젝트"}
              </span>
            </span>
          </div>
          <Button asChild size="sm" className="rounded-lg">
            <Link href="/projects/new">
              <Plus />새 프로젝트
            </Link>
          </Button>
        </header>
        <ProjectWorkspaceNav pathname={path} />
        <main className="mx-auto max-w-[1440px] px-5 py-8 sm:px-9 lg:px-11 lg:py-10">
          {children}
        </main>
        <footer className="px-9 py-8 text-[10px] text-zinc-400">
          © 2026 LinkToon · Every panel, a possibility.
        </footer>
      </div>
    </div>
  );
}

function ProjectWorkspaceNav({ pathname }: { pathname: string }) {
  const projectMatch = pathname.match(/^\/projects\/([^/]+)/);
  const episodeMatch = pathname.match(/^\/projects\/[^/]+\/episodes\/([^/]+)/);
  if (!projectMatch || pathname.includes("/read")) return null;
  const projectId = projectMatch[1];
  const episodeId = episodeMatch?.[1];
  const base = `/projects/${projectId}`;
  const items = [
    {
      href: base,
      label: "Overview",
      icon: LayoutGrid,
      active: pathname === base,
    },
    {
      href: `${base}/story`,
      label: "Story",
      icon: BookOpen,
      active: pathname.startsWith(`${base}/story`),
    },
    {
      href: `${base}/characters`,
      label: "Characters",
      icon: Users,
      active: pathname.startsWith(`${base}/characters`),
    },
    {
      href: `${base}/story#scenes`,
      label: "Scenes",
      icon: Waypoints,
      active: pathname.startsWith(`${base}/episodes`),
    },
    {
      href: episodeId
        ? `${base}/episodes/${episodeId}/read`
        : `${base}#episodes`,
      label: "Reader",
      icon: Eye,
      active: Boolean(episodeId && pathname.endsWith("/read")),
    },
    {
      href: episodeId
        ? `${base}/episodes/${episodeId}/publish`
        : `${base}#episodes`,
      label: "Publish",
      icon: Send,
      active: pathname.endsWith("/publish"),
    },
  ];
  return (
    <nav
      aria-label="프로젝트 메뉴"
      className="mx-auto flex max-w-[1440px] gap-1 overflow-x-auto border-b border-zinc-200/70 px-5 sm:px-9 lg:px-11"
    >
      {items.map(({ href, label, icon: Icon, active }) => (
        <Link
          key={label}
          href={href}
          aria-current={active ? "page" : undefined}
          className={cn(
            "relative inline-flex min-h-12 shrink-0 items-center gap-2 border-b-2 px-3 text-xs font-semibold transition-colors",
            active
              ? "border-violet-400 bg-violet-50/70 text-violet-600"
              : "border-transparent text-zinc-500 hover:bg-white hover:text-zinc-900",
          )}
        >
          <Icon className="size-4" aria-hidden="true" />
          {label}
        </Link>
      ))}
    </nav>
  );
}

export function PageHeading({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow && (
          <p className="mb-2 text-[10px] font-bold tracking-[.18em] text-violet-500">
            {eyebrow}
          </p>
        )}
        <h1 className="text-2xl font-bold tracking-tight text-zinc-900 sm:text-[29px]">
          {title}
        </h1>
        {description && (
          <p className="mt-2 text-sm leading-6 text-zinc-500">{description}</p>
        )}
      </div>
      {children}
    </div>
  );
}

export function ConfirmDelete({
  label,
  onDelete,
  pending,
}: {
  label: string;
  onDelete: () => void;
  pending: boolean;
}) {
  const [confirm, setConfirm] = useState(false);
  return confirm ? (
    <div
      role="group"
      aria-label="삭제 확인"
      className="flex flex-wrap items-center gap-2 rounded-xl bg-red-50 p-2"
    >
      <span className="px-2 text-xs text-red-700">{label} 삭제할까요?</span>
      <Button
        size="sm"
        variant="destructive"
        disabled={pending}
        onClick={onDelete}
      >
        삭제 확인
      </Button>
      <Button size="sm" variant="ghost" onClick={() => setConfirm(false)}>
        취소
      </Button>
    </div>
  ) : (
    <Button
      size="sm"
      variant="ghost"
      className="text-red-600"
      onClick={() => setConfirm(true)}
    >
      삭제
    </Button>
  );
}
