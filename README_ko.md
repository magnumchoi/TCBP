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
- 외부 CLI 도구 뿐 아니라 단일 파일을 처리하는 Python 프로그램을 플러그인으로 추가하여 사용할 수 있습니다. (`bmp2png`, `mozjpeg`, `group_md5`, `remove_bom` 의 4개 플러그인을 기본 제공합니다.)
- recursive 처리 지원 - 특정 폴더 및 그 하위 폴더에 들어있는 파일을 처리할 수 있습니다.
- 파일 처리를 멀티스레드(MultiThread)화하여 여러 파일을 동시 처리할 수 있습니다. 이는  `MP3` 인코딩, `PNG` 인코딩 등 프로세싱 부하가 큰 작업에 유리합니다.
- 멀티스레드에 의해 파일이 비순차 처리되더라도, 화면 출력은 순차 출력을 유지합니다.
- 멀티 프로세싱시 중간 파일명이 프로세스간 충돌하지 않도록 UUID4 기반의 임시ID 생성을 하여 활용할 수 있습니다.
- `유니코드(Unicode)` 파일명, 경로명을 지원합니다. 외부 CLI 도구가 유니코드를 지원하지 않고 `ANSI` 코드만을 지원하더라도, 본 도구에서 자체적으로 경로명을 우회 처리하여 최종 출력으로 연결해 줍니다.
- 배치 실행전에 원하는 파라미터를 수동으로 입력받을 수 있습니다.
- 설정 파일이 포맷이 `INI`인 `TCBL`과 달리, 설정 파일 포맷이 `TOML`이어서 유니코드를 문제없이 처리합니다.

---

## 3. 프로그램 구성 및 사용법
### 3.1 요구사항
- Python 3.11 이상 (`tomllib` 내장)
- 외부 라이브러리 없이도 동작합니다(표준 라이브러리만 사용). 단, 아래는 선택 설치 시 자동으로 활용됩니다.
  - `pydantic`: Session/플러그인 메타정보의 타입을 엄격하게 검증하는 데 사용 (없으면 표준 dataclass 기반의 느슨한 검증으로 자동 대체 — 안내 메시지 출력, 5장 참고)
  - `keyboard`: `pause = true`일 때 "아무 키나 누르면 종료" 대기에 사용 (없으면 Enter 키 대기로 자동 대체)
  - `wcwidth`: 화면에 표시되는 파일명/메시지의 폭 계산에 사용 (없으면 근사치 계산으로 자동 대체)
- 개별 플러그인이 요구하는 패키지(예: MozJPEG의 `jpeglib`)는 별도입니다 — 자동 설치되지 않으며 수동 설치가 필요합니다 (5.7절 참고).
- Windows 환경 (Unicode 경로 완전 지원)
### 3.2 파일 구성
```filelist
tcbp.py             실행 엔진
validate_config.py  config.toml 사전 검증 도구 (4.11절 참고)
config.toml         작업 정의 파일 (기본값)
plugin/              플러그인 폴더 (5장 참고)
logs/                실행 로그 폴더 (log=true 시 자동 생성, 실행마다 파일 분리)
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

목록 파일 대신 **폴더 경로를 직접** 넘겨 그 폴더 안의 파일들을 자동으로 찾아 처리하게 할 수도 있습니다 — 4.12절(폴더 입력 모드) 참고.

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
log_file     = "logs/tcbp_{job}_{timestamp}.log"  # 로그 파일 경로 ({job}/{timestamp} 자리표시자 지원)
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

### 4.2.2 파라미터 preset — 선택 UI
`params` 항목에 `preset`(라벨+값 목록)을 선언하면, 자유 입력 대신 방향키로 값을 고르는 선택 UI가 자동으로 뜹니다. 외부 패키지(questionary 등) 없이 ANSI 이스케이프 + 키보드 입력만으로 구현되어 있습니다.

```toml
params = [{
    key="ch_bitrate", desc="음질(비트레이트)", type="int", default=128,
    preset=[
        { label="128kbps", value=64 },
        { label="192kbps", value=96 },
        { label="256kbps", value=128 },
        { label="320kbps", value=160 },
    ],
}]
```

**조작법 (실제 콘솔 실행 시)**
- ↑/↓ 방향키로 항목 이동, `Enter`로 확정합니다.
- 현재 선택된 항목은 `>> Label명` 접두사와 함께 ANSI 반전 색상으로 표시됩니다.
- `default`에 해당하는 항목이 초기 선택 상태입니다. 아무 키도 누르지 않고 바로 `Enter`를 누르면 `default`가 그대로 확정됩니다.
- `Esc`를 누르면 현재 작업 전체가 취소되고, 취소 메시지와 함께 종료됩니다.

**`default` 규칙**
- `default`는 반드시 `preset`의 `value` 목록 안에 있어야 하며(값·타입 모두 일치), 그렇지 않으면 설정 오류로 즉시 종료됩니다.
- `default`를 아예 생략하면 오류가 아니라, `preset` 목록의 **첫 번째 항목**을 초기 선택값으로 사용합니다.
- `preset`의 각 `value` 타입은 해당 파라미터의 `type`(`int`/`bool`/생략=문자열)과 일치해야 합니다.

**CLI 값과의 관계**
- CLI로 `key=value`가 이미 전달된 파라미터는 대화형 질문을 건너뜁니다.
- 단, `preset`이 있는 파라미터에 CLI 값이 들어오면 `preset` 범위 안에 있는지는 그대로 검증합니다 — 범위 밖 값이면 오류로 종료됩니다.
- `preset`이 없고 `default`만 있는 파라미터는 기존처럼 자유 입력이지만, 프롬프트에 `default`가 미리 채워진 채로 시작해 `Enter`만 눌러도 그 값이 확정됩니다(실제 콘솔 실행 시). `default`도 없으면 100% 기존 동작 그대로입니다.

**TTY/ANSI 미지원 환경 (파이프/리다이렉트 등)**
콘솔이 아니어서 방향키 UI를 쓸 수 없는 환경에서는 번호를 입력하는 방식으로 자동 폴백합니다.
```
    >> [1] 128kbps
       [2] 192kbps
       [3] 256kbps
       [4] 320kbps
  번호 선택 (Enter=기본값 3, c=취소):
