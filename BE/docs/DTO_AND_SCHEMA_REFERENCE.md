# LostLink DTO 및 DB 컬럼 명세

이 문서는 현재 Flask 백엔드 구현을 기준으로 REST API, Socket.IO, PostgreSQL DTO와 컬럼을 정리한다. 별도 DTO 클래스는 없으며 Flask 핸들러의 JSON 계약과 SQLAlchemy 모델을 명세 형태로 표현했다.

## 1. 표기 규칙

| 항목 | 규칙 |
|---|---|
| REST·Socket 필드 | `camelCase` |
| DB 컬럼 | `snake_case` |
| JSON 기본 자료형 | `string`, `number`, `integer`, `boolean`, `object`, `array`, `null` |
| 날짜·시간 DTO | ISO 8601 `string`; 요청의 `Z`·offset을 UTC로 변환 |
| 날짜·시간 DB | `TIMESTAMP WITHOUT TIME ZONE`; 저장값과 응답값은 UTC 의미로 처리 |
| 선택값 | `T \| null` 또는 요청 필수 여부 `N` |
| REST 성공 본문 | `ApiResponse<T>` |
| REST 오류 본문 | `ApiErrorResponse` |
| 인증 | `Authorization: Bearer {accessToken}` |

`siteCode`, 사용자 역할, 플랫폼, 푸시 토큰은 현재 DTO와 DB 스키마에 존재하지 않는다.

## 2. 공통 Enum

### 2.1 ItemCategory

| 값 | 의미 |
|---|---|
| `CARD` | 카드·학생증 |
| `WALLET` | 지갑 |
| `EARPHONE` | 이어폰·이어폰 케이스 |
| `BAG` | 가방 |
| `KEY` | 열쇠·키링 |
| `ELECTRONICS` | 전자기기 |
| `CLOTHING` | 의류 |
| `UMBRELLA` | 우산 |
| `STATIONERY` | 문구류 |
| `ETC` | 기타 |

### 2.2 상태값

| 구분 | 값 |
|---|---|
| `LostPostStatus` | `OPEN`, `MATCHED`, `RETURNED`, `CLOSED` |
| `FoundPostStatus` | `STORED`, `CLAIMED`, `RETURNED`, `CLOSED` |
| `MatchStatus` | `CANDIDATE`, `CLAIM_REQUESTED`, `VERIFIED`, `REJECTED`, `HANDED_OVER` |
| `MatchGrade` | `VERY_HIGH`, `HIGH`, `MEDIUM` |

`contactMethod`는 DB에서 `VARCHAR(20)`이며 기본값은 `NOTIFICATION`이다. 현재 API는 별도 Enum 검증을 하지 않는다.

## 3. 공통 응답 DTO

### 3.1 ApiResponse<T>

| JSON 필드 | 자료형 | 설명 |
|---|---|---|
| `success` | `boolean` | 성공 시 `true` |
| `data` | `T \| null` | 엔드포인트별 응답 데이터 |
| `error` | `null` | 성공 응답에서는 `null` |

### 3.2 ApiErrorResponse

| JSON 필드 | 자료형 | 설명 |
|---|---|---|
| `success` | `boolean` | 항상 `false` |
| `data` | `null` | 항상 `null` |
| `error` | `ErrorDto` | 오류 정보 |

### 3.3 ErrorDto / ErrorDetailDto

| DTO | JSON 필드 | 자료형 | 설명 |
|---|---|---|---|
| `ErrorDto` | `code` | `string` | 서버 오류 코드 |
| `ErrorDto` | `message` | `string` | 사용자 표시 가능 메시지 |
| `ErrorDto` | `details` | `ErrorDetailDto[]` | 필드별 상세 오류, 없으면 빈 배열 |
| `ErrorDetailDto` | `field` | `string` | 오류가 발생한 요청 필드 |
| `ErrorDetailDto` | `reason` | `string` | 오류 사유 |

### 3.4 PageDto

| JSON 필드 | 자료형 | 설명 |
|---|---|---|
| `number` | `integer` | 현재 페이지, 최소 1 |
| `size` | `integer` | 페이지 크기, 1~100 |
| `total` | `integer` | 전체 항목 수 |
| `pages` | `integer` | 전체 페이지 수 |

## 4. 인증·사용자 요청 DTO

### 4.1 SignupRequest

`POST /api/v1/auth/signup`에서 사용한다. 모바일 앱에서는 호출하지 않고 Postman 계정 생성용으로 사용한다.

| JSON 필드 | 자료형 | 필수 | DB 컬럼 | 제약 |
|---|---|---:|---|---|
| `email` | `string` | Y | `users.email` | 이메일 형식, 소문자로 저장, UNIQUE |
| `password` | `string` | Y | `users.password_hash` | 8~64자, 해시 후 저장 |
| `nickname` | `string` | Y | `users.nickname` | 2~20자 |

### 4.2 LoginRequest

