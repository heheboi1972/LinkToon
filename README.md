# LinkToon

AI 기반 웹툰 제작 플랫폼입니다. 실제 계정·DB·파일 저장을 연결하며, Vercel(Next.js) → Render(FastAPI + Background Worker) → Supabase(PostgreSQL/Auth/private Storage) 운영 배포 구성을 포함합니다.

**현재 가능한 웹 흐름:** 가입 → 로그인 → 프로젝트 제작 → Story/Character/Scene Image/Motion → private Reader → Publish snapshot → public/unlisted 공유 URL을 로그인 없이 감상. Project Overview에는 DB에서 계산한 실제 제작 지표가 표시됩니다. Episode Panel 편집·업로드는 Story Scene 흐름과 별도입니다. 모든 AI 생성 요청은 FastAPI의 202 Job으로 접수되고 별도 Worker가 Mock 또는 설정된 OpenAI/fal.ai/Runway Provider로 처리합니다. 새 Scene Image와 Character reference Job은 `IMAGE_PROVIDER=openai|fal`로 고르며 기본값은 OpenAI입니다.

## 빠른 시작 — Windows PowerShell

준비: Node.js 22 이상(검증: 24.16), npm, uv, Python 3.12. Python이 없으면 uv가 관리하는 Python을 사용할 수 있습니다. Docker Desktop은 PostgreSQL Compose를 선택할 때만 필요합니다.

```powershell
cd 'C:\Users\SAMSUNG\OneDrive\문서\ChatGPT\LinkToon'
.\scripts\setup.ps1
```

이 스크립트는 `.env.example`로 `.env`를 만들고 임의의 local signing secret을 생성합니다. 기존 `.env`는 변경하지 않습니다. 이어 npm/uv 의존성 설치와 Alembic upgrade를 실행합니다. 실제 키를 입력할 필요 없이 SQLite + local Auth + local Storage로 실행됩니다. `.env` 및 `.data`는 git ignore 대상입니다.

설치된 Python 실행 파일을 직접 지정할 수도 있습니다.

```powershell
.\scripts\setup.ps1 -Python 'C:\path\to\python.exe'
```

현재 PC에서 이미 설치·마이그레이션을 완료했다면 다음 실행 명령만 사용하면 됩니다.

터미널 1 — API:

```powershell
.\scripts\start-api.ps1
```

터미널 2 — 웹:

```powershell
npm run dev
```

터미널 3 — 개발용 Background Worker:

```powershell
cd apps/api
uv run python -m app.worker
```

Worker는 Redis/Celery 없이 `generation_jobs` 테이블을 queue로 사용합니다. 기본 `MOCK_AI=true`인 개발·테스트 환경의 Mock 결과는 파이프라인 검증용이며 실제 AI 생성 결과가 아닙니다. 한 건만 처리하고 종료하려면 `--once`를 붙입니다.

실제 OpenAI Story와 Scene Image를 로컬에서 실행할 때는 git ignore된 루트 `.env`에서 Mock을 끄고 모델을 정한 뒤 API를 재시작합니다. API는 Provider를 호출하지 않고 OpenAI Job만 만듭니다.

```dotenv
MOCK_AI=false
OPENAI_STORY_MODEL=gpt-5.6-terra
OPENAI_IMAGE_MODEL=gpt-image-2.5-flare
OPENAI_IMAGE_REFERENCE_MODEL=gpt-image-2.5-sunburst
OPENAI_IMAGE_SIZE=1024x1536
OPENAI_IMAGE_QUALITY=low
OPENAI_IMAGE_FORMAT=webp
OPENAI_TIMEOUT_SECONDS=90
IMAGE_PROVIDER=openai
FAL_IMAGE_MODEL=fal-ai/flux-2-pro
FAL_REFERENCE_IMAGE_MODEL=fal-ai/flux-pulid
```

Worker를 시작하는 터미널에만 key를 주입합니다. 키를 PowerShell 명령 기록에 남기지 않으려면 보안 입력창을 사용합니다.