```
`Enter`만 누르면 기본값(`>>` 표시된 항목)이 그대로 확정되고, `c`를 입력하면 취소됩니다.

**실행 직전 최종 확인**
`params`가 선언된 Job이라도, 필요한 값이 모두 CLI `key=value`로 주어졌다면 아무 화면도 추가되지 않습니다(완전한 하위호환). 하나라도 사용자가 직접 입력(preset 선택 포함)해야 했던 경우에만, 실제 실행 직전에 최종 파라미터 요약과 진행/취소 선택 화면이 나타납니다.

**값과 라벨이 달라 헛갈리는 문제 완화**
`preset`의 `value`가 사용자에게 익숙한 숫자와 다를 수 있습니다(예: `ch_bitrate`는 채널당 전송율이라 "128kbps"를 고르면 실제 값은 64). 이런 경우 아래 두 가지를 함께 쓰는 것을 권장합니다.
1. **라벨 문구에 실제 값을 명시** — `label="128kbps (64kbps/ch)"`처럼 실제 저장되는 값의 의미를 라벨 자체에 적어둡니다.
2. **`{key}_label` placeholder 활용** — `preset`이 선언된 파라미터마다 `{key}_label`(사용자가 고른 라벨 텍스트)이 자동 생성되어 `pre`/`post`/`commands`의 `{ msg = "..." }`에서 쓸 수 있습니다.
   ```toml
   { msg = "   Bitrate : {ch_bitrate_label} -> {ch_bitrate} kbps/channel" },
   ```
   또한 실행 직전 최종 확인 화면에도 `preset`으로 선택된 파라미터는 값과 함께 고른 라벨이 자동으로 병기됩니다: `ch_bitrate = 64  (선택: 128kbps (64kbps/ch))`.

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
log_file = "logs/tcbp_{job}_{timestamp}.log"
```
- `log = false`: 콘솔 출력만
- `log = true`: 콘솔 + 파일 동시 기록
- `log_file` 경로가 상대경로면 항상 **tcbp.py 와 같은 폴더** 기준으로 생성됩니다. (실행 위치 무관)
- `log_file`에 `{job}`(작업 이름), `{timestamp}`(실행 시각, `YYYYMMDD_HHMMSS`) 자리표시자를 사용할 수 있어, 실행할 때마다 별도 파일로 분리되고 한 파일에 계속 쌓이지 않습니다.
- 콘솔은 기존처럼 메시지만 표시하고(레벨 프리픽스 없음), 파일에는 `%(asctime)s [%(levelname)s] %(message)s` 형식으로 타임스탬프와 레벨이 함께 기록됩니다.
- 별도의 실패 전용 로그 파일(`*_failed.log`)은 만들지 않으며, 같은 로그 파일 안에서 `[ERROR]` 레벨로 실패 건만 걸러볼 수 있습니다.
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

### 4.11 설정 파일 검증

#### 4.11.1 tcbp.py 자체의 최소 방어
tcbp.py는 Job을 resolve한 직후, `tool`/`output`/`commands` 중 하나라도 비어 있으면 즉시 중단합니다. 이는 오탈자를 진단하는 기능이 아니라, 빈 `{tool}`처럼 config 작성 실수가 알아보기 힘든 실행 오류(예: Windows에 실제로 존재하는 `convert.exe` 같은 엉뚱한 시스템 실행파일이 대신 실행되는 등)로 번지는 것을 막기 위한 최소한의 안전장치입니다.

