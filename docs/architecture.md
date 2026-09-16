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

`apps/api/app/routes.py`는 입출력·의존성과 목록 조회를 담당한다. 생성/수정/삭제는 서비스에 위임하고 Repository가 project ownership을 검사한다. 자식 리소스는 panel → episode → project → owner 경로를 검증한다. 다른 사용자의 ID를 지정하면 404로 응답한다. Pydantic 입력은 알 수 없는 필드를 거부한다.

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

Redis는 Compose에서 실행 가능하고 Celery dependency는 잠겨 있다. **Phase 1에는 worker와 AI job 생성 API가 없다.** Dashboard의 jobs endpoint는 실제 테이블의 소유 row만 읽는다. 아직 없는 작업을 fake fixture로 완료 표시하지 않는다.

Phase 3 이후 경로는 `API → generation_jobs → Celery → AIService → AIRouter → Provider`다. `MOCK_AI`는 중앙 설정에 준비되어 있으며 현재는 AI 호출 자체가 없다. 장시간 HTTP 요청으로 provider 생성을 기다리는 코드는 추가하지 않는다. SDK/payload/model ID는 provider adapter에만 둔다.

향후 AI provider adapter는 작업을 직접 생성하지 않고 `GenerationService.create_job`을 사용한다. 이 서비스는 프로젝트 소유권을 확인하고 PostgreSQL에서 사용자 행을 잠근 뒤 UTC 일일 사용량을 검사하며, Story 10회·Image 5회·Motion/Video 2회의 기본 한도 안에서만 `GenerationJob`을 만든다. 현재 provider 호출 route는 없으며 quota 조회만 `/api/v1/quotas`로 제공한다.

## 전달 및 운영 경계

Compose는 로컬 개발용이며 포트를 loopback에만 노출한다. 외부 서비스로 배포하기 전에는 TLS, Auth rate limit/abuse protection, 별도 DB 사용자·백업·로그 보존 정책을 운영 환경에 맞게 설정해야 한다. 이번 요청은 로컬 Phase 1 구현이며 실제 cloud 배포는 포함하지 않는다. Service Worker의 offline 데이터 저장은 아직 사용하지 않아 인증된 작업실 응답이 offline cache에 남지 않는다.
