# 습득글 AI 사진 분석 실패 (ETC 폴백) 원인 분석 및 수정 보고서

**작성일**: 2026-07-14
**대상**: 습득글(FoundPost) 생성 시 사진 기반 category/color/title/features/description 자동 생성 기능
**증상**: 이미지 업로드로 습득글을 등록하면 실제 사진 내용과 무관하게 `category=ETC`, `color=UNKNOWN`, 설명이 "사진을 참고해 주세요"로만 나옴 (LLM이 사진을 분석한 결과가 전혀 반영되지 않음)

---

## 1. 결론 요약

**진짜 원인은 타임아웃이었다.** 실제 폰으로 찍은 사진(약 3~4MB, 3024×4032 해상도)을 리사이즈 없이 그대로 base64 인코딩해서 Ollama 비전 모델에 보내고 있었고, 이 정도 해상도는 모델이 처리하는 데 60초를 훌쩍 넘겨 매번 타임아웃으로 실패했다. 실패하면 코드는 조용히 `ETC` 템플릿으로 폴백하도록 설계돼 있어서, 사용자 입장에서는 "AI가 사진을 아예 안 본다"처럼 보였다.

그 과정에서 별개로 존재하던 다른 버그 4개도 함께 발견되어 순서대로 고쳤다 (아래 2절 타임라인 참고). 마지막 항목(이미지 리사이즈)이 실사용 환경에서의 실제 증상을 해결한 최종 원인이다.

---

## 2. 조사 타임라인과 발견된 문제들

문제를 하나씩 고칠 때마다 증상이 재현되어, 총 5개의 서로 다른 원인을 순서대로 찾아 제거했다.

### 2-1. 매칭 후보 조회가 카테고리 완전 일치를 요구함
- `category=ETC`인 습득글은 실제로 같은 물건인 분실글과 카테고리가 달라서 매칭 후보에서 아예 제외되고 있었음.
- **수정**: `app/services/matching.py` — 카테고리/색상이 ETC·UNKNOWN이면 해당 조건을 무시하고 전체 매칭하도록 변경.

### 2-2. LLM 생성 콘텐츠 검증이 지나치게 엄격함 (1차)
- `_validate_generated_image_content`가 생성된 문구에 sourceFacts(위치+시각)에 없는 숫자가 하나라도 있으면 응답 전체를 버리도록 되어 있었음. 실제 사진에는 배터리 잔량, 블루투스 버전 등 정상적인 숫자가 자연스럽게 포함되므로 정상 응답도 계속 버려짐.
- **수정**: 숫자/위치/카테고리 텍스트 일치 검사를 제거.

### 2-3. 필드 하나만 안 맞아도 응답 전체를 버림 (2차)
- 위 수정 후에도, `category` 문자열이 enum과 정확히 안 맞는 등 사소한 불일치가 있으면 title/features/description까지 통째로 버려지고 있었음.
- **수정**: 필드별로 개별 처리 — LLM이 준 텍스트는 최대한 그대로 쓰고, category처럼 DB 제약(enum) 때문에 반드시 유효해야 하는 값만 파싱 실패 시 개별적으로 기본값 대체.