#### 4.11.2 사전 검증 도구 — `validate_config.py`
오탈자·미사용 key·undefined placeholder처럼 config 작성을 도와주는 진단은 별도 도구인 `validate_config.py`가 전담합니다. tcbp.py가 실행 중에 자동으로 호출하지 않으므로, `config.toml`을 고친 뒤 batch를 돌리기 전에 수동으로(또는 CI에서) 실행하는 것을 권장합니다.

```commandline
python validate_config.py <config.toml> [--job JOB] [--sample <filelist>] [--lang ko|en]
```

검사 항목:
- **TOML 문법 오류** — 오류 라인·컬럼과 원문 코드 프레임을 함께 보여줍니다.
- **필수 key 누락** — `tool`, `output`, `commands` 중 실제로 비어있는 항목.
- **예약어 오타** — `tool_pat`처럼 표준 key와 철자가 비슷한 key.
- **placeholder 오타** — 어디에서도 채워지지 않는 `{placeholder}`. 비슷한 이름의 실제 placeholder가 있으면 제안.
- **미사용 커스텀 key** — job에 정의했지만 어디에서도 `{key}` 형태로 쓰이지 않는 값.
- **`global.tools` 경로 유효성** — 등록된 tool 실행 파일이 실제로 존재하는지 전체 스윕.
- **output이 input을 덮어쓸 위험** — output 템플릿이 input과 같은 파일을 가리킬 수 있는 경우 경고.
- **타입 오탈자** — `params`의 `type`이 `"int"`가 아닌 값, `parallel`/`log`/`pause`/`stderr_quiet`/`recursive`가 bool이 아닌 값, `input_mode`가 `"list"`/`"directory"`가 아닌 값, `include`가 문자열 리스트가 아닌 경우 등.
- **폴더 입력 모드 설정 오용** — `input_mode = "directory"`가 아닌 Job에 `recursive`/`include`가 설정된 경우 경고 (4.12절 참고).
- **sample dry-run 검증** (`--sample` 지정 시) — 실제 파일 목록으로 placeholder 치환을 시험해, 실행 전에 포맷 오류를 잡아냅니다.

`--job`을 생략하면 `config.toml`에 정의된 모든 Job을 한 번에 검사합니다. 오류(ERROR)가 하나라도 있으면 종료 코드 1을 반환하므로 CI나 배치 스크립트의 게이트로 사용할 수 있고, 경고(WARNING)·정보(INFO)만 있으면 종료 코드 0입니다.

예시 출력:
```
--- global ---
[WARNING] Tool 경로를 찾을 수 없습니다: gm -> C:/tools/gm.exe

--- ResizeImage ---
[ERROR] 필수 Key 누락: tool (또는 global.tools 에 등록된 tool 이름이 필요합니다)
[WARNING] 알 수 없는 Key: tool_pat
        혹시 다음을 의미하셨습니까? tool
[WARNING] 정의되지 않은 Placeholder: {basename}
        혹시: {name}
[INFO] 사용되지 않는 Key: quality

Job 1개 검증 — 총 오류 1개  총 경고 2개  총 정보 1개
```

### 4.12 폴더(디렉토리) 입력 모드

FileList 인자 자리에 목록 파일(list.txt) 대신 **폴더 경로를 직접** 넘겨, 그 폴더(선택적으로 하위 폴더까지) 안의 파일들을 TCBP가 알아서 찾아 처리하게 할 수 있습니다.

```toml
[jobs.Bmp2PngRecursive]
plugin      = "bmp2png"
input_mode  = "directory"   # 이 Job은 폴더 경로만 받는다 — list.txt를 주면 오류
recursive   = true          # 하위 폴더까지 탐색
include     = ["*.bmp"]     # 글롭 패턴 (생략 시 모든 파일)
output      = "{dir}/{base}.png"
```

```commandline
python tcbp.py Bmp2PngRecursive D:\Images
```

| 키 | 기본값 | 설명 |
|---|---|---|
| `input_mode` | `"list"` | `"list"`: FileList 인자는 목록 파일이어야 함 (기존 방식). `"directory"`: FileList 인자는 폴더여야 함. |
| `recursive` | `false` | `input_mode = "directory"`일 때만 의미 있음. `true`면 하위 폴더까지 재귀 탐색. |
| `include` | `[]` (전체) | `input_mode = "directory"`일 때만 의미 있음. 글롭 패턴 목록 (예: `["*.bmp"]`, `["*.jpg", "*.jpeg"]`). 여러 패턴에 매치되는 파일도 중복 없이 한 번만 포함됩니다. |