```powershell
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'OpenAI API key' -AsSecureString)).Password
cd apps/api
uv run python -m app.worker
# Worker 종료 후:
Remove-Item Env:OPENAI_API_KEY
```

fal.ai를 이미지 Provider로 시험할 때는 API와 Worker가 같은 `.env` 설정을 읽도록 루트 `.env`에서 `IMAGE_PROVIDER=fal`로 바꾸고 Worker에만 `FAL_KEY`를 입력합니다. 모델 기본값은 `fal-ai/flux-2-pro`이며 canonical Character reference 기반 장면은 `fal-ai/flux-pulid`를 사용합니다. 일반 자동 테스트는 fake client만 쓰며 실제 과금 요청은 별도 smoke test를 명시적으로 켜기 전까지 보내지 않습니다.

프로젝트의 `/story` 화면에서 아이디어·장르·톤·테마·캐릭터·장면 수(1~20)를 입력하고 생성할 수 있습니다. 화면은 공통 API client로 `Idempotency-Key`를 보내고 Job을 약 2초마다 조회합니다. 같은 탭을 새로고침하면 사용자·프로젝트 또는 사용자·Scene별 `sessionStorage`에 저장된 Job ID로 진행 상태나 결과를 다시 불러옵니다. Story 성공 시 제목·줄거리·장면의 서술·대사를 보여주고, 각 저장된 Scene에서 `이미지 생성`을 실행할 수 있습니다. 이미지 성공 시 private Storage의 새 Asset을 Scene 대표 이미지로 연결하며 재생성해도 과거 Asset은 보존합니다. Episode 상세 화면의 Panel은 생성된 Scene에서 자동으로 만들어지지 않습니다. API 직접 검증과 실제 OpenAI 절차는 [Story 생성](docs/api.md#story-생성)과 [Scene 이미지 생성](docs/api.md#scene-이미지-생성)에 있습니다.

웹은 개발 중 `NEXT_PUBLIC_API_URL`이 비어 있으면 Next.js의 로컬 API proxy를 사용합니다. 별도 API origin에 직접 연결하려면 `apps/web/.env.local`에 `NEXT_PUBLIC_API_URL=http://localhost:8000`을 설정합니다. 운영에서는 이 값을 실제 Render HTTPS origin으로 반드시 설정합니다.

PowerShell의 정책이 로컬 `.ps1` 실행을 제한하면 정책을 바꾸지 않고 동일 명령을 직접 실행합니다.

```powershell
npm ci
cd apps/api
uv sync --frozen --python 3.12
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# 별도 터미널, 저장소 루트에서:
npm run dev
```

이 직접 실행 경로도 먼저 setup으로 생성된 `.env`가 필요합니다. 새 설치에서 스크립트 정책을 변경할 수 없다면 아래 secret 생성 명령을 사용합니다.

```powershell
Copy-Item .env.example .env
$secretBytes = New-Object byte[] 48
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($secretBytes)
$rng.Dispose()
$envText = (Get-Content .env -Raw).Replace('GENERATE_WITH_SETUP_SCRIPT', [Convert]::ToBase64String($secretBytes))
[IO.File]::WriteAllText((Join-Path (Get-Location) '.env'), $envText)
```

## PostgreSQL

SQLite 대안과 PostgreSQL은 같은 모델·마이그레이션·API를 사용합니다. 실제 협업/배포 환경은 PostgreSQL을 사용합니다.

```powershell
docker compose up -d db
# 새 checkout에서 .env가 아직 없다면:
.\scripts\setup.ps1 -Postgres
```

기존 `.env`가 있을 때 `-Postgres`는 이를 덮어쓰지 않습니다. 현재 터미널에서 PostgreSQL을 선택하려면 다음과 같이 실행합니다. SQLite 데이터는 자동으로 이전되지 않습니다.

```powershell
$env:DATABASE_URL = 'postgresql+psycopg://linktoon:linktoon_local@localhost:5432/linktoon'
.\scripts\start-api.ps1
```

네이티브 DLL을 제한하는 Windows 환경에서는 URL의 `postgresql+psycopg`를 `postgresql+pg8000`으로 바꿀 수 있습니다. 환경 변수 override는 현재 PowerShell에만 적용됩니다.

전체 앱을 Docker로 실행:

```powershell
# 먼저 setup.ps1로 .env를 생성
docker compose --profile app up --build -d
docker compose logs -f api web
```

API 컨테이너는 Postgres가 준비되면 migration 후 시작하고, 웹은 API readiness를 확인한 뒤 시작합니다. 현재 생성 Worker는 PostgreSQL queue를 사용하며 Redis/Celery가 필요하지 않습니다. Compose credential과 loopback port mapping은 로컬 개발용입니다.

## 접속 URL과 정상 결과

| URL | 정상 결과 |
| --- | --- |
| [http://localhost:3000](http://localhost:3000) | LinkToon 랜딩 페이지 |
| [http://localhost:3000/signup](http://localhost:3000/signup) | 표시 이름/이메일/10자 이상 비밀번호로 가입 |
| [http://localhost:3000/dashboard](http://localhost:3000/dashboard) | 본인의 프로젝트와 최근 작업 |
| [http://localhost:3000/projects/new](http://localhost:3000/projects/new) | 3단계 생성 Wizard |
| [http://localhost:8000/docs](http://localhost:8000/docs) | FastAPI Swagger UI |
| [http://localhost:8000/health](http://localhost:8000/health) | `{"status":"ok","service":"linktoon-api","phase":"1"}` |
| [http://localhost:8000/ready](http://localhost:8000/ready) | `{"status":"ready"}` |

프로젝트 생성 시 project + project_bible이 한 트랜잭션으로 생성됩니다. 에피소드 번호는 1부터, panel position은 0부터 배정됩니다. 이미지를 업로드하면 image asset이 `ready`, 연결한 panel이 `static`이 됩니다. 페이지를 새로고침해도 그대로 남아야 합니다. 다른 계정은 리소스 ID를 알아도 404를 받습니다.

브라우저 수동 검증용 PNG가 필요하면:

```powershell
cd apps/api
uv run python ../../scripts/make-sample.py
# 루트 .data/sample-panel.png 생성. 업로드 화면에서 선택하세요.
```

개발 서버는 LAN 접속을 위한 `0.0.0.0` bind를 지원하며 모바일에서는 `http://<PC의 LAN IP>:3000`으로 접속합니다. 브라우저 API/이미지 요청은 웹 origin의 proxy를 사용합니다. PC 방화벽 설정과 같은 네트워크 연결은 별도로 필요합니다. Compose는 기본적으로 loopback에만 노출합니다.

## 검증 명령

전체 검사:

```powershell
.\scripts\check.ps1
```

개별 검사:

```powershell
npm run lint
npm run typecheck
npm test
npm run build
cd apps/api
uv run ruff check .
uv run mypy app
uv run pytest -q
uv run alembic check
```

일반 `pytest`는 OpenAI client를 fake로 대체하며 외부 API를 호출하지 않습니다. 실제 계정 검증은 자동 검사와 분리해 [API 문서의 1-Scene Story 절차](docs/api.md#story-생성)와 [1-Image 절차](docs/api.md#scene-이미지-생성)를 명시적으로 실행합니다.

PostgreSQL에서 같은 테스트를 실행하려면 DB를 만들 수 있는 **개발 전용** URL을 지정합니다. 각 테스트는 새 이름의 DB를 만들고 자신이 만든 DB만 삭제합니다.

```powershell
cd apps/api
$env:TEST_POSTGRES_URL = 'postgresql+pg8000://linktoon:linktoon_local@localhost:5432/linktoon'
uv run pytest -q
Remove-Item Env:TEST_POSTGRES_URL
```

Docker가 없는 이 PC에서 실제 PostgreSQL 검증에 사용한 선택적 도구:

```powershell
# 저장소 루트에서
npm install --prefix .data/postgres-runtime --no-save embedded-postgres@18.4.0-beta.17
$env:UV_PROJECT_ENVIRONMENT = 'C:\Users\Public\Documents\ESTsoft\CreatorTemp\linktoon-api-task12-venv'
$env:UV_CACHE_DIR = 'C:\Users\Public\Documents\ESTsoft\CreatorTemp\linktoon-uv-cache'
cd apps/api
uv sync --frozen --python 3.12
cd ../..
$env:TEMP = 'C:\Users\Public\Documents\ESTsoft\CreatorTemp'
$env:TMP = $env:TEMP
node scripts/test-postgres.mjs
```

OneDrive 경로의 `.venv`에서 권한 문제가 나면 위처럼 Python 환경·cache·PostgreSQL 임시 파일을 ASCII 경로에 둡니다. 테스트 도구는 OS 임시 폴더에 별도의 PostgreSQL 클러스터를 만들고 loopback 55432만 사용합니다. 시스템 서비스를 설치하지 않습니다. Windows의 한글 경로 초기화 문제 때문에 바이너리도 임시 경로로 복사합니다. 종료 시 서버를 정지하며 진단용 임시 파일은 남깁니다. 일반 개발 실행에 이 도구는 필요 없습니다.

검증 결과와 환경 한계는 [Phase 1 결과 보고서](docs/phase-1-report.md)에 정리합니다. Frontend tests는 API 오류/인증 헤더/업로드/빈 상태/검색·필터를 검증합니다. Backend tests는 CRUD, 12패널, 자산 권한, 위조 타입/크기, 토큰 목적·만료, production guard, Supabase adapter, migration drift/왕복과 RLS를 검증합니다. RLS는 PostgreSQL 실행에서만 검사합니다.

## Supabase 연결

1. 전용 Supabase 프로젝트의 PostgreSQL URL을 `DATABASE_URL`에 설정하고 migration을 실행합니다.
2. `scripts/supabase-rls.sql`을 Supabase SQL Editor에서 실행합니다. private bucket과 owner SELECT 정책을 구성합니다. 기존 프로젝트의 넓은 정책과 섞지 않습니다.
3. `.env`에서 `AUTH_MODE=supabase`, `STORAGE_PROVIDER=supabase`, Supabase URL/anon/service role 값을 설정합니다.
4. Supabase Auth의 Site URL을 웹 주소로, redirect allow list에 `/login` 복귀 주소를 등록합니다. 이메일 확인이 켜져 있으면 메일 확인 후 로그인합니다.
5. API를 재시작합니다. 웹은 안전한 공개 설정만 API에서 읽으므로 AI secret이 포함된 frontend env는 필요 없습니다.

API는 Supabase access token을 Auth 서버에서 검증합니다. Storage는 서버의 service role을 사용하며 이미지 bytes는 API에서 검증한 뒤 저장합니다. 로컬 계정과 Supabase 계정을 하나의 기존 DB에 혼합/자동 이전하지 않습니다. 실제 cloud credential 없이 adapter mock과 별도 PostgreSQL의 RLS 정책을 검증했습니다. 실제 Supabase tenant의 가입 메일/Storage 네트워크 검증은 미실행입니다.

## 환경변수

| 변수 | 기본/용도 |
| --- | --- |
| APP_ENV | development / test / production |
| AUTH_MODE | local 또는 supabase |
| STORAGE_PROVIDER | local 또는 supabase |
| MOCK_AI | development/test 기본 true. production은 false |
| LOCAL_AUTH_SECRET | setup에서 무작위 생성. local session/asset capability 서명 |
| DATABASE_URL | 기본 SQLite, 운영 PostgreSQL |
| REDIS_URL | 예약된 로컬 인프라 값. 현재 DB Worker는 사용하지 않음 |
| API_PUBLIC_URL | http://localhost:8000, capability URL origin |
| CORS_ORIGINS | 허용 웹 origin JSON 배열 |
| LOCAL_STORAGE_PATH | API 작업 디렉터리 기준 .data/assets |
| MAX_UPLOAD_BYTES | 10485760, 10 MiB |
| SUPABASE_URL | Supabase 프로젝트 URL |
| SUPABASE_ANON_KEY | 공개 Auth 클라이언트 키 |
| SUPABASE_SERVICE_ROLE_KEY | backend Storage 전용 secret |
| SUPABASE_STORAGE_BUCKET | linktoon-private |
| OPENAI_API_KEY | OpenAI Story/Image Worker 전용 secret. frontend에 설정 금지 |
| OPENAI_STORY_MODEL | Story 모델. 기본 `gpt-5.6-terra` |
| OPENAI_IMAGE_MODEL | 기준 이미지가 없는 Scene 이미지 모델. 기본 `gpt-image-2.5-flare` |
| OPENAI_IMAGE_REFERENCE_MODEL | Character 기준 이미지와 reference-conditioned Scene edit 모델. 기본 `gpt-image-2.5-sunburst` |
| OPENAI_IMAGE_SIZE | 이미지 크기. 기본 `1024x1536` |
| OPENAI_IMAGE_QUALITY | 이미지 품질. 기본 `low` |
| OPENAI_IMAGE_FORMAT | 생성·저장 형식. 기본 `webp` |
| IMAGE_PROVIDER | 새 이미지 Job Provider: `openai` 또는 `fal`. API/Worker 동일 |
| FAL_KEY | fal.ai Worker 전용 secret. API/Web/Vercel에 두지 않음 |
| FAL_IMAGE_MODEL | 일반 Image / 최초 Character reference 모델 |
| FAL_REFERENCE_IMAGE_MODEL | canonical Character reference가 있는 Scene 모델 |
| OPENAI_TIMEOUT_SECONDS | Worker의 OpenAI 요청 제한 시간. 기본 90초 |
| RUNWAYML_API_SECRET | Runway Motion Worker 전용 secret. frontend/API에 설정 금지 |
| RUNWAY_VIDEO_MODEL | Motion 모델. 기본 `gen4_turbo` |
| RUNWAY_VIDEO_DURATION_SECONDS | Motion 길이. 기본 `5`초 |
| RUNWAY_API_VERSION | Runway API 버전. 기본 `2024-11-06` |
| MAX_VIDEO_BYTES | 내려받는 Motion 결과의 크기 제한. 기본 100 MiB |
| AI_QUOTAS_ENABLED | backend Generation Job 일일 한도 적용 여부. 운영 기본 true |
| STORY_DAILY_LIMIT | 사용자별 UTC 하루 Story job 기본 10회 |
| IMAGE_DAILY_LIMIT | 사용자별 UTC 하루 Image job 기본 5회 |
| MOTION_DAILY_LIMIT | 사용자별 UTC 하루 Motion/Video job 기본 2회 |
| WORKER_ID | Worker 식별자. 비어 있으면 hostname-process ID 자동 사용 |
| WORKER_POLL_INTERVAL_SECONDS | 처리할 Job이 없을 때 DB 재확인 간격. 기본 2초 |
| WORKER_LEASE_SECONDS | Worker claim 만료 시간. 기본 120초 |
| WORKER_BATCH_SIZE | 한 loop에서 처리할 최대 Job 수. 기본 10 |
| WORKER_MAX_RETRIES | 일시 오류의 최대 재시도 횟수. 기본 3 |
| WORKER_RETRY_BASE_SECONDS | 지수 backoff 시작 간격. 기본 2초 |
| WORKER_PROVIDER_POLL_SECONDS | 비동기 provider poll 간격. 기본 2초 |
| NEXT_PUBLIC_API_URL | 브라우저가 호출할 FastAPI HTTPS origin. Vercel 필수 public 변수 |
| API_INTERNAL_URL | Next 서버의 API upstream. 기본 http://127.0.0.1:8000, Docker http://api:8000. 빌드/실행 시 설정 |
| TEST_POSTGRES_URL | 선택적인 disposable PostgreSQL 통합 테스트 URL |

`APP_ENV=production`은 Supabase Auth/Storage와 PostgreSQL, 강한 서명 secret 없이 시작되지 않습니다. `.env.example`에는 실제 secret이 없습니다. `SUPABASE_ANON_KEY`를 제외한 서비스 키는 공개 `/config`에 나오지 않습니다.

## 저장소 구조와 구현 범위

```text
apps/web/                 Next.js 앱, 공통 API/Auth, UI와 component tests
apps/api/app/             FastAPI와 DB worker/job processor/provider registry
apps/api/app/providers/   typed Provider 계약, Registry, MockProvider, OpenAI Story/Image capabilities
apps/api/alembic/          0001/0002/0003 migration
apps/api/tests/            실제 migration 기반 테스트
docs/                     제품·아키텍처·DB·API·AI·검증 보고서
scripts/                  PowerShell setup/start/check, RLS, 정리/검증 도구
compose.yaml              PostgreSQL + Redis + 선택적 API/Web
render.yaml               Render FastAPI + Background Worker Blueprint
```

## Production 배포

운영 배포는 `main` 브랜치 기준으로 Vercel `apps/web`, Render의 API Web Service와 Generation Background Worker, Supabase 전용 프로젝트를 연결합니다. Render Blueprint의 secret 필드는 비어 있으며 Dashboard에서 입력합니다. `OPENAI_API_KEY`, `FAL_KEY`, `RUNWAYML_API_SECRET`은 Background Worker에만 입력합니다. Vercel에는 `NEXT_PUBLIC_API_URL`만 넣고 DB, service-role, AI 키를 넣지 않습니다. `IMAGE_PROVIDER`와 fal model ID는 API와 Worker에서 일치시킵니다.

초보자용 GitHub → Supabase → Render → Vercel 순서와 각 Dashboard의 정확한 입력값은 [Production 배포 가이드](docs/DEPLOYMENT.md)에 있습니다. 예상 URL은 `linktoon.vercel.app`, `linktoon-api.onrender.com`이며 실제 서비스명과 URL은 각 콘솔에서 생성된 값을 사용합니다.

현재 route: `/`, `/login`, `/signup`, `/dashboard`, `/projects`, `/projects/new`, `/projects/[projectId]`, 해당 프로젝트의 `/story`·`/characters`·`/assets`·`/episodes`, `/projects/[projectId]/episodes/[episodeId]`, `/projects/[projectId]/episodes/[episodeId]/read`, `/projects/[projectId]/episodes/[episodeId]/publish`, `/read/[slug]`, `/generate`, `/jobs`, `/settings`.

프로젝트 `/story`는 Bible 조회와 Story Studio이며, Character 관리 화면은 `/characters`입니다. 인증된 private Reader는 `/projects/[projectId]/episodes/[episodeId]/read`, 공개 Reader는 `/read/[slug]`에서 확인합니다. Episode의 `/publish`에서 slug·visibility·metadata·다시 게시·공개 중단을 관리합니다. Scene generation과 Reader는 private Asset capability URL을 사용하고 bucket은 계속 private입니다.

후속 TASK에서는 Story 편집·명시적 버전 UI, 별도 Motion Studio, 고급 품질 라우팅과 Fal.ai Provider를 진행합니다. 자세한 범위는 [제품 명세](docs/product-spec.md), [아키텍처](docs/architecture.md), [DB/RLS](docs/database.md), [API](docs/api.md), [AI provider 설계](docs/ai-providers.md)를 참고하세요.

## 운영상 현재 제한

- API 목록은 pagination을 지원하며 Phase 1 UI는 최대 200개를 표시합니다.
- SQLite는 개발 대안입니다. PostgreSQL의 동시성 보장을 대체하지 않습니다.
- 프로젝트 삭제 후 orphan 원본은 `cleanup-assets.py` dry-run으로 확인하고 정리할 수 있습니다. DB 원본이 참조 중인 파일은 제거하지 않습니다.
- PWA manifest 기반만 준비했습니다. offline 편집/service worker/background sync는 미구현입니다.
- Auth rate limiting, HTTPS 배포, 백업·복구와 계정 삭제는 운영화 범위입니다. 이 버전은 공개 인터넷에 배포하지 않았습니다.

Frontend 설정은 [Next.js 설치 가이드](https://nextjs.org/docs/app/getting-started/installation), [Tailwind Next.js 가이드](https://tailwindcss.com/docs/installation/framework-guides/nextjs)를 기준으로 작성했습니다.