| JSON 필드 | 자료형 | 필수 | DB 조회 컬럼 | 설명 |
|---|---|---:|---|---|
| `email` | `string` | Y | `users.email` | 소문자로 정규화 |
| `password` | `string` | Y | `users.password_hash` | 해시 비교, 저장하지 않음 |

### 4.3 UpdateUserRequest

`PATCH /api/v1/users/me`에서 사용하며 모든 필드는 선택이다.

| JSON 필드 | 자료형 | 필수 | DB 컬럼 | 제약 |
|---|---|---:|---|---|
| `nickname` | `string` | N | `users.nickname` | 제공 시 2~20자 |
| `profileImageUrl` | `string \| null` | N | `users.profile_image_url` | 업로드 API가 반환한 경로 또는 `null` |

Refresh 요청은 JSON 본문 없이 Refresh JWT만 사용한다.

## 5. 분실글 요청 DTO

### 5.1 CreateLostPostRequest

| JSON 필드 | 자료형 | 필수 | DB 컬럼 | 설명 |
|---|---|---:|---|---|
| `title` | `string` | Y | `lost_posts.title` | 최대 저장 길이 100 |
| `category` | `ItemCategory` | Y | `lost_posts.category` | 대문자 Enum으로 정규화 |
| `color` | `string` | Y | `lost_posts.color` | 대문자로 저장, 최대 30 |
| `location` | `string` | Y | `lost_posts.location` | 최대 100 |
| `lostAt` | ISO 8601 `string` | Y | `lost_posts.lost_at` | UTC 변환 후 저장 |
| `features` | `string` | Y | `lost_posts.features` | 공개 특징 |
| `privateFeature` | `string \| null` | N | `lost_posts.private_feature` | 작성자와 매칭 확인용 |
| `description` | `string \| null` | N | `lost_posts.description` | 추가 설명 |
| `imageUrl` | `string \| null` | N | `lost_posts.image_url` | 최대 500 |
| `contactMethod` | `string` | N | `lost_posts.contact_method` | 기본값 `NOTIFICATION`, 최대 20 |

### 5.2 UpdateLostPostRequest

모든 필드는 선택이며 `PATCH /api/v1/lost-posts/{id}`에서 사용한다.

| JSON 필드 | 자료형 | DB 컬럼 | 설명 |
|---|---|---|---|
| `title` | `string` | `title` | 제목 수정 |
| `category` | `ItemCategory` | `category` | 수정 시 재분석 |
| `color` | `string` | `color` | 수정 시 재분석 |
| `location` | `string` | `location` | 수정 시 재분석 |
| `lostAt` | ISO 8601 `string` | `lost_at` | 수정 시 재분석 |
| `features` | `string` | `features` | 수정 시 재분석 |
| `privateFeature` | `string \| null` | `private_feature` | 비공개 특징 |
| `description` | `string \| null` | `description` | 추가 설명 |
| `imageUrl` | `string \| null` | `image_url` | 이미지 경로 |
| `contactMethod` | `string` | `contact_method` | 수정해도 재분석하지 않음 |
| `status` | `OPEN \| CLOSED` | `status` | 사용자가 직접 변경 가능한 상태만 허용 |

### 5.3 LostPostListQuery

| 쿼리 필드 | 자료형 | 필수 | 기본값 | 설명 |
|---|---|---:|---|---|
| `location` | `string` | N | 없음 | 장소 완전 일치 |
| `status` | `string` | N | 없음 | 대문자 변환 후 완전 일치 |
| `category` | `ItemCategory` | N | 없음 | 카테고리 완전 일치 |
| `page` | `integer` | N | `1` | 최소 1 |
| `size` | `integer` | N | `20` | 1~100 |

## 6. 습득글 요청 DTO

### 6.1 CreateFoundPostRequest

| JSON 필드 | 자료형 | 필수 | DB 컬럼 | 설명 |
|---|---|---:|---|---|
| `category` | `ItemCategory` | Y | `found_posts.category` | 자동 생성 입력 사실 |
| `color` | `string` | Y | `found_posts.color` | 대문자로 저장, 최대 30 |
| `location` | `string` | Y | `found_posts.location` | 최대 100 |
| `foundAt` | ISO 8601 `string` | Y | `found_posts.found_at` | UTC 변환 후 저장 |
| `storageLocation` | `string` | Y | `found_posts.storage_location` | 작성자에게만 반환, 최대 100 |
| `observations` | `string` | N | `found_posts.source_observations` | 공개 관찰 정보, 최대 1000 |
| `features` | `string` | N | `source_observations` | `observations`가 없을 때만 쓰는 레거시 별칭 |
| `privateFeature` | `string \| null` | N | `found_posts.private_feature` | 본인 확인용 비공개 특징 |
| `verificationQuestion` | `string \| null` | N | `found_posts.verification_question` | 최대 255 |
| `imageUrl` | `string \| null` | N | `found_posts.image_url` | 최대 500 |