세 키 모두 `[global]` 섹션에서 기본값을 지정하고 job에서 override할 수 있습니다 (다른 설정과 동일한 상속 규칙).

**계약(contract) — `input_mode`와 실제 인자가 어긋나면 에러**: `input_mode`는 "이 Job에 어떤 종류의 FileList 인자가 와야 하는지"를 미리 선언하는 계약입니다. 실제로 넘어온 인자가 이 계약과 다르면(예: `input_mode="directory"`인데 목록 파일이 넘어옴, 또는 그 반대로 `input_mode` 기본값(`"list"`)인 Job에 폴더가 넘어옴) TCBP는 파일을 처리하지 않고 그 자리에서 명확한 에러로 즉시 중단합니다.

Total Commander와 연동하는 방법(특히 `%P` 사용 시 주의사항)은 7.1절을 참고하세요.

---

## 5. 플러그인(Plugin) 시스템

### 5.1 개요 — `tool` vs `plugin`
외부 CLI 도구를 감싸는 `tool = "..."` 방식 대신, 파일 처리 로직을 파이썬 함수로 직접 작성해 Job에 연결할 수도 있습니다. 하나의 Job 안에서 `tool`과 `plugin`을 동시에 쓸 수는 없습니다.

| | `tool = "..."` | `plugin = "..."` |
|---|---|---|
| 처리 로직 | 외부 CLI 실행 파일 (`subprocess`) | `./plugin/<이름>.py`의 파이썬 함수 |
| 대상 | GraphicsMagick, oxipng 등 기존 실행 파일 | 파이썬으로 직접 구현하는 처리 |
| `commands` 키 | 필수 | 사용 안 함 (있으면 경고) |

플러그인의 API 사양(`FileSession`/`BatchSession`/`ExecResult`/`BatchResult`, `session.log()` 등)과 새 플러그인을 직접 작성하는 방법은 `plugin/plugin_guide_ko.md`(플러그인 제작 가이드)에서 상세히 다룹니다 — 이 장은 번들 플러그인을 **사용**하는 방법에 집중합니다.

### 5.2 세션 타입 — FileSession / BatchSession
| | FileSession | BatchSession |
|---|---|---|
| 처리 단위 | 파일 1개 | 파일 목록 전체 |
| `parallel` | 지원 (`max_workers`만큼 동시 처리) | 무시 (항상 순차) |
| `output` | 필수 | 생략 가능 (또는 `output = ""`) |
| `run()` 반환 타입 | `ExecResult(success, message)` | `BatchResult(succeeded, failed)` |
| 대표 예 | RemoveBOM, MozJPEG, bmp2png | GroupMD5 |

### 5.3 config.toml에서 플러그인 Job 선언
```toml
[jobs.RemoveBOM]
plugin                  = "remove_bom"     # ./plugin/remove_bom.py 로드
output                  = "{dir}/{base}{ext}"
allow_output_overwrite  = true             # output이 input을 덮어써도 되는 Job은 명시적으로 허용해야 함
params = [
    { key="backup", desc="원본을 .bak으로 백업", type="bool" },
]
```
BatchSession Job은 `output`을 생략(또는 `output = ""`)할 수 있습니다 — GroupMD5처럼 파일 그룹 단위로 결과를 쓰는 경우입니다.

### 5.4 번들 플러그인
| Job 이름 | 세션 타입 | 설명 | 주요 params |
|---|---|---|---|
| `RemoveBOM` | FileSession | 텍스트 파일의 UTF-8 BOM 제거 | `backup`, `eachline` (bool) |
| `MozJPEG` | FileSession | MozJPEG으로 JPEG 재압축/변환 | `quality` (int, 1-100) |
| `bmp2png` | FileSession | BMP → 최적화된 PNG 변환 (oxipng) | `delete` (bool) |
| `GroupMD5` | BatchSession | 파일명 유사도로 그룹핑해 그룹별 MD5(`.md5`) 목록 생성 | `bom` (bool), `chunk_size` (int, MB) |

```commandline
python tcbp.py RemoveBOM list.txt backup=true
python tcbp.py MozJPEG   list.txt quality=90
python tcbp.py bmp2png   list.txt delete=true
python tcbp.py GroupMD5  list.txt bom=false chunk_size=8
```

### 5.5 플러그인 단독 CLI
모든 플러그인은 tcbp 없이 파일 1개(GroupMD5는 목록 파일 1개)를 처리하는 단독 CLI 진입점을 갖습니다 — 플러그인 개발/디버깅용이며, 와일드카드·재귀 탐색·목록 파일을 이용한 배치 처리는 지원하지 않습니다.
```commandline
python plugin\remove_bom.py <input> <output> [backup=true] [eachline=true]
python plugin\mozjpeg.py    <input> <output> [quality=90]
python plugin\bmp2png.py    <input> <output> [delete=true] [oxipng_exe=...]
python plugin\group_md5.py  <list_file> [bom=true] [chunk_size=8]
```

