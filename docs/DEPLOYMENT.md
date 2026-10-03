# LinkToon production deployment

이 문서는 GitHub `heheboi1972/LinkToon`의 `main` 브랜치를 Vercel + Render + Supabase에 처음 배포하는 절차다. 예상 주소는 `https://linktoon.vercel.app`과 `https://linktoon-api.onrender.com`이지만, 이름 충돌로 실제 주소가 달라질 수 있다. 대시보드에서 발급된 실제 주소를 아래 입력값에 사용한다.

현재 구현된 사용자 기능은 계정, 프로젝트 제작/실제 DB 제작 지표, Character Bible/기준 이미지, Story/Scene Image/Motion, private Reader, versioned Publish와 로그인 없는 public/unlisted Reader다. Public Reader/media는 private bucket을 유지하면서 active snapshot 기반의 15분 capability를 사용한다. OpenAI Story, OpenAI 또는 fal.ai Image/Character reference, Runway Motion은 Render Background Worker가 처리한다.

## PART A — GitHub

1. GitHub에서 `https://github.com/heheboi1972/LinkToon`을 연다.
2. 기본 브랜치가 `main`인지 확인한다: **Settings → Default branch**.
3. 로컬에서 확인할 때는 저장소 루트에서 다음을 실행한다.

```powershell
git remote -v
git branch --show-current
git status --short
git push -u origin main
```

`.env`, `.env.local`, `.venv`, `node_modules`, `.next`, `.data`는 커밋하면 안 된다. 실제 secret은 GitHub 파일이나 Actions 변수에 복사하지 않는다.

## PART B — Supabase

### 1. 프로젝트와 연결값

