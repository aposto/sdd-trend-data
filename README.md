# sdd-trend-data

SDD(Spec-Driven Development)·AI-SDLC 관련 GitHub 저장소의 스타·릴리즈·커밋 지표를 매일 쌓고, 주간 트렌드 리포트의 근거 데이터로 쓰는 저장소입니다.

## 구조

| 경로 | 역할 |
| --- | --- |
| `watchlist.json` | 관심 목록과 신규 후보 탐지 조건. 저장소 추가·삭제는 이 파일만 고치면 됩니다 |
| `scripts/collect.py` | GitHub API로 지표 수집 → `snapshots/YYYY-MM-DD.json` |
| `scripts/analyze.py` | 스냅샷 이력으로 주간 증가·30일 일평균·추세 계산 → `reports/YYYY-MM-DD.{json,md}` |
| `baselines/` | 자동 수집 이전의 기준점(Wayback 저장본, 리포트 #1 수동값) |
| `.github/workflows/collect.yml` | 매일 08:17 KST 수집·분석·커밋. Actions 탭에서 수동 실행도 가능 |
| `docs/PROCEDURE.md` | 매주 금요일 Claude가 리포트를 쓰는 절차 |

## 지표 정의

- 일평균(전체) = 현재 스타 ÷ 생성 후 경과일
- 일평균(30일) = (현재 − 약 30일 전) ÷ 실제 경과일
- 주간 증가 = 현재 − 약 7일 전
- 추세 = 일평균(30일) ÷ 일평균(전체). 1.2 이상 가속, 0.8 미만 둔화

## 로컬 실행

```bash
GITHUB_TOKEN=$(gh auth token) python3 scripts/collect.py
python3 scripts/analyze.py
```
표준 라이브러리만 씁니다.