### 2-4. `content`가 항상 비어있는 문제 (Ollama 자체 버그)
- 사용자가 직접 코드를 수정하면서 `message.content`만 읽고 비어있으면 예외를 던지도록 바꿨는데, **`qwen3-vl` 모델은 Ollama의 `think: false` 요청 플래그를 무시하는 알려진 버그**(Ollama 이슈 [#14798](https://github.com/ollama/ollama/issues/14798), [#13353](https://github.com/ollama/ollama/issues/13353), [#12906](https://github.com/ollama/ollama/issues/12906))가 있어서 `content`는 항상 빈 문자열이고 실제 답은 항상 `thinking` 필드에 들어온다. 이 상태로는 100% 무조건 폴백됨.
- 직접 라이브로 여러 번 검증: `/no_think` 접미사, ChatML 수동 구성 등 우회법도 이 서버(Ollama 0.31.2)에서는 안 통함. `content` 우선, 없으면 `thinking` 사용이 유일하게 동작하는 방법.
- **수정**: `message.get("content") or message.get("thinking")` 폴백 복구.
- 같은 커밋에서 카테고리 정규화 함수가 `ItemCategory` enum 대신 순수 문자열(`.value`)을 반환하도록 바뀌어 있던 것도 함께 수정 (앱 전체가 category를 enum으로 다루는 걸 전제하므로).
- 라인 길이 초과(E501)로 CI가 실패하던 것도 같이 수정.

### 2-5. 실제 원인: 대용량 사진 처리 시간 초과 ⭐
- EC2 프로덕션 DB에서 최근 습득글 5건을 직접 조회 (`SELECT id, category, content_generator, created_at FROM found_posts ...`) → 위 4가지를 전부 고친 배포 **이후**에 만들어진 글도 여전히 `content_generator = grounded-template-v1`.
- `api` 컨테이너 로그에서 정확한 예외를 확인:
  ```
  httpx.HTTPStatusError: Client error '400 Bad Request' for url 'http://100.102.0.2:11434/api/chat'
  ```
- 실제 문제의 이미지 파일(`/data/uploads/30dfb689ce5144809d474271345c723d.jpg`, 3,443,130 bytes)을 가지고 재현을 시도하던 중, 유사한 크기(3024×4032, ~1.5MB)의 이미지를 리사이즈 없이 그대로 보내자 **120초가 넘도록 응답이 오지 않고 `ReadTimeout`** 발생을 직접 확인함.
- 같은 이미지를 1024px로 축소(1.17MB → 225KB)해서 보내자 **34~40초 만에 정상 200 응답**을 받음.
- **결론**: `OLLAMA_CONTENT_TIMEOUT_SECONDS`(60초) 안에 대용량 원본 사진의 비전 추론이 끝나지 못해 타임아웃 → 예외 발생 → 조용히 ETC 템플릿 폴백. (400 자체의 정확한 사유는 재현 환경상 타임아웃으로 대체 확인했으나, 대형 페이로드가 처리 파이프라인에서 문제를 일으킨다는 점은 동일하게 확인됨.)
- **수정**:
  - `_prepare_image_for_llm()` 추가 — Pillow로 이미지를 최대 1024px, JPEG quality 85로 리사이즈 후 전송.
  - `_post_to_ollama()`로 HTTP 호출을 통합하고, 실패 시 Ollama가 준 응답 본문을 그대로 로그에 남기도록 함 (다음에 실패해도 즉시 원인 파악 가능).

---

## 3. 최종 검증

앱 코드(`generate_found_post_content_from_image`)를 그대로 사용해 실제 Ollama 서버(`100.102.0.2:11434`, `qwen3-vl:4b`)로 라이브 테스트:

| 테스트 | 이미지 크기 | 결과 |
|---|---|---|
| 리사이즈 없이 노이즈 사진 (1.17MB, 3024×4032) | 원본 | 120초+ `ReadTimeout` |
| 동일 사진, 1024px 리사이즈 후 (225KB) | 축소 | 34초, `200 OK`, 정상 JSON |
| 실제 앱 함수로 대용량(1.5MB) 시뮬레이션 사진 end-to-end 실행 | 리사이즈 적용됨 | 40.1초, `generator: ollama-vision:qwen3-vl:4b` 정상 반환 |
| 이어폰 케이스(배터리 표시등 언급) 사진 | 소형 테스트 이미지 | `category: EARPHONE` 정확히 인식, 설명에 실제 관찰 내용 포함 |

로컬 테스트 스위트(`pytest`, 26개) 및 `ruff check` 전부 통과 확인.

---

## 3-1. 압축 포맷/강도 튜닝

리사이즈 적용 후, 압축을 더 세게(WebP, 저해상도) 조정해달라는 요청에 따라 추가로 측정했다.

- **WebP는 이 서버에서 아예 사용 불가**: 실제로 WebP 이미지를 보내보니 크기·해상도와 무관하게 즉시 `400 Bad Request` — 본문 확인 결과 `"Failed to load image or audio file"`. 이 Ollama 서버(0.31.2)의 이미지 디코더가 WebP를 지원하지 않는다. JPEG를 유지해야 한다.
- **해상도/품질을 더 낮춰도 처리 시간은 거의 안 줄어듦**: 같은 사진을 1024/768/512/384px로 각각 인코딩해 실측한 결과 전부 31~33초로 거의 동일했다. 즉 병목은 페이로드 전송량이 아니라 **모델의 고정 추론(생성) 시간**이며, 이는 원본 크기와 무관하게 일정하다. (반대로 리사이즈를 아예 안 한 원본 수 MB 이미지는 120초를 넘겨 타임아웃났다 — 즉 "어느 정도 이하로만 줄이면" 되고, 그 이하로 더 줄이는 건 속도에 별 의미가 없다.)
- **최종 설정**: `LLM_IMAGE_MAX_DIMENSION=768`, JPEG quality `80`으로 하향 조정해 60초 타임아웃 대비 여유를 더 확보했다 (실측 35.8초, 실제 앱 함수로 end-to-end 재검증 완료).

## 4. 변경 파일

- `app/services/found_content.py` — 검증 로직 단순화, thinking 폴백, 이미지 리사이즈, 에러 로깅 통합
- `app/services/matching.py` — ETC/UNKNOWN 카테고리·색상 매칭 완화
- `app/config.py`, `.env.example`, `compose.yaml` — `OLLAMA_CONTENT_TIMEOUT_SECONDS` 기본값 20초 → 60초
- `requirements.txt` — `Pillow` 의존성 추가
- `tests/test_llm.py` — 새 동작(검증 완화, enum 유지)에 맞게 테스트 갱신

`main`, `BE` 브랜치 모두에 동일하게 반영했다.

---

## 5. 남은 작업

- 이번 조사 중 사용자가 `BE` 브랜치에 직접 커밋(`73b4e8b`, `c3b022e`)한 변경을 로컬에서 이어받아 수정했다. **현재 로컬에만 있고 아직 push되지 않은 커밋**(`e1dca25`, `2df7ad1`, `667bd7e`, `ff45d57`)이 있으므로, 이 세션이 아닌 실제 GitHub 인증이 되는 환경에서 `git push origin BE:BE`로 반영해야 배포에 적용된다.
- push 후 GitHub Actions(`Backend CI`, `Deploy Backend to EC2`)가 성공하는지, 그리고 실제 사진으로 습득글을 등록했을 때 `content_generator`가 `ollama-vision:qwen3-vl:4b`로 찍히는지 위에서 사용한 것과 동일한 psql 쿼리로 재확인 권장.
