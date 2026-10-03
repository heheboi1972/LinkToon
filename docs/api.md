# LinkToon API

Base URL은 개발에서 `http://localhost:8000/api/v1`, 운영에서 `NEXT_PUBLIC_API_URL + /api/v1`이다. 대화형 전체 스키마는 `/docs`, JSON 스키마는 `/openapi.json`.

인증 헤더: `Authorization: Bearer <access_token>`. GET `/config`, 로컬 가입/로그인, `/health`, `/ready`, 활성 public/unlisted Publication Reader/media만 공개다. 업로드/미디어 URL에는 resource별 만료 토큰이 필요하다. 외부 계정의 리소스는 404. 입력 스키마 오류 422, 로그인 필요 401, 충돌 409, 파일 초과 413, 잘못된 이미지 415.

```json
{"error":{"code":"not_found","message":"Project not found"}}
```

Pydantic의 422는 표준 `detail` 배열이다. 프런트엔드 공통 client가 양쪽 오류 형식을 처리한다.

| Method | Path | 동작 |
| --- | --- | --- |
| GET | `/config` | 안전한 공개 client 설정 |
| POST | `/auth/signup` | local 전용 가입. email, password(10~128), display_name |
| POST | `/auth/login` | local 전용 로그인. email, password |
| GET | `/auth/me` | 현재 profile. Supabase 사용자 첫 방문 시 profile 동기화 |
| POST / GET | `/projects` | 프로젝트 생성 / 소유 프로젝트 목록 |
| GET / PATCH / DELETE | `/projects/{id}` | 프로젝트 조회·설정 변경·삭제 |
| GET | `/projects/{id}/bible` | 생성 시 저장한 Bible 조회 |
| GET | `/projects/{id}/overview` | 소유 프로젝트의 실 DB 제작 현황 metric 조회 |
| GET | `/projects/{id}/characters` | 소유 프로젝트의 Character 목록. `limit`/`offset` 지원 |
| POST | `/projects/{id}/stories/generate` | 구조화 Story 생성 Job 접수. `Idempotency-Key` 필수, 202 |
| POST / GET | `/projects/{id}/episodes` | 에피소드 생성 / 번호순 목록 |
| GET / PATCH / DELETE | `/episodes/{id}` | 에피소드 조회·수정·삭제 |
| GET | `/episodes/{id}/reader` | 소유 에피소드의 읽기 전용 Story Scene과 private media capability 조회 |
| POST | `/episodes/{id}/publish` | 최소 1개 Scene 확인 후 stable slug와 첫 immutable snapshot 생성 |
| GET | `/episodes/{id}/publication` | 소유 에피소드의 게시 상태 조회 |
| PATCH | `/publications/{id}` | 소유 Publication 제목·설명·visibility 변경 |
| POST | `/publications/{id}/republish` | draft의 현재 Scene을 새 snapshot version으로 명시적 게시 |
| POST | `/publications/{id}/unpublish` | URL을 즉시 비활성화하되 snapshot과 slug 보존 |
| GET | `/publications/{slug}` | 로그인 없는 public/unlisted Reader read model 조회 |
| GET | `/publications/{slug}/assets/{asset_id}/content?token=...` | 현재 노출 중인 snapshot에 참조된 Asset에만 scoped capability media 반환; Range 지원 |
| GET | `/scenes/{id}` | owner-scoped Scene과 현재 `image_asset_id` 조회 |
| POST | `/scenes/{id}/image/generate` | Scene 이미지 생성 Job 접수. `Idempotency-Key` 필수, 202 |
| POST | `/scenes/{id}/video/generate` | Scene Motion Job 접수. `Idempotency-Key` 필수, 202 |
| POST / GET | `/episodes/{id}/panels` | 패널 추가 / position순 목록 |
| GET / PATCH / DELETE | `/panels/{id}` | 패널 조회·수정·삭제 |
| POST | `/assets/upload-url` | 업로드 ticket 발급. pending Asset 생성 |
| PUT | `/assets/{id}/upload?token=...` | 이미지 bytes 검증·저장 |
| POST | `/assets/complete` | 업로드 확인 및 ready 전환. idempotent |
| GET | `/projects/{id}/assets` | 완료된 이미지 자산 목록 |
| GET / DELETE | `/assets/{id}` | 자산 메타데이터/만료 URL 조회, 미사용 자산 삭제 |
| GET | `/assets/{id}/content?token=...` | 이미지 바이트 전달 |
| GET | `/jobs` | 소유자 job 목록 |
| GET | `/jobs/{id}` | 소유자 job 상세 입력·결과·상태 조회 |
| POST | `/jobs/{id}/cancel` | 대기/처리 중인 소유자 job 취소 |
| GET | `/quotas` | Story/Image/Motion UTC 일일 사용량과 잔여량 |

