\section{워크플로 개념 체계}

\subsection{Service / Capability 개념}

본 체계에서 Service와 Capability는 동일한 대상을 서로 다른 관점에서 바라본 개념이다. Service는 외부 사용자(고객) 관점에서 ``바이오파운드리가 어떤 생물학적 실험이나 분석을 대신 수행해 줄 수 있는가''를 의미하고, Capability는 내부 바이오파운드리 관점에서 ``현재 보유하고 있으며 수행 가능한 기술적 역량의 범위''를 의미한다. 즉, 외부에 설명할 때는 Service, 내부에서 관리하고 확장할 때는 Capability라는 용어를 사용하며, 두 개념은 동일한 실체를 가리킨다. Service/Capability는 특정 도메인(동물 세포, 식물, 미생물 및 화이트 바이오테크놀로지, 화학 및 화학생물학, 오믹스 데이터 분석 등)에 속하며, 하나의 서비스는 단일 워크플로가 아니라 여러 워크플로를 순차적 또는 병렬적으로 조합한 결과이다\cite{kim2025}. 따라서 Service/Capability를 정의한다는 것은 해당 서비스를 제공하기 위해 어떤 워크플로들이 필요하며, 이 워크플로들이 어떤 순서와 관계로 연결되는지를 정의하는 것이다. 워크플로가 충분히 정의, 개발, 검증되어야 해당 Service/Capability는 제공할 수 있고, 활용 가능한 워크플로 종류가 확장되면 Service/Capability의 범위도 확장될 수 있다. 

\subsection{Workflow 개념}

본 체계에서 Workflow는 생물학적 실험을 구성하는 핵심 개념 단위로, 특정 생물학적 목적을 달성하기 위한 작업의 묶음을 의미한다. 워크플로는 단순한 절차 나열이나 장비 시퀀스가 아니라, 실험을 이해, 설계, 재사용하기 위한 개념적 모듈이다.

\begin{quote}
\textbf{Workflow의 정의.} Workflow란, 하나의 생물학적 목적을 중심으로 여러 Unit Operation들이 조합된 실행 가능한 개념 단위이다.
\end{quote}

