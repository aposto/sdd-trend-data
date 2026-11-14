# SDD 주간 트렌드 리포트 — 작성 절차

매주 금요일 Claude 예약 작업이 이 문서를 따라 리포트 #N을 만든다. 사람이 수동으로 돌릴 때도 같다.
데이터 수집은 GitHub Actions(`collect.yml`, 매일 08:17 KST)가 하고, 이 절차는 **분석·해석·작성**만 한다.

## 0. 준비
- `git clone --depth 1 https://github.com/aposto/sdd-trend-data` (공개 저장소, 읽기만 필요)
- 회차 번호: claude.ai Project "vibe-coding"의 `claude/sdd-weekly-index.md` 마지막 회차 + 1
- 이전 회차 링크도 같은 파일에 있다. 지난 호의 '다음 주 관전 포인트'를 읽어 이번 호에서 답한다.
- Projects 도구를 쓸 수 없는 실행 환경이면: N = (오늘 − 2026-11-13) ÷ 7 + 1, 사용법 팁은 순번표에서 (N − 1)번째, 회차 목록 갱신은 하지 않고 최종 메시지에 "회차 목록에 추가할 행"으로 적는다.

## 1. 데이터 확인
- `snapshots/` 최신 파일의 `as_of`가 36시간 이내인지 본다. 아니면 Actions 실패로 보고 최신 파일로 진행하되, 리포트 맨 아래와 최종 메시지에 "데이터 기준일 YYYY-MM-DD(수집 지연)"를 적는다.
- `python3 scripts/analyze.py` 실행 → `reports/<날짜>.json`(기계용), `reports/<날짜>.md`(표)
- JSON에서 쓸 것: `repos[]`(stars, delta_7d, avg_life, avg_30d, trend, release, released_this_week, commits_7d), `top_weekly_gain`, `accelerating`, `decelerating`, `released_this_week`, `candidates`, `ecosystem_new_repos_by_month`, `missing_7d`, `missing_30d`
- 숫자는 반드시 이 JSON에서 가져온다. 기억이나 검색 결과의 스타 수를 쓰지 않는다.

## 2. 해석용 조사 (WebSearch standard, 6~12회)
- `released_this_week`의 각 릴리즈: 릴리즈 노트를 열어 바뀐 점 1줄 (예: `<repo> v<tag> release notes`)
- `top_weekly_gain` 상위 3개와 `accelerating`: 왜 움직였는지 (발표, 블로그, 컨퍼런스, SNS 화제)
- `candidates` 중 스타 상위 3개: 무엇을 하는 도구인지
- 업계 흐름: `spec-driven development` 이번 주 뉴스 1~2회
- 숫자·날짜를 가져온 페이지는 열어서 확인하고 출처 목록에 남긴다. 한 출처에서 15단어 이상 인용 금지, 요약은 바꿔 쓴다.

## 3. 리포트 작성 (Claude Docs, 제목 "SDD 주간 트렌드 리포트 #N")
한국어, 짧고 구체적으로. 첫 문장은 이번 주의 결론과 숫자.

| 섹션 | 내용 | 형식 |
| --- | --- | --- |
| 리드 | 이번 주 핵심 1~2문장 (가장 큰 변화 + 숫자) | 문단 |
| 이번 주 소식 | 릴리즈·발표, 최신순 | 표: 날짜 · 프로젝트 · 내용 |
| 저장소 현황 | `reports/<날짜>.md` 표 그대로 (구분·저장소·스타·주간 증가·일평균 전체/30일·추세·릴리즈·7일 커밋) | 표 |
| 주간 상승 | 주간 증가 상위 8개 막대 차트, 1위만 강조색 | 차트 |
| 왜 움직였나 | 가속·둔화·급등 3~4개를 근거와 함께 | 번호 목록 |
| 이번 주 사용법 팁 | 아래 순번표에서 한 도구를 골라 시작 명령 3줄 + 언제 쓰나 | 문단 + 코드 |
| 관찰 후보 | `candidates` 상위 3~5개, 관심 목록 승격 제안 여부 | 표 |
| 다음 주 관전 포인트 | 2~4개 | 목록 |
| 측정 방법과 출처 | 데이터 기준 시각, 계산식 한 줄, 연 페이지 링크 | 목록 |

계산식 문구(고정): "일평균(30일) = 최근 약 30일 증가 ÷ 실제 경과일, 추세 = 일평균(30일) ÷ 일평균(전체), 1.2 이상 가속·0.8 미만 둔화."
`missing_7d`/`missing_30d`에 있는 저장소는 표에 "—"로 두고 이유를 한 줄로 적는다.

사용법 팁 순번(지난 회차에서 다룬 것은 건너뜀): OpenSpec 2.0 마이그레이션 → Spec Kit constitution 작성법 → EGM 설계 리뷰 → GSD Core 실행 루프 → AI-DLC 승인 게이트 → BMAD(V7 출시 시) → Superpowers 스킬 조합 → OpenSpec vs Spec Kit 브라운필드 비교 → 관심 목록 신규 편입 도구

## 4. 게시판용 텍스트
문서와 별도로, 붙여넣기용 Markdown(한 화면 분량)을 만든다.
- 제목 줄: `[SDD 주간 #N] <핵심 한 구절>`
- 핵심 3줄 (숫자 포함)
- 주간 상승 상위 5개 미니 표 (저장소 · 주간 증가 · 추세)
- 이번 주 팁 한 줄
- 전체 리포트 링크

## 5. 기록
- Project `claude/sdd-weekly-index.md`에 행 추가: `| #N | YYYY-MM-DD | <문서 링크> | <핵심 한 줄> | <다룬 팁> |`
- 관찰 후보 승격은 사람이 결정한다. 제안만 하고 `watchlist.json`은 고치지 않는다.

## 6. 마무리 메시지
리포트 링크, 핵심 3줄, 게시판용 텍스트, 데이터 이상(수집 지연·결측)만. 작업 과정은 쓰지 않는다.
