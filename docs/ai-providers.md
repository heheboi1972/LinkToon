# AI provider 통합 계약

현재 실제 외부 AI 기능은 **OpenAI Story, Character reference와 reference-conditioned Scene Image 생성, Runway Image-to-Video Scene Motion 생성**이다. 개발과 테스트에서는 네트워크 호출 없이 `MockProvider`로 같은 Job 파이프라인을 검증할 수 있으며, Mock 결과는 실제 AI 결과가 아니다.

모든 생성 요청은 backend `GenerationService.create_job`을 거친다. 이 서비스는 프로젝트 소유권과 사용자별 idempotency key를 확인하고, PostgreSQL 사용자 행 잠금과 `generation_jobs`의 UTC 일일 개수로 Story 10회, Image 5회, Motion/Video 2회의 기본 제한을 적용한다. 브라우저는 provider를 직접 호출하거나 provider secret을 받지 않는다.

## Provider 분리

```text
POST /projects/{project_id}/stories/generate
POST /scenes/{scene_id}/image/generate
POST /scenes/{scene_id}/video/generate
  -> GenerationService -> generation_jobs
DatabaseWorker -> JobProcessor -> ProviderRegistry
                                  ├ MockProvider (development/test)
                                  ├ OpenAIProvider
                                  │  ├ Story capability
                                  │  └ Image capability
                                  ├ FalProvider (image alternate)
                                  └ RunwayProvider (Scene Motion)
```

Provider는 `submit`, `poll`, `cancel`, `normalize_result` 계약을 구현한다. Application service와 Router는 OpenAI SDK나 모델 payload를 import하지 않는다. API는 요청을 검증하고 `202 Accepted` Job만 만들며, OpenAI 네트워크 호출은 별도 Worker 프로세스의 `OpenAIProvider`만 수행한다.

| Provider | 현재 역할 | Secret |
| --- | --- | --- |
| OpenAI | Responses API 기반 구조화 Story, Image API 기반 Scene 이미지 | `OPENAI_API_KEY` |
| fal.ai | Queue 기반 Scene image 및 Character reference 이미지 | `FAL_KEY` |
| Runway | Scene image-to-video Motion Preview | `RUNWAYML_API_SECRET` |
| Mock | 구조화 Story, deterministic PNG/MP4, polling/error simulation | 없음 |

`MockProvider`는 `MOCK_AI=true`이면서 development/test일 때만 등록된다. 새 이미지 Job의 제공자는 `IMAGE_PROVIDER=openai|fal`로 정하고 Job 생성 시 모델 ID와 함께 DB에 고정한다. 기본값은 `openai`이며 자동 OpenAI↔fal fallback은 하지 않는다. 접근 권한이나 모델 설정이 잘못되면 해당 Job에서 안전한 오류를 돌려준다.

## OpenAI Story

의존성 범위는 공식 OpenAI Python SDK `>=3.16.2,<4`이고 현재 lock은 `3.16.2`다. `OpenAIProvider`는 Responses API의 `responses.parse(..., text_format=StoryResult)`와 Pydantic Structured Outputs를 사용한다. JSON 문자열을 신뢰해 직접 `json.loads`하는 경로는 없다. OpenAI 공식 문서도 Python SDK의 Pydantic parsing helper와 Responses API Structured Outputs를 안내한다: [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).

기본 모델은 `OPENAI_STORY_MODEL=gpt-5.6-terra`이며 Worker 환경변수로 변경할 수 있다. 이 모델은 Responses API와 Structured Outputs를 지원한다: [GPT-5.6 Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra). 모델 이름은 frontend나 요청 body가 선택하지 않는다.

각 요청은 `store=false`를 사용해 OpenAI 측 저장 응답에 의존하지 않으며 LinkToon DB를 source of truth로 유지한다. Developer instructions와 사용자 제공 Story JSON을 별도 message로 전달하고, 사용자 문자열은 지시가 아닌 데이터로 취급한다. 반환 schema는 다음을 강제한다.

- Story `title`, `synopsis`와 요청한 개수의 `scenes`
- 1부터 시작해 중복 없이 연속되는 Scene `order`
- Scene `title`, `narration`, `dialogue`, `visual_prompt`
- Project에 실제 존재하는 character UUID만 포함하는 `character_ids`
- 후속 이미지 생성에 필요한 장소, 시간대, 분위기, 캐릭터 행동, 카메라 구도, 중요 오브젝트, 조명 정보

Structured Output을 받은 뒤에도 domain validation을 다시 수행한다. Scene 개수·순서·필수 문자열·character reference가 유효해야 하며, 성공한 Story는 기존 Episode를 수정하지 않고 **새 Episode와 Scene 행을 한 DB transaction으로 추가**한다. 별도 `StoryVersion` 테이블은 현재 없다. DB 저장이 실패하면 새 Episode와 Scene을 모두 rollback한다.

동기 Responses 호출은 `running → saving → succeeded`로 진행하며 `provider_pending`을 만들 필요가 없다. normalized provider metadata에는 실제 응답에서 얻은 `provider`, `model`, OpenAI request ID와 `input_tokens`·`output_tokens`·`total_tokens`를 보존한다. API key, Authorization header, 전체 prompt는 로그에 남기지 않는다. `store=false` 사용 방식은 [Responses API migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses)도 참고한다.