`title`, `features`, `description` 응답값은 서버가 공개 입력 사실로 생성한다. 위 요청의 `features`는 출력 직접 지정이 아니라 이전 클라이언트 호환용 관찰 정보 별칭이다.

### 6.2 UpdateFoundPostRequest

모든 필드는 선택이며 `title`, `features`, `description` 직접 수정은 거절된다.

| JSON 필드 | 자료형 | DB 컬럼 | 설명 |
|---|---|---|---|
| `category` | `ItemCategory` | `category` | 내용 재생성·재분석 |
| `color` | `string` | `color` | 내용 재생성·재분석 |
| `location` | `string` | `location` | 내용 재생성·재분석 |
| `foundAt` | ISO 8601 `string` | `found_at` | 내용 재생성·재분석 |
| `observations` | `string` | `source_observations` | 최대 1000, 내용 재생성·재분석 |
| `storageLocation` | `string` | `storage_location` | 비공개 보관 장소 |
| `privateFeature` | `string \| null` | `private_feature` | 비공개 특징 |
| `verificationQuestion` | `string \| null` | `verification_question` | 본인 확인 질문 |
| `imageUrl` | `string \| null` | `image_url` | 이미지 경로 |
| `status` | `STORED \| CLOSED` | `status` | 사용자가 직접 변경 가능한 상태만 허용 |

### 6.3 FoundPostListQuery

| 쿼리 필드 | 자료형 | 필수 | 기본값 | 설명 |
|---|---|---:|---|---|
| `location` | `string` | N | 없음 | 장소 완전 일치 |
| `category` | `ItemCategory` | N | 없음 | 카테고리 완전 일치 |
| `page` | `integer` | N | `1` | 최소 1 |
| `size` | `integer` | N | `20` | 1~100 |

목록은 서버에서 항상 `STORED` 상태만 조회한다.

## 7. 매칭·채팅·업로드 요청 DTO

### 7.1 ClaimMatchRequest

| JSON 필드 | 자료형 | 필수 | DB 컬럼 | 설명 |
|---|---|---:|---|---|
| `answer` | `string` | Y | `matches.claim_answer` | 본인 확인 답변 |
| `message` | `string \| null` | N | `matches.claim_message` | 요청 메시지, DB 최대 500 |

### 7.2 RejectMatchRequest

| JSON 필드 | 자료형 | 필수 | DB 컬럼 | 설명 |
|---|---|---:|---|---|
| `reason` | `string \| null` | N | `matches.rejection_reason` | 거절 사유, DB 최대 500 |

`verify`, `handover`, 채팅방 열기, 수동 재분석 요청에는 JSON 본문이 없다.

### 7.3 ChatMessageListQuery

| 쿼리 필드 | 자료형 | 필수 | 기본값 | 설명 |
|---|---|---:|---|---|
| `beforeId` | `integer` | N | 없음 | 해당 ID보다 이전 메시지 조회 |
| `limit` | `integer` | N | `50` | 1~100 |

### 7.4 ReadMessagesRequest

| JSON 필드 | 자료형 | 필수 | DB 대응 컬럼 | 설명 |
|---|---|---:|---|---|
| `messageId` | `integer` | Y | `chat_room_members.last_read_message_id` | 같은 채팅방의 메시지 ID |

### 7.5 UploadImageRequest

| multipart 필드 | 자료형 | 필수 | 설명 |
|---|---|---:|---|
| `image` | binary file | Y | JPEG, PNG, WebP 파일 |

이미지는 Base64 JSON으로 전송하지 않는다.

## 8. 핵심 응답 DTO

### 8.1 UserDto

| JSON 필드 | 자료형 | DB 컬럼 |
|---|---|---|
| `id` | `integer` | `users.id` |
| `email` | `string` | `users.email` |
| `nickname` | `string` | `users.nickname` |
| `profileImageUrl` | `string \| null` | `users.profile_image_url` |
| `isActive` | `boolean` | `users.is_active` |
| `createdAt` | ISO 8601 `string` | `users.created_at` |
| `updatedAt` | ISO 8601 `string` | `users.updated_at` |

### 8.2 인증 응답 데이터

| DTO | JSON 필드 | 자료형 |
|---|---|---|
| `SignupData` | `user` | `UserDto` |
| `LoginData` | `accessToken` | `string` |
| `LoginData` | `refreshToken` | `string` |
| `LoginData` | `user` | `UserDto` |
| `RefreshData` | `accessToken` | `string` |

### 8.3 LostPostDto