목록에는 `limit`(1~200), `offset`(0 이상)을 사용할 수 있다. 프로젝트/에피소드 기본 limit 100, 패널/자산 200, jobs 20. UI는 프로젝트·에피소드·패널·자산에서 최신/처음 200개를 보여준다. 대규모 무한 스크롤은 Phase 2 범위다.

## 주요 payload

프로젝트 생성:

```json
{"title":"달빛 도시","description":"도시의 불빛을 지키는 이야기","genre":"fantasy","orientation":"vertical","creation_mode":"manual","visual_style":"cinematic"}
```

프로젝트 수정 가능 필드: `title`, `description`, `genre`, `status`(draft/active/archived), `thumbnail_asset_id`. 소유자와 생성 방식은 patch로 변경하지 않는다.

에피소드 생성/수정: `title`, `description`. `number`는 서버가 배정한다. Publish visibility/status는 Publication API로만 변경한다.

`GET /episodes/{id}/reader`는 인증된 소유자만 사용할 수 있다. 응답은 에피소드 제목·줄거리와 `position` 순서로 정렬한 Scene 제목·내레이션·대사 및 ready image/video의 짧은 capability URL만 포함한다. Prompt, GenerationJob, storage 경로, provider metadata는 포함하지 않는다. Scene이 없으면 빈 `scenes` 배열을 반환하며 연결 Asset이 없거나 현재 프로젝트의 ready media가 아니면 해당 URL은 `null`이다. Capability URL은 만료 전에 다시 발급해야 한다.

## Publish와 Public Reader

최초 게시 요청은 Episode 소유권과 Scene 1개 이상을 검사한다. 이미지 없는 Text-only Scene도 허용한다.

```json
{"title":"작품에 표시할 제목","description":"짧은 소개","visibility":"unlisted"}
```

`visibility`는 `public`, `unlisted`, `private`다. Public/unlisted slug는 제목 편집이나 다시 게시 후에도 유지된다. 같은 Episode에 대한 최초 publish 재시도는 현재 Publication을 돌려주며 snapshot version을 늘리지 않는다. Story/Scene 변경은 이미 게시된 snapshot에 자동 반영되지 않는다. `POST /publications/{id}/republish`에서만 다음 버전이 생성되고 활성화된다. `unpublish`는 기존 버전과 slug를 보존하면서 public access를 즉시 차단한다.

`GET /publications/{slug}`는 로그인 없이 public/unlisted만 반환하며 private나 미게시 slug는 404다. 응답에는 화면 표시 제목/소개/작성자 표시 이름/게시일과 정제된 Scene narration/dialogue, 짧은 media URL만 있다. owner email, source Scene/Asset ID, prompt, job, provider 정보와 Storage key는 반환하지 않는다. Public media token은 publication ID/version과 Asset ID에 묶여 15분간 유효하다. 요청 시 publication이 여전히 공개 상태인지, Asset이 활성 snapshot에 포함되는지 다시 확인한다. Storage bucket은 계속 private다. Unlisted에는 `noindex`를 적용한다.

`ProjectOverviewOut`의 episode/scene/image/motion/character/reference/publication count는 소유 project row를 통해 DB에서 집계한다. 실패 응답을 임의의 0으로 표시하지 않는다.

