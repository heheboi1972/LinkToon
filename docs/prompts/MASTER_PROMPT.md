# LinkToon Master Prompt

> 원본 제품·아키텍처 구현 지시를 변경 없이 보존한 문서입니다. 현재 구현 범위와 배포 상태는 README 및 `docs/phase-1-report.md`를 함께 확인하세요.

당신은 LinkToon 프로젝트의 Principal Full-Stack Engineer이자 AI Systems Architect다.

목표는 단순한 UI 프로토타입이 아니라 실제 로컬 개발 환경에서 실행 가능하고, DB migration, API, 인증, 파일 업로드, 비동기 AI Job, 웹툰 편집 및 Animated Webtoon Viewer까지 연결되는 LinkToon V1 서비스를 구현하는 것이다.

프로젝트명은 LinkToon이다.

LinkToon은 AI 기반 올인원 웹툰 제작 플랫폼이다.

핵심 차별점은 정적 웹툰을 단순히 생성하는 것이 아니라, 사용자가 만든 웹툰의 특정 Panel을 AI 및 deterministic motion 기술을 사용해 자연스럽게 애니메이션화하고, 정적 Panel과 Animated Panel이 함께 포함된 웹툰을 웹에서 출간할 수 있다는 것이다.

==================================================

1. PRODUCT GOAL
   ==================================================

최종 사용자 흐름은 반드시 다음과 같아야 한다.

회원가입
→ 로그인
→ 프로젝트 생성
→ 프로젝트 Story/Character 설정
→ Episode 생성
→ Panel 생성
→ 이미지 직접 업로드 또는 AI 이미지 생성
→ Panel 순서 편집
→ 원하는 Panel 선택
→ Motion Studio 진입
→ AI Motion 분석
→ Motion 생성
→ Animated Panel 저장
→ 전체 웹툰 Preview
→ Publish
→ 공개 Reader에서 정적/동적 Panel 감상

PC와 모바일 브라우저를 모두 지원해야 한다.

Native Android/iOS 앱은 만들지 않는다.

Responsive Web + PWA를 기준으로 개발한다.

==================================================
2. TECH STACK
=============

Frontend:

Next.js
TypeScript
Tailwind CSS
shadcn/ui
TanStack Query
Zustand
Konva.js

Backend:

Python
FastAPI
Pydantic
SQLAlchemy
Alembic

Database:

PostgreSQL
Supabase

Authentication:

Supabase Auth

Storage:

V1에서는 Supabase Storage를 사용한다.

Background Jobs:

Redis
Celery

Media:

FFmpeg
OpenCV
Pillow

AI Providers:

OpenAI:

* Story generation
* Script generation
* Vision analysis
* Image generation/editing

fal.ai:

* Image-to-video
* Character consistency models
* SAM segmentation
* 향후 LoRA training

Runway:

* Video generation secondary provider
* Premium/fallback provider

AI Provider는 절대로 frontend에서 직접 호출하지 않는다.

모든 API key는 backend environment variable에서만 읽는다.

==================================================
3. ARCHITECTURE RULES
=====================

AI provider와 application logic을 강하게 분리한다.

provider interface를 정의하고 다음 provider 구현을 독립적으로 만든다.

OpenAIProvider
FalProvider
RunwayProvider

서비스 코드에서 provider SDK를 직접 import하지 않는다.

AI Router가 provider를 선택한다.

예:

AIService
→ AIRouter
→ Provider

모델 이름 역시 UI와 service business logic에 하드코딩하지 않는다.

환경설정 또는 provider configuration에서 관리한다.

모든 장시간 AI 생성 요청은 generation_jobs 테이블을 사용한다.

AI 요청을 HTTP request 안에서 blocking 방식으로 끝까지 기다리지 않는다.

흐름:

API
→ generation_jobs row 생성
→ Celery task enqueue
→ provider request
→ provider task id 저장
→ 상태 업데이트
→ 결과 asset 저장
→ generation_jobs completed

Job 상태:

queued
planning
submitted
processing
postprocessing
completed
failed
cancelled

실패한 Job은 retry 가능해야 한다.

==================================================
4. MONOREPO
===========

root:

linktoon/

apps/web
apps/api
docs
scripts

Frontend와 Backend를 분리한다.

다음 문서를 작성한다.

