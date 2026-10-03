# LinkToon 아키텍처

## 실행 구조

```text
Browser
  Next.js App Router + TypeScript + Tailwind v4
  shadcn-compatible Radix/CVA UI + TanStack Query + Zustand
        │ same-origin /api/v1 proxy, Bearer token
        ▼
FastAPI routers (schemas + dependencies)
        ▼
WorkspaceService / AssetService / Auth service
        ▼
Ownership Repository     Storage protocol
        │                 ├─ LocalStorage (development)
SQLAlchemy 2              └─ SupabaseStorage (V1 hosted mode)
        │
PostgreSQL + Alembic
SQLite is a zero-infrastructure local/test alternative.
```

`apps/web`에는 공통 API client, 인증 provider, Query cache, 반응형 작업실 shell 및 페이지별 컴포넌트가 있다. UI 상태(사이드바, 카드/목록)는 Zustand, 서버 상태는 TanStack Query가 담당한다. API 오류·로딩·빈 상태는 공통 컴포넌트로 처리한다. 인증 변경 시 Query cache를 비운다.

프로젝트 `/story`는 기존 Bible 조회 아래에 Character Bible 관리와 Story Studio를 렌더링한다. 공통 인증 API client가 owner-scoped Character와 reference 상태를 가져오고 Character CRUD/reference Job 및 Story를 202 Job으로 접수한다. 저장된 각 Scene은 Scene이 실제 참조하는 canonical reference 상태를 표시하고 Scene/Asset API와 같은 Job polling hook을 사용한다. TanStack Query는 비종결 Job을 2초 간격으로 조회하다가 성공·실패·취소에서 멈춘다. 사용자·프로젝트·Character 또는 사용자·Scene별 `sessionStorage`에는 Job ID와 idempotency key만 저장해 같은 탭의 새로고침 후 진행 상태를 복구한다. 이미지 URL은 private Asset API에서 다시 발급받으므로 새로고침 이후에도 표시되고 10분마다 갱신된다. 브라우저는 Provider endpoint나 key를 사용하지 않는다.

`apps/api/app/routes.py`는 입출력·의존성과 목록 조회를 담당한다. 생성/수정/삭제는 서비스에 위임하고 Repository가 project ownership을 검사한다. 자식 리소스는 panel → episode → project → owner 경로를 검증한다. 다른 사용자의 ID를 지정하면 404로 응답한다. Pydantic 입력은 알 수 없는 필드를 거부한다.

인증된 `GET /api/v1/episodes/{id}/reader`는 Repository에서 소유권을 확인한 뒤 Scene을 `(position, id)` 순으로 정렬한다. Reader read model은 에피소드 제목·줄거리, 장면 제목·내레이션·대사, 같은 프로젝트에서 소유자에게 속한 ready image/video의 짧은 capability URL만 내보낸다. Prompt, private storage key, Job 및 provider 정보는 포함하지 않으며 읽기 진행은 브라우저 `localStorage`에 사용자·에피소드·scene ID 단위로 보관한다. IntersectionObserver는 가장 잘 보이는 장면을 갱신하고 capability URL은 10분마다 다시 발급한다.

Publish는 원본 Episode/Scene을 익명으로 노출하지 않는다. Owner-scoped `PublicationService`는 publish 시 current `Scene`과 공개에 필요한 필드만 `PublicationSnapshot`/`PublicationScene`으로 복사하고 ready `Asset` FK를 고정한다. 이후 원본 Scene pointer가 바뀌어도 기존 version은 그대로 유지되고 explicit republish만 `current_version`을 전진시킨다. Stable slug와 metadata/visibility는 Publication에 저장한다.

익명 `GET /api/v1/publications/{slug}`는 active public/unlisted 상태를 확인하고 최소 reader DTO만 만든다. 매 media URL은 publication/version scope가 목적에 포함된 15분 서명 token을 사용한다. Media endpoint는 매 요청 visibility/status/version을 다시 검사하고 Asset이 활성 snapshot row에서 참조되는지 확인한 뒤 private Storage에서 Range를 포함해 읽는다. Unpublish나 visibility 변경은 기존 media token을 즉시 무효화한다. Browser에는 DB ID나 storage key를 미디어 capability 없이 전달하지 않는다. Supabase RLS는 public snapshot tables의 anonymous 직접 조회를 허용하지 않는다.

