# 데이터베이스와 마이그레이션

주 DB는 PostgreSQL이며 Supabase의 PostgreSQL에 같은 Alembic migration을 적용할 수 있다. 외부 인프라 없이 실행할 때만 SQLite 대안을 사용한다. production 설정은 SQLite를 거부한다.

## revision 0001

`apps/api/alembic/versions/0001_v1_relational_foundation.py`는 ORM metadata를 다시 실행하는 동적 migration이 아니라 명시적인 create/drop 연산을 보존한 migration이다.

| 테이블 | 용도와 주요 관계 |
| --- | --- |
| profiles | 계정 UUID, 이메일 unique, 표시 이름, local 전용 password hash |
| projects | owner → profiles, 제목/장르/방향/제작 방식/상태/표지 |
| project_bibles | project당 1개, story/world/visual JSONB, prompt/negative 규칙 |
| characters | project 소속, 구조화 Character Bible/appearance·style lock/revision, canonical reference Asset |
| character_references | character + asset + reference type |
| episodes | project 소속, 프로젝트별 number unique |
| scenes | episode 소속, 위치와 structured script |
| panels | episode 소속, episode/position unique, image asset/대사/script/상태 |
| assets | owner/project, 파일 타입·MIME·storage key·크기·dimensions·metadata·upload 상태 |
| generation_jobs | user/project, provider/task id/input/output/progress/cost/error/timestamps |
| motion_plans | panel별 version unique, mode/analysis/plan |
| motion_layers | panel/mask asset, locked/z_index/motion_config |
| animations | panel/job, WebM/MP4/poster asset, duration/version |
| publish_versions | legacy episode/version record (현재 Publish API 미사용) |

revision 0006 이후 총 **17개 제품 테이블 + alembic_version**이다. revision 0004는 `characters.character_bible`, appearance/style lock, revision/stale 상태와 canonical `reference_asset_id`를 추가한다. revision 0005는 `scenes.video_asset_id` nullable FK/index를 추가해 최신 Motion Asset을 가리킨다. Character reference 생성은 `generation_jobs`와 immutable `assets`를 사용하고 `character_references`에 history를 남긴다.

## revision 0002

`0002_generation_job_asset_foundation.py`는 기존 테이블을 삭제하지 않고 AI 생성 파이프라인의 데이터 계층을 확장한다.

- `generation_jobs`: canonical 상태, `updated_at`, provider 원본 결과, 재시도/poll 시각, 사용자별 idempotency key, 취소 시각, worker lease를 추가한다.
- 기존 상태는 `planning → running`, `submitted/processing → provider_pending`, `postprocessing → saving`, `completed → succeeded`, `cancelled → canceled`로 보존 변환한다.
- `assets`: storage bucket, `upload/generated` source, provider/task id, generation job FK, prompt를 추가한다.
- provider 생성 성공 후 storage 저장만 재시도할 수 있도록 공개 output과 내부 `provider_output`을 분리한다.

TASK 3은 이 schema를 그대로 사용하므로 새 migration이 없다. Worker는 due 상태와 만료 lease를 조회하고 PostgreSQL에서 `FOR UPDATE SKIP LOCKED`로 한 Job을 선점한다. claim 직후 commit하며 Provider 호출 중에는 transaction을 유지하지 않는다. 만료된 lease는 다른 Worker가 회수한다.

TASK 4의 Story Provider도 schema를 변경하지 않는다. 생성 요청은 `generation_jobs`에 `story:generate`로 저장되고 OpenAI의 구조화 결과와 model/request ID/token usage metadata는 provider 결과에 보존된다. saving 단계는 다음 규칙을 적용한다.

- 성공할 때마다 프로젝트의 다음 `number`로 새 `episodes` 행을 만든다. 이미 존재하는 Episode를 덮어쓰지 않는다.
- Story 제목과 synopsis를 Episode에 매핑하고, Scene은 `position`과 structured `script`에 narration, dialogue, visual prompt, 허용된 character reference를 보존한다.
- Episode 번호 배정, 새 Episode, 모든 Scene과 Job 성공 output은 한 DB transaction으로 commit한다. 일부 Scene 저장이 실패하면 전부 rollback한다.
- 별도 `story_versions`/`StoryVersion` 테이블은 아직 없다. 현재 버전 보존 단위는 새 Episode다.

