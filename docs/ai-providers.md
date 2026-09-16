# AI provider 통합 계약

**현재 구현은 Phase 1이다. 외부 AI provider는 호출하지 않는다.** 아래는 이후 Phase에서 지킬 경계와 입력·결과 계약이다. adapter/worker를 구현 완료한 것으로 간주하지 않는다.

모든 후속 provider adapter는 호출 전에 backend `GenerationService.create_job`을 사용해야 한다. PostgreSQL 사용자 행 잠금과 `generation_jobs`의 UTC 일일 개수로 Story 10회, Image 5회, Motion/Video 2회의 기본 Beta 제한을 적용한다. provider 실패나 사용자의 재시도도 생성 job을 만들었다면 해당 일일 사용량에 포함해 비용 우회를 막는다.

## Provider 분리

```text
API -> generation_jobs + Celery enqueue
Worker -> AIService -> AIRouter -> Provider
                              ├ OpenAIProvider
                              ├ FalProvider
                              ├ RunwayProvider
                              └ MockProvider
```

provider는 `submit`, `poll`, `cancel`과 지원 capability를 노출하고 task id/상태/결과 URL/usage를 공통 타입으로 변환한다. Application service는 provider SDK와 모델별 payload를 import하지 않는다. 입력에는 project bible의 관련 내용, character references, prompt와 normalized quality/mode를 전달한다. model ID는 backend provider config에서만 선택한다.

| Provider | 예정 역할 | Secret |
| --- | --- | --- |
| OpenAI | Story/script/vision/이미지 생성·편집 | OPENAI_API_KEY |
| fal.ai | 이미지 참조 캐릭터 일관성, image-to-video, SAM | FAL_KEY |
| Runway | premium/secondary video, 장애 시 정책 기반 fallback | RUNWAYML_API_SECRET |
| Mock | 고정 structured story/motion + 로컬 sample image/MP4/WebM | 없음 |

현재 `.env.example`은 secret 이름만 포함한다. 모델명은 아직 정하지 않았고 UI에 노출하지 않는다. Phase 1의 `MOCK_AI=true`는 중앙 설정값이며 아직 전체 AI/Animated Reader 흐름을 실행할 수 있는 MockProvider는 아니다.

## Job 상태와 오류

`queued → planning → submitted → processing → postprocessing → completed`.
처리 중 오류는 `failed`, 취소는 `cancelled`. 전이는 서비스에서 검증하고 provider task id를 submit 직후 저장한다. 작업 입력/오류/비용/시간/진행률 schema는 이미 migration에 있다. 재시도 시 원본 작업 입력과 이전 결과 asset을 보존한다. 중복 webhook과 Celery 재전달은 idempotency key로 처리할 예정이다.

`ProviderError`, `GenerationError`, `StorageError`, Pydantic validation은 application 오류로 정규화한다. Provider 요청을 HTTP 요청 안에서 완료까지 기다리지 않는다. webhook은 provider가 서명을 제공하면 검증을 통과한 경우에만 처리한다. Phase 1은 webhook endpoint를 열지 않는다.

## Motion 처리 기준

- `exact`: AI는 plan만 만든다. object segmentation → 필요 시 background 복원 → 위치/회전/크기 interpolation → OpenCV/Pillow 합성 → FFmpeg encode. 생성형 비디오로 픽셀을 매 프레임 재생성하지 않는다.
- `partial_generate`: animate mask + lock mask 전달, 결과에 원본 lock layer를 다시 합성할 수 있어야 한다.
- `full_generate`: 복합 전신 움직임과 액션.
- `first_last`: 두 이미지 사이 연결. 같은 프로젝트의 ready asset만 허용한다.
- 결과는 원본 image와 별도의 WebM/MP4/poster assets + animation record다.

Motion Analyzer와 Panel conversion은 각각 Pydantic structured output schema로 검증할 예정이다. Reference image consistency가 기본이며 LoRA는 확장 가능한 별도 interface로 다룬다.

## Phase 1에서 검증한 것

AI 호출이 없는 상태에서도 Auth/CRUD/upload가 작동하고 모델과 secret이 frontend bundle에 포함되지 않는다. Supabase Auth/Storage의 외부 HTTP는 adapter 단위 mock으로 검증한다. 실제 OpenAI/Fal/Runway API 및 요금 결제는 수행하지 않았다.
