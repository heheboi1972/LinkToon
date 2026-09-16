# Phase 1 완료 보고서

검증일: 2026-09-15. 최초 저장소에는 `.git`만 있었으며 기존 애플리케이션 코드는 없었다. 기존 코드를 이전하거나 덮어쓴 작업은 없다. 이번 실행은 사용자의 마지막 범위 지시에 따라 Phase 1까지만 구현했다.

## 1. 생성·수정 파일

Next.js 앱, FastAPI 서비스, SQLAlchemy 모델, Alembic, 테스트, Docker 구성, PowerShell 실행 도구, 제품/설계/운영 문서를 새로 작성했다. 전체 파일 목록은 이 문서 마지막에 있다. `.env`, local DB, 업로드 이미지, 임시 PostgreSQL 바이너리 및 빌드 산출물은 git ignore에 포함된다. 커밋/원격 push/배포는 하지 않았다.

## 2. 구현 기능

- local signup/login/logout, Supabase Auth 연결 및 서버 토큰 검증
- 반응형 Dashboard, 검색·상태 필터·카드/목록·표지·최근 job 조회
- 프로젝트 3단계 Wizard와 CRUD, 동시에 Project Bible 생성/조회
- 에피소드 CRUD, 자동 번호 배정
- 10개 이상의 패널 CRUD, 장면 설명·대사·이미지 연결/교체/해제
- signed upload ticket, 실제 이미지 검증, Supabase/로컬 private 저장소 adapter
- owner authorization, 자산 cross-project 연결 차단, 사용 중인 파일 삭제 방지
- 로딩/오류/빈 상태, 재시도, 삭제 확인 UI, 모바일 메뉴
- PWA manifest/아이콘 기반
- health/readiness, migration revision 검증, capability query 로그 마스킹

## 3. DB migration

revision `0001`: 요구된 14개 테이블 + Alembic revision table. UUID PK, FK/소유자·정렬 index, JSONB, status/type/progress constraints, episode/panel/version uniqueness. 프로젝트-표지의 순환 FK를 PostgreSQL에서 별도 추가한다. PostgreSQL/SQLite migration upgrade/downgrade와 metadata drift 검사를 통과했다. RLS SQL은 private bucket, 소유자 SELECT, browser write 금지, password_hash column 접근 금지를 포함한다.

## 4. 환경변수

`.env.example`과 README 환경변수 표에 전체 목록이 있다. local 실행은 setup이 만든 signing secret만으로 동작하며 외부 AI/Supabase 결제가 필요 없다. Supabase로 전환할 때 URL, anon/service role key와 DB URL이 필요하다. OPENAI_API_KEY/FAL_KEY/RUNWAYML_API_SECRET은 후속 Phase용 이름만 준비했다.

## 5. Windows 설치

```powershell
.\scripts\setup.ps1
# Docker PostgreSQL을 선택하는 새 설치:
docker compose up -d db redis
.\scripts\setup.ps1 -Postgres
```

Node 22+, uv, Python 3.12 필요. setup은 .env를 새로 생성할 때만 작성한다. 기존 .env는 보존한다. 정책을 변경하지 않는 직접 실행 명령과 Python 경로 지정 방법은 README에 있다.

## 6. 실행

```powershell
# 터미널 1
.\scripts\start-api.ps1
# 터미널 2
npm run dev
# 프로덕션 번들 확인
npm run build
npm run start
```

## 7. 테스트와 결과

| 검증 | 실제 결과 |
| --- | --- |
| Web ESLint | 통과, 경고 0 |
| Next route typegen + TypeScript | 통과 |
| Vitest | **8 passed** |
| Next production build | 통과 |
| Python Ruff (API + scripts) | 통과 |
| Mypy strict | **14 source files**, 오류 0 |
| Pytest / SQLite | **21 passed, 1 skipped**. Skip은 PostgreSQL 전용 RLS |
| Pytest / 실제 PostgreSQL | **22 passed** |
| Alembic check | schema drift 없음 |
| PostgreSQL RLS | 소유자 조회·다른 소유자 차단·anon 차단·password_hash 차단·write 차단 검증 |
| Browser / desktop | 가입 → 프로젝트 → 에피소드 → 패널 → 실제 PNG 업로드 → 대사 저장 확인 |
| Browser / mobile 390×844 | 패널 표시, 메뉴, 가로 넘침 없음 확인 |
| 영속성 | 저장 후 새로고침으로 이미지·장면·대사 보존 확인 |
| 패널 개수 | API 테스트 12개, 브라우저 실제 작업실 10개 생성 확인 |
| 비밀값 | 실제 .env/DB/이미지 git ignore 확인, 공개 config에 signing/service key 제외 |

