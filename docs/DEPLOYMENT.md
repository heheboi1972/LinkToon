# LinkToon production deployment

이 문서는 GitHub `heheboi1972/LinkToon`의 `main` 브랜치를 Vercel + Render + Supabase에 처음 배포하는 절차다. 예상 주소는 `https://linktoon.vercel.app`과 `https://linktoon-api.onrender.com`이지만, 이름 충돌로 실제 주소가 달라질 수 있다. 대시보드에서 발급된 실제 주소를 아래 입력값에 사용한다.

현재 공개 가능한 기능은 계정, 프로젝트, 에피소드, 패널, private 이미지 업로드다. AI Story/Image/Motion, Reader, Publish는 아직 구현되지 않았다. AI 키를 입력해도 이 기능들이 생기지 않는다.

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
- 최대 파일: 10 MiB
- MIME: `image/png`, `image/jpeg`, `image/webp`

브라우저는 service-role key를 받지 않는다. FastAPI가 짧게 유효한 capability URL을 발급하고, 이미지 bytes와 MIME/픽셀 제한을 검사한 뒤 새 UUID object로 저장한다. 같은 key에 upsert하지 않는다.

## PART C — Render

### Blueprint 방식

1. [Render Dashboard](https://dashboard.render.com/)에 로그인한다.
2. **New + → Blueprint**를 누른다.
3. GitHub를 연결하고 `heheboi1972/LinkToon`을 선택한다.
4. repository root의 `render.yaml`을 승인한다.
5. `sync: false`로 표시된 값을 아래 표대로 입력한다.

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

### Render Environment Variables

| Key | 입력값 |
| --- | --- |
| `APP_ENV` | `production` |
| `AUTH_MODE` | `supabase` |
| `STORAGE_PROVIDER` | `supabase` |
| `MOCK_AI` | `true` |
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

`OPENAI_API_KEY`, `FAL_KEY`, `RUNWAYML_API_SECRET`은 현재 호출 코드가 없으므로 입력할 필요가 없다. `REDIS_URL`도 현재 worker가 없어서 운영 배포에 필요하지 않다.

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
- [ ] 브라우저 Network 요청이 실제 Render URL로 전송됨
- [ ] GitHub/Vercel browser bundle과 로그에 secret이 없음
- [ ] Story AI — 현재 미구현임을 표시
- [ ] Image AI — 현재 미구현임을 표시
- [ ] Motion/Video — 현재 미구현임을 표시
- [ ] Reader — 현재 미구현
- [ ] Publish — 현재 미구현

운영 공개 전에 Supabase 비용 한도, Render/Vercel 사용량 알림, 백업 정책과 계정 삭제 절차도 조직 정책에 맞게 설정한다. 백엔드의 생성 입구는 UTC 자정 기준으로 Story 10회, Image 5회, Motion/Video 2회를 기본 제한하지만 현재 provider 호출 route는 없다.