| JSON 필드 | 자료형 | DB 컬럼 | 공개 범위 |
|---|---|---|---|
| `id` | `integer` | `lost_posts.id` | 공개 |
| `userId` | `integer` | `lost_posts.user_id` | 공개 |
| `title` | `string` | `lost_posts.title` | 공개 |
| `category` | `ItemCategory` | `lost_posts.category` | 공개 |
| `color` | `string` | `lost_posts.color` | 공개 |
| `location` | `string` | `lost_posts.location` | 공개 |
| `lostAt` | ISO 8601 `string` | `lost_posts.lost_at` | 공개 |
| `features` | `string` | `lost_posts.features` | 공개 |
| `description` | `string \| null` | `lost_posts.description` | 공개 |
| `imageUrl` | `string \| null` | `lost_posts.image_url` | 공개 |
| `contactMethod` | `string` | `lost_posts.contact_method` | 공개 |
| `status` | `LostPostStatus` | `lost_posts.status` | 공개 |
| `createdAt` | ISO 8601 `string` | `lost_posts.created_at` | 공개 |
| `updatedAt` | ISO 8601 `string` | `lost_posts.updated_at` | 공개 |
| `privateFeature` | `string \| null` | `lost_posts.private_feature` | 작성자만 |

### 8.4 FoundPostDto

| JSON 필드 | 자료형 | DB 컬럼 | 공개 범위 |
|---|---|---|---|
| `id` | `integer` | `found_posts.id` | 공개 |
| `userId` | `integer` | `found_posts.user_id` | 공개 |
| `title` | `string` | `found_posts.title` | 공개·서버 생성 |
| `category` | `ItemCategory` | `found_posts.category` | 공개 |
| `color` | `string` | `found_posts.color` | 공개 |
| `location` | `string` | `found_posts.location` | 공개 |
| `foundAt` | ISO 8601 `string` | `found_posts.found_at` | 공개 |
| `features` | `string` | `found_posts.features` | 공개·서버 생성 |
| `description` | `string \| null` | `found_posts.description` | 공개·서버 생성 |
| `contentGenerator` | `string` | `found_posts.content_generator` | 공개 |
| `imageUrl` | `string \| null` | `found_posts.image_url` | 공개 |
| `status` | `FoundPostStatus` | `found_posts.status` | 공개 |
| `createdAt` | ISO 8601 `string` | `found_posts.created_at` | 공개 |
| `updatedAt` | ISO 8601 `string` | `found_posts.updated_at` | 공개 |
| `storageLocation` | `string` | `found_posts.storage_location` | 작성자만 |
| `observations` | `string` | `found_posts.source_observations` | 작성자만 |
| `privateFeature` | `string \| null` | `found_posts.private_feature` | 작성자만 |
| `verificationQuestion` | `string \| null` | `found_posts.verification_question` | 작성자만 |

### 8.5 게시글 부가 응답 DTO

| DTO | JSON 필드 | 자료형 | 설명 |
|---|---|---|---|
| `PostMutationData<T>` | `post` | `T` | `LostPostDto` 또는 `FoundPostDto` |
| `PostMutationData<T>` | `analysisQueued` | `boolean` | 분석 작업 예약 여부 |
| `FoundPostMutationData` | `contentGeneration` | `ContentGenerationDto` | 생성 또는 재생성 시 포함 |
| `ContentGenerationDto` | `generator` | `string` | Ollama 모델명 또는 템플릿 버전 |
| `ContentGenerationDto` | `sourceFields` | `string[]` | 생성에 사용한 공개 필드명 |
| `PostListData<T>` | `items` | `T[]` | 게시글 목록 |
| `PostListData<T>` | `page` | `PageDto` | 페이지 정보 |
| `AnalyzeJobData` | `jobId` | `string` | Celery 작업 ID |
| `AnalyzeJobData` | `status` | `QUEUED` | 작업 상태 |

### 8.6 MatchDto

| JSON 필드 | 자료형 | DB 컬럼·출처 |
|---|---|---|
| `id` | `integer` | `matches.id` |
| `lostPostId` | `integer` | `matches.lost_post_id` |
| `foundPostId` | `integer` | `matches.found_post_id` |
| `score` | `number` | `matches.score` |
| `grade` | `MatchGrade` | `score` 계산값 |
| `scoreDetails` | `ScoreDetailsDto` | 세부 점수 컬럼 조합 |
| `reasons` | `string[]` | `matches.reasons` JSON |
| `modelVersion` | `string` | `matches.model_version` |
| `status` | `MatchStatus` | `matches.status` |
| `chatRoomId` | `integer \| null` | 연결된 `chat_rooms.id` |
| `claimedAt` | ISO 8601 `string \| null` | `matches.claimed_at` |
| `confirmedBy` | `integer \| null` | `matches.confirmed_by` |
| `confirmedAt` | ISO 8601 `string \| null` | `matches.confirmed_at` |
| `rejectionReason` | `string \| null` | `matches.rejection_reason` |
| `handedOverAt` | ISO 8601 `string \| null` | `matches.handed_over_at` |
| `createdAt` | ISO 8601 `string` | `matches.created_at` |
| `updatedAt` | ISO 8601 `string` | `matches.updated_at` |
| `lostPost` | `LostPostDto` | 목록·상세에서 포함, 비공개 필드 제외 |
| `foundPost` | `FoundPostDto` | 목록·상세에서 포함, 비공개 필드 제외 |
| `claimAnswer` | `string \| null` | `matches.claim_answer`, 민감 응답에서만 포함 |
| `claimMessage` | `string \| null` | `matches.claim_message`, 민감 응답에서만 포함 |