```powershell
.\scripts\check.ps1
# PostgreSQL 검증 도구 (선택)
node scripts/test-postgres.mjs
```

pytest 실행에 Starlette/httpx 및 anyio의 upstream deprecation warning 2개가 있으나 assertion 실패는 없다. 테스트 시 실제 유료 AI는 호출하지 않는다.

이 PC에 Docker 실행 파일이 없어 Compose 컨테이너를 실제로 빌드/기동하지 않았다. 대신 isolated PostgreSQL 18 바이너리와 순수 Python pg8000 driver로 실제 DB 테스트를 실행했다. Compose는 PostgreSQL 17을 지정하고 있다. Windows native psycopg DLL은 PC의 application-control 정책에서 차단되어 pg8000으로 검증했다. 정책을 변경하지 않았다.

Supabase adapter는 mock HTTP로, RLS SQL은 Supabase의 role/auth.uid 인터페이스를 재현한 실제 PostgreSQL에서 검증했다. 실제 Supabase tenant의 이메일·Storage 요청은 credential이 없어 실행하지 않았다.

## 8. URL

- http://localhost:3000 — 랜딩
- http://localhost:3000/signup — 신규 계정
- http://localhost:3000/dashboard — 작업실
- http://localhost:3000/projects/new — 새 프로젝트
- http://localhost:8000/docs — API 문서
- http://localhost:8000/health — 프로세스 상태
- http://localhost:8000/ready — DB/revision 준비 상태

## 9. 정상 결과 예시

브라우저 검증용 프로젝트 `달빛이 머무는 도시`와 에피소드 `01. 마지막 불빛`, 패널 10개를 로컬 DB에 남겼다. 첫 패널은 `도시의 마지막 밤`, 이미지와 대사 `아직, 우리의 이야기는 끝나지 않았어.`를 저장했다. 검증 계정은 개발 환경에만 존재한다. 사용자는 별도의 계정을 만들어 자신의 작업실을 사용할 수 있다.

`GET /ready`는 `{"status":"ready"}`를 반환하며, 잘못된 DB revision은 503이다. 이미지가 없는 패널은 empty, ready image를 연결하면 static이다. 다른 계정의 자원 조회는 404, 사용 중인 자산 삭제는 409, 타입/크기 위조 업로드는 415/413으로 거부된다.

## 10. 아직 구현하지 않은 범위

- Phase 2: Konva Editor, drag reorder, 복제, 완전한 Asset Library, Reader, publish snapshot/공개 URL.
- Phase 3: Celery worker와 Job lifecycle/retry/cancel/SSE, OpenAI Story/Image, AI output schema/Story version, 전체 Mock AI flow, Character UI/reference 연결.
- Phase 4: Fal image-to-video/first-last, Motion Studio, animation 결과 연결.
- Phase 5: SAM/brush mask/Lock/partial/exact/FFmpeg compositor.
- Phase 6: AIRouter 품질 라우팅, Runway, consistency checker.

현재는 AI key 없이 Phase 1 flow를 검증할 수 있다. `MOCK_AI=true`만으로 Motion/Publish까지 실행 가능한 V1 완성 상태는 아니다. 사용자가 지정한 첫 실행 범위를 지켰으며 이후 Phase로 임의로 넘어가지 않았다.

## 전체 파일 목록

