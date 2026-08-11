# TCBP 플러그인 제작 가이드

이 문서는 TCBP(Total Commander Batch Python)의 `plugin = "..."` Job에서 실행되는
플러그인을 새로 만들거나 유지보수하려는 개발자를 위한 가이드입니다. TCBP 사용자
전반을 위한 문서는 상위 폴더의 `README_ko.md`(5장)를 참고하세요 — 이 문서는
플러그인 "제작자" 관점에 집중합니다.

> **요구 사항:** TCBP는 Python 3.11 이상에서 동작합니다(`README_ko.md` 참고).
> 이 문서의 스켈레톤 코드도 `str | None`, `list[str]`처럼 3.10+ 문법을
> 그대로 사용하므로, 그보다 낮은 버전에서는 별도 수정 없이 동작하지 않습니다.

## 1. 목차

- [1. 목차](#1-목차)
- [2. TCBP 플러그인 개요 및 개념](#2-tcbp-플러그인-개요-및-개념)
  - [2.1 `tool` vs `plugin`](#21-tool-vs-plugin)
  - [2.2 설계 원칙](#22-설계-원칙)
  - [2.3 세션 타입 — FileSession / BatchSession](#23-세션-타입--filesession--batchsession)
  - [2.4 처리 흐름 개요](#24-처리-흐름-개요)
- [3. API 사양](#3-api-사양)
  - [3.1 `@plugin(...)` 데코레이터와 `PluginInfo`](#31-plugin-데코레이터와-plugininfo)
  - [3.2 `FileSession`](#32-filesession)
  - [3.3 `BatchSession`](#33-batchsession)
  - [3.4 반환값 계약 — `ExecResult` / `BatchResult`](#34-반환값-계약--execresult--batchresult)
  - [3.5 `session.log()`와 slot 규칙](#35-sessionlog와-slot-규칙)
  - [3.6 `session.params`와 타입 변환](#36-sessionparams와-타입-변환)
  - [3.7 config.toml에서 플러그인 Job 선언](#37-configtoml에서-플러그인-job-선언)
  - [3.8 `tcbp`에서 import 가능한 것들](#38-tcbp에서-import-가능한-것들)
- [4. 플러그인 Python 프로그램의 기본 구조](#4-플러그인-python-프로그램의-기본-구조)
  - [4.1 파일 위치 및 이름 규칙](#41-파일-위치-및-이름-규칙)
  - [4.2 스켈레톤 — FileSession 플러그인](#42-스켈레톤--filesession-플러그인)
  - [4.3 스켈레톤 — BatchSession 플러그인](#43-스켈레톤--batchsession-플러그인)
  - [4.4 단독 CLI 진입점 작성 규칙](#44-단독-cli-진입점-작성-규칙)
  - [4.5 의존성 선언 (`requirements`)](#45-의존성-선언-requirements)
  - [4.6 테스트 작성](#46-테스트-작성)
- [5. 테크니컬 노트](#5-테크니컬-노트)
  - [5.1 fail-fast 2단계 검증](#51-fail-fast-2단계-검증)
  - [5.2 pydantic 유무에 따른 검증 강도 차이](#52-pydantic-유무에-따른-검증-강도-차이)
  - [5.3 병렬 모드에서의 log() slot 예약 메커니즘](#53-병렬-모드에서의-log-slot-예약-메커니즘)
  - [5.4 `--strict` 플래그](#54---strict-플래그)
  - [5.5 BatchSession의 진행률 출력 규칙](#55-batchsession의-진행률-출력-규칙)
  - [5.6 예외 vs 반환값 — 언제 무엇을 쓸까](#56-예외-vs-반환값--언제-무엇을-쓸까)
  - [5.7 dry-run 동작](#57-dry-run-동작)
  - [5.8 Session은 읽기 전용이다](#58-session은-읽기-전용이다)
  - [5.9 흔한 실수 체크리스트](#59-흔한-실수-체크리스트)
  - [5.10 병렬 모드에서 플러그인 코드의 스레드 안전성](#510-병렬-모드에서-플러그인-코드의-스레드-안전성)

---

## 2. TCBP 플러그인 개요 및 개념

### 2.1 `tool` vs `plugin`

TCBP의 Job은 파일 1개(또는 파일 그룹)를 처리하는 방법을 두 가지 중 하나로 지정합니다.

| | `tool = "..."` | `plugin = "..."` |
|---|---|---|
| 처리 로직 | 외부 CLI 실행 파일 (`subprocess`) | `./plugin/<이름>.py`의 파이썬 함수 |
| 대상 | GraphicsMagick, oxipng 등 기존 실행 파일 | 파이썬으로 직접 구현하는 처리 |
| `commands` 키 | 필수 | 사용 안 함 (있으면 `validate_config.py` 경고) |

하나의 Job 안에서 `tool`과 `plugin`을 동시에 쓸 수 없습니다 — 둘 다 지정하면
tcbp.py가 즉시 오류로 중단합니다.

### 2.2 설계 원칙

TCBP 전체를 관통하는 역할 분리 원칙이 플러그인에도 그대로 적용됩니다.

1. **파일 선택은 Total Commander, 배치 처리는 TCBP, 파일 1개(또는 그룹)의 실제
   처리는 tool 또는 plugin이 담당**합니다. 플러그인은 파일 목록 탐색, 와일드카드
   처리, 재귀 탐색을 구현하지 않습니다 — 이건 이미 Total Commander(파일 선택)와
   TCBP(목록 읽기·순회)가 끝낸 일입니다.
2. **인터페이스로 파일 오브젝트를 넘기지 않습니다.** 플러그인은 항상 파일의
   경로(`str`)와 파라미터(`dict`)만 받습니다. `FileSession.input`/`output`도,
   `BatchSession.filelist`의 각 원소도 전부 `str`입니다 (`Path` 객체나 파일
   핸들이 아님).
3. **플러그인은 tcbp 없이도 단독 CLI로 실행 가능해야 합니다** (4장 참고). 이는
   플러그인 개발/디버깅을 tcbp 전체를 거치지 않고 파일 1개(BatchSession은 목록
   파일 1개) 단위로 빠르게 검증하기 위함입니다.

### 2.3 세션 타입 — FileSession / BatchSession

플러그인은 처리 단위에 따라 두 가지 타입 중 하나로 작성합니다.

| | FileSession | BatchSession |
|---|---|---|
| 처리 단위 | 파일 1개 | 파일 목록 전체 |
| 진입 함수 시그니처 | `run(session: FileSession) -> ExecResult` | `run(session: BatchSession) -> BatchResult` |
| `parallel` | 지원 (`max_workers`만큼 동시 처리) | 무시 (항상 순차 — 활성화해도 조용히 무시됨) |
| `output` | 필수 | 생략 가능 (`output = ""` 또는 키 자체 생략) |
| 대표 예 | `remove_bom`, `mozjpeg`, `bmp2png` | `group_md5` |

파일 단위로 독립적으로 처리 가능하면 FileSession을, 여러 파일을 묶어서 함께
봐야만 결과를 낼 수 있으면(예: 파일명 유사도로 그룹핑해 그룹당 결과물 1개 생성)
BatchSession을 선택합니다.

### 2.4 처리 흐름 개요

```
Total Commander (파일 선택, %UL로 목록 전달)
        │
        ▼
tcbp.py  ── config.toml의 Job 정의를 resolve
        │     (plugin = "이름" → ./plugin/<이름>.py 를 결정론적으로 로드)
        ▼
PluginJobExecutor  ── dry-run 여부 판단, run() 호출, 예외를 결과값으로 합성
        │
        ▼
plugin/<이름>.py 의 run(session) ── 실제 파일 처리 로직
        │
        ▼
ExecResult(FileSession) 또는 BatchResult(BatchSession) 반환
        │
        ▼
tcbp.py ── 성공/실패 집계, 콘솔·로그 출력
```

플러그인 탐색·등록 메커니즘은 따로 없습니다. `plugin = "resize"`는 항상
`./plugin/resize.py`로 결정론적으로 매핑되며, Job이 resolve될 때 해당 파일의
존재 여부만 확인합니다.

---

## 3. API 사양

### 3.1 `@plugin(...)` 데코레이터와 `PluginInfo`

플러그인의 진입점 함수는 반드시 이름이 `run`이어야 하며, `tcbp`가 제공하는
`@plugin(...)` 데코레이터로 감싸 메타정보를 부착해야 합니다.

```python
from tcbp import plugin

@plugin(
    name="remove_bom",       # 플러그인 식별 이름 (통상 파일명과 동일하게 유지)
    contract_version="1.0",  # 이 플러그인이 작성 시점에 대상으로 삼은 계약 버전 (필수, 아래 참고)
    version="1.0",
    author="...",
    session_type="file",     # "file" | "batch" (2.3 참고)
    requirements=[],         # 필요 외부 패키지 목록 (4.5 참고). 기본값 []
    notes_per_file=0,        # FileSession + parallel일 때 쓸 log() slot 개수. 기본값 0
    thread_safe=True,        # FileSession + parallel에서 스레드 안전한가. 기본값 True (5.10 참고)
)
def run(session):
    ...
```

`@plugin(...)`에 전달된 값은 내부적으로 `PluginInfo`(frozen dataclass)로
검증됩니다.

```python
@strict_dataclass(frozen=True)
class PluginInfo:
    name: str
    contract_version: str
    version: str
    author: str
    session_type: Literal["file", "batch"]
    requirements: list = []
    notes_per_file: int = 0
    thread_safe: bool = True
```

`session_type`에 `"file"`/`"batch"` 이외의 값을 넣거나 타입이 안 맞으면, 이
데코레이터가 평가되는 **plugin import 시점에 즉시 예외**가 발생합니다 (5.1절
fail-fast 참고) — Job이 실제로 실행되기 한참 전, 심지어 `validate_config.py`
사전 검증 단계에서부터 걸러집니다.

#### `contract_version` — 플러그인 계약 버전 (필수)

`contract_version`은 `bmp2png`/`mozjpeg`/`group_md5`/`remove_bom` 자신의
`version`(플러그인 저자가 매기는 버전)과는 다른 개념입니다 — **`FileSession`
/`BatchSession`/`PluginInfo`의 "형태" 자체**가 몇 번 버전인지를 선언하는
`"MAJOR.MINOR"` 문자열이며(예: `"1.0"`), TCBP 자신의 제품 버전
(`pyproject.toml`)과도 무관합니다.

`load_plugin()`이 플러그인을 import할 때마다 이 값을 TCBP가 현재 구현하고
있는 계약 버전과 비교합니다:

- **MAJOR가 다르면 즉시 거부** — 기존 플러그인을 깨뜨리는 변경(필드 제거,
  타입 변경 등)이 있었다는 뜻입니다.
- **MAJOR가 같고 선언한 MINOR가 TCBP의 것보다 크면 거부** — 플러그인이 이
  TCBP 버전엔 아직 없는 계약 기능을 요구한다는 뜻입니다.
- **MAJOR가 같고 MINOR가 같거나 낮으면 통과** — TCBP가 그 사이 하위 호환되는
  필드만 추가했다는 뜻이므로 문제없습니다.

즉, 계약이 정말로 깨지는 변경이 있을 때만(자주 있는 일이 아닙니다) 값을 올려
쓰면 되고, 평소에는 그대로 두어도 됩니다. 형식이 `"MAJOR.MINOR"`가 아니거나
호환되지 않으면 `load_plugin()`이 그 자리에서 `TcbpError`로 거부합니다 —
`session_type` 오타와 동일하게 plugin import 시점의 fail-fast 대상입니다.

### 3.2 `FileSession`

파일 1개를 처리하는 플러그인이 받는 인자입니다. 필드는 (`log()` 호출을 제외
하고) 읽기 전용입니다.

```python
@strict_dataclass(frozen=True)
class FileSession:
    input:  str    # 입력 파일의 절대경로
    output: str    # 출력 파일의 절대경로 (job.output 템플릿이 이미 치환된 값)
    itemid: int    # 파일당 1-based 순번 (배치 내 몇 번째 파일인지)
    taskid: str    # 배치 전체에서 1회만 생성되는 공용 임시 ID (문자열)
    params: dict   # job.params(타입 선언분은 변환됨) + job.defaults 병합 결과 (3.6 참고)

    def log(self, text: str, slot: int = 0) -> None: ...
```

> **주의:** `session.itemid`는 파일당 1-based 순번(정수)입니다. `config.toml`의
> `{itemid}` placeholder(임시 파일명용으로 매번 새로 생성되는 랜덤 문자열)와는
> 이름만 같을 뿐 서로 다른 값이니 혼동하지 마세요.

### 3.3 `BatchSession`

파일 그룹 전체를 한 번에 처리하는 플러그인이 받는 인자입니다.

```python
@strict_dataclass(frozen=True)
class BatchSession:
    filelist: list       # list[str] — TCBP가 이미 읽고 존재 확인까지 마친 절대경로 목록
    output:   str | None # job.output이 비어 있으면 None
    taskid:   str
    params:   dict

    def log(self, text: str, slot: int = 0) -> None: ...
```

`filelist`는 목록 파일의 "경로 1개"가 아니라, TCBP가 이미 목록 파일을 읽고
각 파일의 존재 여부까지 확인한 절대경로 문자열의 리스트입니다 — 플러그인이
다시 파일 존재 검사를 할 필요는 없습니다(그래도 처리 도중 사라질 가능성까지
막을 수는 없으니, 실제 파일 접근 시점의 예외는 정상적으로 처리해야 합니다).

> **주의:** `BatchSession.output`은 `FileSession.output`과 의미가 다릅니다.
> `FileSession.output`은 `{dir}`/`{base}` 등 placeholder가 파일별로 전부
> 치환된 완성된 절대경로 문자열입니다. 반면 `BatchSession`은 파일 1개에
> 묶이지 않으므로 `{dir}`/`{base}` 같은 파일 단위 placeholder를 애초에 치환할
> 방법이 없습니다 — 그래서 `job.output`이 비어 있지 않으면 **placeholder가
> 하나도 치환되지 않은 TOML 원본 문자열 그대로** 전달됩니다(예:
> `"{dir}/report.txt"`라는 문자열 자체). 이 값을 실제 경로로 쓰려면 플러그인이
> 직접 의미를 해석하거나 치환해야 합니다. 번들 플러그인(`group_md5`)은 이
> 필드를 아예 쓰지 않고 항상 `output = ""`(→ `None`)로 선언합니다 — 새
> BatchSession 플러그인을 작성할 때 `output`이 꼭 필요하지 않다면 마찬가지로
> 비워두는 것을 권장합니다.

### 3.4 반환값 계약 — `ExecResult` / `BatchResult`

플러그인은 "예외가 없으면 성공"이라는 암묵적 규칙 대신, **명시적인 반환값**으로
성공/실패를 알립니다.

```python
@strict_dataclass(frozen=True)
class ExecResult:
    success: bool
    message: str = ""

@strict_dataclass(frozen=True)
class BatchResult:
    succeeded: list = []   # 성공 처리된 파일 경로 목록
    failed:    list = []   # 실패 처리된 파일 경로 목록
```

- FileSession: `run(session: FileSession) -> ExecResult`
- BatchSession: `run(session: BatchSession) -> BatchResult`

`BatchResult.succeeded + failed`가 `session.filelist` 전체를 다 채우지 않아도
(=일부 파일이 조용히 스킵돼도) TCBP는 이를 강제하지 않습니다. 다만 요약 로그의
"성공/실패" 건수는 이 두 리스트의 길이를 그대로 반영하므로, 처리한 파일은
빠짐없이 둘 중 하나에 담는 것을 권장합니다.

**run()에서 예외가 새어나오면** TCBP가 그 자리에서 잡아 다음과 같이 결과를
합성합니다.

- FileSession: `ExecResult(success=False, message=str(exc))`
- BatchSession: `session.filelist` 전체를 `failed`로 채운 `BatchResult`
  (예외 이전에 일부 성공시킨 정보가 있어도 전부 버려집니다)

즉 **run()에서의 예외는 "이 파일/이 Job을 더 이상 신뢰할 수 없는 catastrophic
상황"에만 사용**하고, 처리 대상 일부의 예상 가능한 실패(예: 그룹 내 손상된
파일 1개)는 반환값으로 구조화해 보고하는 것이 플러그인 작성자에게 기대되는
관례입니다. `group_md5`가 이 패턴의 참고 예시입니다 — 그룹별 루프 안에서
개별 파일 실패는 `try/except`로 잡아 `failed` 리스트에 쌓고, `run()` 자체는
정상적으로 `BatchResult`를 반환합니다.

**FileSession에서 성공 시 `message`의 표시 위치.** `success=True`인
`ExecResult`의 `message`가 비어 있지 않으면, TCBP는 이를 별도 줄이 아니라
`[idx] input → output` 결과 줄 자체에 줄바꿈 없이 이어 붙여 보여줍니다
(예: `[   1] 001.bmp → 001.png  [source deleted]`, `bmp2png` 참고). 단,
이는 병렬 모드(ANSI 블록)에서만 그 줄 자체에 합쳐지고, 순차 모드에서는
이미 출력된 줄을 ANSI로 다시 덮어쓸 수 없으므로 바로 아래 줄로 출력됩니다
— 어느 모드든 플러그인 코드는 동일하게 `ExecResult(True, "짧은 메모")`만
반환하면 됩니다. 진행률 표시처럼 같은 자리를 여러 번 갱신해야 하는
경우에는 이 방식 대신 3.5절의 `session.log()`/slot을 쓰세요 — `message`는
"완료 시 한 줄짜리 짧은 부가 정보"에만 적합합니다.

### 3.5 `session.log()`와 slot 규칙

```python
session.log(text: str, slot: int = 0) -> None
```

- `slot`은 **FileSession + `parallel = true`** 조합일 때만 의미를 가집니다.
  같은 slot을 여러 번 호출하면 화면상 그 자리를 갱신합니다(% 진행률 표시 등에
  활용). 그 외의 경우(BatchSession, 또는 `parallel = false`)엔 `slot` 값은
  무시되고 그냥 순서대로 로그 한 줄로 출력됩니다.
- **병렬 모드에서 플러그인이 사용할 slot 개수는 `@plugin(notes_per_file=N)`로
  미리 선언해야 합니다.** 선언한 개수를 벗어난 slot을 쓰면 5.3/5.4절의 규칙이
  적용됩니다.

### 3.6 `session.params`와 타입 변환

`session.params`는 다음 두 값을 병합한 `dict`입니다 (CLI 값이 우선).

1. `job` 섹션의 비표준 키(placeholder 기본값, 예: `watermark = "..."`) — 항상
   문자열
2. `job.params`에 선언된 키 — CLI `key=value` 또는 config 기본값

`job.params`에 `type = "int"` 또는 `type = "bool"`로 선언된 키만 TCBP가 실제
`int`/`bool` 타입으로 변환해 넣어줍니다. 선언하지 않은 키는 항상 문자열
그대로 유지됩니다.

```toml
params = [
    { key="backup",   desc="원본을 .bak으로 백업", type="bool" },
    { key="chunk_size", desc="청크 크기(MB)",        type="int"  },
]
```

```python
session.params["backup"]      # True/False (bool)
session.params["chunk_size"]  # 64 (int)
session.params["watermark"]   # "c:/path/logo.png" (str, 비표준 키는 변환 안 됨)
```

`bool` 변환 규칙(대소문자 무관):

| 참(True) | 거짓(False) |
|---|---|
| `true`, `1`, `yes`, `on` | `false`, `0`, `no`, `off` |

그 외 문자열은 변환 오류로 처리되어 Job 실행 자체가 실행 전에 (`_coerce_params`
단계에서) 명확한 에러 메시지로 중단됩니다 — 플러그인 코드 안에서 이 검증을
직접 할 필요가 없습니다. 단, 플러그인 단독 CLI(4.4절)에서는 이 자동 변환이
적용되지 않으므로 필요 시 `tcbp._to_bool()` 등을 직접 불러 써야 합니다.

### 3.7 config.toml에서 플러그인 Job 선언

```toml
# FileSession 플러그인 Job
[jobs.RemoveBOM]
desc                   = "Remove BOM from text files"
plugin                 = "remove_bom"        # ./plugin/remove_bom.py 로드, run(session) 호출
output                 = "{dir}/{base}{ext}" # FileSession은 output 필수
allow_output_overwrite = true                # output이 input을 덮어쓰는 걸 의도했다면 명시적으로 허용
params = [
    { key="backup",   desc="원본을 .bak으로 백업", type="bool" },
    { key="eachline", desc="각 줄마다 BOM 제거",   type="bool" },
]

# BatchSession 플러그인 Job
[jobs.GroupMD5]
desc   = "Generate grouped MD5 hash files"
plugin = "group_md5"
# output 생략 가능 — session.output은 None이 됨
params = [
    { key="bom", desc="MD5 파일을 BOM 포함으로 생성", type="bool" },
]
```

세부 규칙:

- `commands`는 plugin Job엔 쓰지 않습니다(있으면 `validate_config.py`가
  "사용되지 않는 키"로 경고). 처리 로직 자체가 `run(session)` 호출이라 셸
  명령 템플릿이 필요 없습니다.
- `pre`/`post`(`{ msg = "..." }` 배너 포함)는 tool Job과 동일하게 배치 전체
  1회 실행됩니다.
- `params`, `desc`, `on_error`는 CLI Job과 완전히 동일하게 동작합니다.
- `parallel`/`max_workers`: FileSession엔 정상 적용, BatchSession엔 무시됩니다
  (`validate_config.py`가 BatchSession Job에 `parallel = true`가 있으면 경고).
- `stderr_quiet`: 플러그인엔 subprocess stderr 개념이 없으므로 조용히
  무시됩니다(오류 아님).
- 표준 키가 아닌 커스텀 키는 지금처럼 `job.defaults`로 들어가
  `session.params`에 문자열로 병합됩니다 (3.6절).
- `input_mode`/`recursive`/`include`(12장, directory 입력 모드)는 tool Job과
  동일하게 plugin Job에도 적용됩니다 — 예: `config.toml`의 `Bmp2PngRecursive`
  Job은 `plugin = "bmp2png"`에 `input_mode = "directory"`를 함께 선언해 폴더를
  직접 입력받아 재귀 탐색합니다. 플러그인 코드 입장에서는 이미 tcbp가 구성한
  `filelist`/`input`만 받으므로 별도 처리가 필요 없습니다 (2.2절).

### 3.8 `tcbp`에서 import 가능한 것들

플러그인은 상위 폴더의 `tcbp.py`를 `sys.path`에 넣고 `from tcbp import ...`로
필요한 심볼을 가져옵니다. 플러그인 작성 시 실제로 쓰게 되는 주요 심볼:

| 심볼 | 용도 |
|---|---|
| `plugin` | 진입점 함수에 붙이는 데코레이터 (3.1) |
| `FileSession` / `BatchSession` | 세션 타입 (3.2/3.3) |
| `ExecResult` / `BatchResult` | 반환값 타입 (3.4) |
| `parse_params` | 단독 CLI에서 `key=value` 목록을 `dict[str, str]`로 파싱 |
| `_to_bool` | 단독 CLI에서 문자열을 bool로 변환할 때 재사용 (3.6의 변환 규칙과 동일) |
| `_truncate_filename` | 화면 표시용으로 파일명을 자를 때 사용 — 전각 문자(한글/한자/가나 등)를 폭 2로 계산하는 표시 폭 기준이라 len() 자르기보다 콘솔 줄바꿈을 잘 피한다. `group_md5`가 진행률/로그 표시에 사용 (5.5절) |

`from tcbp import ...`는 `tcbp.py`가 `__main__`으로 실행 중이든
`validate_config.py` 등에서 라이브러리로 import됐든 항상 동일한 실행 중인
모듈 인스턴스를 가리키도록 tcbp.py 내부에서 처리되어 있습니다 — 플러그인
작성자가 이 부분을 신경 쓸 필요는 없습니다.

---

## 4. 플러그인 Python 프로그램의 기본 구조

### 4.1 파일 위치 및 이름 규칙

- 플러그인은 반드시 `./plugin/<이름>.py`에 위치해야 합니다 (`tcbp.py`와 같은
  폴더의 `plugin` 하위).
- `config.toml`의 `plugin = "이름"`이 그대로 파일명(확장자 제외)이 됩니다 —
  대소문자·철자가 정확히 일치해야 합니다.
- 플러그인 전용 테스트 자료는 `./plugin/testdata/<이름>/`에 둡니다
  (`input.*`, `expected_output.*`, 선택적 `params.json`/`tolerance.json` —
  4.6절 참고).

### 4.2 스켈레톤 — FileSession 플러그인

```python
#!/usr/bin/env python3
"""
plugin/<name>.py - TCBP FileSession 플러그인: <한 줄 설명>.

Usage (standalone):
    python <name>.py <input> <output> [param1=value1] [param2=value2]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # tcbp.py가 있는 상위 폴더
from tcbp import plugin, FileSession, ExecResult, parse_params, _to_bool


# ── 핵심 로직 — run()과 단독 CLI가 공유 ─────────────────────────
def _process(input_path: str, output_path: str, params: dict) -> None:
    ...  # 실제 파일 1개 처리. 실패는 예외로 던진다.


@plugin(
    name="<name>", contract_version="1.0", version="1.0", author="...",
    session_type="file", requirements=[], notes_per_file=0,
)
def run(session: FileSession) -> ExecResult:  # TCBP 진입점
    try:
        _process(session.input, session.output, session.params)
    except Exception as exc:
        return ExecResult(False, str(exc))
    return ExecResult(True, "")


if __name__ == "__main__":  # 단독 CLI 진입점
    if len(sys.argv) < 3:
        print("Usage: python <name>.py <input> <output> [param1=value1]")
        raise SystemExit(1)
    input_path, output_path, *rest = sys.argv[1:]
    raw = parse_params(rest)
    cli_params = {
        # 필요한 키만 명시적으로 뽑아 기본값과 함께 정리
    }
    try:
        _process(input_path, output_path, cli_params)
        print(f"OK: {input_path}")
    except Exception as exc:
        print(f"FAILED: {input_path} -> {exc}")
        raise SystemExit(1)
```

이 구조는 `plugin/remove_bom.py`, `plugin/mozjpeg.py`, `plugin/bmp2png.py`가
그대로 따르는 패턴입니다. `run()`은 `_process()`를 호출하고 예외를
`ExecResult(False, ...)`로 변환하는 얇은 래퍼일 뿐이며, 실질적인 처리 로직은
전부 `_process()`(또는 그 아래의 헬퍼 함수들)에 있습니다.

### 4.3 스켈레톤 — BatchSession 플러그인

```python
#!/usr/bin/env python3
"""
plugin/<name>.py - TCBP BatchSession 플러그인: <한 줄 설명>.

Usage (standalone):
    python <name>.py <list_file> [param1=value1]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # tcbp.py가 있는 상위 폴더
from tcbp import plugin, BatchSession, BatchResult, parse_params


# ── 핵심 로직 — run()과 단독 CLI가 공유 ─────────────────────────
def _process(filelist: list[str], params: dict, log_fn) -> BatchResult:
    succeeded, failed = [], []
    try:
        for fp in filelist:
            try:
                ...  # 파일 1개 처리
                succeeded.append(fp)
            except Exception:
                failed.append(fp)  # 예상 가능한 개별 실패는 반환값으로 보고 (3.4)
    finally:
        print()  # stdout에 \r 진행률을 찍었다면 반드시 개행으로 마무리 (5.5)
    return BatchResult(succeeded=succeeded, failed=failed)


@plugin(
    name="<name>", contract_version="1.0", version="1.0", author="...",
    session_type="batch", requirements=[], notes_per_file=0,
)
def run(session: BatchSession) -> BatchResult:  # TCBP 진입점
    # run()의 예외는 catastrophic 신호로 예약된다 (3.4) — 여기서 삼키지 않는다.
    return _process(session.filelist, session.params, log_fn=lambda t: session.log(t, slot=0))


if __name__ == "__main__":  # 단독 CLI 진입점 — 목록 파일을 직접 읽는다
    if len(sys.argv) < 2:
        print("Usage: python <name>.py <list_file> [param1=value1]")
        raise SystemExit(1)
    list_path = Path(sys.argv[1])
    files = [line.strip() for line in list_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    cli_params = parse_params(sys.argv[2:])
    result = _process(files, cli_params, log_fn=print)
    print(f"succeeded={len(result.succeeded)} failed={len(result.failed)}")
    raise SystemExit(0 if not result.failed else 1)
```

`plugin/group_md5.py`가 이 패턴의 실제 구현 예시입니다.

### 4.4 단독 CLI 진입점 작성 규칙

`if __name__ == "__main__":` 블록은 tcbp 없이 콘솔에서 직접 실행 가능한
최소 CLI입니다. TCBP 런타임 진입점(`run()`)과 이 단독 CLI는 **반드시 동일한
`_process()` 함수를 공유**해야 합니다 — 처리 로직이 두 곳에서 따로 구현되어
어긋나는 일을 막기 위함입니다.

이 CLI의 목적은 "넘겨받은 파일 1개(BatchSession은 목록 파일 1개)의 처리가 잘
작동하는지"를 빠르게 확인하는 것뿐입니다. 따라서 다음은 **구현 대상이
아닙니다** — 전부 Total Commander(파일 선택)와 TCBP(배치 순회)가 이미 하는
일이기 때문입니다.

- 와일드카드 확장
- 재귀 디렉토리 탐색
- (FileSession의 경우) 여러 파일에 대한 배치 처리 — 인자로 정확히 파일 1개만
  받습니다.
- (BatchSession의 경우) 목록 파일 자체를 찾는 로직 — 인자로 받은 경로를 그대로
  읽습니다.

인자 형식은 예제들과 동일하게 유지하는 것을 권장합니다.

```commandline
python plugin\<name>.py <input> <output> [key=value ...]     # FileSession
python plugin\<name>.py <list_file> [key=value ...]           # BatchSession
```

단독 CLI에서는 TCBP의 `_coerce_params()`(3.6절의 자동 bool/int 변환)를 거치지
않으므로, bool 파라미터는 `tcbp._to_bool()`을 직접 불러 변환하거나(3.8절),
`int()`처럼 표준 변환을 사용합니다.

### 4.5 의존성 선언 (`requirements`)

플러그인이 표준 라이브러리 이외의 외부 패키지를 필요로 하면
`@plugin(requirements=[...])`에 패키지 이름을 나열합니다.

```python
@plugin(
    name="mozjpeg", contract_version="1.0", version="1.0", author="...",
    session_type="file",
    requirements=["jpeglib", "numpy", "Pillow"],
    notes_per_file=0,
)
```

**TCBP는 이 목록을 자동 설치하지 않습니다** — 문서화 목적이며, 사용자가
`pip install jpeglib numpy Pillow`처럼 수동으로 설치해야 합니다. 대신 다음
두 규칙을 지켜 "패키지 미설치"와 "플러그인 코드 자체의 결함"을 구분할 수
있게 합니다.

1. **모듈 최상단에서 외부 패키지를 강제 import하지 않습니다.** `try/except
   ImportError`로 감싸 `None`으로 폴백해두면, 패키지가 없는 환경에서도
   `validate_config.py`의 메타정보 검증(=`run.plugin_info` 확인을 위한
   import)이 실패하지 않습니다.

   ```python
   try:
       import jpeglib
   except ImportError:
       jpeglib = None
   ```

2. **실제 처리 시점(`_process()`)에서 값이 `None`이면 명확한 `RuntimeError`를
   던집니다.**

   ```python
   def _process(input_path, output_path, params):
       if jpeglib is None:
           raise RuntimeError("mozjpeg plugin requires jpeglib — pip install jpeglib")
       ...
   ```

이렇게 하면 필요 패키지가 없어도 `validate_config.py`는 정상 통과하고
(메타정보만 확인, 실제 처리는 실행하지 않으므로), 실제 실행 시점에만 원인이
분명한 에러 메시지로 실패합니다.

**대체 가능한 패키지가 여럿인 경우 (OR 의존성):** 같은 기능을 제공하는 후보
패키지가 여러 개 있어 그중 하나만 있어도 동작 가능하다면, `requirements`에는
후보 패키지를 전부 나열하고, 실제 선택은 사용 시점에 `try/except ImportError`를
중첩해 우선순위대로 시도합니다. 이 경우는 모듈 최상단에서 미리 지연 import를
해둘 필요 없이, 그 패키지를 실제로 쓰는 함수 안에서 바로 `import`해도 됩니다 —
`validate_config.py`가 하는 것은 `run.plugin_info`를 확인하기 위한 모듈 import뿐이고,
함수 내부의 import 문은 그 함수가 호출되기 전까지 실행되지 않기 때문입니다.
`plugin/bmp2png.py`의 `bmp_to_png()`가 이 패턴의 예시입니다 — OpenCV(우선,
고속)를 시도하고 `ImportError`면 Pillow로 폴백하며, 폴백마저 실패하면 그
예외를 실패 메시지로 변환해 반환합니다.

```python
def bmp_to_png(bmp_path: str, png_path: str) -> tuple[bool, str]:
    """OpenCV(우선) 또는 Pillow(폴백)로 BMP를 PNG로 변환한다."""
    try:
        import cv2
        ...  # OpenCV로 변환
        return True, ""
    except ImportError:
        try:
            from PIL import Image
            ...  # Pillow로 변환
            return True, ""
        except Exception as e:
            return False, f"ERROR (Pillow): {e}"   # 폴백마저 실패 — 에러로 보고
    except Exception as e:
        return False, f"ERROR (OpenCV): {e}"
```

원칙은 단일 패키지의 경우와 동일합니다 — "패키지가 하나도 없다"는 사실이
모듈 import 자체를 실패시키지 않고, 실제 처리 시점에만 명확한 실패로 드러나야
합니다. 단일 패키지 경우와의 차이는 그 실패를 `RuntimeError`로 던질지,
`bmp2png.py`처럼 `(ok, message)` 튜플 등 반환값으로 알릴지뿐입니다 — 둘 다
3.4절의 반환값 계약을 지키는 한 허용됩니다.

### 4.6 테스트 작성

`tests/` 스위트는 세 계층으로 나뉘며, 신규 플러그인을 추가할 때 계층별로
해야 할 일이 다릅니다.

| 계층 | 파일 | 신규 플러그인 시 필요한 작업 |
|---|---|---|
| unit | `tests/test_plugin_<name>.py` | **수기 작성** — `_process()`를 직접 import해 `tmp_path`로 호출하는 테스트. subprocess 없음, 에러 경로도 여기서 검증. |
| metadata | `tests/test_plugin_metadata.py` | 불필요 — `plugin/*.py`를 자동 순회하며 `run.plugin_info`가 유효한지 검증 |
| cli (golden) | `tests/test_plugin_cli_golden.py` | 불필요 — `plugin/testdata/<name>/`만 추가하면 자동 발견됨 |

**cli(golden) 계층용 testdata 준비:**

```
plugin/testdata/<name>/
    input.*              # 입력 파일 (BatchSession이면 input/ 폴더 등 플러그인에 맞게)
    expected_output.*    # 기대 출력
    params.json          # CLI에 전달할 파라미터 (선택)
    tolerance.json        # 이미지 출력 전용, { "rmse": 2.5 } 형태로 허용 오차 override (선택)
```

`test_plugin_cli_golden.py`가 이 폴더를 발견해 실제로
`python plugin/<name>.py <input> <output> [params...]`를 subprocess로 실행하고
결과를 `expected_output`과 비교합니다 — 4.4절의 "단독 CLI로 실행 가능"을
실제로 검증하는 유일한 계층입니다(unit 계층은 argparse를 거치지 않으므로 CLI
인자 파싱 버그를 잡지 못합니다).

이미지 출력(MozJPEG/bmp2png 등 인코더 버전에 따라 출력 바이트가 달라질 수
있는 플러그인)은 원본 바이트 diff 대신 Pillow로 디코드한 뒤 RMSE 기반 픽셀
비교를 사용합니다. 기본 허용치는 `RMSE <= 1.0`(0~255 스케일)이며, 손실 압축
강도가 높아 기본값으로 오탐이 잦다면 `tolerance.json`으로 개별 override할 수
있습니다.

로컬 개발 중 빠른 피드백이 필요하면 느린 계층을 제외하고 실행합니다.

```commandline
pytest -m "not cli and not integration"   # unit + metadata만, subprocess 없음
pytest                                     # 전체 계층 (CI)
```

---

## 5. 테크니컬 노트

### 5.1 fail-fast 2단계 검증

플러그인 메타정보 누락/오류는 두 단계에서 즉시 실패로 처리됩니다.

**(a) plugin import 시점** — `@plugin(...)`에 전달된 값 자체가 유효하지
않으면(예: `session_type="fil"`처럼 오타) `PluginInfo` 생성이 그 자리에서
실패하며 모듈 import 자체가 실패합니다. `validate_config.py`도 실제 실행 없이
동일한 시점에 동일한 검사를 수행하므로, config를 배치 실행하기 전에 미리
잡아낼 수 있습니다.

**(b) Job 실행 시점** — `run`이 아예 `@plugin(...)`으로 감싸지지 않아
`run.plugin_info` 속성 자체가 없으면, TCBP가 (기존 `_require_essentials()`와
같은 성격의) fail-fast 가드로 즉시 Job 실행을 중단하고 플러그인명과 문제를
명시한 에러 메시지를 냅니다.

### 5.2 pydantic 유무에 따른 검증 강도 차이

`FileSession`/`BatchSession`/`PluginInfo`/`ExecResult`/`BatchResult`는 모두
`strict_dataclass(frozen=True)`로 정의되어 있으며, 이는 다음과 같이 동작합니다.

- **pydantic이 설치된 환경**: `pydantic.dataclasses.dataclass`를 그대로 사용
  — 생성 시점에 필드 타입을 엄격히 검증하고, 실패 시 상세한
  `ValidationError`를 던집니다. `Literal["file", "batch"]` 같은 값 범위
  제약도 정확히 검증됩니다.
- **pydantic이 없는 환경**: 표준 `dataclasses.dataclass(frozen=True)` +
  `__post_init__` 내 최소 `isinstance` 기반 검증으로 자동 폴백합니다. 이때는
  중첩 타입 재귀 검증이나 `Literal` 값 범위 검사가 pydantic만큼 촘촘하지
  않습니다 — 예를 들어 대략적인 타입은 걸러내지만 미묘한 케이스는 통과시킬
  수 있습니다.

플러그인 코드 입장에서는 어느 쪽이 활성화됐는지 몰라도 됩니다 — 둘 다 같은
이름(`strict_dataclass`)으로 노출되며, `FileSession`/`ExecResult` 등을 다루는
코드는 동일합니다. 다만 pydantic 미설치 환경에서 타입 오류를 다루는
테스트를 짤 때는 이 검증 강도 차이를 염두에 두세요.

### 5.3 병렬 모드에서의 log() slot 예약 메커니즘

`parallel = true` + FileSession 플러그인에서, TCBP는 파일마다 "제목줄 +
`notes_per_file`만큼의 메시지 줄"로 구성된 고정 크기 화면 블록을 미리
예약합니다. 여러 워커 스레드가 서로 다른 파일을 동시에 처리하며 완료 순서가
뒤섞이더라도, 각 파일의 로그는 ANSI 커서 이동으로 자신에게 예약된 자리에만
쓰기 때문에 화면이 순서대로 유지됩니다(이 "여러 워커 스레드가 동시에
처리"한다는 사실 자체가 플러그인 코드에 미치는 영향은 5.10절 참고).

이 메커니즘이 성립하려면 **플러그인이 파일당 사용할 `log()` slot 개수를
`@plugin(notes_per_file=N)`으로 미리 선언**해야 합니다. 하나의 slot을 여러 번
호출해 내용을 갱신하는 것(% 진행률 표시 등)은 허용됩니다 — 제약은 "호출
횟수"가 아니라 "동시에 쓰는 slot 개수"입니다.

선언한 개수를 벗어난 slot 인덱스(`slot >= notes_per_file` 또는 `slot < 0`)를
쓰면 5.4절의 규칙에 따라 처리됩니다. 이 제약은 **병렬 모드에서만** 적용됩니다
— 순차 모드(`parallel = false`, BatchSession 포함)에서는 slot 예약이 필요
없으므로 log() 호출 횟수 제약이 아예 없습니다.

### 5.4 `--strict` 플래그

slot 초과 시 동작은 실행 모드에 따라 나뉩니다. "콘솔 스킵 + 로그만 기록"만
유일한 동작으로 두면 플러그인 개발자가 "왜 콘솔에 진행률이 안 뜨지?"의
원인을 못 찾은 채 방치하게 되므로, 운영 모드와 개발 모드를 분리했습니다.

- **기본(운영/배치) 모드**: 예외를 던지지 않습니다. 콘솔 블록 갱신만
  스킵하고, `log = true`일 때 해당 `log()` 호출 내용을 로그 파일에만
  `[WARNING]`으로 남깁니다(플러그인명·사용된 slot 인덱스·선언된
  `notes_per_file` 값 포함). **콘솔(stdout)에는 절대 출력되지 않습니다** —
  병렬 모드에서 여러 워커가 ANSI 커서로 고정 블록을 동시에 갱신하는 중에
  경고가 stdout에 섞여 나가면, 정작 막으려던 "콘솔 출력 꼬임"을 경고 자신이
  유발하게 되기 때문입니다.
- **`--strict` 모드**(`--dry-run`과 같은 레벨의 전역 CLI 플래그): slot 초과
  시 즉시 `IndexError`를 던지고 해당 Job 실행을 중단합니다(Fail-Fast).

```commandline
python tcbp.py MyPluginJob list.txt --strict
```

플러그인을 새로 만들거나 수정할 때는 **소규모 파일 목록 + `parallel = true`
+ `--strict` 조합으로 먼저 slot 사용이 올바른지 검증**하고, 실제
운영/예약 실행에서는 `--strict` 없이 돌리는 것을 권장합니다. 단독 CLI
진입점(4.4절)은 parallel/ANSI 블록 관리가 아예 없어 이 버그를
재현/검증할 수 없으므로, `--strict`가 사실상 이 문제를 검증할 유일한 수단
입니다.

### 5.5 BatchSession의 진행률 출력 규칙

BatchSession은 병렬 처리가 없으므로, plugin 실행 중에는 TCBP가 콘솔에 다른
내용을 쓰지 않습니다. 따라서 **plugin이 stdout에 직접 `\r`로 숫자 % 진행률을
찍는 것 자체는 안전**합니다(`group_md5`가 이 방식을 사용 — `rich` 같은
라이브러리의 ANSI 커서 이동은 TCBP 자체의 ANSI 블록 관리와 양립하지 않으므로
피합니다).

다만 다음 두 가지를 반드시 지켜야 합니다.

1. 그룹별 처리가 끝난 뒤의 최종 결과(예: `"생성됨: xxx.md5 (12개 파일)"`)는
   `\r` 진행률이 아니라 `session.log()`로 되돌려주어 로그 파일에도 남깁니다.
2. **plugin은 (정상 종료든 예외 발생이든) `run()`을 리턴하기 전에 반드시
   개행(`print()`)으로 마무리해야 합니다.** plugin이 처리 도중 죽거나 진행률
   줄 끝에 개행 없이 리턴하면, 바로 뒤에 이어지는 TCBP의 요약 로그와 줄이
   겹칠 수 있습니다. `group_md5`처럼 `try/finally`로 개행을 보장하세요.

```python
def _process(filelist, params, log_fn):
    try:
        for fp in filelist:
            print(f"\r{...}", end="", flush=True)
            ...
    finally:
        print()  # 중간에 죽거나 개행 없이 리턴하는 경우까지 포함해 개행 보장
    return BatchResult(...)
```

### 5.6 예외 vs 반환값 — 언제 무엇을 쓸까

| 상황 | 처리 방법 |
|---|---|
| 파일 그룹 중 일부(예: 손상된 파일 1개)만 실패 | `BatchResult.failed`에 담아 반환 (예외 아님) |
| 파일 1개 처리 도중 예상 가능한 실패(형식 오류, 지원하지 않는 확장자 등) | `_process()`에서 예외를 던지고, `run()`이 이를 잡아 `ExecResult(False, str(exc))`로 변환 |
| Job 실행 자체를 더 이상 신뢰할 수 없는 catastrophic 상황(BatchSession) | `run()` 밖으로 예외를 그대로 던짐 — TCBP가 `filelist` 전체를 실패로 합성 |
| 필요 패키지 미설치 | `_process()`에서 `RuntimeError` (4.5절) |

FileSession 플러그인은 대부분 `_process()`의 예외를 `run()`이
`ExecResult(False, ...)`로 감싸는 패턴(4.2절 스켈레톤)으로 충분합니다.
BatchSession 플러그인은 "그룹/파일 단위의 예상 가능한 실패"와 "Job 전체를
신뢰할 수 없게 만드는 실패"를 구분해서 다뤄야 합니다(3.4절, `group_md5`
참고) — 전자는 루프 안에서 잡아 `failed`에 쌓고, 후자만 예외로 흘려보냅니다.

### 5.7 dry-run 동작

`--dry-run` 플래그가 지정되면 TCBP는 `run()`을 아예 호출하지 않고, 대신
파라미터가 어떻게 치환됐는지 안내 문구만 로그로 출력합니다.

```
[DRY-RUN] plugin=resize input=... output=... params={...}          # FileSession
[DRY-RUN] plugin=group_md5 files=42 params={...}                    # BatchSession
```

이때 각각 `ExecResult(True, "")`, `BatchResult(succeeded=[], failed=[])`로
간주되어 "성공"으로 집계됩니다. 플러그인 작성자는 dry-run 전용 분기를
직접 만들 필요가 없습니다 — `run()` 진입 이전에 TCBP가 이미 걸러줍니다.

### 5.8 Session은 읽기 전용이다

`FileSession`/`BatchSession`은 `frozen=True`로 생성되므로, `log()` 호출을
제외하면 필드를 변경할 수 없습니다(`session.params["x"] = 1`처럼 값 자체를
바꾸는 것은 가능하지만 — `params`가 `dict`이므로 — 필드 자체의 재할당,
예를 들어 `session.input = "..."`은 예외를 발생시킵니다). 플러그인 내부에서
세션을 통해 상태를 되돌려주는 유일한 통로는 `log()`와 반환값(`ExecResult`/
`BatchResult`)뿐입니다.

### 5.9 흔한 실수 체크리스트

새 플러그인을 작성했다면 다음을 점검하세요.

- [ ] `run` 함수에 `@plugin(...)` 데코레이터를 붙였고, `session_type`이
      `"file"`/`"batch"` 중 실제 처리 단위와 일치하는가?
- [ ] `@plugin(contract_version=...)`을 선언했는가? (3.1절 — 현재 TCBP의 계약
      버전은 `tcbp.CONTRACT_VERSION`으로 확인 가능)
- [ ] `run()`과 단독 CLI가 동일한 `_process()` 함수를 호출하는가? (4.4절)
- [ ] 단독 CLI에서 파일 목록/와일드카드/재귀 탐색을 구현하지 않았는가?
      (구현했다면 삭제 대상 — 2.2절)
- [ ] 외부 패키지를 모듈 최상단에서 강제 import하지 않고 `try/except
      ImportError`로 감쌌는가? (4.5절)
- [ ] `@plugin(requirements=[...])`에 필요한 패키지를 빠짐없이 나열했는가?
- [ ] 병렬 모드에서 `log()`를 쓴다면 `notes_per_file`을 실제 사용하는 slot
      개수와 정확히 일치하게 선언했는가? (5.3절)
- [ ] BatchSession 플러그인이 `run()` 리턴 전에 반드시 개행을 보장하는가?
      (5.5절, `try/finally`)
- [ ] BatchSession에서 예상 가능한 개별 파일 실패를 예외로 던지지 않고
      `BatchResult.failed`로 보고하는가? (5.6절)
- [ ] `plugin/testdata/<name>/`에 골든 테스트 자료를 추가했는가? (4.6절)
- [ ] `parallel = true`인 FileSession 플러그인에서 모듈 전역/클래스 변수처럼
      파일 간에 공유되는 상태를 쓴다면, 락 없이도 안전한 멱등적 캐시인지
      확인했는가? 그렇지 않다면 `@plugin(thread_safe=False)`를 선언했는가?
      (5.10절)

### 5.10 병렬 모드에서 플러그인 코드의 스레드 안전성

`parallel = true` + FileSession 조합에서는 TCBP가 `ThreadPoolExecutor`로 여러
워커 스레드를 띄워 서로 다른 파일에 대해 동시에 `run()`(따라서
`_process()`)을 호출합니다(2.3/5.3절). 파일마다 새로 생성되는 `session` 인스턴스
자체는 서로 독립적이라 안전하지만, **모듈 전역 변수나 클래스 변수처럼 파일
간에 공유되는 상태는 플러그인 작성자가 직접 스레드 안전성을 책임져야
합니다** — 이 부분은 tcbp가 대신 보장해주지 않습니다.

실용적 기준은 다음과 같습니다.

- **락 없이 허용:** 여러 스레드가 동시에 계산해 같은 전역 변수에 대입해도
  결과가 항상 같은 값이 되는 멱등적 캐시. `plugin/mozjpeg.py`의
  `_CHOSEN_MOZJPEG`(설치된 MozJPEG 버전 감지 결과 캐시)가 이 패턴입니다 —
  두 스레드가 동시에 `_ensure_mozjpeg_selected()`를 호출해 값을 두 번
  계산하더라도 매번 같은 값이 나오므로, 락 없이 마지막에 대입된 값을
  그대로 써도 결과가 달라지지 않습니다.
- **반드시 락(또는 스레드-로컬/스레드 안전 자료구조)이 필요:** 누적
  카운터, 호출 순서에 결과가 좌우되는 상태 갱신, 파일 핸들이나 네트워크
  커넥션처럼 그 자체가 스레드 안전하지 않은 외부 리소스를 여러 스레드가
  공유하는 경우. 이런 상태는 애초에 전역으로 두지 말고 `_process()` 내부의
  지역 변수로 유지하는 편을 권장합니다 — 공유 자체가 없어지면 스레드
  안전성 문제도 함께 사라집니다.
- **판단이 애매하면 전역 상태 자체를 없애세요.** "이 캐시가 멱등적인가?"를
  매번 증명하려 하기보다, 가능하면 상태를 아예 갖지 않는(각 호출이
  완전히 독립적인) 함수로 작성하는 편이 더 안전하고 단순합니다.

이 제약은 **FileSession + `parallel = true`일 때만** 해당합니다. BatchSession
(3.3절)은 TCBP가 병렬로 실행하지 않으므로 이 문제 자체가 없습니다.

**위 기준으로도 스레드 안전하게 만들 수 없다면 `@plugin(thread_safe=False)`를
선언하세요.** `thread_safe`는 3.1절의 `PluginInfo` 필드로, 기본값은 `True`
(별도 선언 없으면 "스레드 안전하다"고 간주)입니다. `session_type="file"`인
플러그인이 `thread_safe=False`로 선언되어 있으면, 다음 두 지점이 **동일한
기준으로 즉시 실행을 거부**합니다.

- **tcbp.py 런타임** — `_require_essentials()`가 Job을 resolve한 직후(5.1절
  (b)와 같은 성격의 가드) `parallel=true` + `max_workers>1`과 매칭되는지
  검사해, 매칭되면 명확한 에러 메시지와 함께 그 자리에서 종료합니다.
- **`validate_config.py`** — `_check_plugin()`이 같은 조건을 실행 전에 미리
  진단해 `[ERROR]`로 보고합니다(BatchSession+parallel 조합은 "무시되니
  경고"로 충분하지만, 이 조합은 조용히 넘어가면 실제 레이스 컨디션으로
  이어질 수 있으므로 경고가 아니라 오류입니다).

`max_workers=1`이면 `parallel=true`라도 워커가 하나뿐이라 두 파일이 동시에
처리되지 않으므로 거부 대상이 아닙니다 — `parallel=true`를 켜둔 채로
`max_workers=1`로 낮추는 것이 이 제약을 우회하는 정당한 방법입니다.

> **참고: `validate_config.py`가 플러그인의 `@plugin(...)` 메타정보를 읽어도
> 되는가?** 이 검사는 새로운 결합이 아니라 기존 패턴의 연장입니다 —
> `validate_config.py`는 이미 `_check_plugin()`에서 `load_plugin()`으로
> 플러그인을 import해 `plugin_info.session_type`을 읽고
> "BatchSession+parallel=true는 무시됨" 경고를 내고 있었습니다(§3.7).
> `run(session)`은 절대 호출하지 않고 import(메타정보 확인)까지만 하므로
> "실행 없이 진단한다"는 이 도구의 설계 원칙(§5.5)을 그대로 지킵니다.
> `thread_safe` 검사는 여기에 새 필드 하나를 추가로 읽는 것뿐이라 동일한
> 원칙 위에서 타당합니다.