Workspace UI는 shared CSS palette를 쓰며 dark neutral surface, subtle border, restrained lavender accent를 적용한다. Project metric은 `/projects/{id}/overview`에서 owner-scoped SQL count로 집계하고 mock 수치는 표시하지 않는다. `/read/{slug}`는 public metadata에서 public만 index 허용하며 unlisted는 noindex다. Private/public Reader 모두 reduced-motion 상태를 존중한다.

## 인증 모드

- `AUTH_MODE=local`: 개발 전용 계정. scrypt(salt 포함) password hash, HS256 서명·issuer·audience·만료·purpose 검증. JWT는 브라우저 로컬 저장소에 보관하며 15시간 후 재로그인이 필요하다. 로컬 로그아웃은 브라우저 토큰 제거이고 별도 서버 토큰 폐기는 없다.
- `AUTH_MODE=supabase`: 브라우저의 Supabase client가 가입·로그인·토큰 갱신을 처리한다. API는 `/auth/v1/user`로 access token을 검증하고, 동일 UUID로 profiles를 생성한다. 이메일 확인이 활성화된 경우 확인 안내 후 로그인한다. 가입 표시 이름은 인증 서비스가 검증한 user metadata에서 가져온다.
- `APP_ENV=production`: 로컬 Auth/Storage 및 SQLite를 시작 단계에서 거부한다. 배포에는 Supabase Auth/Storage, PostgreSQL, 강한 서명 secret이 필요하다.