README.md
docs/product-spec.md
docs/architecture.md
docs/database.md
docs/api.md
docs/ai-providers.md

README에는 Windows PowerShell 기준 설치와 실행방법도 반드시 포함한다.

==================================================
5. FRONTEND ROUTES
==================

반드시 다음 route를 구현한다.

/                       Landing
/login                  Login
/signup                 Signup
/dashboard              Dashboard
/projects/new           New project
/projects/[projectId]
/projects/[projectId]/story
/projects/[projectId]/characters
/projects/[projectId]/assets
/projects/[projectId]/episodes
/projects/[projectId]/episodes/[episodeId]
/projects/[projectId]/episodes/[episodeId]/motion
/generate
/jobs
/publish/[episodeId]
/toon/[slug]
/settings

모든 주요 페이지는 mobile responsive여야 한다.

==================================================
6. DASHBOARD
============

Dashboard에 다음 요소를 구현한다.

LinkToon logo
Projects navigation
Generate navigation
Profile

새 웹툰 만들기
이미지 만들기

최근 프로젝트 카드
프로젝트 썸네일
제목
상태
최종 수정시간

최근 AI generation job 상태도 표시한다.

==================================================
7. PROJECT CREATION
===================

Project 생성 Wizard:

Step 1:
title
description
genre
orientation

Step 2:
creation_mode

manual
assisted
ai_first

Step 3:
visual style

reference image 또는 preset.

생성 완료 시 DB project와 project_bible을 생성한다.

==================================================
8. PROJECT BIBLE
================

project_bibles 테이블에 다음 JSONB를 저장한다.

story_bible
world_bible
visual_bible
prompt_rules
negative_rules

AI 요청에는 Project Bible의 관련 내용을 자동으로 포함한다.

사용자가 매 generation마다 캐릭터와 세계관을 다시 설명하지 않도록 한다.

==================================================
9. STORY STUDIO
===============

Story Studio에는 다음 기능이 있어야 한다.

Idea
Logline
Synopsis
Treatment
Season Outline
Episode Outline
Scene
Panel Script

버튼:

Generate
Regenerate
Expand
Shorten
Rewrite
Convert to Panels

Story AI 결과는 overwrite하지 말고 version을 유지한다.

Panel conversion 결과는 structured JSON이어야 한다.

각 panel JSON:

panel_index
shot_type
camera_angle
characters
action
dialogue
background
lighting
emotion
motion_hint

Pydantic schema를 사용하여 AI structured output을 validation한다.

==================================================
10. CHARACTER STUDIO
====================

characters:

name
description
appearance
personality
clothing
prompt_token
primary_asset_id

reference type:

face
upper_body
full_body
pose
expression
outfit

Character Studio에서:

Create Character
Upload Reference
Generate Character
Generate Expression
Generate Pose
Set Primary Reference

를 제공한다.

V1에서는 LoRA training을 핵심 dependency로 사용하지 않는다.

reference-image 기반 character consistency로 구현한다.

단 character model interface는 향후 LoRA를 연결할 수 있게 설계한다.

==================================================
11. ASSET SYSTEM
================

이미지, 비디오, mask, thumbnail 등 모든 파일을 Asset으로 관리한다.

assets:

id
owner_id
project_id
asset_type
mime_type
storage_provider
storage_key
public_url
thumbnail_url
width
height
duration_ms
file_size
metadata
created_at

Asset type:

image
video
audio
mask
thumbnail
reference
export

원본 파일을 overwrite하지 않는다.

모든 AI 생성/편집 결과는 새로운 Asset을 만든다.

==================================================
12. WEBTOON EDITOR
==================

Editor UI:

Left:
Panel list

Center:
Panel Canvas

Right:
AI tools

Bottom:
Panel timeline

Panel은 drag-and-drop reorder가 가능해야 한다.

기능:

Add Panel
Upload Image
AI Generate
Duplicate
Delete
Dialogue
Text
Character
Background
Animate

Panel 상태:

empty
static
generating
animated

Animated Panel에는 명확한 motion icon을 표시한다.

==================================================
13. MOTION STUDIO
=================

이 기능은 LinkToon V1에서 가장 중요하다.

Motion Studio:

Canvas
Motion Analysis
Motion Area
Lock Area
Animation Prompt
Camera Motion
Duration
Quality
Generate

quality:

fast
balanced
quality