### 8.7 ScoreDetailsDto

| JSON 필드 | 자료형 | DB 컬럼 | 최대 배점 |
|---|---|---|---:|
| `category` | `number` | `matches.category_score` | 30 |
| `color` | `number` | `matches.color_score` | 15 |
| `location` | `number` | `matches.location_score` | 20 |
| `time` | `number` | `matches.time_score` | 15 |
| `feature` | `number` | `matches.feature_score` | 20 |

### 8.8 ChatMemberDto / ChatMessageDto

| DTO | JSON 필드 | 자료형 | DB 컬럼·출처 |
|---|---|---|---|
| `ChatMemberDto` | `id` | `integer` | `users.id` |
| `ChatMemberDto` | `nickname` | `string` | `users.nickname` |
| `ChatMemberDto` | `profileImageUrl` | `string \| null` | `users.profile_image_url` |
| `ChatMessageDto` | `id` | `integer` | `chat_messages.id` |
| `ChatMessageDto` | `roomId` | `integer` | `chat_messages.room_id` |
| `ChatMessageDto` | `sender` | `ChatMemberDto` | `chat_messages.sender_id`로 조회 |
| `ChatMessageDto` | `content` | `string` | `chat_messages.content` |
| `ChatMessageDto` | `clientMessageId` | `string \| null` | `chat_messages.client_message_id` |
| `ChatMessageDto` | `createdAt` | ISO 8601 `string` | `chat_messages.created_at` |

### 8.9 ChatRoomDto

| JSON 필드 | 자료형 | DB 컬럼·출처 |
|---|---|---|
| `id` | `integer` | `chat_rooms.id` |
| `matchId` | `integer` | `chat_rooms.match_id` |
| `matchStatus` | `MatchStatus` | 연결된 `matches.status` |
| `members` | `ChatMemberDto[]` | `chat_room_members`와 `users` 조합 |
| `lastMessage` | `ChatMessageDto \| null` | 해당 방의 마지막 메시지 |
| `unreadCount` | `integer` | 마지막 읽은 ID 기준 계산값 |
| `createdAt` | ISO 8601 `string` | `chat_rooms.created_at` |
| `updatedAt` | ISO 8601 `string` | `chat_rooms.updated_at` |

### 8.10 채팅 부가 응답 DTO

| DTO | JSON 필드 | 자료형 |
|---|---|---|
| `ChatRoomListData` | `items` | `ChatRoomDto[]` |
| `ChatMessageListData` | `items` | `ChatMessageDto[]` |
| `ChatMessageListData` | `hasMore` | `boolean` |
| `ChatMessageListData` | `nextBeforeId` | `integer \| null` |
| `ReadReceiptDto` | `roomId` | `integer` |
| `ReadReceiptDto` | `messageId` | `integer` |
| `ReadReceiptDto` | `lastReadMessageId` | `integer` |
| `ReadReceiptDto` | `lastReadAt` | ISO 8601 `string` |

### 8.11 기타 응답 DTO

| DTO | JSON 필드 | 자료형 | 설명 |
|---|---|---|---|
| `CategoryDto` | `code` | `ItemCategory` | 카테고리 코드 |
| `CategoryDto` | `label` | `string` | 한국어 표시명 |
| `CategoryListData` | `items` | `CategoryDto[]` | 전체 카테고리 |
| `UploadImageData` | `fileName` | `string` | UUID 기반 저장 파일명 |
| `UploadImageData` | `url` | `string` | `/uploads/{fileName}` |
| `HealthDto` | `status` | `ok` | `/healthz`는 공통 envelope 없이 반환 |

## 9. REST 엔드포인트와 DTO 매핑

모든 응답은 별도 표기가 없으면 `ApiResponse<응답 데이터>` 형태다.