## revision 0003

`0003_scene_image_asset.py`는 `scenes.image_asset_id` nullable FK와 index를 추가한다. FK는 `assets.id`를 가리키며 Asset 삭제 시 `SET NULL`이다. Scene 이미지 성공 시 새 generated Asset을 만들고 이 컬럼을 최신 Asset으로 갱신한다. 재생성은 기존 Asset row와 object를 삭제하지 않으므로 프로젝트 Asset 목록이 자연스러운 생성 이력을 보존한다.

`0005_scene_video_asset.py`는 같은 삭제 정책으로 `scenes.video_asset_id`를 추가한다. Motion 재생성은 이 pointer만 최신 immutable MP4 Asset으로 바꾸며 과거 video Asset과 Storage object는 보존한다.

## revision 0006 — Publication snapshot

`0006_publication_snapshots.py`는 `publications`, `publication_snapshots`, `publication_scenes`를 추가한다. Episode당 하나의 Publication과 안정적인 unique slug를 가지며 visibility는 `private`, `unlisted`, `public`이다. 상태는 `published`/`unpublished`; 다시 게시할 때 `current_version`을 올리고 새 snapshot과 Scene row를 추가한다. 기존 version의 row는 API에서 수정하지 않는다.

각 snapshot은 당시 Episode 제목/설명과 순서가 고정된 Scene title, narration, 정제된 dialogue, image/video Asset ID를 저장한다. Prompt, Character ID, GenerationJob, provider output, storage key는 복사하지 않는다. snapshot Scene의 asset FK는 `ON DELETE RESTRICT`이며 API도 사용 중인 모든 버전 Asset 삭제를 409로 거부한다. 따라서 Scene에서 새 이미지/Motion을 연결해도 기존 공개본은 이전 Asset을 계속 읽고, 변경은 명시적 다시 게시 후 반영된다. Asset bucket은 계속 private다.

Image Provider의 normalized 결과는 Storage 저장 전에 `generation_jobs.provider_output`에 commit한다. 현재 OpenAI Image API가 반환하는 bounded base64를 이 durable JSON에 저장하므로 Worker/Render 재시작 뒤 `saving`부터 복구할 수 있다. 생성 Asset ID는 `uuid5(job_id, artifact position)`, Storage key는 `users/{user_id}/projects/{project_id}/generated/{asset_id}.{ext}`로 결정한다. 업로드 성공 후 DB insert가 실패해도 재시도는 같은 object를 사용하고, 기존 object의 bytes가 다르면 실패시킨다.

모든 primary key는 UUID다. 소유자, parent FK, 최근 프로젝트/작업 정렬, provider task id에 index를 둔다. Project Bible과 episode 번호, panel 위치, motion/publish 버전은 unique constraint로 보호한다. status/orientation/mode/reference type/asset size/progress에는 check constraint가 있다. JSON column은 PostgreSQL JSONB, SQLite JSON으로 매핑된다.

부모 삭제는 관계에 따라 CASCADE, 편집 중 선택적인 asset 참조는 SET NULL이다. API는 Panel/Scene/Character/Publication snapshot에서 사용 중인 Asset 삭제를 거부한다. 패널에서 이미지를 연결 해제하면 상태를 empty로 변경한다. 표지 FK는 projects/assets 순환 관계 때문에 PostgreSQL에서 양쪽 테이블을 생성한 뒤 추가한다.

`profiles.id`는 Supabase 모드에서 검증된 Auth 사용자 UUID와 동일하다. standalone Postgres와 로컬 인증도 지원해야 하므로 Alembic 자체는 Supabase 전용 `auth.users`에 FK를 만들지 않는다. Supabase 계정 삭제/탈퇴 동기화는 아직 UI에 없다.

## 명령

항상 `apps/api` 디렉터리에서 실행한다.

