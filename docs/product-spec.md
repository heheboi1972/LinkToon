# LinkToon 제품 명세

LinkToon은 프로젝트의 이야기·캐릭터·이미지·패널·애니메이션을 한곳에서 제작하고 출간하는 반응형 웹 서비스다. V1의 목표는 정적 패널과 동적 패널을 함께 읽는 Animated Webtoon Reader다. 네이티브 모바일 앱은 범위에 포함하지 않는다.

## 현재 구현 범위

웹에서 실행 가능한 범위는 **회원가입 → 프로젝트 제작 → Story/Character/Scene Image/Motion → private Reader → immutable Publication snapshot → public/unlisted Reader 공유**다. Story/Image/Video 작업은 Backend 비동기 Job API를 사용하며 개발 기본값은 MockProvider다. 실제 OpenAI나 Runway Provider는 Worker에 key를 설정했을 때만 호출한다. 생성 데이터와 Publication snapshot은 새로고침과 서버 재시작 이후에도 DB/Storage에 남는다.

| 영역 | 현재 동작 |
| --- | --- |
| 계정 | 로컬 개발용 가입·로그인, Supabase 이메일/비밀번호 인증 통합, 로그아웃 |
| 대시보드 | 소유 프로젝트, 표지, 상태, 수정일, 검색, 상태 필터, 카드/목록 전환, 최근 job 조회 |
| 프로젝트 Wizard | 제목·설명·장르·방향 → manual/assisted/ai_first → 3가지 스타일 프리셋 |
| Project Bible | 프로젝트와 동시에 생성, 최초 아이디어/스타일 보존, Character Bible CRUD와 기준 이미지 상태/생성, 조회 화면 |
| Story Studio | Bible 아래 Character Bible과 기준 이미지 관리, 아이디어·장르·톤·테마·장면 수·프로젝트 Character 선택, 202 Job 접수·2초 상태 조회·취소, 새로고침 복구, 결과와 새 Episode 링크 |
| Scene Image | 저장된 Scene별 reference-conditioned 생성·재생성·취소, 독립 Job 상태, private Asset 표시, 새로고침 복구, 기존 Asset 이력 보존 |
| Scene Motion | 저장된 Scene 이미지에서 짧은 Motion Video 생성·취소·재생성, private MP4 Asset 저장과 이전 결과 보존 |
| Private Reader | 인증된 에피소드 vertical 감상, image/Motion poster fallback, 서술·대사, 이어보기 및 읽기 진행 표시 |
| Publish / Public Reader | Episode snapshot version, stable slug, public/unlisted/private visibility, explicit republish/unpublish, anonymous reader와 scoped 15분 media capability |
| Project Overview | 실제 DB 장면·이미지·Motion·Character·게시 수, 최근 Scene preview와 제작 단계 |
| 프로젝트 CRUD | 생성·조회·제목/소개/장르/상태/표지 변경·삭제 |
| 에피소드 CRUD | 생성·목록·조회·제목/소개 수정·삭제, 프로젝트별 번호 자동 배정 |
| 패널 CRUD | 10개 이상 생성, 장면 제목/설명/대사 저장, 이미지 교체·연결 해제·삭제 |
| 업로드 | 정적 PNG/JPEG/WebP, 10 MiB 이하, 25 MP 이하, 원본 보존, 소유권 검사 |
| 자산 목록 | 프로젝트 업로드 이미지 조회·참고 이미지 업로드·사용 중인 자산 삭제 방지 |
| AI Story backend | owner-scoped Character 목록과 202 Job 생성, 일일 한도/idempotency, OpenAI Structured Output, 새 Episode + Scene 원자 저장 |
| AI Worker | PostgreSQL queue, lease/복구/retry/cancel, 개발·테스트 Mock, 운영 OpenAI Story/Image/Character reference |
| 반응형 | 데스크톱 사이드바, 작은 화면 메뉴와 한 열 레이아웃 |
| PWA 기반 | manifest, SVG 앱 아이콘, theme-color, standalone 시작 경로 |

이미지 보관함은 업로드 관리 화면이다. 전체 Asset Library(선택/재사용/검색/분류)와 캔버스 편집기는 아직 아니다. Story Scene의 대사는 Reader에서 텍스트로 표시하며 이미지 픽셀에 렌더링하지 않는다. Reader는 반응형 vertical 흐름을 사용한다. Public Reader는 공개 Publication만 노출하고 unlisted 링크는 검색에서 제외한다.

## 후속 Phase의 경계

1. **Phase 2:** Konva 캔버스 편집, 드래그 재정렬, 패널 복제, Asset Library. Reader 접근성·PWA 캐싱 정책 확장.
2. **Phase 3:** PostgreSQL generation worker, jobs 상태전이/취소/제한된 재시도, OpenAI Story/Image/Character reference adapter, Character Bible/Reference UI, Story Studio 단계 표시·polling·결과와 reference-conditioned Scene 이미지 UI는 구현됨. 남은 범위는 Story 편집/명시적 버전 UI, 별도 Image Studio와 consistency checker다. SSE는 현재 사용하지 않는다.
3. **Phase 4:** Fal adapter, 고급 image/video 생성, first/last frame, Motion Studio, animation asset 연결.
4. **Phase 5:** SAM segmentation, brush/lock mask, 부분 생성 후 원본 lock 영역 합성, deterministic exact motion, OpenCV/FFmpeg compositor.
5. **Phase 6:** AI Router의 품질별 라우팅, 추가 provider fallback과 consistency checker.