| Method | Endpoint | 요청 DTO | 응답 데이터 DTO |
|---|---|---|---|
| POST | `/api/v1/auth/signup` | `SignupRequest` | `SignupData` |
| POST | `/api/v1/auth/login` | `LoginRequest` | `LoginData` |
| POST | `/api/v1/auth/refresh` | 본문 없음 | `RefreshData` |
| GET | `/api/v1/users/me` | 본문 없음 | `UserDto` |
| PATCH | `/api/v1/users/me` | `UpdateUserRequest` | `UserDto` |
| GET | `/api/v1/categories` | 본문 없음 | `CategoryListData` |
| POST | `/api/v1/uploads/images` | `UploadImageRequest` | `UploadImageData` |
| GET | `/uploads/{fileName}` | 본문 없음 | 이미지 binary, Nginx 직접 응답 |
| POST | `/api/v1/lost-posts` | `CreateLostPostRequest` | `PostMutationData<LostPostDto>` |
| GET | `/api/v1/lost-posts` | `LostPostListQuery` | `PostListData<LostPostDto>` |
| GET | `/api/v1/lost-posts/{id}` | 본문 없음 | `LostPostDto` |
| PATCH | `/api/v1/lost-posts/{id}` | `UpdateLostPostRequest` | `PostMutationData<LostPostDto>` |
| DELETE | `/api/v1/lost-posts/{id}` | 본문 없음 | 본문 없음, HTTP 204 |
| POST | `/api/v1/lost-posts/{id}/matches/analyze` | 본문 없음 | `AnalyzeJobData` |
| POST | `/api/v1/found-posts` | `CreateFoundPostRequest` | `FoundPostMutationData` |
| GET | `/api/v1/found-posts` | `FoundPostListQuery` | `PostListData<FoundPostDto>` |
| GET | `/api/v1/found-posts/{id}` | 본문 없음 | `FoundPostDto` |
| PATCH | `/api/v1/found-posts/{id}` | `UpdateFoundPostRequest` | `FoundPostMutationData` |
| DELETE | `/api/v1/found-posts/{id}` | 본문 없음 | 본문 없음, HTTP 204 |
| GET | `/api/v1/matches/lost-posts/{id}` | 본문 없음 | `{ items: MatchDto[] }` |
| GET | `/api/v1/matches/found-posts/{id}` | 본문 없음 | `{ items: MatchDto[] }` |
| GET | `/api/v1/matches/{id}` | 본문 없음 | 민감 필드 포함 `MatchDto` |
| POST | `/api/v1/matches/{id}/claims` | `ClaimMatchRequest` | 민감 필드 포함 `MatchDto` |
| PATCH | `/api/v1/matches/{id}/verify` | 본문 없음 | 민감 필드 포함 `MatchDto` |
| PATCH | `/api/v1/matches/{id}/reject` | `RejectMatchRequest` | `MatchDto` |
| PATCH | `/api/v1/matches/{id}/handover` | 본문 없음 | 민감 필드 포함 `MatchDto` |
| GET | `/api/v1/chats` | 본문 없음 | `ChatRoomListData` |
| POST | `/api/v1/chats/matches/{matchId}` | 본문 없음 | `ChatRoomDto` |
| GET | `/api/v1/chats/{roomId}` | 본문 없음 | `ChatRoomDto` |
| GET | `/api/v1/chats/{roomId}/messages` | `ChatMessageListQuery` | `ChatMessageListData` |
| PATCH | `/api/v1/chats/{roomId}/read` | `ReadMessagesRequest` | `ReadReceiptDto` |
| GET | `/healthz` | 본문 없음 | `HealthDto` |

## 10. Socket.IO DTO

### 10.1 연결 인증

| 필드 | 자료형 | 필수 | 설명 |
|---|---|---:|---|
| `auth.token` | `string` | Y | Access JWT, `Bearer ` 접두사는 선택 |

연결 성공 시 서버가 `connected` 이벤트로 `{ "userId": integer }`를 전송한다.

### 10.2 클라이언트 송신 이벤트

| 이벤트 | 필드 | 자료형 | 필수 | 설명 |
|---|---|---|---:|---|
| `join_chat` | `roomId` | `integer` | Y | 참여할 채팅방 |
| `leave_chat` | `roomId` | `integer` | Y | 퇴장할 채팅방 |
| `send_message` | `roomId` | `integer` | Y | 대상 채팅방 |
| `send_message` | `content` | `string` | Y | 1~1000자 |
| `send_message` | `clientMessageId` | `string` | N | 재전송 중복 방지 ID, 최대 64자 |
| `typing` | `roomId` | `integer` | Y | 대상 채팅방 |
| `typing` | `isTyping` | `boolean` | N | 입력 중 여부, 누락 시 `false` |
| `mark_read` | `roomId` | `integer` | Y | 대상 채팅방 |
| `mark_read` | `messageId` | `integer` | Y | 마지막으로 읽은 메시지 |

### 10.3 acknowledgement DTO

| 동작 | 성공 acknowledgement |
|---|---|
| `join_chat`, `leave_chat` | `{ success: true, data: { roomId: integer } }` |
| `send_message` | `{ success: true, data: ChatMessageDto, created: boolean }` |
| `typing` | `{ success: true }` |
| `mark_read` | `{ success: true, data: SocketReadReceiptDto }` |
| 모든 이벤트 오류 | `{ success: false, error: { code: string, message: string } }` |

`SocketReadReceiptDto`는 `ReadReceiptDto`에 읽은 사용자 `userId: integer`가 추가된다.

### 10.4 서버 송신 이벤트