```powershell
uv run python -m alembic upgrade head
uv run python -m alembic current
uv run python -m alembic check
uv run python -m alembic revision --autogenerate -m "describe change"
```

`downgrade base`는 모든 제품 테이블을 제거하므로 disposable test DB에서만 실행한다. 자동 테스트는 매번 새 DB/임시 DB를 생성하고 실제 migration을 적용한다. PostgreSQL 테스트는 UUID로 명명한 전용 DB를 만든 뒤 그 DB만 제거한다. 사용자 DB의 기존 테이블은 삭제하지 않는다.

PostgreSQL URL은 `postgresql+psycopg://user:password@host:5432/database`다. 네이티브 DLL을 제한하는 Windows 환경에서는 동일한 SQLAlchemy 모델로 `postgresql+pg8000://...`를 사용할 수 있다. pg8000은 순수 Python driver로 의존성에 포함되어 있다. Supabase에서는 제공되는 direct/session-pool connection string에 driver와 필요 시 `sslmode=require`를 적용한다. pg8000의 SSL 설정은 해당 드라이버 연결 옵션에 맞춰 별도로 지정한다.

## Supabase RLS

API의 ownership 검사는 모든 모드에서 적용된다. Supabase REST로 직접 읽을 때도 계정 간 데이터가 섞이지 않도록 아래 RLS를 적용한다. Publication 테이블도 owner read policy를 갖고 anonymous role에는 direct SELECT를 열지 않는다. Public Reader와 media capability는 FastAPI가 활성 public/unlisted snapshot에 포함된 Asset을 검증한 뒤 제공한다. browser role의 direct INSERT/UPDATE/DELETE는 부여하지 않으며 쓰기는 FastAPI service를 거친다. `password_hash`는 authenticated role에도 SELECT 권한을 주지 않는다. `service_role`과 migration용 postgres 연결은 backend 전용이다.

전용 Supabase 프로젝트에서 migration 후 SQL Editor로 [실행 파일](../scripts/supabase-rls.sql)을 적용한다. 아래 SQL은 동일한 내용이다. 기본 bucket 이름을 바꾸었다면 SQL의 `linktoon-private`도 동일하게 변경한다. 기존에 넓게 열린 storage.objects policy가 있는 공용 bucket을 재사용하지 않는다.

