# TCBP — Total Commander Batch Python
[TOC]
## 1. 개요
본 도구는 [TCBL (Total Commander Batch Builder & Launcher)](https://totalcmd.net/plugring/TCBL_1.02.html) 도구에 영감을 받아 유사한 기능을 Python으로 재구축한 것입니다.

## 2. 특징
본 도구는 주요 특징은 다음과 같습니다.

### 2.1 `TCBL`과 동일한 특징
- 단일 파일을 처리하는 CLI(command line interface) 기반 도구를 반복 배치(batch)로 실행할 수 있습니다.
- 처리 대상 파일은 목록파일(list file)로 입력받아 처리합니다.
- [토탈 커맨더(Total Commander)](https://www.ghisler.com/), [디렉토리 오퍼스(Directory Opus)](https://www.gpsoft.com.au/)와 같은 파일 관리자 도구와 결합하면 강력한 위력을 발휘합니다. (대상 파일을 파일 관리자에서 선택하여 리스트 파일을 본 도구에 넘기면 선택된 파일들을 배치처리합니다.)
- 최초 1회 실행할 명령(pre), 대상 파일들에 반복 실행할 명령(command), 최종 1회 실행할 명령(post)를 각기 지정할 수 있습니다.

### 2.2 `TCBL` 대비 향상된 특징
- 파일 처리를 멀티스레드(MultiThread)화하여 여러 파일을 동시 처리할 수 있습니다. `MP3` 인코딩, `PNG` 인코딩 등 프로세싱 부하가 큰 작업에 유리합니다.
- 멀티스레드에 의해 파일이 비순차 처리되더라도, 화면 출력은 순차 출력을 유지합니다.
- 멀티 프로세싱시 중간 파일명이 프로세스간 충돌하지 않도록 UUID4 기반의 임시ID 생성을 하여 활용할 수 있습니다.
- `유니코드(Unicode)` 파일명, 경로명을 지원합니다. 외부 CLI 도구가 유니코드를 지원하지 않고 `ANSI` 코드만을 지원하더라도, 본 도구에서 자체적으로 경로명을 우회 처리하여 최종 출력으로 연결해줍니다.
- 배치 실행전에 원하는 파라미터를 수동으로 입력받을 수 있습니다.
- 설정 파일이 포맷이 `INI`인 `TCBL`과 달리, 설정 파일 포맷이 `TOML`이어서 유니코드를 문제없이 처리합니다.

---

## 3. 프로그램 구성 및 사용법
### 3.1 요구사항
- Python 3.11 이상 (`tomllib` 내장)
- 외부 라이브러리 없음 (표준 라이브러리만 사용). 단, 아래는 선택 설치 시 자동으로 활용됩니다.
  - `keyboard`: `pause = true`일 때 "아무 키나 누르면 종료" 대기에 사용 (없으면 Enter 키 대기로 자동 대체)
  - `wcwidth`: 화면에 표시되는 파일명/메시지의 폭 계산에 사용 (없으면 근사치 계산으로 자동 대체)
- Windows 환경 (Unicode 경로 완전 지원)
### 3.2 파일 구성
```filelist
tcbp.py           실행 엔진
config.toml       작업 정의 파일 (기본값)
tcbp.log          실행 로그 (log=true 시 자동 생성)
```
### 3.3 기본 사용법

```commandline
python tcbp.py <JobName> <FileList> [key=value ...] [--config <path>] [--dry-run] [--lang ko|en]
```

기본 출력 언어는 한국어이며, 오류·경고·로그 등 tcbp.py 자신이 출력하는 문구만 대상입니다 (config.toml에 사용자가 직접 쓴 `desc`, `{ msg = "..." }` 내용은 번역하지 않고 작성한 그대로 출력됩니다). 언어는 다음 우선순위로 결정됩니다.
1. `--lang ko` / `--lang en` (CLI 인자, `--help` 텍스트에도 적용됨)
2. `config.toml`의 `[global] lang = "en"`
3. 기본값 `ko`
### 3.4 예시 - 기본 사용
```commandline
:: 단순 변환 (파라미터 없음)
python tcbp.py Conv2PNG list.txt

:: 실행 없이 명령만 출력 (dry-run)
python tcbp.py ResizeImages list.txt size=1024 --dry-run

:: 별도 설정 파일 사용
python tcbp.py Conv2PNG list.txt --config my_project.toml
```

### 3.4 예시 - 파라미터 전달
- 설정 파일내에 `params = []` 항목에 지정한 파라미터를 전달할 수 있습니다.
- 파라미터는 실행시 커맨드 라인상에서 전달할 수도 있으나, 생략하면 실행시 사용자로부터 직접 입력(타이핑)을 받아 처리합니다.
```commandline
:: 파라미터 전달
python tcbp.py ResizeImages list.txt size=1024
python tcbp.py CropImages   list.txt x=10 y=20 width=800 height=600
python tcbp.py Helix_MP3    list.txt bitrate=64
```


### 3.5 dry-run 모드
```commandline
python tcbp.py ResizeImages list.txt size=1024 --dry-run
```
- 파일 목록, placeholder 치환, 명령 구성까지 수행
- 실제 subprocess 실행 없이 명령만 출력
- 설정 검증 및 디버깅에 활용

샘플 출력:
```log
[DRY-RUN 모드] 명령 출력만 수행하고 실제 실행하지 않습니다.
Job: ResizeImages — Resize images (keep aspect ratio, only to smaller size)
파일 3개  |  sequential
[DRY-RUN][PRE] Resize images
[DRY-RUN][PRE] Side Length: 1024 pixels
[   1] photo01.jpg → photo01_out.jpg
  [DRY-RUN] "C:/.../gm.exe" convert -resize 1024x1024> "photo01.jpg" "photo01_out.jpg"
[   2] photo02.png → photo02_out.png
...
완료 — 성공: 3  실패: 0  전체: 3
```

### 3.6 입력 파일 목록 형식 (list.txt)
- 입력 파일 목록은 `UTF-8` 또는 `UTF-8 with BOM` 형식으로 인코딩된 텍스트 문서입니다.
- 각 작업 대상은 유니코드의 경로명+파일명(full-path)으로 기록합니다.
- 파일관리자인 토탈 커맨더(Total Commander)에서는 파라미터로` %UL` 을 전달하면, 토탈커맨더에서 선택한 판일들의 목록이 임시 폴더에 리스트 파일로 만들어져서 전달됩니다.
```listfile
# 주석은 # 으로 시작
C:\images\photo01.jpg
C:\images\photo02.png
C:\images\photo03.bmp
```

---

## 4. `config.toml` 구조 및 설정법

### 4.1 global 섹션 설정

```toml
[global]
on_error     = "continue"               # "continue" | "stop"
parallel     = false                    # 전체 기본값
max_workers  = 4                        # 멀티스레드 병렬 처리 시 최대 worker 수
output       = "{dir}/{base}_out{ext}"  # 출력 경로 규칙
log          = false                    # 로그 파일 기록 여부
log_file     = "tcbp.log"               # 로그 파일 경로
pause        = false                    # 완료 후 키 입력 대기 여부
stderr_quiet = false                    # 도구 STDERR 출력 억제 여부
lang         = "ko"                     # "ko" | "en" — tcbp.py 출력 언어 (CLI --lang이 우선)

[global.tools]
magick   = "C:/path/magick.exe"         # 그래픽 프로세싱/포맷변환 : https://imagemagick.org/ (느리나 더 강력하고 고급 기능 다룸)
gm       = "C:/path/gm.exe"             # 그래픽 프로세싱/포맷변환 : https://imagemagick.org/ (빠르고 일반 작업에 적합)
flac     = "C:/path/flac.exe"           # 무손실 음원 포맷 : https://xiph.org/flac/
hmp3     = "C:/path/hmp3.exe"           # 초고속 MP3 인코더 : https://www.rarewares.org/mp3-others.php#helix_enc
pngcrush = "C:/path/pngcrush.exe"       # PNG 이미지 최적화 재압축기 : https://pmt.sourceforge.io/pngcrush/
oxipng   = "c:/path/oxipng.exe"         # PNG 이미지 최적화 재압축기 : https://github.com/oxipng/oxipng/releases
```

### 4.2 job 섹션 설정
```toml
[jobs.MyJob]
desc         = "작업 설명"
tool         = "gm"             # global.tools 키 또는 직접 경로
on_error     = "continue"       # global override
parallel     = false            # global override
max_workers  = 4                # global override
output       = "{dir}/{base}_out{ext}"  # global override
pause        = false            # global override
stderr_quiet = false            # 도구 STDERR 출력 억제

pre      = [ { msg = "시작..." } ]
commands = [ "{tool} convert {input} {output}" ]
post     = [ { msg = "완료." } ]

# 파라미터 선언 (선택)
params = [
    { key="size", desc="출력 크기 (픽셀)", type="int" },
]
```
- pre에 지정된 명령은 최초 1회만 실행합니다.
- command에 지정된 명령은 리스트 내의 파일들에 대해 배치 처리하여 반복 실행합니다.
- post에 지정된 명령은 최종 1회만 실행합니다.
- pre/post/commands 모두 shell 없이(`shell=False`) 실행됩니다. `del`/`copy`/`dir` 등 cmd.exe 내장 명령을 실제로 실행해야 한다면 실행 파일이 아니므로 4.8절 예시처럼 `cmd /c` 를 직접 붙여서 작성해야 합니다. 단순 안내 메시지 출력은 `cmd /c echo`가 아니라 `{ msg = "..." }` 테이블로 씁니다 — 4.2.1절 참고.
- MyJob에 자신만의 작업명을 기재하고, 실행시 작업명을 파라미터로 넘겨서 실행한다.
```commandline
python tcbp.py MyJob filelist.txt
```

### 4.2.1 메시지 출력 — `{ msg = "..." }`
`pre` / `commands` / `post` 배열의 원소는 문자열(실행할 명령) 또는 `{ msg = "..." }` 테이블(화면·로그에 출력만 할 메시지) 중 하나로 쓸 수 있습니다. 메시지는 프로세스를 전혀 띄우지 않고 파이썬이 직접 로그로 출력합니다.

```toml
pre = [
    { msg = "-------------------------------------------------------------------------------" },
    { msg = "   Convert images PNG format" },
    { msg = "-------------------------------------------------------------------------------" },
]
```

`commands` 안에서는 실제 명령들 사이에 끼워 넣어 **파일 단위 진행 메시지**로 쓸 수 있습니다. 이때 `{input}`/`{output}`/`{name}`/`{base}`/`{dir}`/`{tool}`/`{index}`는 명령 인자용 따옴표가 없는 원본 값으로 치환됩니다 (아래 4.8절 예시 참고).

```toml
commands = [
    "cmd /c copy {input} C:\\src.tmp",
    { msg = "[{index}] {name} 임시 변환 시작" },
    "C:\\path\\HCONV.EXE C:\\src.tmp C:\\tgt.tmp /k",
    { msg = "[{index}] {name} 최종 이동 중" },
    "cmd /c copy C:\\tgt.tmp {output}",
]
```

- `parallel = true` job에서도 파일별 메시지 줄은 순서가 보장됩니다. 한 job의 `commands` 안에 있는 메시지 개수는 고정값이므로, 파일마다 "제목줄 + 메시지 줄" 만큼의 화면 영역을 미리 예약해두고 각 줄을 완료 시점과 무관하게 정해진 위치에 덮어씁니다.
- `on_error = "stop"` 등으로 뒤 단계가 아예 실행되지 못해 메시지가 발생하지 않으면, 예약된 그 줄은 그냥 빈 줄로 남습니다 (별도 처리 불필요).
- 메시지 한 줄이 콘솔 폭을 넘으면 줄바꿈이 일어나 화면이 깨지므로, 자동으로 말미가 `...`로 잘립니다.

#### job 섹션 비표준 키 — placeholder 기본값
표준 필드(`desc`, `tool`, `pre`, `commands` 등)가 아닌 임의 키를 job 섹션에 추가하면, 해당 키가 자동으로 `{placeholder}` 기본값이 됩니다.

```toml
[jobs.AddWatermark]
tool      = "gm"
watermark = "c:/_FIX/images/logo.png"   # ← 비표준 키 → {watermark} 로 사용 가능

commands = [
    "{tool} composite -gravity southeast \"{watermark}\" {input} {output}",
]
```

- CLI에서 같은 이름의 파라미터를 전달하면 job 정의 값을 덮어씁니다. (CLI 우선)
- 경로값은 자동 따옴표 처리가 되지 않으므로, 명령 내에서 `\"{key}\"` 로 감싸야 합니다.

### 4.3 치환자(Placeholder) 일람
| Placeholder | 설명 | 예시 |
|---|---|---|
| `{input}` | 입력 파일 전체 경로 | `C:\images\photo.jpg` |
| `{dir}` | 입력 파일의 디렉토리 | `C:\images` |
| `{name}` | 파일명 (확장자 포함) | `photo.jpg` |
| `{base}` | 파일명 (확장자 제외) | `photo` |
| `{ext}` | 확장자 (점 포함) | `.jpg` |
| `{index}` | 처리 순번 (1부터) | `1` |
| `{output}` | output 적용 결과 경로 | `C:\images\photo_out.jpg` |
| `{tool}` | 해당 job의 tool 경로 | `C:\path\to\gm.exe` |
| `{max_workers}` | 병렬 worker 수 | `8` |
| `{key}` | CLI `key=value` 파라미터 또는 job 섹션 비표준 키 | `size=1024` → `{size}` = `1024` |
| `{taskid}` | 배치 전체에서 1회만 생성되어 공용으로 사용하는 임시 ID (주로 임시 폴더명에 사용) | `tmp_550e8400e29b` |
| `{itemid}` | 파일(아이템)마다 새로 생성되는 임시 ID. 한 아이템의 여러 command 줄에서는 동일한 값 유지. (주로 임시 파일명에 사용) | `tmp_3fa85f645717` |

`{taskid}` / `{itemid}`는 멀티스텝 명령 중 임시 파일이 필요할 때, 파일명 충돌(특히 `parallel = true` 멀티스레드 처리 중)을 피하기 위한 용도입니다. 프로그램이 자동적으로 UUID4 난수를 사용한 임시 이름을 생성합니다.

### 4.4 Placeholder 치환 범위
| 위치 | 파일 단위 placeholder | named params | `{tool}` | `{max_workers}` | `{taskid}` | `{itemid}` |
|---|---|---|---|---|---|---|
| `pre` / `post` | 치환 안 됨 | 치환됨 | 치환됨 | 치환됨 | 치환됨 | 치환 안 됨 |
| `commands` | 치환됨 | 치환됨 | 치환됨 | 치환됨 | 치환됨 | 치환됨 |
| `output` | 치환됨 | 치환됨 | 치환됨 | 치환됨 | 치환됨 | 치환됨 |

- 미정의된 placeholder는 placeholder로 간주하지 않고 원문을 유지합니다. (`{unknown}` → `{unknown}`).

### 4.5 자동 따옴표 처리
- 경로를 담는 placeholder는 commands 실행 시 자동으로 따옴표로 감싸집니다. `"..."` 로 감싸진다. 
- 따라서 `config.toml`에 `\"` 를 직접 쓰지 않습니다.
- 단, 표준 정의된 placeholder가 아닌 사용자 정의 placeholder를 삽입하려는 경우, 그 내용이 경로명이라면 `\"` 를 직접 써야 합니다.

| Placeholder | 자동 따옴표 | 비고 |
|---|:---:|---|
| `{input}` | ✓ | 입력 파일 전체 경로 |
| `{output}` | ✓ | 출력 파일 전체 경로 |
| `{dir}` | ✓ | 디렉토리 경로 |
| `{name}` | ✓ | 파일명 (확장자 포함) |
| `{base}` | ✓ | 파일명 (확장자 제외) |
| `{tool}` | ✓ | 실행 파일 경로 |
| `{ext}` | — | `.jpg` 형태, 공백 없음 |
| `{index}` | — | 숫자 |
| `{max_workers}` | — | 숫자 |
| `{key}` (user param) | — | 값 성격 불명, 필요 시 수동 처리 |
| `{taskid}` | — | `tmp_` 접두 hex 문자열, 공백 없음 |
| `{itemid}` | — | `tmp_` 접두 hex 문자열, 공백 없음 |

```toml
# 일반 작성법 (따옴표 불필요) 예1 
commands = [
    "{tool} convert -quality 95 {input} {output}",
]

# 일반 작성법 (따옴표 불필요) 예2
commands = [
    "RemoveBOM.exe {name} {dir}",
]

```

```toml
# 사용자 정의 placeholder가 경로명 -> 따옴표 필요
watermark = "c:/path/images/fuzzy-magick.png"
commands = [
    "{tool} composite -gravity southeast -quality 95 \"{watermark}\" {input} {output}",
]
```

### 4.6 output 작성 가이드
#### 4.6.1 확장자 변경 (포맷 변환)

```toml
# 출력 포맷이 출력 파일명에 붙어있는 확장자를 따르는 도구에서 사용
output = "{dir}/{base}.png"     # 항상 PNG
output = "{dir}/{base}.jpg"     # 항상 JPG
output = "{dir}/{base}.bmp"     # 항상 BMP
```

#### 4.6.2 접미사 추가
```toml
# 출력확장자 = 원본 확장자로 유지하며, 덮어쓰기 방지를 위해 접미사(suffix) 추가
output = "{dir}/{base}_out{ext}"        # photo_out.jpg
output = "{dir}/{base}_resized{ext}"    # photo_resized.jpg
```

#### 4.6.3 파라미터 포함
```toml
output = "{dir}/{base}_{size}px{ext}"   # photo_1024px.jpg
```

### 4.7 병렬 처리
```toml
[jobs.Conv2PNG_Fast]
tool        = "gm"
output      = "{dir}/{base}.png"
parallel    = true
max_workers = 8

commands = [
    "{tool} convert -quality 95 {input} {output}",
]
```

- `parallel = true`: `ThreadPoolExecutor`로 파일 단위 병렬 실행합니다.
- 병렬 모드에서도 `pre` / `post` 는 1회만 실행합니다.

---

### 4.8 멀티 스텝 (Multi-step)
- 한 파일에 대해 여러 명령을 순서대로 실행합니다.
- 중간 파일 경로는 명령 내에 직접 기술합니다.
- `{output}`은 최종 결과 경로를 가리킵니다.
- `parallel = true`로 여러 파일을 동시 처리하면 중간 파일 경로가 고정 문자열일 때 파일명이 충돌할 수 있습니다. 이때는 `{taskid}` / `{itemid}` (4.3절 참고)를 중간 파일명에 사용하여 충돌을 피합니다.
```toml
[jobs.Johap_to_KS]
tool     = ""
on_error = "stop"

pre = [
    { msg = "임시 폴더 생성: C:\\Temp\\{taskid}" },
    "cmd /c mkdir C:\\Temp\\{taskid}",
]

commands = [
    "cmd /c copy {input} C:\\Temp\\{taskid}\\{itemid}_src.tmp",
    { msg = "[{index}] {name} 조합형→KS 변환 중..." },
    "C:\\path\\HCONV.EXE C:\\Temp\\{taskid}\\{itemid}_src.tmp C:\\Temp\\{taskid}\\{itemid}_tgt.tmp /k",
    { msg = "[{index}] {name} 결과 이동 중..." },
    "cmd /c copy C:\\Temp\\{taskid}\\{itemid}_tgt.tmp {output}",
    "cmd /c del C:\\Temp\\{taskid}\\{itemid}_src.tmp",
    "cmd /c del C:\\Temp\\{taskid}\\{itemid}_tgt.tmp",
]

post = [
    "cmd /c rmdir /s /q C:\\Temp\\{taskid}",
    { msg = "임시 폴더 삭제 완료: C:\\Temp\\{taskid}" },
]
```
- `{ msg = "..." }` 는 4.2.1절 참고. `on_error = "stop"`이라 `HCONV.EXE` 단계가 실패하면 두 번째 메시지는 아예 출력되지 않고 그 줄은 빈 채로 남습니다.
- `{itemid}`는 한 파일을 처리하는 동안 모든 단계에서 동일한 값을 유지하므로, 위 예시처럼 여러 명령에 걸쳐 같은 중간 파일을 참조할 수 있습니다.
- `{taskid}`는 배치 전체에서 1회만 생성되어 `pre`/`commands`/`post` 어디서나 동일한 값을 가리키므로, 위 예시처럼 `pre`에서 배치 공용 임시 폴더를 만들고 `post`에서 정리하는 용도로 사용할 수 있습니다. `commands`에서는 그 폴더 안에 `{itemid}`로 파일별 중간 파일명을 구분해 `parallel = true`에서도 충돌 없이 동작합니다.

### 4.9 에러 처리
```toml
on_error = "continue"   # 실패한 파일 건너뛰고 계속 진행
on_error = "stop"       # 첫 실패 즉시 중단
```
- `global` 또는 `job` 단위 설정 가능
- 병렬 모드에서 `stop`: 진행 중인 나머지 Future 취소
- 실패한 파일은 로그에 기록 (CMD + STDERR 포함)

### 4.10 로깅
```toml
[global]
log      = true
log_file = "tcbp.log"
```
- `log = false`: 콘솔 출력만
- `log = true`: 콘솔 + 파일 동시 기록
- 로그 파일은 항상 **tcbp.py 와 같은 폴더**에 생성됩니다. (실행 위치 무관)
- 로그에는 잡 헤더, 파일별 처리 결과, 오류 메시지(CMD + STDERR)가 기록됩니다.

#### 긴급 오류 로그 (`tcbp_error.log`)
설정 파일 로드 실패 등 로거 초기화 이전에 발생한 오류는 `tcbp_error.log`에 타임스탬프와 함께 기록됩니다.

```
[2026-06-27 23:51:15]
[ERROR] config.toml 문법 오류

Line 297, Column 1

296 | [jobs.Sharpen]
297 | desc
298 | tool = "gm"
      ^

키 뒤에 '=' 가 필요합니다.
```

오류 발생 시 콘솔창이 자동으로 유지되어 내용을 확인할 수 있습니다.

### 4.11 설정 파일 자동 검증 (Config Validation)
`config.toml`을 읽어들인 직후, 실행할 Job에 흔한 작성 실수가 없는지 자동으로 점검합니다. `config.toml`의 구조나 작성 방식은 전혀 바뀌지 않으며, 정상적으로 작성된 Job은 아무 메시지 없이 기존과 동일하게 실행됩니다.

검사 항목:
- **필수 key 누락** — `tool`, `output`, `commands` 중 실제로 비어있는 항목이 있으면 오류로 판단해 실행을 중단합니다.
- **예약어 오타** — `tool_pat`처럼 표준 key(`tool`, `output`, `pre` 등)와 철자가 비슷한 key를 쓰면 오타로 의심해 경고합니다.
- **placeholder 오타** — `{basename}`처럼 어디에서도 채워지지 않는 placeholder를 쓰면 경고하고, 비슷한 이름의 실제 placeholder가 있으면 제안합니다.
- **미사용 커스텀 key** — job에 정의했지만 `pre`/`commands`/`post`/`output` 어디에서도 `{key}` 형태로 쓰이지 않는 값은 정보로 알려줍니다.

오류(ERROR)가 있으면 실행을 중단하고, 경고(WARNING)·정보(INFO)는 알려주기만 하고 그대로 계속 진행합니다.

```
=== Config Validation Result ===

Job: ResizeImage

[ERROR]
- 필수 Key 누락: tool (또는 global.tools 에 등록된 tool 이름이 필요합니다)

[WARNING]
- 알 수 없는 Key: tool_pat
  혹시 다음을 의미하셨습니까? tool
- 정의되지 않은 Placeholder: {basename}
  혹시: {name}

[INFO]
- 사용되지 않는 Key: quality

총 오류 1개  총 경고 2개  총 정보 1개
```

---

## 5. 새 Job 추가 방법
1. `config.toml`에 `[jobs.NewJobName]` 섹션 추가
2. `tool`, `output`, `commands` 정의
3. 파라미터가 필요하면 `{param_name}` 형태로 commands에 기술
4. 실행 시 `key=value` 형태로 전달
```toml
[jobs.Sharpen]
desc        = "Sharpen images"
tool        = "gm"

commands = [
    "{tool} convert -unsharp {radius}x{sigma} -quality {quality} {input} {output}",
]
```

```batch
python tcbp.py Sharpen list.txt radius=3 sigma=1.5 quality=95
```

`output` 키와 `{output}` placeholder를 쓰지 않고 `commands` 키에 직접 출력 규칙 `{dir}/{base}_out{ext}`을 적어 넣어도 동작할 수도 있으나, 유니코드를 지원하지 않는 도구의 경우는 경로 회피 로직이 제대로 적용되지 못하게 됩니다. `output` 키와 `{output}` placeholder를 사용하는 것을 권합니다. `tool` 키도 마찬가지로 사용하지 않고 `commands` 키에 직접 tool 실행파일을 지정해도 되나, 동일 툴을 여러 job에서 사용할 경우 툴이 변경되면 수정할 곳이 늘어나게 됩니다. `[global.tools]` 섹션에 정의하여 사용하는 것을 권장합니다.

---

## 6. Total Commander 연동
- 토탈 커맨더의 버튼바, Start 메뉴 하위의 사용자 메뉴에서 다음과 같이 설정합니다.
- 시작 경로는 특별한 의도가 없다면 공란으로 비웁니다. 그렇게 해야 토탈 커맨더 상의 현재 경로가 작업 경로가 됩니다.
- `%UL` : TC가 생성하는 선택 파일 목록 경로 (list.txt 역할, UTF-8로 인코딩, 대상 파일리스트를 full-path로 담고 있음.) 
 
```
명령:    C:\python\python.exe
파라미터: C:\path\TCBP\tcbp.py Conv2PNG %UL
시작경로: (공란)
```

파라미터 포함 job에 파라미터를 전달하려면 다음과 같이 설정합니다.
```
파라미터: C:\path\TCBP\tcbp.py ResizeImages %UL size=1024
```

---
## 7. 테크니컬 노트 : Unicode 경로 처리 정책
일부 외부 도구(gm.exe 등)는 ANSI 빌드이므로, 시스템 코드 페이지(cp949) 범위를 벗어나는 문자(일본어 등)가 경로나 파일명에 포함되면 파일을 열지 못하는 경우가 있습니다. TCBP는 `subprocess.run(cwd=unicode_dir)`로 작업 디렉토리(cwd)로 지정하고, 도구의 인수에는 파일명만 상대 경로로 전달하는 방식을 사용합니다. 이를 통해 ANSI 경로명만 지원하는 프로그램을 상대로도 유니코드 경로명의 파일을 이상없이 우회처리할 수 있습니다. 
```
gm.exe convert -quality 95 "001.jpg" "001.png"
(cwd = X:\publisher\双葉社\)
```
- `CreateProcessW` 의 `lpCurrentDirectory` 파라미터로 전달되므로 Python에서 Unicode 디렉토리를 cwd로 설정 합니다.
- 도구가 `fopen("001.jpg")` 를 호출하면 OS가 내부적으로 `cwd + 파일명` 으로 해석합니다.

## 8. 테크니컬 노트 : TCBL → TCBP 이전 대응표
기존 TCBL 도구를 쓰던 분이 본 도구로 이전(migration)하고자 할 때, placeholder의 대응표입니다.

| TCBL | TCBP |
|---|---|
| `$f` | `{input}` |
| `$x` | `{base}` (output과 함께) |
| `$n` | `{name}` |
| `$e` | `{ext}` |
| `$p` | `{dir}` |
| `$i` | `{index}` |
| `$1`, `$2` | `{key}` (named param) |
| `pre=` | `pre = [...]` |
| `cmd=` | `commands = [...]` |
| `end=` | `post = [...]` |
| `batch_preset.ini [Section]` | `config.toml [jobs.JobName]` |

## 9. 테크니컬 노트 : `shell=True` / `shell=False` 차이와 내장 명령·외부 명령 기술 규칙

TCBP는 `pre` / `commands` / `post` 모든 명령을 **`shell=False`**로 `subprocess`를 실행합니다. 이 챕터는 그렇게 하는 이유와, `config.toml`에서 명령을 기술할 때 지켜야 할 규칙을 설명합니다.

### 9.1 `subprocess`가 프로세스를 띄우는 두 가지 방식

| 구분 | 실제로 실행되는 프로세스 | 명령 문자열의 운명 |
|---|---|---|
| `shell=True` | `cmd.exe` | `cmd.exe /c "전체 문자열"` 형태로 전달되어 **cmd.exe가 다시 파싱** |
| `shell=False` (tcbp 사용) | `args[0]`이 가리키는 프로그램 자체 | `CommandLineToArgvW`로 미리 분해한 인자 배열이 **그대로** 대상 프로그램에 전달 |

```python
# shell=True  →  CreateProcess("cmd.exe", '/c echo hello & del temp.txt')
subprocess.run("echo hello & del temp.txt", shell=True)

# shell=False →  CreateProcess("gm.exe", ["convert", "photo.jpg", "photo.png"])
subprocess.run(["gm.exe", "convert", "photo.jpg", "photo.png"], shell=False)
```

`shell=True`는 `cmd.exe`가 문자열을 한 번 더 해석하기 때문에:
- `&`, `|`, `>`, `<`, `^`, `%VAR%` 같은 **셸 메타문자를 cmd.exe가 해석**합니다. 파일명에 이런 문자가 섞이면 명령이 의도치 않게 쪼개지거나 리다이렉션으로 오인될 수 있습니다.
- 인용부호(`"`) 처리 규칙이 cmd.exe 고유 규칙을 따르므로, 유니코드 경로·공백·특수문자가 섞이면 따옴표를 어떻게 감싸야 안전한지가 미묘해집니다.
- 파일명 등 외부에서 들어온 문자열이 그대로 명령에 삽입되면 **명령 인젝션** 위험이 있습니다.

`shell=False`는 cmd.exe를 거치지 않으므로 위 문제가 원천적으로 사라지고, 7장에서 설명한 유니코드 경로 우회가 인자를 그대로 전달한다는 전제 위에서 안정적으로 동작합니다. 이것이 TCBP가 모든 명령을 `shell=False`로 통일한 이유입니다.

### 9.2 셸 커맨드 내장 명령을 사용하고 싶다면

`echo`, `del`, `copy`, `dir`, `cd`, `set` 등은 **실행 파일이 아니라 cmd.exe 내부에만 존재하는 내장 명령(builtin)** 입니다 (`echo.exe`, `del.exe` 같은 파일은 Windows에 없습니다). `shell=False`로 `"echo 안녕"`을 그대로 실행하면 OS가 `echo`라는 이름의 실행 파일을 찾으려 들지만, 그런 실행파일은 없으므로 `FileNotFoundError`를 내며 실패합니다. 

따라서 `config.toml`에서 셸 커맨드 내장 명령을 사용하고 싶다면 `cmd /c` 를 명시적으로 앞에 두어야 합니다. `cmd /c ...` 는 `args[0]`이 `cmd.exe`(실제 실행 파일)이므로 `shell=False`에서도 정상 동작하며, 내장 명령을 쓰고 싶다는 의도를 설정 파일 작성자가 명시적으로 표현해야 합니다. (단, 화면·로그에 문구만 출력하려는 목적이라면 `cmd /c echo` 대신 4.2.1절의 `{ msg = "..." }`를 쓰는 것을 권장합니다.)

```toml
commands = [
    "cmd /c echo \"출력할 문구\" ",
    "cmd /c copy {input} C:\\src.tmp",
]
```

## 10. 버전 이력
- **v1.0:** 초도 배포판
- **v1.1:** 멀티 프로세싱에서 먼저 끝나는 결과를 먼저 출력하도록 수정 (기존에는 뒤에 시작한 파일은 먼저 끝나도 앞 파일 결과 출력할 때까지 출력을 보류했음)
- **v1.2:** `output_rule` 키값을 `output`으로 이름 변경 (`{output}` placeholder와 일치성을 위해)
- **v1.3:** 출력이 길어서 한 줄에 다 나오지 못하는 경우, 파일명을 중간 생략하여 표시
- **v1.4:** `pre`/`post`가 `commands`와 동일하게 `shell=False` (CommandLineToArgvW 파싱)로 실행되도록 변경. `cmd.exe` 내장 명령은 예외 없이 `cmd /c`를 명시해야 하며(`config.toml` 전체 반영), pre/post 결과(STDOUT/STDERR)도 이제 로그 파일에 함께 기록됨. 그 결과 배너 등을 출력하기 위해 `cmd /c echo ----어쩌구저쩌구---` 로 명령을 추는 것을 너무 복잡해지므로, 메시지 출력용 `msg` 명령을 추가하였음.
- **v1.5:** {output}을 참조하면서 실제로는 파일을 안 만드는 명령이 '성공'으로 카운트되는 문제(조용한 실패)를 '실패'로 카운트하도록 수정
- **v1.6:** 멀티 스텝 명령에서 임시 파일이 필요할 때 파일명 충돌을 피하도록 `{taskid}`(배치 전체 공용) / `{itemid}`(파일 단위) placeholder 추가. 설명서 챕터7 Unicode 경로 처리 정책 설명을 실제 구현(상대 경로 모드)에 맞게 정리. 챕터9 테크니컬 노트 내용 정리.
- **v1.7:** 화면 표시 파일명 길이 계산에 `wcwidth`를 우선 사용하도록 개선(미설치 시 기존 방식으로 대체). `config.toml` 로드 직후 Job 정의를 자동 검증하는 기능 추가(TOML 문법 오류 메시지 개선, 필수 key 누락·예약어 오타·placeholder 오타·미사용 key 진단).
- **v1.8:** tcbp.py 자신이 출력하는 문구(오류·경고·로그·`--help`)를 한국어/영어 이중 언어로 지원. `--lang ko|en` 또는 `config.toml`의 `[global] lang`으로 선택 (기본값 `ko`). `config.toml`에 사용자가 작성한 내용(`desc`, `msg`)은 번역 대상에서 제외.
