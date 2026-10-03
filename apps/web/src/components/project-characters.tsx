"use client";

import Image from "next/image";
import { useCallback, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LoaderCircle, Save, Sparkles, Trash2 } from "lucide-react";
import {
  ApiError,
  api,
  clearCharacterReference,
  createCharacter,
  createCharacterReferenceGeneration,
  deleteCharacter,
  listProjectCharacters,
  selectCharacterReference,
  updateCharacter,
} from "@/lib/api";
import type { Asset, CharacterCreateInput, CharacterSummary } from "@/lib/types";
import { mediaUrl } from "@/lib/api";
import {
  forgetGenerationJob,
  rememberGenerationJob,
  terminalGenerationStatuses,
  useGenerationJob,
  useRememberedGenerationJob,
} from "@/lib/generation-job";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";

type Form = CharacterCreateInput;

const blank: Form = {
  name: "",
  description: "",
  age_range: "",
  face_description: "",
  hair_description: "",
  eye_description: "",
  clothing: "",
  visual_style: "",
};

function CharacterCard({
  character,
  projectId,
  userId,
  assets,
  refresh,
}: {
  character: CharacterSummary;
  projectId: string;
  userId: string;
  assets: Asset[];
  refresh: () => void;
}) {
  const [form, setForm] = useState<Form>({
    ...blank,
    name: character.name,
    description: character.description,
    appearance: character.appearance,
    personality: character.personality,
    clothing: character.clothing,
    age_range: String(character.character_bible?.age_range || ""),
    face_description: String(character.character_bible?.face_description || ""),
    hair_description: String(character.character_bible?.hair_description || ""),
    eye_description: String(character.character_bible?.eye_description || ""),
    visual_style: String(character.character_bible?.visual_style || ""),
  });
  const [selectedAsset, setSelectedAsset] = useState("");
  const queryClient = useQueryClient();
  const scope = `linktoon-character-reference-job:${userId}:${character.id}`;
  const storedJobId = useRememberedGenerationJob(scope);
  const job = useGenerationJob({
    queryKey: ["character-reference-job", userId, character.id, storedJobId],
    jobId: storedJobId,
    validate: (value) =>
      value.project_id === projectId &&
      value.job_type === "character:reference" &&
      value.input.character_id === character.id,
  });
  useEffect(() => {
    if (job.data?.status === "succeeded") {
      void queryClient.invalidateQueries({ queryKey: ["characters", projectId] });
      forgetGenerationJob(scope);
      refresh();
    }
    if (job.data && terminalGenerationStatuses.has(job.data.status) && job.data.status !== "succeeded")
      forgetGenerationJob(scope);
  }, [job.data, projectId, queryClient, refresh, scope]);
  const save = useMutation({
    mutationFn: () => updateCharacter(character.id, form),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: () => deleteCharacter(character.id),
    onSuccess: refresh,
  });
  const generate = useMutation({
    mutationFn: () => createCharacterReferenceGeneration(character.id, crypto.randomUUID()),
    onSuccess: (accepted) => rememberGenerationJob(scope, accepted.job_id, ""),
  });
  const choose = useMutation({
    mutationFn: (assetId: string) => selectCharacterReference(character.id, assetId),
    onSuccess: refresh,
  });
  const clear = useMutation({
    mutationFn: () => clearCharacterReference(character.id),
    onSuccess: refresh,
  });
  const pending = save.isPending || remove.isPending || generate.isPending || choose.isPending || clear.isPending;
  return (
    <article className="rounded-2xl border border-zinc-200 bg-white p-5">
      <div className="flex gap-4">
        {character.reference_media_url ? (
          <Image unoptimized src={mediaUrl(character.reference_media_url) || ""} alt={`${character.name} 기준 이미지`} width={96} height={120} className="size-24 rounded-xl object-cover" />
        ) : (
          <div className="flex size-24 items-center justify-center rounded-xl bg-violet-50 text-xs text-violet-500">기준 이미지 없음</div>
        )}
        <div className="min-w-0 flex-1">
          <h3 className="font-bold">{character.name}</h3>
          <p className="mt-1 text-xs text-zinc-500">revision {character.character_revision || 1}</p>
          {character.reference_stale && <p className="mt-2 text-xs font-semibold text-amber-600">캐릭터 정보가 바뀌어 기준 이미지 업데이트가 필요합니다.</p>}
        </div>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        <Input aria-label="캐릭터 이름" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <Input aria-label="나이대" placeholder="나이대" value={form.age_range || ""} onChange={(e) => setForm({ ...form, age_range: e.target.value })} />
        <Textarea aria-label="얼굴 설명" placeholder="얼굴 특징" value={form.face_description || ""} onChange={(e) => setForm({ ...form, face_description: e.target.value })} />
        <Textarea aria-label="헤어스타일 설명" placeholder="머리카락과 헤어스타일" value={form.hair_description || ""} onChange={(e) => setForm({ ...form, hair_description: e.target.value })} />
        <Textarea aria-label="눈 설명" placeholder="눈과 표정" value={form.eye_description || ""} onChange={(e) => setForm({ ...form, eye_description: e.target.value })} />
        <Textarea aria-label="기본 의상" placeholder="기본 의상" value={form.clothing || ""} onChange={(e) => setForm({ ...form, clothing: e.target.value })} />
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button type="button" size="sm" disabled={pending || !form.name.trim()} onClick={() => save.mutate()}><Save /> 저장</Button>
        <Button type="button" size="sm" variant="outline" disabled={pending} onClick={() => generate.mutate()}><Sparkles /> 기준 이미지 생성</Button>
        {character.reference_asset_id && <Button type="button" size="sm" variant="ghost" disabled={pending} onClick={() => clear.mutate()}>기준 이미지 해제</Button>}
        <Button type="button" size="sm" variant="destructive" disabled={pending} onClick={() => { if (window.confirm("이 캐릭터를 삭제할까요?")) remove.mutate(); }}><Trash2 /> 삭제</Button>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <select aria-label="기존 이미지 선택" className="h-9 rounded-xl border border-zinc-200 bg-white px-2 text-xs" value={selectedAsset} onChange={(e) => setSelectedAsset(e.target.value)}>
          <option value="">업로드한 이미지에서 선택</option>
          {assets.filter((asset) => asset.mime_type?.startsWith("image/")).map((asset) => <option key={asset.id} value={asset.id}>{asset.metadata.filename || asset.id}</option>)}
        </select>
        <Button type="button" size="sm" variant="outline" disabled={!selectedAsset || pending} onClick={() => choose.mutate(selectedAsset)}>이 이미지 사용</Button>
        {job.data && <span className="text-xs text-violet-700">{job.data.status === "succeeded" ? "기준 이미지 생성 완료" : job.data.status === "failed" ? "생성 실패" : "기준 이미지 생성 중…"}</span>}
      </div>
      {(save.error || remove.error || generate.error || choose.error || clear.error || job.error) && <p role="alert" className="mt-3 text-xs text-red-700">{(save.error || remove.error || generate.error || choose.error || clear.error || job.error) instanceof ApiError ? "요청을 처리하지 못했습니다. 권한과 입력을 확인해 주세요." : "요청을 처리하지 못했습니다."}</p>}
    </article>
  );
}