패널 생성/수정: `title`, `description`, `dialogue`, `image_asset_id`. 상태는 이미지 연결에 따라 empty/static으로 서버가 결정한다. position을 patch할 수 없으며 재정렬은 Phase 2에 추가한다.

업로드:

```json
{"project_id":"<uuid>","filename":"panel.png","mime_type":"image/png","file_size":34567,"asset_type":"image"}
```

응답:

```json
{"asset_id":"<uuid>","upload_url":"http://localhost:8000/api/v1/assets/<uuid>/upload?token=<signed>","method":"PUT","expires_in":900}
```

`upload_url`에 `Content-Type: image/png`로 원본 bytes를 PUT한 뒤 `/assets/complete`에 `{"asset_id":"<uuid>"}`를 POST한다. 이후 패널에 `{"image_asset_id":"<uuid>"}` PATCH. 연결 해제는 null. 이미지 교체는 새 업로드/Asset을 만든 뒤 새 ID로 연결한다.

asset response에는 id/owner_id/project_id/type/mime/storage provider/bucket/key, source, 생성 provider/task/job 연결, prompt, dimensions, size, created_at, metadata, upload_status와 15분 media URL이 포함된다. 업로드 자산의 source는 `upload`, 이후 worker가 만들 생성 자산은 `generated`다. DB의 public_url column은 private 원본에 대해 null이며 API가 만료 URL을 계산해서 반환한다.

Job 상태는 `queued`, `running`, `provider_pending`, `saving`, `succeeded`, `failed`, `canceled` 중 하나다. 상세 응답에는 provider에 전달할 정규화 입력과 저장된 결과가 포함되며, 재시도용 원본 provider 응답과 worker lease는 노출하지 않는다. 완료된 `succeeded`/`failed` 작업의 취소는 409다. 다른 사용자의 job ID는 조회와 취소 모두 404다.

## Story 생성

`POST /projects/{project_id}/stories/generate`는 HTTP 요청 안에서 OpenAI 응답을 기다리지 않는다. 인증과 프로젝트 소유권, UTC 일일 Story 한도, 입력을 검증한 뒤 `202 Accepted`로 `queued` Job을 반환한다. 요청마다 안정적인 `Idempotency-Key` header가 필요하다.

```http
POST /api/v1/projects/<project_uuid>/stories/generate
Authorization: Bearer <access_token>
Idempotency-Key: story-draft-2026-09-21-01
Content-Type: application/json
```

```json
{
  "idea": "달빛을 잃은 도시에서 두 친구가 마지막 등대를 찾는다.",
  "genre": "fantasy",
  "tone": "hopeful and cinematic",
  "theme": "우정과 책임",
  "characters": ["<project-character-uuid>"],
  "scene_count": 6
}
```

`idea`는 필수이며 `scene_count`는 1~20이다. `genre`를 생략하면 Project 장르를 사용하고 `characters`에는 이 Project에 등록된 Character UUID를 최대 20개까지 중복 없이 지정할 수 있다. 서버는 모든 UUID의 프로젝트 소속을 검증한 뒤 이름, 설명, 외형, 성격과 의상을 provider context에 추가한다. Client는 provider나 model을 지정할 수 없다.

Character API는 `POST /projects/{project_id}/characters`, `GET /projects/{project_id}/characters`, `GET /characters/{id}`, `PATCH /characters/{id}`, `DELETE /characters/{id}`를 제공한다. 응답에는 구조화된 `character_bible`, `appearance_lock`, `style_lock`, `character_revision`, `reference_asset_id`, `reference_stale`가 포함된다. 모든 조회와 mutation은 Project owner로 제한된다. Scene script가 참조 중인 Character는 저장된 Story를 보존하기 위해 삭제할 수 없다.

기존 ready image를 `PUT /characters/{id}/reference` body `{ "asset_id": "..." }`로 canonical reference로 선택할 수 있고, `DELETE /characters/{id}/reference`로 연결만 해제할 수 있다. Asset 자체는 삭제되지 않으며 `character_references` history와 immutable Asset을 보존한다. Character Bible을 수정하면 revision이 증가하고 기존 reference는 `reference_stale=true`가 된다.

