# Prophage Biology Reference

## 핵심 개념

### Prophage란?

Prophage는 박테리아 숙주의 게놈에 통합된 박테리오파지(bacteriophage) DNA이다. 용원성(lysogenic) 주기를 통해 숙주와 함께 복제되며, 특정 조건에서 용균성(lytic) 주기로 전환될 수 있다.

### 용원-용균 전환 (Lysogeny-Lysis Decision)

- **CI repressor**: 용원 상태를 유지하는 주요 억제자. 용균 유전자를 억제
- **Cro protein**: 용균 전환을 촉진. CI와 길항적 관계
- **RecA**: SOS response에서 CI repressor를 자가분해(autocleavage) 유도
- **SOS response**: DNA 손상 시 활성화되어 prophage 유도를 촉발

## 유전자 분류 체계

### Integration (통합)
- **integrase (int)**: 사이트 특이적 재조합(site-specific recombination)으로 파지 DNA를 숙주 게놈에 삽입
- **excisionase (xis)**: 통합된 prophage의 절제(excision) 촉진
- **att sites**: attP (파지 측), attB (박테리아 측), attL/attR (통합 후 경계)

### Regulatory (조절)
- **CI repressor**: 용원 유지, 자가 유전자 프로모터와 용균 유전자를 동시에 조절
- **Cro protein**: 초기 용균 조절자
- **N antiterminator**: 초기 전사 종결 억제
- **Q antiterminator**: 후기 전사 종결 억제

### Lysis (용균)
- **holin**: 내막에 구멍을 형성하여 endolysin 방출
- **endolysin (lysozyme)**: 펩티도글리칸(peptidoglycan) 분해
- **spanin**: 외막 파괴를 완성하여 세포 용해
- **Rz/Rz1**: spanin 구성 요소

### Structural (구조)
- **capsid (head) proteins**: DNA를 감싸는 이십면체 캡시드
- **tail proteins**: 숙주 인식과 DNA 주입
- **baseplate**: 꼬리 섬유와 숙주 수용체 간 상호작용 매개
- **tail fiber/spike**: 숙주 표면 수용체 인식 (receptor binding protein, RBP)

### Replication (복제)
- **replication origin (ori)**: 파지 DNA 복제 개시점
- **DNA primase**: RNA 프라이머 합성
- **helicase**: 이중나선 풀기
- **terminase (large/small subunit)**: DNA 패키징 (capsid에 DNA 주입)

## 숙주 감염 메커니즘

### 수용체 (Receptors)
- **LPS (lipopolysaccharide)**: 그람 음성균 외막의 주요 수용체
- **OmpC/OmpF**: 외막 포린 단백질
- **FhuA**: ferric hydroxamate uptake receptor (T5 phage 등)
- **LamB**: maltose transporter (lambda phage)
- **BtuB**: vitamin B12 transporter
- **Flagella/Pili**: 일부 파지의 1차 수용체

### 통합 부위 (Integration Sites)
- **tRNA genes**: 가장 흔한 통합 부위 (tRNA-Arg, tRNA-Leu, tRNA-Ser 등)
- **tmRNA (ssrA)**: SsrA-mediated trans-translation 관련 유전자
- **intergenic regions**: 유전자 간 비코딩 영역

## 유도 조건 (Induction Conditions)

| 조건 | 메커니즘 | 효율 |
|------|----------|------|
| UV irradiation | SOS response → RecA → CI cleavage | 높음 |
| Mitomycin C | DNA crosslink → SOS response | 높음 |
| Ciprofloxacin | DNA gyrase 억제 → SOS response | 중간 |
| Temperature shift | CI thermosensitive mutant에서 | 높음 (ts mutant) |
| Oxidative stress | ROS-mediated DNA damage → SOS | 중간 |
| Hydrogen peroxide | DNA damage → SOS response | 중간-낮음 |

## 주요 모델 Prophage 시스템

| Prophage | 숙주 | 크기 (kb) | 특징 |
|----------|------|-----------|------|
| Lambda (λ) | E. coli K-12 | 48.5 | 가장 잘 연구된 temperate phage |
| P22 | S. enterica | 41.7 | Generalized transduction 모델 |
| Mu | E. coli | 36.7 | Transposable phage |
| DLP12 | E. coli K-12 | 21.3 | Defective prophage, 부분 삭제 |
| Gifsy-1/2 | S. enterica | 48/45 | Virulence factor 운반 |
| CTXφ | V. cholerae | 6.9 | Cholera toxin 유전자 운반 |
| Phi80 | E. coli | 46.4 | Lambda 유사, att site 다름 |

## Prophage 탐지 도구

- **PHASTER**: 가장 널리 사용되는 웹 기반 prophage 예측 도구
- **PhiSpy**: 기계학습 기반 prophage 예측
- **VirSorter/VirSorter2**: 메타게놈에서 바이러스 시퀀스 탐지
- **VIBRANT**: 통합 바이러스 식별 및 기능 분석
- **Prophage Hunter**: Random Forest 기반 활성 prophage 예측
