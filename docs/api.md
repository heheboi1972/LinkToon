# LinkToon Phase 1 API

Base URL은 개발에서 `http://localhost:8000/api/v1`, 운영에서 `NEXT_PUBLIC_API_URL + /api/v1`이다. 대화형 전체 스키마는 `/docs`, JSON 스키마는 `/openapi.json`.

인증 헤더: `Authorization: Bearer <access_token>`. GET `/config`, 로컬 가입/로그인, `/health`, `/ready`만 공개다. 업로드/미디어 URL에는 resource별 만료 토큰이 필요하다. 외부 계정의 리소스는 404. 입력 스키마 오류 422, 로그인 필요 401, 충돌 409, 파일 초과 413, 잘못된 이미지 415.

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
| POST / GET | `/projects/{id}/episodes` | 에피소드 생성 / 번호순 목록 |
| GET / PATCH / DELETE | `/episodes/{id}` | 에피소드 조회·수정·삭제 |
| POST / GET | `/episodes/{id}/panels` | 패널 추가 / position순 목록 |
| GET / PATCH / DELETE | `/panels/{id}` | 패널 조회·수정·삭제 |
| POST | `/assets/upload-url` | 업로드 ticket 발급. pending Asset 생성 |
| PUT | `/assets/{id}/upload?token=...` | 이미지 bytes 검증·저장 |
| POST | `/assets/complete` | 업로드 확인 및 ready 전환. idempotent |
| GET | `/projects/{id}/assets` | 완료된 이미지 자산 목록 |
| GET / DELETE | `/assets/{id}` | 자산 메타데이터/만료 URL 조회, 미사용 자산 삭제 |
| GET | `/assets/{id}/content?token=...` | 이미지 바이트 전달 |
| GET | `/jobs` | 소유자 job 목록. Phase 1에는 생성 기능 없음 |

목록에는 `limit`(1~200), `offset`(0 이상)을 사용할 수 있다. 프로젝트/에피소드 기본 limit 100, 패널/자산 200, jobs 20. UI는 프로젝트·에피소드·패널·자산에서 최신/처음 200개를 보여준다. 대규모 무한 스크롤은 Phase 2 범위다.

## 주요 payload

프로젝트 생성:

```json
{"title":"달빛 도시","description":"도시의 불빛을 지키는 이야기","genre":"fantasy","orientation":"vertical","creation_mode":"manual","visual_style":"cinematic"}
```

프로젝트 수정 가능 필드: `title`, `description`, `genre`, `status`(draft/active/archived), `thumbnail_asset_id`. 소유자와 생성 방식은 patch로 변경하지 않는다.

에피소드 생성/수정: `title`, `description`. `number`는 서버가 배정하며 publish 상태 변경은 Phase 2 API로만 허용할 예정이다.

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

asset response에는 id/owner_id/project_id/type/mime/storage provider/key, dimensions, size, created_at, metadata, upload_status와 15분 media URL이 포함된다. DB의 public_url column은 private 원본에 대해 null이며 API가 만료 URL을 계산해서 반환한다.

## 후속 API

Story 생성, Character CRUD/generation, AI Images, Motion, job 생성/취소/재시도/SSE, Publish, Public Reader 및 Fal/Runway webhook은 현재 라우트에 등록하지 않았다. AI 기능처럼 보이는 가짜 성공 응답이나 비어 있는 worker는 없다. 자세한 분할은 [제품 명세](product-spec.md)에 있다.

현재 인증된 `GET /quotas`는 UTC 일일 Story/Image/Motion 사용량, 한도, 남은 횟수와 reset 시각을 반환한다. 향후 provider 호출은 backend `GenerationService.create_job`을 통해서만 job을 승인해야 한다. `GET /jobs`는 이렇게 기록된 본인 작업만 반환하며, 공개 job 생성 endpoint는 아직 없다.