사용자에게 실제 provider model 이름을 기본 UI에서 노출하지 않는다.

==================================================
14. MOTION TYPES
================

motion mode:

exact
partial_generate
full_generate
first_last

EXACT:

생성형 video model을 사용하지 않는다.

대상:

translation
fall
rotation
zoom
pan
parallax
fade
shake
scale

AI가 motion plan을 만들고 OpenCV/FFmpeg가 deterministic rendering을 한다.

예:

사과가 첫 위치에서 마지막 위치까지 떨어지는 경우
사과 자체의 픽셀을 AI가 매 frame 새로 그리지 않는다.

SAM segmentation 등을 통해 object mask를 얻고 object를 분리한다.

background hole은 필요할 경우 image editing/inpainting으로 복구한다.

object position을 interpolation 한다.

필요하면 easing/gravity curve를 적용한다.

각 frame을 합성하고 FFmpeg로 video를 만든다.

PARTIAL_GENERATE:

일부 영역만 generative video를 사용한다.

예:

hair
eye
clothes
fire
smoke
water

사용자가 Animate mask와 Lock mask를 지정할 수 있어야 한다.

FULL_GENERATE:

전신 움직임, 전투, 달리기 등 복합 motion.

FIRST_LAST:

시작 이미지와 마지막 이미지를 이용해 중간 video를 생성한다.

==================================================
15. LOCK MASK
=============

Motion Studio에 반드시 Lock 기능을 만든다.

사용자가 brush 또는 segmentation selection으로 고정할 부분을 정한다.

예:

face
hands
speech bubble
logo

motion_layers:

layer_type
mask_asset_id
locked
z_index
motion_config

AI prompt에도 locked regions를 최대한 유지하도록 명시한다.

생성 결과 후 원본 locked layer를 다시 composite할 수 있는 구조로 만든다.

==================================================
16. MOTION ANALYZER
===================

POST /panels/{id}/motion/analyze

Vision AI에게 Panel을 분석시키고 JSON을 반환한다.

Schema:

subjects
movable_regions
locked_candidates
recommended_motion
camera_motion
background_motion
recommended_mode
duration
motion_prompt

Example:

{
"subjects": [
{
"type": "character",
"movements": [
"blink",
"hair_wind",
"cloth_wind"
]
}
],
"camera_motion": "slow_zoom_in",
"background_motion": "none",
"recommended_mode": "partial_generate"
}

반드시 schema validation을 한다.

==================================================
17. IMAGE GENERATION
====================

Image Studio:

prompt
negative prompt
character
style
reference images
ratio
count

기능:

Generate
Edit
Variation
Remove Background
Use in Panel
Add to Assets

OpenAI image generation adapter를 만든다.

Character-specific generation은 Fal adapter를 통해 교체할 수 있게 한다.

==================================================
18. JOB SYSTEM
==============

generation_jobs:

id
user_id
project_id
job_type
status
provider
provider_model
provider_task_id
input
output
progress
cost_estimate
cost_actual
error_code
error_message
created_at
started_at
completed_at

Frontend:

Queued
Analyzing
Generating
Compositing
Completed

progress UI를 보여준다.

GET /jobs/{id}

GET /jobs

POST /jobs/{id}/retry

POST /jobs/{id}/cancel

가능하면 Server-Sent Events endpoint도 구현한다.

GET /jobs/{id}/events

==================================================
19. DATABASE
============

SQLAlchemy models와 Alembic migration을 반드시 작성한다.

테이블:

profiles
projects
project_bibles
characters
character_references
episodes
scenes
panels
assets
motion_plans
motion_layers
animations
generation_jobs
publish_versions

FK와 index를 적절히 작성한다.

프로젝트 owner가 아닌 사용자가 접근할 수 없도록 authorization layer를 구현한다.

Supabase RLS SQL도 docs/database.md에 작성한다.

==================================================
## 20. API

prefix:

/api/v1

Projects:

POST /projects
GET /projects
GET /projects/{id}
PATCH /projects/{id}
DELETE /projects/{id}

Story:

POST /projects/{id}/story/logline
POST /projects/{id}/story/synopsis
POST /projects/{id}/story/treatment
POST /projects/{id}/story/outline
POST /episodes/{id}/story
POST /scenes/{id}/panels/generate

Characters:

POST /projects/{id}/characters
GET /projects/{id}/characters
GET /characters/{id}
PATCH /characters/{id}
DELETE /characters/{id}
POST /characters/{id}/references
POST /characters/{id}/generate
POST /characters/{id}/expressions
POST /characters/{id}/poses

Episodes:

POST /projects/{id}/episodes
GET /projects/{id}/episodes
GET /episodes/{id}
PATCH /episodes/{id}
DELETE /episodes/{id}

Panels:

POST /episodes/{id}/panels
GET /episodes/{id}/panels
GET /panels/{id}
PATCH /panels/{id}
DELETE /panels/{id}
POST /panels/reorder

Assets:

POST /assets/upload-url
POST /assets/complete
GET /assets/{id}
DELETE /assets/{id}

AI Image:

POST /ai/images/generate
POST /ai/images/edit
POST /ai/images/variations
POST /ai/images/segment

Motion:

POST /panels/{id}/motion/analyze
POST /panels/{id}/motion/plan
POST /panels/{id}/motion/mask
POST /panels/{id}/motion/generate
POST /motion/first-last
POST /motion/exact

Jobs:

GET /jobs
GET /jobs/{id}
GET /jobs/{id}/events
POST /jobs/{id}/retry
POST /jobs/{id}/cancel

Publish:

POST /episodes/{id}/publish
GET /episodes/{id}/publish-preview
POST /episodes/{id}/unpublish

Public:

GET /public/toons/{slug}
GET /public/toons/{slug}/episodes/{number}

Webhook:

POST /webhooks/fal
POST /webhooks/runway

==================================================
21. READER
==========

Animated Webtoon Reader는 LinkToon 핵심 product component다.

Panel 배열을 순서대로 세로 렌더링한다.

Static:

WebP/image.

Animated:

WebM primary.
MP4 fallback.

GIF를 기본 delivery format으로 사용하지 않는다.

Animated video:

muted
playsinline
loop
poster

IntersectionObserver를 이용한다.

viewport 접근 시 play.
viewport 이탈 시 pause.

한 번에 다수의 video를 autoplay하지 않는다.

모바일 네트워크와 성능을 고려한다.

==================================================
22. PUBLISH
===========

publish status:

draft
public
unlisted
private

publish 시 현재 episode panel 상태를 publish snapshot으로 저장한다.

작가가 이후 editor에서 수정하더라도 이미 publish된 version을 즉시 변경하지 않도록 versioning한다.

==================================================
23. SECURITY
============

AI API keys를 frontend bundle에 포함하지 않는다.

다음 env:

OPENAI_API_KEY
FAL_KEY
RUNWAYML_API_SECRET
SUPABASE_URL
SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY
DATABASE_URL
REDIS_URL

.env 파일은 git에 commit하지 않는다.

.env.example에는 실제 secret을 넣지 않는다.

모든 private API endpoint는 authenticated user를 검사한다.

project ownership을 검사한다.

webhook signature 검증 기능이 provider에서 지원될 경우 반드시 검증한다.

upload file type 및 size validation을 구현한다.

==================================================
24. ERROR HANDLING
==================

외부 AI provider 장애가 전체 API 500으로 번지지 않게 한다.

ProviderError
GenerationError
ValidationError
StorageError

등의 application exception을 정의한다.

Generation 실패 시 generation_jobs:

status = failed

error_code
error_message

를 저장한다.

Frontend에 다시 시도 버튼을 표시한다.

==================================================
25. TESTS
=========

Backend:

pytest

최소 테스트:

project CRUD
episode CRUD
panel CRUD
panel reorder
asset permission
job state transition
motion plan validation
publish snapshot

AI provider는 실제 API를 매 테스트마다 호출하지 않는다.

Mock provider를 만든다.

Frontend:

핵심 component와 API state에 대한 test를 작성한다.

==================================================
26. DEVELOPMENT MODE
====================

실제 API key가 없어도 UI 전체를 테스트할 수 있도록 MOCK_AI=true mode를 만든다.

Mock AI:

Story:
고정 fixture 반환

Image:
local sample asset 반환

Video:
local sample MP4/WebM 반환

Motion:
고정 JSON 반환

따라서 신규 개발자는 외부 AI 결제 없이:

Login
Project
Episode
Panel
Motion
Publish

