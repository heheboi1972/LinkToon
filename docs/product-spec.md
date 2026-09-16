# LinkToon 제품 명세

LinkToon은 프로젝트의 이야기·캐릭터·이미지·패널·애니메이션을 한곳에서 제작하고 출간하는 반응형 웹 서비스다. V1의 목표는 정적 패널과 동적 패널을 함께 읽는 Animated Webtoon Reader다. 네이티브 모바일 앱은 범위에 포함하지 않는다.

## 이번 납품: Phase 1

실행 가능한 범위는 **회원가입 → 로그인 → 프로젝트 생성 → 에피소드 생성 → 패널 생성 → 이미지 업로드·연결·장면 편집**이다. 생성 데이터는 새로고침과 서버 재시작 이후에도 DB/Storage에 남는다. AI 작업을 수행한 것처럼 표시하지 않는다.

| 영역 | 현재 동작 |
| --- | --- |
| 계정 | 로컬 개발용 가입·로그인, Supabase 이메일/비밀번호 인증 통합, 로그아웃 |
| 대시보드 | 소유 프로젝트, 표지, 상태, 수정일, 검색, 상태 필터, 카드/목록 전환, 최근 job 조회 |
| 프로젝트 Wizard | 제목·설명·장르·방향 → manual/assisted/ai_first → 3가지 스타일 프리셋 |
| Project Bible | 프로젝트와 동시에 생성, 최초 아이디어/스타일 보존, 조회 화면 |
| 프로젝트 CRUD | 생성·조회·제목/소개/장르/상태/표지 변경·삭제 |
| 에피소드 CRUD | 생성·목록·조회·제목/소개 수정·삭제, 프로젝트별 번호 자동 배정 |
| 패널 CRUD | 10개 이상 생성, 장면 제목/설명/대사 저장, 이미지 교체·연결 해제·삭제 |
| 업로드 | 정적 PNG/JPEG/WebP, 10 MiB 이하, 25 MP 이하, 원본 보존, 소유권 검사 |
| 자산 목록 | 프로젝트 업로드 이미지 조회·참고 이미지 업로드·사용 중인 자산 삭제 방지 |
| 반응형 | 데스크톱 사이드바, 작은 화면 메뉴와 한 열 레이아웃 |
| PWA 기반 | manifest, SVG 앱 아이콘, theme-color, standalone 시작 경로 |

이미지 보관함은 Phase 1 업로드 관리 화면이다. Phase 2의 전체 Asset Library(선택/재사용/검색/분류)와 캔버스 편집기는 아직 아니다. 대사는 DB와 패널 카드에 저장되며 이미지 픽셀에 렌더링하지 않는다. 수평 orientation은 설정값을 보존하며 실제 Reader 레이아웃은 Phase 2 범위다.

## 후속 Phase의 경계

1. **Phase 2:** Konva 캔버스 편집, 드래그 재정렬, 패널 복제, Asset Library, Reader, publish snapshot/slug/공개 URL. IntersectionObserver 기반 비디오 재생 제한, WebM 우선/MP4 fallback. 접근성·PWA 캐싱 정책 확장.
2. **Phase 3:** Celery worker 및 jobs 생성/상태전이/취소/재시도/SSE, OpenAI adapter, Story Studio 단계별 작성·버전 관리·구조화 출력, Image Studio, 실제 Mock AI fixture 생성. 캐릭터 CRUD/reference UI 및 일관성 입력 기반.
3. **Phase 4:** Fal adapter, image-to-video, first/last frame, Motion Studio, animation asset 연결.
4. **Phase 5:** SAM segmentation, brush/lock mask, 부분 생성 후 원본 lock 영역 합성, deterministic exact motion, OpenCV/FFmpeg compositor.
5. **Phase 6:** AI Router의 품질별 라우팅, Runway adapter, fallback과 consistency checker.

각 Phase는 lint/typecheck/backend test/frontend test/build와 README 갱신을 마친 뒤 다음으로 진행한다. 모델/Job/Publish 테이블이 존재하는 것은 해당 기능의 완료를 뜻하지 않는다.

## V1 이후에도 유지할 제약

- AI는 브라우저에서 직접 호출하지 않는다. 모델 ID는 환경 설정과 provider 설정에서 결정한다.
- 모든 생성/편집 결과는 새 Asset을 만든다. 원본을 덮어쓰지 않는다.
- Story와 출간 결과는 버전을 보존한다.
- exact motion은 생성형 비디오 모델을 사용하지 않는다.
- Lock 영역은 prompt와 후처리 compositor에서 함께 보호한다.
- LoRA 학습은 V1 핵심 dependency로 사용하지 않는다.
- GIF를 기본 동영상 포맷으로 사용하지 않는다.

## 확인할 사용자 흐름

로컬 계정 가입 후 프로젝트를 만들고 첫 에피소드를 추가한다. 패널 12개를 만들고 첫 패널에 PNG를 업로드한 뒤 대사를 저장한다. 페이지를 새로고침해 값이 남는지 확인한다. 다른 계정에는 원래 프로젝트가 보이지 않아야 한다. UI 삭제는 확인 버튼을 거친다. DB에서는 부모 리소스 삭제 시 자식 row가 cascade 삭제된다.