## OpenAI Scene Image

Image capability는 공식 Python SDK `client.images.generate(...)`와 여러 reference 파일을 받는 `client.images.edit(...)`를 사용한다. 기준 이미지가 없으면 `OPENAI_IMAGE_MODEL=gpt-image-2.5-flare`로 생성하고, Character reference 생성과 reference-conditioned Scene에는 `OPENAI_IMAGE_REFERENCE_MODEL=gpt-image-2.5-sunburst`를 사용한다. 공통 기본값은 `OPENAI_IMAGE_SIZE=1024x1536`, `OPENAI_IMAGE_QUALITY=low`, `OPENAI_IMAGE_FORMAT=webp`다. 모델과 옵션은 Settings에만 정의하고 browser 요청이 바꾸지 못한다. 공식 가이드는 Image API의 generation/edit 흐름과 GPT Image의 base64 결과를 안내한다: [Image generation guide](https://developers.openai.com/api/docs/guides/image-generation), [Images API reference](https://developers.openai.com/api/reference/cli/resources/images).

API 입력은 scene ID뿐이다. Backend가 저장된 `Scene.script.visual_prompt`, narration, Project Bible visual preset과 Scene이 실제 참조하는 Character의 Bible/lock을 읽어 prompt를 구성하고, 선택된 ready image Asset의 bytes를 provider adapter에 전달한다. OpenAI edit는 reference image를 최대 4개까지 장면 prompt와 함께 사용하며, reference Asset은 private Storage에 immutable하게 보존된다. face embedding, LoRA, DreamBooth, custom training은 사용하지 않는다.

SDK 응답의 `b64_json`은 decoded upper bound를 먼저 검사하고 typed image artifact로 정규화한다. Worker는 decode 후 실제 MIME/header, 정적 PNG/JPEG/WebP, byte 수와 25 MP를 다시 검사한다. source URL이나 사용자 URL을 내려받는 경로가 없으므로 일반 URL downloader와 SSRF 표면을 만들지 않는다. request ID가 실제 응답에 있을 때만 metadata에 보존하며 model/요청 size/quality/format도 기록한다.

동기 Image 호출은 `running → saving → succeeded`다. base64 artifact를 포함한 normalized 결과를 `provider_output`에 먼저 commit한 후 private Storage와 Asset DB에 저장한다. 이 선택은 DB JSON 크기를 증가시키지만 현재 1-job/1-image와 `MAX_UPLOAD_BYTES` 상한 안에서 Render 재시작에도 남는 durable recovery를 제공한다. Storage 실패는 저장만 재시도하며 provider를 재호출하지 않는다. Asset UUID와 object key가 결정적이므로 DB insert 실패 뒤에도 같은 object를 재사용한다.

## Job 상태와 오류

일반 상태는 `queued → running → provider_pending → saving → succeeded`이고 동기 OpenAI Story/Image는 `provider_pending`을 건너뛴다. 처리 중 오류는 `failed`, 취소는 `canceled`다. Provider 결과는 `provider_output`에 먼저 보존한 뒤 saving을 수행하므로 결과 저장 재시도가 성공한 provider 호출을 반복하지 않는다.

OpenAI 오류는 재시도 가능 여부와 안전한 오류 코드를 포함한 `ProviderSubmitResult`로 변환한다.

- API key/모델 설정, 인증, 잘못된 요청: retry하지 않음
- rate limit, timeout, 연결 오류, 5xx/일시 장애: `WORKER_MAX_RETRIES` 안에서 지수 backoff
- refusal, incomplete response, Structured Output/domain validation 실패: 제한된 정책으로 종료하며 무한 재생성하지 않음

SDK가 제공하는 request ID는 성공 metadata와 실패 진단에 사용한다. 요청에는 Job ID와 attempt로 만든 `X-Client-Request-Id`도 보내 추적성을 높이지만, 이 값은 OpenAI 호출의 멱등성 보장으로 취급하지 않는다. secret이나 사용자 prompt를 오류 메시지에 복사하지 않는다. 실제 과금 단가는 코드에 하드코딩하지 않고 응답의 token usage만 저장한다.

## fal.ai Image

Worker는 `fal-client` 1.0.3의 동기 client로 Queue 상태·결과·취소를 처리한다. Submit은 Queue endpoint에 단일 HTTP POST로 보내고, 이후 SDK의 `status`, `result`, `cancel` API를 사용한다. 현재 SDK의 submit 경로는 POST를 내부 재시도할 수 있어, 응답이 사라진 상황에서 과금 작업을 중복 생성할 위험이 있다. 따라서 submit에서 timeout/5xx 등 요청 접수 여부가 모호한 오류는 자동 재시도하지 않고 `fal_submit_outcome_unknown`으로 종료한다. Queue request ID가 기록된 뒤에는 DB의 `provider_task_id`를 기준으로 Worker 재시작 후에도 재제출 없이 polling한다.

새 Scene Image와 Character reference Job의 제공자는 API 설정 `IMAGE_PROVIDER`가 고른다. Worker에 같은 설정과 model ID를 지정해야 한다. `FAL_IMAGE_MODEL=fal-ai/flux-2-pro`는 prompt 기반 이미지 생성을 담당하고, canonical Character reference가 있는 Scene은 `FAL_REFERENCE_IMAGE_MODEL=fal-ai/flux-pulid`를 사용한다. PuLID 입력은 fal에 보내는 data URI이며, private Storage 주소나 signed URL을 외부에 노출하지 않는다. 이 모델은 reference 이미지 하나를 입력받으므로 첫 canonical reference를 보내고 나머지 인물은 구성된 Character Bible prompt에 유지한다. Character의 최초 reference 생성에는 입력 reference가 필요 없는 일반 이미지 모델을 쓴다.

fal 결과의 Image URL은 Worker의 임시 saving 복구 데이터에만 둔다. Worker는 허용된 HTTPS fal/GCS media host와 redirect를 검사하고, Content-Length와 실제 byte 상한을 적용한 뒤 private Storage에 새 immutable object로 저장한다. PNG/JPEG/WebP signature·decode·pixel 검증을 다시 수행하고 Asset을 생성해 Scene 또는 Character reference에 연결한다. Storage가 실패하면 저장된 fal request/result를 재사용해 저장만 재시도한다. 성공 또는 terminal failure에서는 임시 CDN URL을 지운다. fal key, 원본 이미지 bytes는 browser 응답이나 로그에 넣지 않는다.

선택적 fal live smoke test는 `FAL_KEY`와 `RUN_FAL_INTEGRATION_TESTS=true`를 둘 다 지정할 때만 켤 수 있다. 일반 pytest와 Worker fake-client tests는 네트워크를 사용하지 않고 비용도 발생시키지 않는다. OpenAI Story, fal Image, Runway Motion은 서로 다른 capability로 남으며 Runway Video는 변경하지 않았다.

## Motion 처리 기준

Scene Motion은 기존 `video:scene` GenerationJob을 사용한다. API는 소유한 Scene과 ready Image Asset을 검사하고, Worker는 private image bytes를 Runway SDK의 data URI 입력으로 전달한다. Runway task ID는 `provider_task_id`에 먼저 저장하고 durable polling을 재개한다. `SUCCEEDED` 결과 URL은 저장 복구를 위해서만 job `provider_output`에 잠시 보관하며, Worker가 MP4를 받아 MIME, 크기와 MP4 `ftyp` container signature를 검사한 후 private immutable Asset으로 저장한다. URL이 만료되면 task를 자동 재생성하지 않고 `runway_output_expired`로 끝낸다.

기본값은 `RUNWAY_VIDEO_MODEL=gen4_turbo`, `RUNWAY_VIDEO_DURATION_SECONDS=5`, `RUNWAY_API_VERSION=2024-11-06`이다. Scene 이미지의 폭/높이에서 Runway 지원 ratio 중 centered crop 손실이 가장 작은 값을 고른다. `gen4_turbo`는 5/10초, `gen4.5`는 2–10초 duration validation을 Provider adapter에서 적용한다.

- `exact`: AI는 plan만 만든다. object segmentation → 필요 시 background 복원 → 위치/회전/크기 interpolation → OpenCV/Pillow 합성 → FFmpeg encode. 생성형 비디오로 픽셀을 매 프레임 재생성하지 않는다.
- `partial_generate`: animate mask + lock mask 전달, 결과에 원본 lock layer를 다시 합성할 수 있어야 한다.
- `full_generate`: 복합 전신 움직임과 액션.
- `first_last`: 두 이미지 사이 연결. 같은 프로젝트의 ready asset만 허용한다.
- 결과는 원본 image와 별도의 WebM/MP4/poster assets + animation record다.

Motion Analyzer와 Panel conversion은 각각 Pydantic structured output schema로 검증할 예정이다. Reference image consistency가 기본이며 LoRA는 확장 가능한 별도 interface로 다룬다.

## 검증 경계

자동 테스트는 OpenAI/fal/Runway clients를 대체해 요청, polling, output normalize, binary 검증, 오류 분류와 Worker 저장·복구를 검증하며 외부 API를 호출하거나 요금을 발생시키지 않는다. 실제 OpenAI API의 선택적 smoke는 `OPENAI_API_KEY`와 `RUN_OPENAI_INTEGRATION_TESTS=true`를 명시적으로 설정한 뒤 Story는 `uv run pytest -q tests/test_openai_story.py -k opt_in_live`, Image는 `uv run pytest -q tests/test_openai_image.py -k opt_in_live`로만 실행한다. fal smoke는 Worker에 `FAL_KEY`와 `RUN_FAL_INTEGRATION_TESTS=true`를 지정한 경우에만 실행한다. Runway live smoke는 Worker에 `RUNWAYML_API_SECRET`을 설정한 뒤 Scene 하나를 명시적으로 실행할 때만 과금된다.

이번 Reader 작업은 MockProvider만 사용했으며 실제 OpenAI와 Runway smoke test는 실행하지 않았다.
