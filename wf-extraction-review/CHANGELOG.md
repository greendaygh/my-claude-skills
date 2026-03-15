# Changelog — wf-extraction-review

## [1.0.0] — 2026-03-16

### Added

- 초기 스킬 생성
- 5단계 검토·보강 파이프라인: 대상 파악 → 검토·보강 → Panel C → flag 처리 → 집계
- wf-paper-mining 스킬의 assets/scripts 공유 참조
- 기존 추출 데이터 유지 원칙: 유효 데이터 삭제 금지, 보강/수정만 수행
- Panel C에서 flag_reextract 판정 시 clean slate 재추출 지원
- 백업/롤백 메커니즘