각 Phase는 lint/typecheck/backend test/frontend test/build와 README 갱신을 마친 뒤 다음으로 진행한다. `publish_versions` legacy table은 사용하지 않으며 현재 게시 흐름은 `publications`와 versioned snapshot tables를 사용한다.

## V1 이후에도 유지할 제약

- AI는 브라우저에서 직접 호출하지 않는다. 모델 ID는 환경 설정과 provider 설정에서 결정한다.
- 모든 생성/편집 결과는 새 Asset을 만든다. 원본을 덮어쓰지 않는다.
- Story 재생성은 새 Episode를 만들어 기존 Episode를 보존한다. 별도 StoryVersion 모델은 후속 범위다.
- exact motion은 생성형 비디오 모델을 사용하지 않는다.
- Lock 영역은 prompt와 후처리 compositor에서 함께 보호한다.
- LoRA 학습은 V1 핵심 dependency로 사용하지 않는다.
- GIF를 기본 동영상 포맷으로 사용하지 않는다.

## 확인할 사용자 흐름

로컬 계정 가입 후 프로젝트를 만들고 첫 에피소드를 추가한다. 패널 12개를 만들고 첫 패널에 PNG를 업로드한 뒤 대사를 저장한다. 페이지를 새로고침해 값이 남는지 확인한다. 다른 계정에는 원래 프로젝트가 보이지 않아야 한다. UI 삭제는 확인 버튼을 거친다. DB에서는 부모 리소스 삭제 시 자식 row가 cascade 삭제된다.

Story 화면에서는 프로젝트의 Character ID를 선택하고 아이디어·장르·톤·테마·1~20개 Scene 수를 입력한다. API는 `Idempotency-Key`를 검증해 202 Job을 반환하고 화면은 2초 간격으로 비종결 상태를 조회한다. 같은 탭을 새로고침해도 사용자·프로젝트별 `sessionStorage`의 Job ID로 결과를 복구한다. Worker 성공 후 기존 Episode는 그대로 있고 새 Episode와 정확한 수의 Scene이 제목·줄거리·서술·대사와 함께 보여야 한다. 같은 key의 동일 요청은 같은 Job을 반환하고, 다른 payload 재사용이나 다른 사용자의 프로젝트 접근은 거부해야 한다. 개발 기본값은 MockProvider이며 실제 OpenAI 호출은 Worker에 key를 명시적으로 설정한 환경에서만 수행한다. 이번 작업 환경에는 key가 없어 실제 유료 OpenAI smoke는 실행하지 않았다.

저장된 Scene은 각자 `이미지 생성` 버튼을 가진다. Backend가 Scene 소유권과 실제 `visual_prompt`를 읽어 `image:scene` Job을 만들고, Worker가 생성 bytes를 검증해 private Storage와 새 Asset에 저장한 뒤 Scene의 현재 이미지로 연결한다. canonical Character reference가 있으면 최대 4개 image bytes를 OpenAI edit에 전달하고 없으면 text prompt로 fallback한다. 같은 Scene의 활성 Job은 하나만 허용하고 다른 Scene Job은 독립적으로 진행한다. 재생성은 새 key·Asset을 사용하고 과거 Asset을 보존한다. 실패 또는 새로고침 후에도 사용자·Scene별 Job ID와 DB의 `image_asset_id`로 상태와 이미지를 복구해야 한다.

에피소드 상세에서 `읽기`를 선택하면 인증된 private Reader로 이동한다. Reader는 Backend read model의 순서대로 Story Scene을 표시하고 image-only, image+video, text-only Scene을 지원한다. 기본 Motion 자동 재생은 꺼져 있고 사용자가 켤 수 있으며 `prefers-reduced-motion`을 존중하고 한 번에 하나만 자동 재생한다. Observer 기반 진행 위치는 사용자·에피소드 범위의 localStorage에 Scene ID로 저장하며 다음 방문에서 `이어서 보기`를 선택해 복구한다. API·일부 media 오류는 전체 에피소드 감상을 막지 않는다.

에피소드의 `Publish` 화면은 장면 1개 이상을 확인한 뒤 현재 Scene content와 ready media ID를 새 snapshot version으로 저장한다. Scene 수정과 Asset 재생성은 기존 공개본에 반영되지 않는다. 작가가 명시적으로 `다시 게시`할 때만 새 버전이 활성화된다. Public/unlisted URL은 로그인 없이 열리며 private는 public endpoint에서 404다. 공개 미디어 권한은 활성 snapshot에 포함된 Asset만을 대상으로 하며, private Storage bucket을 공개하지 않는다. 사용 중인 Publication Asset 삭제는 409다.