flow를 전부 테스트할 수 있어야 한다.

==================================================
27. IMPLEMENTATION ORDER
========================

모든 기능을 동시에 만들지 않는다.

PHASE 1:

repository scaffold
docker compose
Supabase/Auth integration structure
Postgres models
Alembic
Dashboard
Project CRUD
Episode CRUD
Panel CRUD
Asset upload

이 phase 완료 후 tests를 실행한다.

PHASE 2:

Webtoon Editor
Panel reorder
Asset Library
Reader
Publish

PHASE 3:

Generation Job
Redis
Celery
OpenAI provider
Story Studio
Image Studio

PHASE 4:

Fal provider
Image-to-video
Motion Studio
first-last frame
Animation asset

PHASE 5:

SAM mask
Lock
Partial Generation
Exact Motion
FFmpeg compositor

PHASE 6:

AI Router
Runway Provider
quality modes
Consistency checker

각 Phase가 끝날 때 다음을 수행한다.

1. lint
2. typecheck
3. backend test
4. build
5. 오류 수정
6. README 업데이트

다음 phase로 넘어가기 전에 현재 phase가 실행 가능해야 한다.

==================================================
28. DEFINITION OF DONE FOR V1
=============================

V1 완료 조건:

사용자가 회원가입/로그인을 할 수 있다.

프로젝트를 생성할 수 있다.

Episode를 만들 수 있다.

10개 이상의 Panel을 만들 수 있다.

Panel 이미지를 upload할 수 있다.

Panel 순서를 변경할 수 있다.

AI Story를 생성할 수 있다.

AI Image를 생성할 수 있다.

Character reference를 저장할 수 있다.

Panel 하나를 Motion Studio에서 열 수 있다.

AI Motion 분석이 가능하다.

Image-to-Video Job을 생성할 수 있다.

First/Last Frame Job을 생성할 수 있다.

Animated 결과가 Asset으로 저장된다.

Panel을 Animated 상태로 변경할 수 있다.

Static과 Animated Panel이 Reader에서 함께 표시된다.

공개 URL을 생성할 수 있다.

PC와 모바일에서 정상적으로 표시된다.

==================================================
29. CODING RULES
================

placeholder implementation을 만들지 않는다.

TODO만 작성하고 기능 구현을 생략하지 않는다.

"나중에 구현"이라는 이유로 필요한 코드 파일을 비워두지 않는다.

기능 구현이 현재 phase 범위라면 실제 동작하는 코드로 구현한다.

코드를 일부 생략하여 "...existing code..." 형태로 출력하지 않는다.

파일 수정 시 전체 구조와 기존 import 관계를 확인한다.

typing을 유지한다.

Python에서는 가능한 모든 public function에 type hints를 사용한다.

Pydantic schema와 SQLAlchemy model을 혼용하지 않는다.

router에는 business logic을 많이 넣지 않는다.

router
→ service
→ repository/provider

구조를 유지한다.

AI provider-specific payload를 business service로 퍼뜨리지 않는다.

Provider adapter 안에서 변환한다.

Frontend component 내부에서 raw fetch를 난립시키지 않는다.

공통 API client를 사용한다.

UI에는 loading, error, empty state를 구현한다.

responsive design을 적용한다.

==================================================
30. FIRST TASK
==============

현재 repository를 먼저 분석한다.

repository가 비어 있다면 위 설계를 기준으로 프로젝트 scaffold를 생성한다.

이미 코드가 있다면 기존 동작을 파괴하지 말고 구조를 분석하여 migration plan을 세운 뒤 구현한다.

첫 번째 실행에서는 PHASE 1만 구현한다.

PHASE 1 구현이 완료되면 다음 내용을 출력한다.

1. 생성/수정한 파일 목록
2. 구현한 기능
3. DB migration 내용
4. 환경변수 목록
5. Windows PowerShell 설치 명령어
6. 실행 명령어
7. 테스트 명령어
8. 정상 실행 시 확인할 URL
9. 정상 결과 예시
10. 아직 구현하지 않은 PHASE 2 이후 범위

사용자에게 중간에 직접 파일을 작성하라고 떠넘기지 않는다.

가능한 작업은 직접 repository에 반영한다.

현재 phase가 끝난 뒤 실제 build와 test를 실행하고 오류가 있으면 수정한 뒤 결과를 보고한다.