| 이벤트 | payload DTO |
|---|---|
| `connected` | `{ userId: integer }` |
| `new_message` | `ChatMessageDto` |
| `typing` | `{ roomId: integer, userId: integer, isTyping: boolean }` |
| `messages_read` | `SocketReadReceiptDto` |

## 11. PostgreSQL 테이블 컬럼

아래 타입은 배포된 PostgreSQL 16 스키마의 실제 `information_schema` 결과를 기준으로 한다.

### 11.1 users

| 컬럼 | PostgreSQL 타입 | NULL | 키·제약 | DTO 대응 |
|---|---|---:|---|---|
| `id` | `INTEGER` | N | PK, sequence | `UserDto.id` |
| `email` | `VARCHAR(255)` | N | UNIQUE, index | `UserDto.email` |
| `password_hash` | `VARCHAR(255)` | N |  | 응답 미노출 |
| `nickname` | `VARCHAR(20)` | N |  | `UserDto.nickname` |
| `profile_image_url` | `VARCHAR(500)` | Y |  | `UserDto.profileImageUrl` |
| `is_active` | `BOOLEAN` | N | 앱 기본값 `true` | `UserDto.isActive` |
| `created_at` | `TIMESTAMP WITHOUT TIME ZONE` | N | UTC | `UserDto.createdAt` |
| `updated_at` | `TIMESTAMP WITHOUT TIME ZONE` | N | UTC | `UserDto.updatedAt` |

### 11.2 lost_posts

| 컬럼 | PostgreSQL 타입 | NULL | 키·제약 | DTO 대응 |
|---|---|---:|---|---|
| `id` | `INTEGER` | N | PK, sequence | `LostPostDto.id` |
| `user_id` | `INTEGER` | N | FK `users.id`, index | `userId` |
| `title` | `VARCHAR(100)` | N |  | `title` |
| `category` | `VARCHAR(11)` | N | `ItemCategory` check, index | `category` |
| `color` | `VARCHAR(30)` | N | index | `color` |
| `location` | `VARCHAR(100)` | N | index | `location` |
| `lost_at` | `TIMESTAMP WITHOUT TIME ZONE` | N | index | `lostAt` |
| `features` | `TEXT` | N |  | `features` |
| `private_feature` | `TEXT` | Y |  | `privateFeature` |
| `description` | `TEXT` | Y |  | `description` |
| `image_url` | `VARCHAR(500)` | Y |  | `imageUrl` |
| `contact_method` | `VARCHAR(20)` | N | 앱 기본값 `NOTIFICATION` | `contactMethod` |
| `status` | `VARCHAR(20)` | N | 앱 기본값 `OPEN`, index | `status` |
| `created_at` | `TIMESTAMP WITHOUT TIME ZONE` | N | UTC | `createdAt` |
| `updated_at` | `TIMESTAMP WITHOUT TIME ZONE` | N | UTC | `updatedAt` |

후보 조회 복합 인덱스는 `(status, category, lost_at)`이다.

### 11.3 found_posts

| 컬럼 | PostgreSQL 타입 | NULL | 키·제약 | DTO 대응 |
|---|---|---:|---|---|
| `id` | `INTEGER` | N | PK, sequence | `FoundPostDto.id` |
| `user_id` | `INTEGER` | N | FK `users.id`, index | `userId` |
| `title` | `VARCHAR(100)` | N | 서버 생성 | `title` |
| `category` | `VARCHAR(11)` | N | `ItemCategory` check, index | `category` |
| `color` | `VARCHAR(30)` | N | index | `color` |
| `location` | `VARCHAR(100)` | N | index | `location` |
| `found_at` | `TIMESTAMP WITHOUT TIME ZONE` | N | index | `foundAt` |
| `storage_location` | `VARCHAR(100)` | N | 비공개 | `storageLocation` |
| `features` | `TEXT` | N | 서버 생성 | `features` |
| `private_feature` | `TEXT` | Y | 비공개 | `privateFeature` |
| `verification_question` | `VARCHAR(255)` | Y | 비공개 | `verificationQuestion` |
| `description` | `TEXT` | Y | 서버 생성 | `description` |
| `image_url` | `VARCHAR(500)` | Y |  | `imageUrl` |
| `status` | `VARCHAR(20)` | N | 앱 기본값 `STORED`, index | `status` |
| `created_at` | `TIMESTAMP WITHOUT TIME ZONE` | N | UTC | `createdAt` |
| `updated_at` | `TIMESTAMP WITHOUT TIME ZONE` | N | UTC | `updatedAt` |
| `source_observations` | `TEXT` | N | DB 기본값 빈 문자열 | `observations` |
| `content_generator` | `VARCHAR(100)` | N | DB 기본값 `legacy/manual-v1` | `contentGenerator` |

후보 조회 복합 인덱스는 `(status, category, found_at)`이다.

### 11.4 matches