export function ProjectCharacters({ projectId, userId }: { projectId: string; userId: string }) {
  const queryClient = useQueryClient();
  const characters = useQuery({ queryKey: ["characters", projectId], queryFn: () => listProjectCharacters(projectId) });
  const assets = useQuery({ queryKey: ["assets", projectId], queryFn: () => api<Asset[]>(`/projects/${projectId}/assets?limit=200`) });
  const [form, setForm] = useState<Form>(blank);
  const create = useMutation({
    mutationFn: () => createCharacter(projectId, form),
    onSuccess: () => { setForm(blank); void queryClient.invalidateQueries({ queryKey: ["characters", projectId] }); },
  });
  const refresh = useCallback(() => { void queryClient.invalidateQueries({ queryKey: ["characters", projectId] }); }, [projectId, queryClient]);
  return (
    <section className="mt-8 rounded-2xl border border-violet-100 bg-violet-50/30 p-5 sm:p-7">
      <div><p className="text-xs font-bold tracking-wider text-violet-600">CHARACTER BIBLE</p><h2 className="mt-1 text-xl font-bold">캐릭터 일관성 관리</h2><p className="mt-2 text-sm text-zinc-500">얼굴, 헤어, 의상과 스타일을 고정하고 기준 이미지를 장면 생성에 자동으로 연결합니다.</p></div>
      <form className="mt-5 grid gap-2 sm:grid-cols-[1fr_2fr_auto]" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
        <Input aria-label="새 캐릭터 이름" placeholder="이름" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <Input aria-label="새 캐릭터 설명" placeholder="짧은 설명" value={form.description || ""} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        <Button type="submit" disabled={create.isPending || !form.name.trim()}>{create.isPending ? <LoaderCircle className="animate-spin" /> : "캐릭터 추가"}</Button>
      </form>
      {create.error && <p role="alert" className="mt-3 text-sm text-red-700">캐릭터를 추가하지 못했습니다.</p>}
      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        {characters.data?.map((character) => <CharacterCard key={character.id} character={character} projectId={projectId} userId={userId} assets={assets.data || []} refresh={refresh} />)}
      </div>
    </section>
  );
}