- [.dockerignore](<../.dockerignore>)
- [.env.example](<../.env.example>)
- [.gitignore](<../.gitignore>)
- [README.md](<../README.md>)
- [apps/api/Dockerfile](<../apps/api/Dockerfile>)
- [apps/api/alembic.ini](<../apps/api/alembic.ini>)
- [apps/api/alembic/env.py](<../apps/api/alembic/env.py>)
- [apps/api/alembic/script.py.mako](<../apps/api/alembic/script.py.mako>)
- [apps/api/alembic/versions/0001_v1_relational_foundation.py](<../apps/api/alembic/versions/0001_v1_relational_foundation.py>)
- [apps/api/app/__init__.py](<../apps/api/app/__init__.py>)
- [apps/api/app/assets.py](<../apps/api/app/assets.py>)
- [apps/api/app/auth.py](<../apps/api/app/auth.py>)
- [apps/api/app/config.py](<../apps/api/app/config.py>)
- [apps/api/app/db.py](<../apps/api/app/db.py>)
- [apps/api/app/errors.py](<../apps/api/app/errors.py>)
- [apps/api/app/logging.py](<../apps/api/app/logging.py>)
- [apps/api/app/main.py](<../apps/api/app/main.py>)
- [apps/api/app/models.py](<../apps/api/app/models.py>)
- [apps/api/app/repository.py](<../apps/api/app/repository.py>)
- [apps/api/app/routes.py](<../apps/api/app/routes.py>)
- [apps/api/app/schemas.py](<../apps/api/app/schemas.py>)
- [apps/api/app/services.py](<../apps/api/app/services.py>)
- [apps/api/app/storage.py](<../apps/api/app/storage.py>)
- [apps/api/pyproject.toml](<../apps/api/pyproject.toml>)
- [apps/api/tests/conftest.py](<../apps/api/tests/conftest.py>)
- [apps/api/tests/test_assets.py](<../apps/api/tests/test_assets.py>)
- [apps/api/tests/test_infrastructure.py](<../apps/api/tests/test_infrastructure.py>)
- [apps/api/tests/test_rls.py](<../apps/api/tests/test_rls.py>)
- [apps/api/tests/test_workspace.py](<../apps/api/tests/test_workspace.py>)
- [apps/api/uv.lock](<../apps/api/uv.lock>)
- [apps/web/Dockerfile](<../apps/web/Dockerfile>)
- [apps/web/components.json](<../apps/web/components.json>)
- [apps/web/eslint.config.mjs](<../apps/web/eslint.config.mjs>)
- [apps/web/next-env.d.ts](<../apps/web/next-env.d.ts>)
- [apps/web/next.config.ts](<../apps/web/next.config.ts>)
- [apps/web/package.json](<../apps/web/package.json>)
- [apps/web/postcss.config.mjs](<../apps/web/postcss.config.mjs>)
- [apps/web/public/icon.svg](<../apps/web/public/icon.svg>)
- [apps/web/public/manifest.webmanifest](<../apps/web/public/manifest.webmanifest>)
- [apps/web/public/studio-art.svg](<../apps/web/public/studio-art.svg>)
- [apps/web/src/app/(workspace)/dashboard/page.tsx](<../apps/web/src/app/(workspace)/dashboard/page.tsx>)
- [apps/web/src/app/(workspace)/generate/page.tsx](<../apps/web/src/app/(workspace)/generate/page.tsx>)
- [apps/web/src/app/(workspace)/jobs/page.tsx](<../apps/web/src/app/(workspace)/jobs/page.tsx>)
- [apps/web/src/app/(workspace)/layout.tsx](<../apps/web/src/app/(workspace)/layout.tsx>)
- [apps/web/src/app/(workspace)/projects/[projectId]/assets/page.tsx](<../apps/web/src/app/(workspace)/projects/[projectId]/assets/page.tsx>)
- [apps/web/src/app/(workspace)/projects/[projectId]/episodes/[episodeId]/page.tsx](<../apps/web/src/app/(workspace)/projects/[projectId]/episodes/[episodeId]/page.tsx>)
- [apps/web/src/app/(workspace)/projects/[projectId]/episodes/page.tsx](<../apps/web/src/app/(workspace)/projects/[projectId]/episodes/page.tsx>)
- [apps/web/src/app/(workspace)/projects/[projectId]/page.tsx](<../apps/web/src/app/(workspace)/projects/[projectId]/page.tsx>)
- [apps/web/src/app/(workspace)/projects/[projectId]/story/page.tsx](<../apps/web/src/app/(workspace)/projects/[projectId]/story/page.tsx>)
- [apps/web/src/app/(workspace)/projects/new/page.tsx](<../apps/web/src/app/(workspace)/projects/new/page.tsx>)
- [apps/web/src/app/(workspace)/projects/page.tsx](<../apps/web/src/app/(workspace)/projects/page.tsx>)
- [apps/web/src/app/(workspace)/settings/page.tsx](<../apps/web/src/app/(workspace)/settings/page.tsx>)
- [apps/web/src/app/error.tsx](<../apps/web/src/app/error.tsx>)
- [apps/web/src/app/globals.css](<../apps/web/src/app/globals.css>)
- [apps/web/src/app/layout.tsx](<../apps/web/src/app/layout.tsx>)
- [apps/web/src/app/login/page.tsx](<../apps/web/src/app/login/page.tsx>)
- [apps/web/src/app/not-found.tsx](<../apps/web/src/app/not-found.tsx>)
- [apps/web/src/app/page.tsx](<../apps/web/src/app/page.tsx>)
- [apps/web/src/app/signup/page.tsx](<../apps/web/src/app/signup/page.tsx>)
- [apps/web/src/components/asset-image.tsx](<../apps/web/src/components/asset-image.tsx>)
- [apps/web/src/components/auth-form.tsx](<../apps/web/src/components/auth-form.tsx>)
- [apps/web/src/components/dashboard.test.tsx](<../apps/web/src/components/dashboard.test.tsx>)
- [apps/web/src/components/dashboard.tsx](<../apps/web/src/components/dashboard.tsx>)
- [apps/web/src/components/episode-detail.tsx](<../apps/web/src/components/episode-detail.tsx>)
- [apps/web/src/components/project-assets.tsx](<../apps/web/src/components/project-assets.tsx>)
- [apps/web/src/components/project-bible.tsx](<../apps/web/src/components/project-bible.tsx>)
- [apps/web/src/components/project-detail.tsx](<../apps/web/src/components/project-detail.tsx>)
- [apps/web/src/components/project-wizard.tsx](<../apps/web/src/components/project-wizard.tsx>)
- [apps/web/src/components/providers.tsx](<../apps/web/src/components/providers.tsx>)
- [apps/web/src/components/shell.tsx](<../apps/web/src/components/shell.tsx>)
- [apps/web/src/components/states.tsx](<../apps/web/src/components/states.tsx>)
- [apps/web/src/components/ui/button.tsx](<../apps/web/src/components/ui/button.tsx>)
- [apps/web/src/components/ui/input.tsx](<../apps/web/src/components/ui/input.tsx>)
- [apps/web/src/lib/api.test.ts](<../apps/web/src/lib/api.test.ts>)
- [apps/web/src/lib/api.ts](<../apps/web/src/lib/api.ts>)
- [apps/web/src/lib/store.ts](<../apps/web/src/lib/store.ts>)
- [apps/web/src/lib/types.ts](<../apps/web/src/lib/types.ts>)
- [apps/web/src/lib/utils.ts](<../apps/web/src/lib/utils.ts>)
- [apps/web/src/test/setup.ts](<../apps/web/src/test/setup.ts>)
- [apps/web/tsconfig.json](<../apps/web/tsconfig.json>)
- [apps/web/vitest.config.ts](<../apps/web/vitest.config.ts>)
- [compose.yaml](<../compose.yaml>)
- [docs/ai-providers.md](<../docs/ai-providers.md>)
- [docs/api.md](<../docs/api.md>)
- [docs/architecture.md](<../docs/architecture.md>)
- [docs/database.md](<../docs/database.md>)
- [docs/phase-1-report.md](<../docs/phase-1-report.md>)
- [docs/product-spec.md](<../docs/product-spec.md>)
- [package-lock.json](<../package-lock.json>)
- [package.json](<../package.json>)
- [scripts/check.ps1](<../scripts/check.ps1>)
- [scripts/cleanup-assets.py](<../scripts/cleanup-assets.py>)
- [scripts/make-sample.py](<../scripts/make-sample.py>)
- [scripts/setup.ps1](<../scripts/setup.ps1>)
- [scripts/start-api.ps1](<../scripts/start-api.ps1>)
- [scripts/supabase-rls.sql](<../scripts/supabase-rls.sql>)
- [scripts/test-postgres.mjs](<../scripts/test-postgres.mjs>)
