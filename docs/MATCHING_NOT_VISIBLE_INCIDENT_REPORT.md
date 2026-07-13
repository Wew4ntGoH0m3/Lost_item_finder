# "매칭이 안 뜬다" 원인 분석 및 수정 보고서

**작성일**: 2026-07-14
**증상**: 습득글/분실글을 등록해도 앱에서 매칭이 전혀 안 보임 ("AI 추천 매칭", "매칭" 탭 모두 항상 비어 있음)

---

## 1. 결론 요약

**백엔드 매칭 로직 자체는 정상 동작하고 있었다.** 실제로 EC2 프로덕션 DB를 직접 조회해 확인했다:

- `lost_post id=11` 등록 → Celery worker 로그: `Task lostlink.analyze_lost_post ... succeeded in 39.06s: {'lostPostId': 11, 'candidates': 10, 'matched': 7}` — **매칭 7건이 실제로 생성됨**.

그런데도 앱 화면에는 매칭이 하나도 안 보였다. 원인은 백엔드가 아니라 **프론트엔드(Flutter)에 "내 매칭 목록을 가져오는 API 호출 자체가 없었던 것"**과 **백엔드에 그 API가 아예 없었던 것** 두 가지였다.

---

## 2. 조사 과정

### 2-1. 중간에 나온 두 가지 "거짓 양성" (버그 아님, 정상 동작)
조사 중간에 매칭이 안 되는 것처럼 보인 케이스가 두 번 있었는데, 둘 다 실제로는 로직이 의도대로 동작한 것이었다.

1. **같은 계정으로 분실글/습득글을 둘 다 등록한 경우** — `FoundPost.user_id != lost.user_id` 조건 때문에 매칭에서 제외됨 (자작극 방지용 정상 로직).
2. **`found_at`이 `lost_at`보다 빠른 경우** — "분실 시점 이후에 발견된 것만 후보로 인정"하는 규칙 때문에 후보에서 제외됨. 이 과정에서 별개로 **`foundAt`/`lostAt`이 실제 시각보다 9시간 어긋나 저장되는 타임존 버그**를 발견해 별도로 수정함 (FE가 로컬 시간을 UTC 표기 없이 전송 + 백엔드가 offset 없는 timestamp를 UTC로 직렬화하던 두 가지 문제, 각각 `fe/lib/screen/home_widget/add_widget.dart`와 `app/models.py`에서 수정).

### 2-2. 진짜 원인: 매칭을 "가져오는" 코드가 없었음
Celery 로그로 매칭이 실제로 DB에 쌓이고 있는 것(`matched: 7`)을 확인한 뒤, FE 코드를 뒤져보니 `fe/lib/screen/home_widget/matched_widget.dart`에 다음 주석이 그대로 남아 있었다:

> "내 매칭 목록을 모아서 보여주는 통합 엔드포인트가 아직 정의되어 있지 않아, 우선 `Store.lostMatches`(홈 화면 AI 추천 매칭과 동일한 데이터 소스)를 재사용합니다."

그런데 `Store.lostMatches`는 앱 전체에서 **선언만 되고 어디서도 값을 채우는 코드가 없었다** (`home_widget.dart`의 `loadHome()`도 `loadLostPosts`/`loadFoundPosts`만 호출하고 매칭 관련 API는 호출하지 않았음). 즉:

- "매칭" 탭(`MatchedWidget`)과 홈 화면 "AI 추천 매칭" 미리보기 모두 항상 빈 배열(`[]`)을 보고 있었다.
- 이 데이터를 채워줄 백엔드 엔드포인트(`GET /api/v1/matches`, 로그인한 사용자의 모든 매칭을 모아 보여주는 것)도 **아예 구현돼 있지 않았다** (`matches.py`에는 특정 lost/found 글 하나에 대한 매칭 조회만 있었음).

---

## 3. 수정 내용

### 백엔드
- `app/api/matches.py`: `GET /api/v1/matches` 신규 추가. 로그인한 사용자가 소유한 분실글 또는 습득글에 걸린 매칭을 전부 모아서 반환, `?status=` 쿼리로 필터링 가능.
- `tests/test_api.py`: 양쪽 당사자 모두 조회 가능한지, 무관한 사용자에겐 안 보이는지, status 필터가 되는지 검증하는 테스트 추가.

### 프론트엔드
- `fe/lib/service/http_service.dart`: `loadMyMatches({status})` 추가 — 위 신규 엔드포인트 호출.
- `fe/lib/screen/home_widget/home_widget.dart`: `loadHome()`에서 `loadMyMatches(status: 'CANDIDATE')`를 호출해 `Store.lostMatches`를 실제로 채우도록 수정. "AI 추천 매칭" 섹션도 매칭이 있을 때 실제 항목을 렌더링하도록 수정 (기존엔 매칭이 있어도 빈 `SizedBox()`만 그리고 있었음 — 두 번째 버그).
- `fe/lib/screen/home_widget/matched_widget.dart`: `loadMatches()`가 `Store.lostMatches`를 재사용하는 대신 `HttpService.loadMyMatches()`를 직접 호출하도록 수정.

---

## 4. 검증

- 신규 백엔드 엔드포인트를 테스트 클라이언트로 직접 호출해 확인: 분실글 소유자(A)와 습득글 소유자(B) 양쪽 모두 `/api/v1/matches`에서 서로의 매칭을 정상 조회함, `status=CANDIDATE` 필터 정상 동작.
- 로컬 테스트 스위트 27개 전부 통과, `ruff check` 통과.
- `dart analyze`로 FE 변경 파일 문법 오류 없음 확인 (기존에 있던 무관한 스타일 경고만 존재).

---

## 5. 남은 작업

- 백엔드 커밋(`bb72d50` 외)이 로컬에만 있고 아직 `origin/BE`에 push되지 않음 — 인증 가능한 환경에서 `git push origin BE:BE` 필요.
- FE(`fe/`)는 이 git 저장소에서 추적되지 않는 디렉토리라 커밋 대상이 없음. 디스크 파일은 수정해뒀으니, 기존에 앱을 빌드/배포하던 방식으로 반영 필요.
- 반영 후 실제 앱에서 "매칭" 탭과 홈 화면 "AI 추천 매칭"에 실제 매칭이 뜨는지 확인 권장.