1. [Supabase Dashboard](https://supabase.com/dashboard)에 로그인한다.
2. **New project**를 누르고 전용 LinkToon 프로젝트를 만든다.
3. **Project Settings → API**에서 다음 값을 복사해 둔다.
   - Project URL → `SUPABASE_URL`
   - anon/public key → `SUPABASE_ANON_KEY`
   - service_role key → `SUPABASE_SERVICE_ROLE_KEY` (Render에만 입력)
4. 상단 **Connect**에서 PostgreSQL Session pooler URI를 복사한다. SQLAlchemy용 scheme을 `postgresql+psycopg://`로 바꾸고 TLS 옵션 `?sslmode=require`를 유지하거나 추가해 `DATABASE_URL`로 쓴다.

### 2. 스키마와 RLS

전용 Supabase 프로젝트에만 적용한다. 저장소 루트의 PowerShell에서 실제 DB URL을 현재 셸에만 넣고 Alembic을 실행한다.

```powershell
cd apps/api
$env:DATABASE_URL = 'postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres?sslmode=require'
uv sync --frozen
uv run alembic upgrade head
uv run alembic current
Remove-Item Env:DATABASE_URL
```

이어서 Supabase **SQL Editor → New query**에서 `scripts/supabase-rls.sql` 전체를 실행한다. 이 SQL은 모든 앱 테이블에 RLS를 켜고, 로그인 사용자의 owner-scoped 읽기 정책을 만들며, `profiles.password_hash`를 브라우저 role에 공개하지 않는다. 브라우저 쓰기는 허용하지 않고 FastAPI가 데이터 무결성을 검사한다.

### 3. Auth URL

Supabase **Authentication → URL Configuration**에서 다음을 입력한다.

- Site URL: 실제 Vercel production URL. 예상값 `https://linktoon.vercel.app`
- Redirect URLs에 `http://localhost:3000/**` 추가
- Redirect URLs에 `https://linktoon.vercel.app/**` 추가

현재 회원가입 코드는 `${location.origin}/login`을 `emailRedirectTo`로 보낸다. 별도 `/auth/callback` route는 없다. 실제 Vercel 주소가 다르면 그 주소의 `/**`를 등록한다. Preview 배포에서 Auth를 시험할 때만 팀이 통제하는 Vercel preview pattern을 추가한다.

### 4. Storage

`scripts/supabase-rls.sql`이 다음 bucket을 생성 또는 보정한다.

- 이름: `linktoon-private`
- Public: off
- 최대 파일: 100 MiB
- MIME: `image/png`, `image/jpeg`, `image/webp`, `video/mp4`

브라우저는 service-role key를 받지 않는다. FastAPI가 짧게 유효한 capability URL을 발급하고, 이미지 bytes와 MIME/픽셀 제한을 검사한 뒤 새 UUID object로 저장한다. 같은 key에 upsert하지 않는다.

## PART C — Render

### Blueprint 방식

1. [Render Dashboard](https://dashboard.render.com/)에 로그인한다.
2. **New + → Blueprint**를 누른다.
3. GitHub를 연결하고 `heheboi1972/LinkToon`을 선택한다.
4. repository root의 `render.yaml`을 승인한다.
5. Blueprint가 API Web Service와 Generation Background Worker를 만드는지 확인한다.
6. 각 서비스에서 `sync: false`로 표시된 값을 아래 표대로 입력한다. AI provider 키는 Worker에만 입력한다. API와 Worker의 `IMAGE_PROVIDER` 및 fal model ID는 동일하게 둔다.

### Web Service를 직접 만드는 방식

**New + → Web Service → Build and deploy from a Git repository**에서 저장소를 선택하고 다음을 입력한다.

| 필드 | 값 |
| --- | --- |
| Name | `linktoon-api` 또는 사용 가능한 이름 |
| Branch | `main` |
| Root Directory | `apps/api` |
| Runtime | `Python 3` |
| Build Command | `uv sync --frozen --no-dev` |
| Start Command | `uv run --no-sync alembic upgrade head && uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/health` |
| Python | `3.12.14` (`.python-version`) |
| uv | `0.10.9` (`UV_VERSION`) |

같은 저장소에서 Background Worker도 만든다.

| 필드 | 값 |
| --- | --- |
| Name | `linktoon-generation-worker` 또는 사용 가능한 이름 |
| Branch | `main` |
| Root Directory | `apps/api` |
| Runtime | `Python 3` |
| Build Command | `uv sync --frozen --no-dev` |
| Start Command | `uv run --no-sync python -m app.worker` |
| Python | `3.12.14` |
| uv | `0.10.9` |

### API Web Service Environment Variables

| Key | 입력값 |
| --- | --- |
| `APP_ENV` | `production` |
| `AUTH_MODE` | `supabase` |
| `STORAGE_PROVIDER` | `supabase` |
| `MOCK_AI` | `false` |
| `LOCAL_AUTH_SECRET` | Blueprint 자동 생성값 또는 암호학적으로 무작위인 32자 이상 문자열 |
| `DATABASE_URL` | Supabase PostgreSQL SQLAlchemy URL |
| `API_PUBLIC_URL` | 실제 Render origin, 예: `https://linktoon-api.onrender.com` |
| `CORS_ORIGINS` | JSON 배열, 예: `["https://linktoon.vercel.app"]` |
| `SUPABASE_URL` | Supabase Project URL |
| `SUPABASE_ANON_KEY` | Supabase anon/public key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service_role key |
| `SUPABASE_STORAGE_BUCKET` | `linktoon-private` |
| `MAX_UPLOAD_BYTES` | `10485760` |
| `AI_QUOTAS_ENABLED` | `true` |
| `STORY_DAILY_LIMIT` | `10` |
| `IMAGE_DAILY_LIMIT` | `5` |
| `MOTION_DAILY_LIMIT` | `2` |
| `RUNWAY_VIDEO_MODEL` | `gen4_turbo` (API와 Worker에 동일하게 설정) |
| `RUNWAY_VIDEO_DURATION_SECONDS` | `5` (API와 Worker에 동일하게 설정) |
| `OPENAI_STORY_MODEL` | Worker와 같은 `gpt-5.6-terra` 또는 선택한 모델. secret 아님 |
| `OPENAI_IMAGE_MODEL` | Worker와 같은 `gpt-image-2.5-flare` 또는 선택한 모델. secret 아님 |
| `OPENAI_IMAGE_REFERENCE_MODEL` | Character reference와 reference-conditioned Scene edit 모델. 기본 `gpt-image-2.5-sunburst` |
| `OPENAI_IMAGE_SIZE` | `1024x1536` |
| `OPENAI_IMAGE_QUALITY` | `low` |
| `OPENAI_IMAGE_FORMAT` | `webp` |
| `IMAGE_PROVIDER` | `openai` 또는 `fal` (API와 Worker 동일) |
| `FAL_IMAGE_MODEL` | 기본 `fal-ai/flux-2-pro` (API와 Worker 동일) |
| `FAL_REFERENCE_IMAGE_MODEL` | 기본 `fal-ai/flux-pulid` (API와 Worker 동일) |

API Web Service에는 `OPENAI_API_KEY`를 설정하지 않는다. API는 Story 요청을 검증하고 DB Job을 만들 뿐 OpenAI 네트워크 요청을 보내지 않는다. Worker는 PostgreSQL queue를 사용하므로 `REDIS_URL`이 필요하지 않다.

### Generation Background Worker Environment Variables

Worker에는 API와 동일한 `APP_ENV`, `AUTH_MODE`, `STORAGE_PROVIDER`, `MOCK_AI`, `DATABASE_URL`, `API_PUBLIC_URL`, `CORS_ORIGINS`, Supabase 연결값, Provider/model 값과 이미지 제한을 설정한다. 두 서비스는 같은 Supabase PostgreSQL을 사용해야 한다. Quota 값은 Job을 접수하는 API 설정이다. Worker 전용 secret과 처리 설정은 아래와 같다.

| Key | 입력값 |
| --- | --- |
| `OPENAI_API_KEY` | 실제 OpenAI project API key. Worker에만 입력 |
| `FAL_KEY` | fal.ai API key. Worker에만 입력하고 `IMAGE_PROVIDER=fal`일 때 사용 |
| `RUNWAYML_API_SECRET` | Runway API key. Worker에만 입력 |
| `RUNWAY_VIDEO_MODEL` | `gen4_turbo` 또는 `gen4.5` (API 설정과 동일) |
| `RUNWAY_VIDEO_DURATION_SECONDS` | `5` (API 설정과 동일) |
| `RUNWAY_API_VERSION` | `2024-11-06` |
| `MAX_VIDEO_BYTES` | `104857600` (100 MiB) |
| `OPENAI_STORY_MODEL` | `gpt-5.6-terra` 또는 계정에서 명시적으로 사용할 Story 모델 |
| `OPENAI_IMAGE_MODEL` | `gpt-image-2.5-flare` 또는 계정에서 명시적으로 사용할 Image 모델 |
| `OPENAI_IMAGE_REFERENCE_MODEL` | `gpt-image-2.5-sunburst` 또는 계정에서 명시적으로 사용할 reference/edit 모델 |
| `OPENAI_IMAGE_SIZE` | `1024x1536` |
| `OPENAI_IMAGE_QUALITY` | `low` |
| `OPENAI_IMAGE_FORMAT` | `webp` |
| `OPENAI_TIMEOUT_SECONDS` | `90`. Worker lease보다 짧게 유지 |
| `WORKER_ID` | 비워 두면 hostname-process ID 자동 사용 |
| `WORKER_POLL_INTERVAL_SECONDS` | `2` |
| `WORKER_LEASE_SECONDS` | `120` |
| `WORKER_BATCH_SIZE` | `10` |
| `WORKER_MAX_RETRIES` | `3` |
| `WORKER_RETRY_BASE_SECONDS` | `2` |
| `WORKER_PROVIDER_POLL_SECONDS` | `2` |

### Production Environment Matrix

| Service | Variables | Secret |
| --- | --- | --- |
| Vercel Web | `NEXT_PUBLIC_API_URL` (required); `API_INTERNAL_URL` only when a server-side upstream is intentionally configured | No. `NEXT_PUBLIC_API_URL` is public by design |
| Render API + Worker | `APP_ENV`, `AUTH_MODE`, `STORAGE_PROVIDER`, `MOCK_AI`, `LOCAL_AUTH_SECRET`, `DATABASE_URL`, `API_PUBLIC_URL`, `CORS_ORIGINS`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_STORAGE_BUCKET`, `MAX_UPLOAD_BYTES`, `OPENAI_STORY_MODEL`, `OPENAI_IMAGE_MODEL`, `OPENAI_IMAGE_REFERENCE_MODEL`, `OPENAI_IMAGE_SIZE`, `OPENAI_IMAGE_QUALITY`, `OPENAI_IMAGE_FORMAT`, `IMAGE_PROVIDER`, `FAL_IMAGE_MODEL`, `FAL_REFERENCE_IMAGE_MODEL`, `RUNWAY_VIDEO_MODEL`, `RUNWAY_VIDEO_DURATION_SECONDS` | `LOCAL_AUTH_SECRET`, `DATABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` are secrets. `SUPABASE_ANON_KEY` is public |
| Render API only | `AI_QUOTAS_ENABLED`, `STORY_DAILY_LIMIT`, `IMAGE_DAILY_LIMIT`, `MOTION_DAILY_LIMIT` | No |
| Render Worker only | `OPENAI_API_KEY`, `FAL_KEY`, `RUNWAYML_API_SECRET`, `OPENAI_TIMEOUT_SECONDS`, `RUNWAY_API_VERSION`, `MAX_VIDEO_BYTES`, `WORKER_ID`, `WORKER_POLL_INTERVAL_SECONDS`, `WORKER_LEASE_SECONDS`, `WORKER_BATCH_SIZE`, `WORKER_MAX_RETRIES`, `WORKER_RETRY_BASE_SECONDS`, `WORKER_PROVIDER_POLL_SECONDS` | Provider keys are secrets |
| Local / CI only | `LOCAL_STORAGE_PATH`, `REDIS_URL` (reserved; current DB Worker does not use it), `TEST_POSTGRES_URL` | Treat a real test database URL as a secret |

Vercel supplies `VERCEL` and `NODE_ENV`; do not copy secrets into `NEXT_PUBLIC_*`. Render API and Worker must use the same database, Supabase project, Provider selection, and model IDs. Provider keys stay on the Worker. Production defaults are OpenAI for Story and Image, with `IMAGE_PROVIDER=openai`; Runway handles Motion. fal is enabled only when both services are configured for it. Provider failures do not automatically charge another Provider.

실제 secret을 `render.yaml`, `.env.example`, GitHub 또는 Vercel에 입력하지 않는다. Production에서는 `MOCK_AI=false`를 유지한다. 모델 접근 권한 오류를 다른 모델로 자동 fallback하지 않으므로 배포 전에 해당 OpenAI project가 Story와 Image 모델을 사용할 수 있는지 확인한다.

API Web Service가 Alembic migration을 적용한 뒤 Worker를 시작한다. Worker에는 health endpoint가 없으며 Render process 상태와 로그의 `started=true`를 확인한다. 로그에 key, Authorization header나 전체 Story prompt가 나타나면 안 된다.

**Create Web Service / Apply**를 눌러 배포한다. 완료 후 브라우저에서 다음을 확인한다.

- `https://<actual-render-host>/health` → status `ok`
- `https://<actual-render-host>/ready` → status `ready`
- `https://<actual-render-host>/docs` → FastAPI 문서

`/health`는 프로세스 health check이고 `/ready`는 DB 연결과 Alembic revision까지 검사한다.

## PART D — Vercel

1. [Vercel Dashboard](https://vercel.com/dashboard)에 로그인한다.
2. **Add New… → Project**를 누른다.
3. **Import Git Repository**에서 `heheboi1972/LinkToon`의 **Import**를 누른다.
4. **Root Directory → Edit**에서 `apps/web`을 선택한다.
5. Framework Preset이 **Next.js**인지 확인한다.
6. Build 설정은 저장소의 `apps/web/vercel.json`을 사용한다.
   - Install Command: `npm ci --prefix ../..`
   - Build Command: `npm run build`
   - Output Directory: override하지 않음(Next.js 기본 `.next`)
7. **Environment Variables**에 `NEXT_PUBLIC_API_URL` 하나를 추가한다. 값은 실제 Render origin이며 마지막 `/`를 생략한다.
8. 적용 범위는 Production과 Preview를 선택한다. Preview가 별도 API를 쓰지 않으면 같은 Render URL을 넣는다.
9. **Deploy**를 누르고 실제 production URL을 기록한다.

`NEXT_PUBLIC_API_URL`은 브라우저에 공개되는 값이다. Supabase service-role key, DB URL, 로컬 서명 secret, AI provider key는 Vercel에 입력하지 않는다. Vercel build는 이 변수가 없으면 실패하도록 설정되어 있다.

## PART E — 실제 Production URL 반영

Vercel 주소가 확정되면 Supabase **Authentication → URL Configuration**으로 돌아간다.

1. Site URL을 실제 Vercel URL로 바꾼다.
2. Redirect URLs에 `https://<actual-vercel-host>/**`가 있는지 확인한다.
3. 예전에 예상 주소를 넣었는데 실제 주소가 다르면 예상 주소를 제거한다.

회원가입 확인 메일은 `/login`으로 돌아와야 한다.

## PART F — CORS와 API public URL

Render **linktoon-api → Environment**에서 다음을 실제 주소로 갱신한다.

```text
API_PUBLIC_URL=https://<actual-render-host>
CORS_ORIGINS=["https://<actual-vercel-host>"]
```

저장 후 **Save, rebuild, and deploy**를 선택한다. Preview origin을 실제로 시험할 경우에만 그 정확한 origin을 JSON 배열에 추가한다. wildcard `*`는 허용되지 않는다.

Vercel **Project → Settings → Environment Variables**의 `NEXT_PUBLIC_API_URL`도 같은 실제 Render origin인지 확인하고 Redeploy한다. 이 값은 빌드 시 브라우저 bundle에 들어간다.

## PART G — 최종 점검

아래 순서대로 실제 production URL에서 확인한다.

- [ ] `/health`, `/ready`, `/docs`가 열림
- [ ] 회원가입 후 확인 메일이 실제 Vercel `/login`으로 복귀
- [ ] 로그인과 로그아웃
- [ ] 프로젝트 생성·수정·삭제
- [ ] 에피소드 생성·수정·삭제
- [ ] 10개 이상 패널 생성과 설명·대사 저장
- [ ] PNG/JPG/WebP 업로드와 새로고침 후 표시
- [ ] 다른 계정으로 첫 계정의 project/episode/panel/asset ID 접근 시 404
- [ ] 모바일 폭에서 가로 스크롤 없이 사용 가능
- [ ] Render `/ready`가 `ready`
- [ ] `linktoon-generation-worker`가 실행 중이고 같은 `DATABASE_URL`을 사용함
- [ ] API Web Service에는 `OPENAI_API_KEY`가 없고 Worker에만 설정됨
- [ ] 소유 프로젝트 `/story`에서 아이디어·장르·톤·테마·Character·장면 수를 입력해 202 Job을 만들 수 있음
- [ ] Story 화면이 `queued`·`running`·`saving`을 보여주고 약 2초 polling 후 새 Episode의 제목·줄거리·Scene 서술·대사를 Story 화면에 표시함
- [ ] Story 생성 중 새로고침 후 같은 탭에서 Job 상태를 복구하고, Worker 성공 후 새 Episode와 요청한 수의 Scene이 생성됨
- [ ] 다른 사용자의 Character·Job·Project ID는 조회할 수 없고 404 처리됨
- [ ] 같은 `Idempotency-Key`의 동일 요청은 같은 Job을 반환하고 다른 payload 재사용은 409
- [ ] 각 저장된 Scene에서 이미지 Job을 만들고 `queued`·`running`·`saving` 후 생성 이미지가 표시됨
- [ ] Scene 이미지 생성 중 새로고침 후 Job을 복구하고 완료 후 `image_asset_id`와 private Asset URL로 표시됨
- [ ] 동일 Scene의 활성 Job 중복은 409, 다른 Scene은 독립 실행, 재생성 시 기존 Asset은 남음
- [ ] generated object 경로가 `users/{user}/projects/{project}/generated/{asset}.{ext}`이고 bucket이 private임
- [ ] 브라우저 Network 요청이 실제 Render URL로 전송됨
- [ ] GitHub/Vercel browser bundle과 로그에 secret이 없음
- [ ] `OPENAI_API_KEY`가 준비된 환경에서 1-Scene Story smoke를 명시적으로 실행하고 `output.mock=false`, Job 성공, Episode 1개·Scene 1개를 확인
- [ ] 같은 Scene으로 1-Image smoke를 실행하고 `output.mock=false`, Job 성공, Asset/object/Scene 연결과 화면 표시를 확인
- [ ] Runway Motion live smoke를 `RUNWAYML_API_SECRET`이 있는 명시적 환경에서 실행하고 MP4 Asset/Range playback을 확인
- [ ] Public Reader는 로그아웃 또는 시크릿 브라우저에서 `/read/{slug}`로 열고 이미지/Motion을 감상
- [ ] Public/unlisted/private visibility를 각각 확인하고 unlisted noindex, private 404를 검증
- [ ] Publication을 다시 게시한 뒤 원본 Scene/Asset 변경이 이전 public snapshot에 자동 반영되지 않고 새 version에서만 나타나는지 확인
- [ ] 공개 중단 후 public route와 기존 media capability가 즉시 거부되는지 확인

운영 공개 전에 Supabase 비용 한도, OpenAI project 예산/사용량 알림, Render/Vercel 사용량 알림, 백업 정책과 계정 삭제 절차도 조직 정책에 맞게 설정한다. 백엔드의 생성 입구는 UTC 자정 기준으로 Story 10회, Image 5회, Motion/Video 2회를 기본 제한한다. 구현된 Provider Job은 Story, Scene Image, Character Reference와 Motion이며, live smoke는 실제 key와 배포 환경을 확인한 경우에만 수행한다.

실제 Provider smoke는 `MOCK_AI=false`, Worker 전용 key, 소유 리소스와 새 `Idempotency-Key`를 사용해 Provider별로 최소 1회씩 분리한다. Scene Image/Motion 결과는 Story Scene에 연결되며 Episode 상세의 Panel과는 별도 흐름이다.

## Release Checklist and Rollback

Release 전에 backend/frontend clean-install 검사를 통과시키고, ignored secret 파일이 stage에 없는지 확인한다. Supabase 백업과 migration 변경을 검토한 뒤 API service만 `alembic upgrade head`를 실행한다. API와 Worker는 같은 commit 및 database/configuration을 사용하고, Vercel은 해당 commit의 production build를 제공해야 한다. `/health`, `/ready`, 가입 redirect, private Storage, Provider별 명시적 smoke, 익명 Reader와 mobile/desktop 핵심 화면을 확인한 뒤 배포 완료로 기록한다.

Rollback은 Vercel에서 직전 정상 Production deployment를 선택하고, Render API와 Worker를 함께 직전 정상 deployment로 되돌린다. 적용된 migration은 자동 downgrade하거나 `base`로 되돌리지 않는다. 새 schema가 이미 production에 적용됐다면 호환성이 확인된 애플리케이션 버전만 롤백하고, schema 문제는 forward migration으로 우선 수정한다. 데이터 복구가 필요할 때는 승인된 Supabase 백업과 incident 절차를 사용한다. Rollback 후 `/health`, `/ready`, Worker 시작 로그, 로그인, private Asset, public Reader를 다시 확인한다.