하나의 워크플로는 유닛오퍼레이션으로 구성되거나 더 작은 단위의 워크플로로 구성된다. 작은 단위의 워크플로는 상위 워크플로 내에서 반복 사용되는 (sub-process)이며, PCR 기반 DNA 증폭, DNA 조립 등이 그 예이다. Plasmid Preparation, PCR Amplification, DNA Assembly, Purification, Sequencing Data Processing 등이 Workflow의 예에 해당한다. 워크플로 및 유닛오퍼레이션은 실무에서 ID로 식별되며, 워크플로는 W와 DBTL 구분자(D: Design, B: Build, T: Test, L: Learn) 및 숫자(예: WD010), 유닛오퍼레이션은 U와 HW/SW 및 숫자(예: UHW400, USW005)로 구성된다. 공개 카탈로그는 웹(\url{https://sblabkribb.github.io/biofoundry_workflows/})에서 참조할 수 있다. 워크플로는 재현성을 위해 정형화된 실행 경로를 지향하나, 실험자, 연구실 환경, 장비 구성, 실험 목적의 세부 차이에 따라 같은 이름의 워크플로라도 실제 구성(Unit Operation의 수, 순서, 세부 내용)은 달라질 수 있다. 그러므로 본 체계에서 워크플로는 절차를 엄격히 고정하는 규칙이 아니라, 공통된 목적을 공유하는 실험들의 개념적 묶음으로 이해한다. 워크플로를 동일하게 인식하는 기준은 입력과 출력이나 세부 절차보다 워크플로의 이름(라벨)이다. 워크플로는 사전에 정의된 카탈로그(예: 약 37개 항목) 중 하나로 선택되며, 같은 워크플로 이름으로 선택되면 개념적으로는 같은 워크플로로 취급한다\cite{kim2025}. 워크플로는 처음부터 완벽하게 정의되지 않으며, 초기에는 탐색적 실험과 다양한 변형을 포함하고, 연구 노트가 축적되면 자주 등장하는 Unit Operation 조합, 반복적으로 관측되는 QC 지표, 안정적인 실행 패턴이 드러난다. 이후 이 데이터를 근거로 SOP를 만들거나 워크플로의 범위와 대표적 형태를 정제할 수 있다. 요약하면, 워크플로는 사전에 완성된 규칙이 아니라 운영과 데이터 축적을 통해 점진적으로 다듬어지는 개념이다.

\subsection{Unit Operation 개념}

Unit Operation은 워크플로를 구성하는 가장 기본적인 실행 단위이다. 워크플로가 ``무엇을 하기 위한 목적 단위''라면, Unit Operation은 ``실제로 무엇을 실행하는가''에 해당한다.

\begin{quote}
\textbf{Unit Operation의 정의.} Unit Operation이란, 특정 입력을 받아 일정한 방법으로 처리하여 출력(결과)을 생성하는 최소 실행 단위이다.
\end{quote}

이 최소 실행 단위는 반드시 하나의 장비일 필요는 없으며, 하드웨어 실행과 소프트웨어 실행을 모두 포함한다. 하나의 워크플로는 여러 Unit Operation의 조합으로 이루어지며, 선행 Unit Operation의 출력이 후속 Unit Operation의 입력이 된다. 이때 연결되는 대상은 실물(세포, 조직, DNA/RNA, Plasmid, 시료 등)이거나 데이터(농도 값, QC 판정, 파일, 분석 결과 등)이며, QC 체크포인트에서는 실물이 측정값 등 데이터로 바뀌어 다음 단계 수행 여부 판단, 반복 실험 데이터 축적, 검증 및 SOP 기준 설정의 근거로 쓰인다. 워크플로 간 연결도 결국 Unit Operation 간의 같은 원칙(선행 출력 $\rightarrow$ 후속 입력)의 연속으로 표현할 수 있으며, 워크플로 내부, 워크플로 간, 서비스 수준을 막론하고 동일한 방식으로 통일된다. 따라서 Unit Operation만으로 전체 서비스 그래프를 표현할 수 있다. Unit Operation은 하드웨어 기반과 소프트웨어 기반으로 구분된다. 하드웨어 기반 Unit Operation은 Liquid Handling, Centrifugation, Thermocycling, Incubation, Plate Reading, Sequencing 등 물리적 장비를 사용하는 실행 단위이며, 장비 중심으로 정의되고 샘플(실물)의 이동과 상태 변화를 주로 다룬다. 소프트웨어 기반 Unit Operation은 데이터 처리, 분석, 계산 과정을 동등한 실행 단위로 취급하며(예: Sequencing data preprocessing, Read filtering, Mapping, DEG analysis, Machine learning model inference), 소프트웨어 패키지, 스크립트, 알고리즘, 모델을 실행 주체로 가진다. 이를 통해 실험 단계와 데이터 분석 단계를 하나의 연속적인 워크플로 체계 안에서 다룰 수 있다.

Unit Operation의 이름(타입)은 사전에 정의된 표준 카탈로그(예: 약 80개 항목)에서 선택하고, 해당 Unit Operation이 이번 실행에서 무엇을 하는지, 어떤 맥락에서 사용되는지에 대한 설명은 자연어로 자유롭게 기록한다. 이 구조는 표준화(이름)와 유연성(설명)을 동시에 만족시키기 위한 핵심 설계 원칙이다. Unit Operation은 워크플로를 실행 가능한 단위로 분해하고, 실험과 분석을 하나의 연속된 과정으로 연결하며, 입출력 관계를 통해 그래프 표현을 가능하게 하고, 자연어 기록으로 사람과 LLM이 공통으로 이해하고 활용할 수 있는 기반을 제공한다.




\subsection{Unit Operation의 구성 요소}

하드웨어 Unit Operation과 소프트웨어 Unit Operation은 필요한 구성 항목이 다르므로, 아래에서 각각 별도로 정의한다. 연구자가 실험을 자연스럽게 기록할 수 있으면서도 이후 데이터 분석, 재현, 자동화로 확장될 수 있도록 설계된다.

\paragraph{하드웨어 Unit Operation.} 실물(샘플, 시약, DNA, 세포 등)을 다루는 Unit Operation은 다음 항목으로 기술한다.

\textbf{Input}: 이 단계에 투입된 실물. 어떤 이전 Unit Operation의 출력에서 왔는지 추적 가능하도록 기록한다. \textbf{Output}: 이 단계에서 생성된 실물(정제 DNA, colony plate, 배지 등). \textbf{장비(Equipment)}: 사용한 장비와 장비 설정값(예: centrifuge 12,000\,rpm, thermocycler 온도·시간, liquid handler 프로그램). \textbf{소모품(Consumables)}: 팁, 튜브, 플레이트, 키트 등. \textbf{Material and Method}: 실험 환경(온실, 실험실 온도, 장비 배치 등)과 위 장비·소모품을 사용한 구체적 절차(자연어 중심). \textbf{Result}: 관측된 값 또는 상태(예: DNA 농도 18\,ng/µL, colony 수 120개). 반복 실험 축적·검증·SOP 기준의 근거가 된다. \textbf{Discussion}: Result 해석, 특이사항, 실패·예외 기록; 데이터가 쌓이면 SOP 작성 시 지식 자산이 된다.

간단한 예: ``DNA 정제'' Unit Operation — Input: 플라스미드 추출 lysate(이전 단계 plasmid prep 출력). Output: 정제 DNA 50\,µL. 장비: centrifuge 12,000\,rpm 1\,min, vortex; elution 50\,µL. 소모품: 미니프렙 키트 A, 1.5\,mL 튜브. Material and Method: 실험실 상온; 키트 A 프로토콜에 따라 바인딩—세척—용출 수행. Result: 농도 42\,ng/µL, 260/280=1.92. Discussion: (없음 또는 ``수율 양호'').

\paragraph{소프트웨어 Unit Operation.} 데이터나 모델을 다루는 Unit Operation은 다음 항목으로 기술한다.

\textbf{Input}: 이 단계에 투입된 데이터·파일·모델(예: FASTQ, count matrix) 및 해당 데이터(Data)에 대한 설명을 포함한다. 출처 추적 가능하도록 기록. \textbf{Output}: 생성된 산출물(분석 결과 파일, 통계 요약, 모델 출력 등). \textbf{Parameters}: 옵션, 하이퍼파라미터, seed 등 재현에 필요한 설정값. \textbf{Environment}: conda/poetry/container, OS, HW 사양, 사용한 패키지·스크립트·알고리즘·모델, 버전, 참조 레포(GitHub, Hugging Face 등) 등 실행 환경. \textbf{Method}: 위 환경에 포함된 자원을 사용한 절차나 처리 내용(자연어 또는 스크립트 요약). \textbf{Result}: 성능 지표, QC 지표, 중간 결과(예: DEG 342개, 정확도 0.87). \textbf{Discussion}: Result 해석, 특이사항, 실패·예외; SOP·재현 시 참고된다.

간단한 예: ``QC 필터링'' Unit Operation — Input: FASTQ 쌍(Unit Operation ``시퀀싱'' 출력), paired-end 150\,bp. Output: 필터링된 FASTQ. Parameters: quality threshold 30, min length 100. Environment: conda env \texttt{ngs}, Python 3.10, \texttt{fastp} 0.23.2. Method: fastp로 Q30 미만 리드 제거, adapter trim. Result: 전처리 후 read 수 8.2M, Q30 비율 95.2\%. Discussion: (없음 또는 ``일부 샘플에서 adapter 잔류'').

이와 같은 구분은 ``구조는 고정, 내용은 유연'', ``자연어 우선, 추적 가능성 유지'' 원칙에 부합하며, 실험 단계와 데이터 분석 단계를 하나의 체계로 연결한다.