### 5.6 `--strict` 플래그
FileSession 플러그인이 병렬(`parallel = true`) 모드에서 선언된 slot 개수(`notes_per_file`)를 벗어나 `log()`를 호출하면, 기본값은 콘솔 출력만 건너뛰고 로그 파일에 경고를 남기며, `--strict`를 지정하면 즉시 오류로 중단합니다.

동작 원리와 플러그인 개발 시 권장 사용법은 `plugin/plugin_guide_ko.md`의 5.3~5.4절(병렬 모드 slot 예약 메커니즘 / `--strict` 플래그)을 참고하세요.

### 5.7 플러그인 의존성
플러그인이 필요로 하는 외부 패키지는 tcbp가 **자동 설치하지 않으므로**, 아래 표를 참고해 수동으로 `pip install`하세요.

| 플러그인 | 필요 패키지 |
|---|---|
| `remove_bom` | 없음 (표준 라이브러리만) |
| `mozjpeg` | `jpeglib`, `numpy`, `Pillow` |
| `bmp2png` | `opencv-python`, `Pillow`, `numpy` |
| `group_md5` | 없음 (표준 라이브러리만) |

의존성 선언 방식과 `validate_config.py`가 이를 어떻게 다루는지는 `plugin/plugin_guide_ko.md`의 4.5절을 참고하세요.

---

## 6. 새 Job 추가 방법
1. `config.toml`에 `[jobs.NewJobName]` 섹션 추가
2. `tool`, `output`, `commands` 정의
3. 파라미터가 필요하면 `{param_name}` 형태로 commands에 기술
4. 실행 시 `key=value` 형태로 전달
5. (권장) `python validate_config.py config.toml --job NewJobName` 으로 사전 점검 후 실제 배치 실행 (4.11절 참고)
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

## 7. Total Commander 연동
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

### 7.1 폴더(디렉토리) 입력 Job 연동 — 토탈커맨더에서 `%P` 사용 시 주의사항

⚠️주의: `input_mode = "directory"`로 선언된 Job(목록 파일 대신 폴더 자체를 입력받아 재귀 탐색하는 Job)을 TC 버튼에 연결할 때는, 선택한 파일 목록(`%UL`) 대신 현재 패널의 폴더 경로를 넘겨주는 `%P` 매크로**를 사용합니다. 이 때 **반드시 닫는 따옴표 바로 앞에 마침표(`.`)를 하나 추가해서 사용해야 합니다.**

```
파라미터: C:\path\TCBP\tcbp.py Bmp2PngRecursive "%P."
```