```sql
-- Run after Alembic on a dedicated Supabase project (SQL Editor, postgres role).
-- All writes go through FastAPI, preserving ownership + asset validation invariants.
BEGIN;

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'profiles','projects','project_bibles','characters','character_references',
    'episodes','scenes','panels','assets','motion_plans','motion_layers',
    'animations','generation_jobs','publish_versions'
  ] LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('REVOKE ALL ON public.%I FROM anon, authenticated', table_name);
    EXECUTE format('GRANT ALL ON public.%I TO service_role', table_name);
    IF table_name <> 'profiles' THEN
      EXECUTE format('GRANT SELECT ON public.%I TO authenticated', table_name);
    END IF;
  END LOOP;
END $$;

-- Never grant password_hash to the browser role.
GRANT SELECT (id, email, display_name, created_at, updated_at)
ON public.profiles TO authenticated;

DROP POLICY IF EXISTS profiles_owner_read ON public.profiles;
CREATE POLICY profiles_owner_read ON public.profiles FOR SELECT TO authenticated
USING (id = (SELECT auth.uid()));

DROP POLICY IF EXISTS projects_owner_read ON public.projects;
CREATE POLICY projects_owner_read ON public.projects FOR SELECT TO authenticated
USING (owner_id = (SELECT auth.uid()));

DROP POLICY IF EXISTS assets_owner_read ON public.assets;
CREATE POLICY assets_owner_read ON public.assets FOR SELECT TO authenticated
USING (owner_id = (SELECT auth.uid()) AND EXISTS (
  SELECT 1 FROM public.projects p WHERE p.id = assets.project_id AND p.owner_id = (SELECT auth.uid())
));

DROP POLICY IF EXISTS jobs_owner_read ON public.generation_jobs;
CREATE POLICY jobs_owner_read ON public.generation_jobs FOR SELECT TO authenticated
USING (user_id = (SELECT auth.uid()) AND EXISTS (
  SELECT 1 FROM public.projects p WHERE p.id = generation_jobs.project_id
  AND p.owner_id = (SELECT auth.uid())
));

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['project_bibles','characters','episodes'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS owner_read ON public.%I', table_name);
    EXECUTE format(
      'CREATE POLICY owner_read ON public.%I FOR SELECT TO authenticated USING
       (EXISTS (SELECT 1 FROM public.projects p WHERE p.id = %I.project_id
       AND p.owner_id = (SELECT auth.uid())))', table_name, table_name);
  END LOOP;
  FOREACH table_name IN ARRAY ARRAY['scenes','panels','publish_versions'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS owner_read ON public.%I', table_name);
    EXECUTE format(
      'CREATE POLICY owner_read ON public.%I FOR SELECT TO authenticated USING
       (EXISTS (SELECT 1 FROM public.episodes e JOIN public.projects p ON p.id = e.project_id
       WHERE e.id = %I.episode_id AND p.owner_id = (SELECT auth.uid())))', table_name, table_name);
  END LOOP;
  FOREACH table_name IN ARRAY ARRAY['motion_plans','motion_layers','animations'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS owner_read ON public.%I', table_name);
    EXECUTE format(
      'CREATE POLICY owner_read ON public.%I FOR SELECT TO authenticated USING
       (EXISTS (SELECT 1 FROM public.panels pn JOIN public.episodes e ON e.id = pn.episode_id
       JOIN public.projects p ON p.id = e.project_id WHERE pn.id = %I.panel_id
       AND p.owner_id = (SELECT auth.uid())))', table_name, table_name);
  END LOOP;
END $$;

DROP POLICY IF EXISTS owner_read ON public.character_references;
CREATE POLICY owner_read ON public.character_references FOR SELECT TO authenticated
USING (EXISTS (
  SELECT 1 FROM public.characters c JOIN public.projects p ON p.id = c.project_id
  WHERE c.id = character_references.character_id AND p.owner_id = (SELECT auth.uid())
));

-- Object writes/reads use the backend service role after application validation.
-- Do not create a public bucket or broad storage.objects policies for this bucket.
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('linktoon-private', 'linktoon-private', false, 10485760,
        ARRAY['image/png','image/jpeg','image/webp'])
ON CONFLICT (id) DO UPDATE SET public = false, file_size_limit = 10485760,
  allowed_mime_types = ARRAY['image/png','image/jpeg','image/webp'];

COMMIT;

```

Phase 1에는 익명 Reader가 없다. anonymous SELECT 정책을 열지 않는다. Phase 2에서는 현재 publish snapshot에 대해서만 공개 Reader 접근을 추가하고 편집 원본과 소유자 자산은 계속 비공개로 유지한다.

## 파일 보존과 정리

사용자 업로드 Asset의 storage key는 `owner_uuid/project_uuid/asset_uuid`이고 생성 Asset은 `users/{owner_uuid}/projects/{project_uuid}/generated/{asset_uuid}.{ext}`다. 원본 교체와 이미지 재생성은 새 key를 만든다. 프로젝트 삭제 시 metadata와 접근 권한은 DB cascade로 제거되지만 외부 Storage와 DB를 원자적으로 삭제할 수는 없다. 24시간이 지난 orphan 파일은 다음 도구로 확인한 뒤 정리할 수 있다.

```powershell
cd apps/api
uv run python ../../scripts/cleanup-assets.py
# 위 출력에서 대상 확인 후에만 실행
uv run python ../../scripts/cleanup-assets.py --apply
```

기본은 dry-run이다. UUID 경로가 아닌 파일, DB에 남아 있는 Asset, 최근 파일은 제외한다. local root와 전용 Supabase bucket을 지원한다. 업로드 미완료 pending row는 원본 유실 방지를 위해 이 정리 작업에서 자동 제거하지 않는다.