`POST /characters/{id}/reference/generate`는 `Idempotency-Key`를 받아 202 `character:reference` Job을 만든다. Worker는 Bible/lock prompt를 OpenAI Image API로 생성(개발 환경은 Mock)하고 새 private image Asset을 저장한 뒤 Character의 canonical reference와 history row에 연결한다. 같은 Character의 활성 reference job은 하나만 허용된다.

같은 사용자의 같은 `Idempotency-Key`와 같은 요청은 기존 Job을 반환한다. 같은 key를 다른 입력이나 프로젝트에 재사용하면 409다. 일일 한도 초과는 429, 외부 사용자 프로젝트는 404, 존재하지 않거나 다른 프로젝트에 속한 Character와 schema 오류는 422다.

접수 응답은 최소 Job 식별자만 반환한다.

```json
{"job_id":"<job-uuid>","status":"queued"}
```

Client는 `GET /jobs/{job_id}`로 상세 상태를 조회한다. 상세 응답에는 `project_id`, `job_type=story:generate`, 입력, 진행률, 오류와 `output`이 포함된다. 성공한 `output`에는 Story 구조, `episode_id`, `scene_ids`, `asset_ids`와 Mock 여부가 있다. Provider 이름, 모델, provider task ID와 provider metadata는 client 응답에서 제외된다. 생성은 기존 Episode를 덮어쓰지 않으며 Worker가 새 Episode와 모든 Scene을 한 transaction으로 저장한다.

프로젝트의 `/story` 화면은 기존 Bible 아래에서 Story 입력과 결과를 표시한다. 공통 인증 API client가 202 Job을 접수하고, TanStack Query가 `queued`, `running`, `provider_pending`, `saving`을 약 2초 간격으로 조회한다. `succeeded`, `failed`, `canceled`에서 polling을 멈추고 단계·오류를 사용자용 문구로 보여준다. 브라우저 `sessionStorage`에는 사용자·프로젝트별 Job ID와 idempotency key만 저장해 같은 탭의 새로고침 후 Job 조회를 재개한다. 성공 시 제목·줄거리·순서가 있는 장면의 서술·대사를 보여주고 `episode_id`의 새 초안 에피소드로 연결한다. 네트워크 재시도는 같은 key, 사용자의 명시적 다시 생성은 새 key를 사용한다.

로컬에서 API와 Worker를 실행한 뒤 다음과 같이 확인할 수 있다. 기본 `.env`의 `MOCK_AI=true`에서는 외부 비용 없이 같은 흐름을 처리한다.

```powershell
$headers = @{
  Authorization = 'Bearer <access_token>'
  'Idempotency-Key' = [guid]::NewGuid().ToString()
}
$body = @{
  idea = '달빛을 잃은 도시의 마지막 등대'
  tone = 'hopeful'
  theme = 'friendship'
  characters = @()
  scene_count = 2
} | ConvertTo-Json
$accepted = Invoke-RestMethod -Method Post `
  -Uri 'http://localhost:8000/api/v1/projects/<project_uuid>/stories/generate' `
  -Headers $headers -ContentType 'application/json' -Body $body

cd apps/api
uv run python -m app.worker --once
Invoke-RestMethod -Headers @{Authorization = 'Bearer <access_token>'} `
  -Uri "http://localhost:8000/api/v1/jobs/$($accepted.job_id)"