공개 `/config`는 Auth 모드와 Supabase URL/anon key만 반환한다. anon key는 공개 클라이언트 키다. service role, local signing secret, AI provider key는 응답에 포함하지 않는다. 이 구분은 [Supabase 사용자 문서](https://supabase.com/docs/guides/auth/users)와 [서버 인증 가이드](https://supabase.com/docs/guides/auth/server-side/advanced-guide)를 따른다.

## Asset 업로드

```text
POST /assets/upload-url (authenticated + project ownership)
  -> immutable UUID/storage key + pending row + signed 15-minute ticket
PUT /assets/{id}/upload?token=...
  -> streamed size limit -> declared size/type -> Pillow verify/load
  -> storage.put(upsert=false) -> uploaded
POST /assets/complete (authenticated + ownership)
  -> ready -> 15-minute media capability URL
PATCH /panels/{id} {image_asset_id}
  -> same project + ready image required -> status=static
```

Phase 1 업로드 URL은 **API가 발급하는 제한된 업로드 capability URL**이다. Supabase native signed-upload URL로 브라우저를 직접 보내지 않는다. 이미지 바이트를 검증하기 위해 API를 경유한 뒤 private Supabase bucket에 service role로 저장한다. 로컬 개발은 Next proxy를 사용할 수 있고, Vercel 운영은 `NEXT_PUBLIC_API_URL`의 Render origin을 사용한다. capability URL의 origin은 브라우저 설정값으로 정규화하므로 API가 지정하지 않은 외부 origin으로 업로드하지 않는다.

media capability는 소유자가 조회한 뒤 공유할 수 있는 짧은 bearer URL이다. 익명에게 무제한 공개되는 public bucket이 아니다. 15분 만료, 응답은 private cache, 10분마다 UI의 URL을 갱신한다. 키/secret이 들어가는 쿼리 로그를 외부 분석 도구에 수집하지 않는다.

파일 타입은 정적 PNG/JPEG/WebP만 허용한다. SVG/HTML과 임의 파일은 받지 않는다. 이미지 포맷과 실제 디코딩, 파일 크기, 픽셀 수를 검사한다. file_size와 실제 전송량이 다르면 거부한다. 업로드 ticket은 하나의 Asset에만 사용 가능하며 이미 uploaded/ready인 row는 다시 쓸 수 없다.

에피소드/패널 삭제는 Asset 원본을 남긴다. 개별 Asset 삭제는 파일과 row를 제거하고 사용 중이면 409다. 프로젝트 삭제는 row를 cascade 삭제해 접근을 즉시 폐기한다. 프로젝트 삭제 후 남은 저장소 원본 정리는 `scripts/cleanup-assets.py`의 dry-run/apply로 수행한다. DB와 외부 객체 저장소 사이에 분산 트랜잭션은 없다.

## DB와 동시성

PostgreSQL에서 에피소드 번호는 project row, 패널 위치는 episode row를 잠근 상태로 배정한다. unique constraint가 중복을 최종 방어한다. SQLite는 간단한 로컬 작업을 위한 대안이며 PostgreSQL의 행 잠금과 동일한 동시성 보장은 하지 않는다. 충돌 시 409를 반환하고 클라이언트가 새로고침 후 재시도한다.

DB schema 자동 생성은 애플리케이션 부팅에서 수행하지 않는다. 반드시 Alembic을 적용하며 `/ready`가 DB 연결과 revision 상태를 확인한다. 표지 FK는 assets ↔ projects 순환을 고려해 PostgreSQL에서 테이블 생성 후 추가한다.

## Jobs와 AI 확장

Generation Worker는 Redis/Celery 없이 PostgreSQL의 `generation_jobs`를 queue로 사용한다. 공개 생성 입구는 Story용 `POST /api/v1/projects/{project_id}/stories/generate`, Character reference용 `POST /api/v1/characters/{character_id}/reference/generate`, Scene Image용 `POST /api/v1/scenes/{scene_id}/image/generate`, Scene Motion용 `POST /api/v1/scenes/{scene_id}/video/generate`다. Router는 입력과 `Idempotency-Key`를 받아 `GenerationService`에 위임하고 즉시 202 Job을 반환한다. Scene Image 입력은 scene ID뿐이며 service가 소유권을 확인하고 실제 Scene/Bible/Character/참조 Asset 데이터를 읽어 provider prompt와 reference Asset id를 만든다. Motion도 소유한 Scene과 ready Image Asset을 확인한 뒤 Worker가 private Storage bytes를 provider adapter에 전달한다. HTTP API 프로세스는 AI provider를 호출하지 않는다.

웹 client는 한 사용자 생성 의도에 UUID idempotency key를 발급한다. 모호한 네트워크 오류에서 같은 요청·key로 HTTP 요청을 재시도하고, 명시적 다시 생성은 새 key를 사용한다. 진행 중에는 해당 Scene 생성 버튼을 잠그며 DB의 Scene row lock과 active scope 검사도 같은 Scene의 병렬 Job을 거부한다. Scene별 상태는 독립적이다. 새 Story는 별도 draft Episode, 새 이미지는 별도 Asset이므로 기존 결과를 덮어쓰지 않는다.

현재 경로는 `Router → GenerationService → generation_jobs → DatabaseWorker → JobProcessor → ProviderRegistry → Provider`다. Worker claim transaction은 즉시 commit하고 Provider 호출 중에는 DB transaction을 열지 않는다. SDK/payload/model ID는 provider adapter에만 둔다. Production 배포에서 `OPENAI_API_KEY`, `FAL_KEY`, `RUNWAYML_API_SECRET`은 Worker에만 설정한다. API와 Worker는 Job admission 시 같은 `IMAGE_PROVIDER`, `FAL_IMAGE_MODEL`, `FAL_REFERENCE_IMAGE_MODEL` 값을 사용해 provider/model을 Job에 고정한다.

AI provider adapter는 작업을 직접 생성하지 않는다. `GenerationService.create_job`은 프로젝트 소유권을 확인하고 PostgreSQL에서 사용자 행을 잠근 뒤 UTC 일일 사용량을 검사하며, Story 10회·Image/Character 5회·Motion/Video 2회의 기본 한도 안에서만 `GenerationJob`을 만든다. 사용자별 idempotency key와 Character/Scene active scope가 중복 job을 막고 상태 전이 서비스가 허용되지 않은 전이를 409로 거부한다. `GET /api/v1/jobs/{id}`와 취소 endpoint는 Repository의 owner 조건을 통과해야 한다.

상태는 `queued → running → provider_pending → saving → succeeded`이며 동기 OpenAI Story/Image는 `provider_pending`을 건너뛴다. Provider 결과를 내부 `provider_output`에 commit한 뒤 별도 `saving` 단계로 진행한다. Image 결과는 제한된 base64와 metadata를 DB에 durable하게 보존하고, saving에서 binary/header/pixel을 재검증한 뒤 immutable Asset을 저장한다. Runway video는 임시 결과 URL만 복구용 `provider_output`에 보관하고 Worker가 MP4를 크기와 container signature로 검증한 뒤 immutable Asset에 저장한다. Asset UUID와 `users/{user}/projects/{project}/generated/{asset}.{ext}` 경로는 Job과 artifact 위치로 결정한다. 동일 object가 이미 있으면 bytes가 같은지 확인하므로 Storage 또는 Asset insert 재시도마다 새 object를 만들지 않는다. Asset과 Scene의 최신 image/video pointer 갱신은 같은 DB transaction으로 commit하며 과거 Asset은 남긴다. 저장 재시도는 보존된 provider 결과를 사용하므로 성공한 Provider 호출을 다시 수행하지 않는다.

PostgreSQL claim은 `FOR UPDATE SKIP LOCKED`와 lease 조건부 update를 함께 사용한다. SQLite는 조건부 update로 개발 테스트를 지원한다. 만료된 `running` Job은 provider task id가 없을 때 같은 idempotency key로 재제출하고, task id가 있으면 submit하지 않고 poll한다. `saving` Job은 보존된 provider 결과에서 저장만 재개한다. retry는 제한된 지수 backoff를 사용한다.

`OpenAIProvider`는 capability를 분리한다. Story capability는 공식 Python SDK의 Responses API와 Pydantic Structured Outputs를 사용하고, Image capability는 Image API `images.generate` 또는 여러 reference 파일을 받는 `images.edit`를 사용한다. 기본값은 `OPENAI_STORY_MODEL=gpt-5.6-terra`, `OPENAI_IMAGE_MODEL=gpt-image-2.5-flare`, `OPENAI_IMAGE_REFERENCE_MODEL=gpt-image-2.5-sunburst`, `1024x1536`, low, WebP이며 fallback은 없다. Image capability는 SDK의 base64 결과를 하나의 typed artifact로 정규화한다. Request ID와 실제 응답 metadata는 보존하지만 key와 전체 prompt는 로그에 남기지 않는다.

`FalProvider`는 `IMAGE_PROVIDER=fal`인 새 Image/Character Job만 받으며 `fal-client` Queue의 submit → `provider_pending` → status/result → `saving` 흐름을 사용한다. Submit 응답의 request ID와 생성 시 고정된 model ID를 저장해 Worker가 재시작돼도 같은 모델을 poll한다. Submit POST는 중복 과금 가능성 때문에 단 한 번만 보내고 접수 여부가 모호한 실패는 자동 재제출하지 않는다. Reference-conditioned Scene에서는 첫 canonical Character reference를 Data URI로 `fal-ai/flux-pulid`에 보내며 다른 캐릭터는 Character Bible prompt에 남긴다. fal의 임시 output URL은 허용된 HTTPS fal/GCS host에서 제한된 크기로 다운로드하고 이미지 MIME/header/pixel 검증을 거쳐 private Storage에 저장한다. Asset ID/key는 Job과 artifact 순서에서 결정한다. 자동 Provider fallback은 없다.

`MockProvider`는 개발·테스트 전용이다. 구조화 Story, deterministic PNG, 재생 가능한 작은 MP4 fixture, 동기/비동기 polling과 오류를 네트워크 없이 시뮬레이션한다. Production 예시는 `MOCK_AI=false`이며 Mock 결과는 실제 AI 결과가 아니다.

## 전달 및 운영 경계

Compose는 로컬 개발용이며 포트를 loopback에만 노출한다. 외부 서비스로 배포하기 전에는 TLS, Auth rate limit/abuse protection, 별도 DB 사용자·백업·로그 보존 정책을 운영 환경에 맞게 설정해야 한다. 이번 요청은 로컬 Phase 1 구현이며 실제 cloud 배포는 포함하지 않는다. Service Worker의 offline 데이터 저장은 아직 사용하지 않아 인증된 작업실 응답이 offline cache에 남지 않는다.