**해설**: `%P`는 관례상 경로 끝에 백슬래시(`\`)가 붙어서 치환됩니다 (예: `D:\Images\`). 이 상태로 Parameters 필드에 `"%P"`처럼 단순히 따옴표로만 감싸면, Windows 커맨드라인 인자 파싱 규칙상 **닫는 따옴표 바로 앞의 백슬래시가 그 따옴표를 이스케이프**해버려 인자가 의도한 위치에서 끝나지 않습니다. 그 결과 뒤에 와야 할 Job 이름이나 다른 파라미터까지 한 인자에 뒤섞여 들어가거나, 예상치 못한 오류가 발생할 수 있습니다. 이를 박기 위해 마침표(trailing dot)를 하나 찍어서 이스케이프를 회피할 수 있습니다. `"%P."`로 마침표를 찍게 되면 치환되는 경로명은 `D:\Images\.`가 되며, 이는 `D:\Images\`와 동일한 폴더를 가리키는 유효한 경로가 됩니다.

| 작성 방식 | 결과 |
|---|---|
| `%P` (따옴표 없음) | ❌ 폴더 경로에 공백이 있으면 인자가 여러 개로 쪼개짐 |
| `"%P"` (마침표 없이 따옴표만) | ❌ 트레일링 백슬래시가 닫는 따옴표를 이스케이프해 인자가 깨짐 |
| `"%P."` (마침표 추가) | ✅ 정상 동작 |

### 7.2 폴더(디렉토리) 입력 모드의 파일 리스트 생성 방식

**정렬 로직**: 폴더 스캔 결과는 항상 이름순으로 정렬되어, 파일시스템이 반환하는 순서에 실행마다 좌우되지 않고 `{index}` placeholder나 병렬 모드의 화면 출력 순서가 재현 가능합니다. `recursive = true`일 때는 단순히 전체 경로 문자열을 한 번에 정렬하지 않고, **"폴더 자신의 파일을 먼저(이름순), 그다음 하위 폴더를 이름순으로(각 하위 폴더에도 같은 규칙을 재귀 적용)"** 순서로 처리합니다.

만일 이렇게 하지 않고 절대경로 문자열 전체를 그대로 정렬하면, 하위 폴더 이름이 숫자일 때(예: `001`)일 때 현재 폴더내의 숫자 이름의 파일(예: `009.bmp`)과 비교되어 순서가 뒤섞일 수 있습니다. 루트에 `001/`, `009.bmp`~`012.bmp`가 있으면 `"001\013.bmp"`의 세 번째 글자 `1`이 `"009.bmp"`의 세 번째 글자 `9`보다 작아 `001` 폴더의 내용 전체가 루트의 `009.bmp`~`012.bmp`보다 먼저 오는 식으로, 현재 폴더 자신의 파일이 하위 폴더 사이에 끼어들어 직관에 어긋나는 결과가 나올 수 있습니다.

**기존 기능과의 관계**: 폴더 입력은 내부적으로 (list.txt와 동일한) 파일 목록으로 변환된 뒤 기존 처리 엔진에 그대로 전달됩니다. 즉 tool 기반 Job, FileSession/BatchSession 플러그인, `parallel` 병렬 처리, placeholder 치환, 로깅 등 다른 모든 기능은 수정 없이 그대로 동작합니다.

---
## 8. 테크니컬 노트 : Unicode 경로 처리 정책
일부 외부 도구(gm.exe 등)는 ANSI 빌드이므로, 시스템 코드 페이지(cp949) 범위를 벗어나는 문자(일본어 등)가 경로나 파일명에 포함되면 파일을 열지 못하는 경우가 있습니다. TCBP는 `subprocess.run(cwd=unicode_dir)`로 작업 디렉토리(cwd)로 지정하고, 도구의 인수에는 파일명만 상대 경로로 전달하는 방식을 사용합니다. 이를 통해 ANSI 경로명만 지원하는 프로그램을 상대로도 유니코드 경로명의 파일을 이상없이 우회처리합니다.
```
gm.exe convert -quality 95 "001.jpg" "001.png"
(cwd = X:\publisher\双葉社\)
```
- `CreateProcessW` 의 `lpCurrentDirectory` 파라미터로 전달되므로 Python에서 Unicode 디렉토리를 cwd로 설정 합니다.
- 도구가 `fopen("001.jpg")` 를 호출하면 OS가 내부적으로 `cwd + 파일명` 으로 해석합니다.

## 9. 테크니컬 노트 : TCBL → TCBP 이전 대응표
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

## 10. 테크니컬 노트 : `shell=True` / `shell=False` 차이와 내장 명령·외부 명령 기술 규칙

TCBP는 `pre` / `commands` / `post` 모든 명령을 **`shell=False`**로 `subprocess`를 실행합니다. 이 챕터는 그렇게 하는 이유와, `config.toml`에서 명령을 기술할 때 지켜야 할 규칙을 설명합니다.

### 10.1 `subprocess`가 프로세스를 띄우는 두 가지 방식

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

`shell=False`는 cmd.exe를 거치지 않으므로 위 문제가 원천적으로 사라지고, 8장에서 설명한 유니코드 경로 우회가 인자를 그대로 전달한다는 전제 위에서 안정적으로 동작합니다. 이것이 TCBP가 모든 명령을 `shell=False`로 통일한 이유입니다.

### 10.2 셸 커맨드 내장 명령을 사용하고 싶다면

`echo`, `del`, `copy`, `dir`, `cd`, `set` 등은 **실행 파일이 아니라 cmd.exe 내부에만 존재하는 내장 명령(builtin)** 입니다 (`echo.exe`, `del.exe` 같은 파일은 Windows에 없습니다). `shell=False`로 `"echo 안녕"`을 그대로 실행하면 OS가 `echo`라는 이름의 실행 파일을 찾으려 들지만, 그런 실행파일은 없으므로 `FileNotFoundError`를 내며 실패합니다. 

따라서 `config.toml`에서 셸 커맨드 내장 명령을 사용하고 싶다면 `cmd /c` 를 명시적으로 앞에 두어야 합니다. `cmd /c ...` 는 `args[0]`이 `cmd.exe`(실제 실행 파일)이므로 `shell=False`에서도 정상 동작하며, 내장 명령을 쓰고 싶다는 의도를 설정 파일 작성자가 명시적으로 표현해야 합니다. (단, 화면·로그에 문구만 출력하려는 목적이라면 `cmd /c echo` 대신 4.2.1절의 `{ msg = "..." }`를 쓰는 것을 권장합니다.)

```toml
commands = [
    "cmd /c echo \"출력할 문구\" ",
    "cmd /c copy {input} C:\\src.tmp",
]
```

## 11. 테크니컬 노트 : Placeholder `{key.label}` / `{key.value}` 문법 설탕
4.2.2절에서 설명한 것처럼, `preset`이 있는 파라미터는 실제로 저장되는 값(`value`)과 사용자가 고른 라벨(`label`)이 다를 수 있습니다(예: `ch_bitrate`는 채널당 전송율이라 "128kbps"를 고르면 실제 값은 64). 이 값·라벨 쌍을 `pre`/`post`/`commands`의 `{ msg = "..." }`에서 함께 보여줄 때 쓰라고 `{key}_label`이라는 placeholder를 자동 생성해두었지만, 그 이름만 봐서는 `{key}`로부터 파생된 것인지 알아보기 어렵다는 문제가 있었습니다. 이를 보완하기 위해 `{key.label}` / `{key.value}` 표기를 추가로 지원합니다 — 관계가 표기 자체에서 드러나도록 한 것입니다.

**중요: 이건 Python의 진짜 객체 속성 접근이 아닙니다.** Python `str.format()`의 `"{name.attr}"` 문법은 실제로 `context[name]`이라는 객체를 먼저 찾은 뒤, 그 객체에 대해 `getattr(obj, "attr")`을 수행합니다. `{ch_bitrate.label}`을 이 방식 그대로 지원하려면 `context["ch_bitrate"]`에 들어가는 값 자체를 `.label` 속성을 가진 `int`/`str` 서브클래스로 감싸야 하는데, **`bool`은 파이썬에서 서브클래싱이 금지**되어 있어(`TypeError: type 'bool' is not an acceptable base type`) `type="bool"`인 preset 파라미터를 이 방식으로는 지원할 수 없습니다.

그래서 `tcbp.py`의 [substitute()](tcbp.py)는 실제 속성 접근 프로토콜을 쓰는 대신, `str.format_map()`을 호출하기 **전에** 정규식으로 텍스트를 먼저 바꿔치기합니다 ([_expand_dot_sugar()](tcbp.py)):
- `{key.label}` → context에 `key_label`이 있으면 `{key_label}`로, 없으면 `{{key.label}}`(이스케이프된 리터럴)로 치환
- `{key.value}` → context에 `key`가 있으면 `{key}`로, 없으면 마찬가지로 이스케이프된 리터럴로 치환

context 안의 실제 값 타입(`int`/`bool`/`str`)은 전혀 건드리지 않고, 순수 텍스트 전처리 계층 하나만 얹는 방식이라 `bool` 문제 자체가 발생하지 않습니다.

**못 찾았을 때 이스케이프가 필요한 이유** — 처음 구현에서는 매칭되는 값이 없으면 그냥 원본 텍스트 `"{key.label}"`을 그대로 두려고 했지만, 그러면 뒤이어 실행되는 `format_map()`이 이 문자열을 또다시 진짜 `"{name.attr}"` 속성 접근으로 파싱해버립니다. 만약 `key`는 context에 있지만(예: `size`) 그 값에 `.label` 속성이 없다면(예: 평범한 `int`), `AttributeError: 'int' object has no attribute 'label'`로 전체 치환이 죽어버립니다. 이를 막기 위해 못 찾은 경우 `{{key.label}}`처럼 중괄호를 이스케이프해 `format_map()`에게는 순수 텍스트로만 보이게 만들고, 최종 출력에서는 `{key.label}`이 리터럴 그대로 남습니다 — [SafeDict](tcbp.py)의 "정의되지 않은 placeholder는 원문 유지" 철학과 동일한 결과를 안전하게 재현한 것입니다.

**적용 범위**
- `.label`/`.value` 두 가지 속성만 지원하는 좁은 규칙이며, 임의의 속성 접근을 지원하는 범용 템플릿 엔진이 아닙니다.
- 기존에 문서화된 flat 이름(`{key}_label`)도 내부 구현 그대로 남아 있어 계속 유효합니다 — 완전한 하위호환.
- `validate_config.py`의 미정의 placeholder 검사기(`_extract_placeholders`)는 원래부터 `.`/`[...]` 뒤를 잘라내고 베이스 이름만 검사하므로, `{ch_bitrate.label}` 표기도 별도 수정 없이 `ch_bitrate`(이미 선언된 파라미터)로 인식되어 오탐이 나지 않습니다.

## 12. 버전 이력
- **v1.0:** 초도 배포판
- **v1.1:** 멀티 프로세싱에서 먼저 끝나는 결과를 먼저 출력하도록 수정 (기존에는 뒤에 시작한 파일은 먼저 끝나도 앞 파일 결과 출력할 때까지 출력을 보류했음)
- **v1.2:** `output_rule` 키값을 `output`으로 이름 변경 (`{output}` placeholder와 일치성을 위해)
- **v1.3:** 출력이 길어서 한 줄에 다 나오지 못하는 경우, 파일명을 중간 생략하여 표시
- **v1.4:** `pre`/`post`가 `commands`와 동일하게 `shell=False` (CommandLineToArgvW 파싱)로 실행되도록 변경. `cmd.exe` 내장 명령은 예외 없이 `cmd /c`를 명시해야 하며(`config.toml` 전체 반영), pre/post 결과(STDOUT/STDERR)도 이제 로그 파일에 함께 기록됨. 그 결과 배너 등을 출력하기 위해 `cmd /c echo ----어쩌구저쩌구---` 로 명령을 추는 것을 너무 복잡해지므로, 메시지 출력용 `msg` 명령을 추가하였음.
- **v1.5:** {output}을 참조하면서 실제로는 파일을 안 만드는 명령이 '성공'으로 카운트되는 문제(조용한 실패)를 '실패'로 카운트하도록 수정
- **v1.6:** 멀티 스텝 명령에서 임시 파일이 필요할 때 파일명 충돌을 피하도록 `{taskid}`(배치 전체 공용) / `{itemid}`(파일 단위) placeholder 추가. 설명서 챕터8 Unicode 경로 처리 정책 설명을 실제 구현(상대 경로 모드)에 맞게 정리. 챕터10 테크니컬 노트 내용 정리.
- **v1.7:** 화면 표시 파일명 길이 계산에 `wcwidth`를 우선 사용하도록 개선(미설치 시 기존 방식으로 대체). `config.toml` 로드 직후 Job 정의를 자동 검증하는 기능 추가(TOML 문법 오류 메시지 개선, 필수 key 누락·예약어 오타·placeholder 오타·미사용 key 진단).
- **v1.8:** tcbp.py 자신이 출력하는 문구(오류·경고·로그·`--help`)를 한국어/영어 이중 언어로 지원. 실행시 옵션을 `--lang ko` 또는 `--lang en`로 지정하거나, `config.toml`의 `[global] lang`으로 선택 (기본값 `ko`). `config.toml`에 사용자가 작성한 내용(`desc`, `msg`)은 번역 대상에서 제외.
- **v1.9:** 섹션 구분 주석 추가 및 일부 함수 위치 재배치 (코드 수정은 없음)
- **v2.0:** 클래스 리팩토링, config.toml 설정파일 검증용 도구인 validate_config.py 신규 작성
- **v2.1:** 작업별 로그 분리
- **v2.2:** 플러그인(Plugin) 시스템 추가 — 외부 CLI 도구 대신 파이썬 함수로 파일을 처리하는 `plugin = "..."` Job 타입. FileSession(파일 1개, 병렬 가능)/BatchSession(파일 그룹, 항상 순차) 두 세션 타입, `--strict` 플래그(slot 초과 시 경고 대신 즉시 중단), 번들 플러그인 4종(RemoveBOM/MozJPEG/bmp2png/GroupMD5) 추가. Session/플러그인 메타정보 타입 검증에 `pydantic`을 선택적으로 사용(미설치 시 표준 dataclass 폴백). `tests/` pytest 스위트 추가.
- **v2.3:** 폴더(디렉토리) 입력 모드 추가 — `input_mode = "directory"` Job은 FileList 인자로 목록 파일 대신 폴더 경로를 받아, `recursive`(하위 폴더 탐색)와 `include`(글롭 패턴 필터) 설정에 따라 파일 목록을 자동 생성한다.
- **v2.4:** thread_safe 메타 정보를 플러그인에 추가, 플러그인 측에서는 호출시의 스레드 모드를 재확인, validate_config.py에도 검증루틴 추가. 디자인 가이드라인 보완.
- **v2.41:** 번들 플러그인 group_md5의 그룹핑 알고리즘 개선 (플러그인 버전 v1.0 -> v1.1)
- **v2.5:** `params` 항목에 `preset`(라벨+값 목록) 선언을 추가
  - 자유 입력 대신 방향키로 값을 고르는 선택 UI를 questionary 없이 ANSI + 키보드 입력만으로 제공(4.2.2절).
  - `default`가 preset 값 목록 밖이면 설정 오류, CLI 값도 preset 범위를 그대로 검증. 
  - TTY/ANSI 미지원 환경은 번호 선택으로 자동 폴백
  - 사용자가 값을 직접 입력해야 했던 경우에만 실행 직전 최종 파라미터 확인 화면 표시(CLI로 전부 채워진 기존 Job은 동작 무변화)
  - preset의 값과 사용자가 고른 라벨이 달라 헛갈리는 문제를 완화하기 위해, 최종 확인 화면에 고른 라벨을 값과 함께 병기하고 placeholder에 `{key.label}`와 `{key.value}`의 placeholder를 사용하여 `pre`/`post` 메시지 등에서 쓸 수 있게 함