```

실제 OpenAI 1-scene 검증은 다음 순서로 별도 수행한다. 현재 작업 환경에는 `OPENAI_API_KEY`가 없어 실호출 smoke test를 실행하지 않았다. 일반 pytest는 fake client/MockProvider만 사용해 비용을 발생시키지 않는다.

1. 저장소 루트 `.env`에 `MOCK_AI=false`, `OPENAI_STORY_MODEL=gpt-5.6-terra`를 설정하고 API를 재시작한다. 또는 API 터미널에서 `$env:MOCK_AI='false'; .\scripts\start-api.ps1`을 실행한다.
2. Worker 터미널에서 `cd apps/api` 후 `$env:MOCK_AI='false'`를 설정한다. `$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'OpenAI API key' -AsSecureString)).Password`로 키를 화면과 명령 기록에 남기지 않고 주입한다.
3. 위 POST 예시에서 아이디어를 짧게 하고 `scene_count = 1`로 설정해 202 `job_id`를 받는다. 실제 계정의 소유 프로젝트 UUID와 access token을 사용하고 새 요청마다 새 `Idempotency-Key`를 만든다.
4. Worker 터미널에서 `uv run python -m app.worker --once`를 실행한 뒤 `GET /jobs/{job_id}`의 `status=succeeded`, `output.mock=false`, `output.episode_id` 존재, `output.scene_ids` 길이 1을 확인한다. `GET /episodes/{episode_id}`가 새 Episode를 반환하는지도 확인한다. 동기 Story 응답은 정상일 때 한 번의 `--once` 실행에서 `saving`과 저장까지 완료한다.
5. Worker 터미널에서 `Remove-Item Env:OPENAI_API_KEY`를 실행한다. Job이 실패하면 `error_code`와 Worker 로그를 확인하고 key나 전체 prompt를 공유하지 않는다.

## Scene 이미지 생성

`POST /scenes/{scene_id}/image/generate`는 body를 받지 않는다. API가 인증된 사용자의 Scene → Episode → Project 소유권을 확인하고 DB에 저장된 `visual_prompt`를 직접 읽는다. Project의 visual preset, narration, Character Bible/lock을 조합하고 Scene이 참조하는 canonical reference Asset 최대 4개의 id를 Job input에 보존한다. Worker가 private Storage에서 bytes를 읽어 reference가 있으면 OpenAI `images.edit`, 없으면 `images.generate`를 호출한다. `visual_prompt`가 없으면 422, 다른 사용자의 Scene은 404, Image 일일 한도 초과는 429다.

```http
POST /api/v1/scenes/<scene_uuid>/image/generate
Authorization: Bearer <access_token>
Idempotency-Key: <new-uuid>
```

응답은 `{"job_id":"<job-uuid>","status":"queued"}`이고 기존 `GET /jobs/{job_id}`를 약 2초마다 조회한다. Job type은 `image:scene`이다. 동일 Scene에 활성 이미지 Job이 있으면 다른 key라도 409를 반환한다. 같은 key의 같은 요청은 기존 Job을 반환하며 명시적 재생성은 새 key와 새 Asset을 만든다.

Worker는 동기 OpenAI Image 결과를 `queued → running → saving → succeeded`로 처리한다. 성공 output 예시는 다음과 같다.

```json
{
  "scene_id": "<scene-uuid>",
  "asset_id": "<latest-asset-uuid>",
  "asset_ids": ["<latest-asset-uuid>"],
  "mock": false
}
```

Provider의 base64 결과는 허용 크기, MIME/header, 정적 PNG/JPEG/WebP, 25 MP 제한을 확인한 뒤 private Storage에 저장한다. 저장 경로는 `users/{user_id}/projects/{project_id}/generated/{asset_id}.{ext}`이고 `asset_id`는 Job과 결과 위치에서 결정적으로 만든다. base64를 포함한 normalized provider 결과는 `provider_output`에 먼저 commit하므로 Storage 또는 Asset DB 저장이 재시도되어도 OpenAI를 다시 호출하지 않는다. 이미 같은 경로가 있으면 기존 bytes가 동일한지 확인한다. Scene은 성공 transaction에서 최신 `image_asset_id`만 가리키며 과거 generated Asset과 object는 보존한다.

이미지는 `GET /assets/{asset_id}`가 반환하는 15분 media capability URL로 읽는다. bucket은 public이 아니며 DB에 임시 URL을 저장하지 않는다. Story 화면은 URL을 10분 간격으로 갱신하고 Scene별 Job ID를 `sessionStorage`에 보존해 같은 탭의 새로고침 후 polling을 재개한다.

Mock 검증은 API·웹·Worker를 실행한 상태에서 Story를 먼저 생성한 뒤 Scene 카드의 `이미지 생성`을 누르거나 다음 명령을 사용한다.

```powershell
$imageHeaders = @{
  Authorization = 'Bearer <access_token>'
  'Idempotency-Key' = [guid]::NewGuid().ToString()
}
$accepted = Invoke-RestMethod -Method Post `
  -Uri 'http://localhost:8000/api/v1/scenes/<scene_uuid>/image/generate' `
  -Headers $imageHeaders