| 컬럼 | PostgreSQL 타입 | NULL | 키·제약 | DTO 대응 |
|---|---|---:|---|---|
| `id` | `INTEGER` | N | PK, sequence | `MatchDto.id` |
| `lost_post_id` | `INTEGER` | N | FK `lost_posts.id`, index | `lostPostId` |
| `found_post_id` | `INTEGER` | N | FK `found_posts.id`, index | `foundPostId` |
| `score` | `NUMERIC(5,2)` | N | index | `score` |
| `category_score` | `NUMERIC(5,2)` | N |  | `scoreDetails.category` |
| `color_score` | `NUMERIC(5,2)` | N |  | `scoreDetails.color` |
| `location_score` | `NUMERIC(5,2)` | N |  | `scoreDetails.location` |
| `time_score` | `NUMERIC(5,2)` | N |  | `scoreDetails.time` |
| `feature_score` | `NUMERIC(5,2)` | N |  | `scoreDetails.feature` |
| `reasons` | `JSON` | N | 앱 기본값 빈 배열 | `reasons` |
| `model_version` | `VARCHAR(50)` | N |  | `modelVersion` |
| `status` | `VARCHAR(30)` | N | 앱 기본값 `CANDIDATE`, index | `status` |
| `claim_answer` | `TEXT` | Y | 민감 정보 | `claimAnswer` |
| `claim_message` | `VARCHAR(500)` | Y | 민감 정보 | `claimMessage` |
| `claimed_at` | `TIMESTAMP WITHOUT TIME ZONE` | Y | UTC | `claimedAt` |
| `confirmed_by` | `INTEGER` | Y | FK `users.id` | `confirmedBy` |
| `confirmed_at` | `TIMESTAMP WITHOUT TIME ZONE` | Y | UTC | `confirmedAt` |
| `rejection_reason` | `VARCHAR(500)` | Y |  | `rejectionReason` |
| `handed_over_at` | `TIMESTAMP WITHOUT TIME ZONE` | Y | UTC | `handedOverAt` |
| `created_at` | `TIMESTAMP WITHOUT TIME ZONE` | N | UTC | `createdAt` |
| `updated_at` | `TIMESTAMP WITHOUT TIME ZONE` | N | UTC | `updatedAt` |

`(lost_post_id, found_post_id)` 조합은 UNIQUE다.

### 11.5 chat_rooms

| 컬럼 | PostgreSQL 타입 | NULL | 키·제약 | DTO 대응 |
|---|---|---:|---|---|
| `id` | `INTEGER` | N | PK, sequence | `ChatRoomDto.id` |
| `match_id` | `INTEGER` | N | FK `matches.id` ON DELETE CASCADE, UNIQUE | `matchId` |
| `created_at` | `TIMESTAMP WITHOUT TIME ZONE` | N | UTC | `createdAt` |
| `updated_at` | `TIMESTAMP WITHOUT TIME ZONE` | N | UTC | `updatedAt` |

### 11.6 chat_room_members

| 컬럼 | PostgreSQL 타입 | NULL | 키·제약 | DTO 대응 |
|---|---|---:|---|---|
| `id` | `INTEGER` | N | PK, sequence | 직접 미노출 |
| `room_id` | `INTEGER` | N | FK `chat_rooms.id` ON DELETE CASCADE, index | `roomId` 계산 기준 |
| `user_id` | `INTEGER` | N | FK `users.id`, index | `members[].id` 조회 기준 |
| `last_read_message_id` | `INTEGER` | Y | index | `lastReadMessageId` |
| `last_read_at` | `TIMESTAMP WITHOUT TIME ZONE` | Y | index, UTC | `lastReadAt` |
| `created_at` | `TIMESTAMP WITHOUT TIME ZONE` | N | UTC | 직접 미노출 |
| `updated_at` | `TIMESTAMP WITHOUT TIME ZONE` | N | UTC | 직접 미노출 |

`(room_id, user_id)` 조합은 UNIQUE다.

### 11.7 chat_messages

| 컬럼 | PostgreSQL 타입 | NULL | 키·제약 | DTO 대응 |
|---|---|---:|---|---|
| `id` | `INTEGER` | N | PK, sequence | `ChatMessageDto.id` |
| `room_id` | `INTEGER` | N | FK `chat_rooms.id` ON DELETE CASCADE, index | `roomId` |
| `sender_id` | `INTEGER` | N | FK `users.id`, index | `sender.id` 조회 기준 |
| `content` | `VARCHAR(1000)` | N | 1~1000자 | `content` |
| `client_message_id` | `VARCHAR(64)` | Y | 재전송 중복 방지 | `clientMessageId` |
| `created_at` | `TIMESTAMP WITHOUT TIME ZONE` | N | index, UTC | `createdAt` |

`(room_id, sender_id, client_message_id)` 조합은 UNIQUE이며, 메시지 내역 조회 인덱스는 `(room_id, id)`다.