cd apps/api
uv run python -m app.worker --once
$job = Invoke-RestMethod -Headers @{Authorization = 'Bearer <access_token>'} `
  -Uri "http://localhost:8000/api/v1/jobs/$($accepted.job_id)"
$scene = Invoke-RestMethod -Headers @{Authorization = 'Bearer <access_token>'} `
  -Uri 'http://localhost:8000/api/v1/scenes/<scene_uuid>'
$asset = Invoke-RestMethod -Headers @{Authorization = 'Bearer <access_token>'} `
  -Uri "http://localhost:8000/api/v1/assets/$($scene.image_asset_id)"
$job.status; $asset.storage_key; $asset.public_url
```

실제 OpenAI 1-image smoke는 `MOCK_AI=false`와 Worker의 `OPENAI_API_KEY`를 설정하고 `OPENAI_IMAGE_MODEL=gpt-image-2.5-flare`, `OPENAI_IMAGE_SIZE=1024x1536`, `OPENAI_IMAGE_QUALITY=low`, `OPENAI_IMAGE_FORMAT=webp`로 같은 절차를 한 번 실행한다. `status=succeeded`, `output.mock=false`, 새 Asset, private object, Scene 연결과 Story 화면 표시를 확인한다. 선택적 live 테스트는 `RUN_OPENAI_INTEGRATION_TESTS=true`를 추가한 뒤 `uv run pytest -q tests/test_openai_image.py -k opt_in_live`로 실행한다. 현재 작업 환경에는 `OPENAI_API_KEY`가 없어 이 유료 smoke를 실행하지 않았다.

## 후속 API

Story와 Scene Image/Video Job 접수·조회·취소, owner-scoped Character/Scene 조회, Character Bible CRUD, canonical reference 선택/생성, reference-conditioned Scene image, private Episode Reader, versioned Publish API와 public/unlisted Reader가 등록되어 있다. Scene Motion은 `POST /api/v1/scenes/{scene_id}/video/generate`와 기존 Job 조회/취소 route를 사용하며 private MP4 Asset은 Range 요청을 지원한다. 일반 목적 job 생성, job 재시도/SSE 및 Fal webhook은 현재 라우트에 등록하지 않았다. 자세한 분할은 [제품 명세](product-spec.md)에 있다.

Character reference live 설정은 `OPENAI_IMAGE_REFERENCE_MODEL=gpt-image-2.5-sunburst`이며, 현재 환경에는 `OPENAI_API_KEY`가 없어 유료 live smoke를 실행하지 않았다.

현재 인증된 `GET /quotas`는 UTC 일일 Story/Image/Motion 사용량, 한도, 남은 횟수와 reset 시각을 반환한다. 모든 provider 호출은 backend `GenerationService.create_job`을 통해서만 승인한다. Character는 Image 한도, Video와 기존 Motion job은 Motion 한도를 공유한다.

별도 `python -m app.worker` 프로세스가 Job을 처리한다. `MOCK_AI=true`인 development/test에서는 Mock Story, deterministic PNG와 재생 가능한 작은 Mock MP4 fixture를 반환하며 결과의 `mock` metadata로 구분한다. Production은 `MOCK_AI=false`, Worker 전용 `OPENAI_API_KEY`와 `RUNWAYML_API_SECRET`을 사용한다. Browser용 Job/Asset 및 Reader 응답은 provider 이름, 모델, provider task ID, provider 전용 metadata와 Storage 경로를 숨긴다. Story Studio는 Scene Motion Job을 생성하고 private video를 재생하며 private Reader는 만료 가능한 media capability만 받는다.
