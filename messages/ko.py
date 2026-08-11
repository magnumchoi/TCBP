"""
[ko] i18n 메시지 카탈로그 — 한국어 (기준 언어)
[en] i18n message catalog — Korean (the reference language)
"""

MESSAGES: dict[str, str] = {
    # [ko] CLI 도움말
    # [en] CLI help messages
    "cli_description":       "Total Commander Batch Python - TOML 기반 배치 처리 엔진",
    "cli_epilog_header":     "예시:",
    "help_job":              "실행할 Job 이름",
    "help_filelist":         "입력 파일 목록 텍스트 파일 (input_mode=\"directory\" Job은 대신 폴더 경로)",
    "help_params":           "Named 파라미터",
    "help_config":           "설정 파일 경로 (기본: tcbp.py와 같은 폴더의 config.toml)",
    "help_dry_run":          "명령 출력만 하고 실행 안 함",
    "help_strict":           "FileSession 플러그인의 log() slot 초과 시 경고 대신 즉시 예외로 중단 (플러그인 개발/검증용)",
    "help_lang":             "출력 언어 (ko/en). 기본값은 config.toml의 global.lang, 없으면 ko",

    # [ko] 일반 오류 및 경고
    # [en] general error and warning messages
    "err_need_integer":      "  [오류] 정수를 입력하세요.",
    "err_need_bool":         "  [오류] true/false/1/0/yes/no/on/off 중 하나를 입력하세요.",
    "err_tool_and_plugin_both": "[오류] Job '{job}': tool과 plugin을 동시에 지정할 수 없습니다.",
    "err_param_type_mismatch": "[오류] 파라미터 '{param}' 타입 불일치 (type=\"{type}\" 기대, 값={value!r})",
    "warn_param_format":     "[경고] 파라미터 형식 오류 (무시됨)",
    "warn_param_format_hint": "key=value 형식 필요",

    # [ko] 플러그인 관련 오류
    # [en] plugin-related error messages
    "err_plugin_not_found":  "[오류] 플러그인 '{name}'을(를) 찾을 수 없습니다: {path}",
    "err_plugin_import_failed": "[오류] 플러그인 '{name}' import 실패: {error}",
    "err_plugin_no_run":     "[오류] 플러그인 '{name}'에 run() 함수가 없습니다.",
    "err_plugin_invalid_metadata": "[오류] 플러그인 '{name}'의 run()에 @plugin(...) 메타정보가 없거나 유효하지 않습니다.",
    "err_plugin_contract_version_invalid": "[오류] 플러그인 '{name}'의 contract_version 형식이 올바르지 않습니다: {value!r} (\"MAJOR.MINOR\" 형식이어야 함, 예: \"1.0\")",
    "err_plugin_contract_major_mismatch": "[오류] 플러그인 '{name}'은(는) 계약 버전 {declared}를 대상으로 작성됐지만, 현재 TCBP의 플러그인 계약 버전은 {current}입니다 (호환 불가 — major 버전 불일치).",
    "err_plugin_contract_minor_ahead": "[오류] 플러그인 '{name}'은(는) 계약 버전 {declared}를 대상으로 작성됐지만, 현재 TCBP의 플러그인 계약 버전은 {current}입니다 (이 TCBP 버전이 아직 지원하지 않는 계약 기능을 요구함).",
    "err_plugin_not_thread_safe_parallel": "[오류] Job '{job}': 플러그인 '{name}'은(는) thread_safe=False로 선언되어 있어 parallel=true와 함께 쓸 수 없습니다. config.toml에서 parallel=false로 바꾸거나 max_workers=1로 순차 처리하세요.",

    # [ko] TOML 파서 오류
    # [en] TOML parser error messages
    "toml_syntax_error":     "[오류] {name} 문법 오류",
    "toml_reason_overwrite_value":        "이미 값이 정의된 키를 다시 정의했습니다.",
    "toml_reason_declare_twice":          "키 '{name}' 를 두 번 선언했습니다.",
    "toml_reason_immutable_namespace":    "'{name}' 테이블은 이미 확정되어 더 이상 수정할 수 없습니다.",
    "toml_reason_redefine_namespace":     "'{name}' 테이블을 다시 정의했습니다.",
    "toml_reason_expected_equals":        "키 뒤에 '=' 가 필요합니다.",
    "toml_reason_expected_close_table":   "테이블 선언을 닫는 ']' 가 필요합니다.",
    "toml_reason_expected_close_array_table": "배열 테이블 선언을 닫는 ']]' 가 필요합니다.",
    "toml_reason_expected_token":         "'{token}' 이(가) 필요합니다.",
    "toml_reason_invalid_key_start":      "키의 시작 문자가 올바르지 않습니다.",
    "toml_reason_invalid_statement":      "올바르지 않은 구문입니다.",
    "toml_reason_invalid_value":          "값 형식이 올바르지 않습니다. 문자열은 큰따옴표로 감싸고, 숫자/불리언/배열/테이블 형식을 확인하세요.",
    "toml_reason_invalid_datetime":       "날짜/시간 형식이 올바르지 않습니다.",
    "toml_reason_invalid_hex":            "16진수 이스케이프 값이 올바르지 않습니다.",
    "toml_reason_unclosed_array":         "배열이 닫히지 않았습니다. 항목 뒤 콤마(,) 또는 닫는 ']' 를 확인하세요.",
    "toml_reason_unclosed_inline_table":  "인라인 테이블이 닫히지 않았습니다. 닫는 '}' 를 확인하세요.",
    "toml_reason_unterminated_string":    "문자열을 닫는 따옴표가 없습니다.",
    "toml_reason_unescaped_backslash":    "문자열 안의 '\\' 는 이스케이프 처리가 필요합니다.",
    "toml_reason_invalid_unicode_escape": "이스케이프된 문자가 올바른 유니코드 문자가 아닙니다.",
    "toml_reason_duplicate_inline_key":   "인라인 테이블 키 '{table_key}' 가 중복되었습니다.",
    "toml_reason_invalid_character":      "허용되지 않는 문자 '{char}' 가 있습니다.",
    "toml_reason_illegal_character":      "허용되지 않는 문자 '{char}' 가 있습니다.",

    # [ko] 실행 및 입력 관련 메시지
    # [en] runtime and input-related messages
    "err_config_not_found":  "[오류] 설정 파일 없음",
    "err_job_not_found":     "[오류] Job '{job}' 없음.",
    "label_available_jobs":  "사용 가능한 Job",
    "none_placeholder":      "(없음)",
    "err_filelist_not_found": "[오류] 파일 목록 없음",
    "warn_file_missing":     "[경고] 파일 없음 (건너뜀)",
    "err_no_files":          "[오류] 처리할 파일이 없습니다.",
    "err_directory_not_found": "[오류] 폴더를 찾을 수 없음",
    "err_input_mode_expects_directory": "[오류] Job '{job}'는 input_mode=\"directory\"로 선언되었는데, 전달된 경로가 폴더가 아닙니다",
    "err_input_mode_expects_list":      "[오류] Job '{job}'는 input_mode=\"list\"(기본값)인데, 전달된 경로가 폴더입니다 — 폴더를 입력하려면 config.toml에 input_mode = \"directory\"를 설정하세요",
    "warn_tool_not_found":   "Tool 경로를 찾을 수 없습니다",
    "err_on_error_stop_cancel": "on_error=stop: 나머지 작업 취소 중...",
    "err_exception":         "예외 발생",
    "err_on_error_stop_abort": "on_error=stop: 처리 중단",
    "info_job_summary":      "완료 — 성공: {success}  실패: {failed}  전체: {total}",
    "err_output_not_created": "출력 파일 미생성 (tool이 exit 0으로 실패)",
    "prompt_error_pause":    "\n--- 오류 발생. Enter 키를 누르면 종료합니다. ---",
    "info_dry_run_mode":     "[DRY-RUN 모드] 명령 출력만 수행하고 실제 실행하지 않습니다.",
    "info_file_count":       "파일 {count}개  |  {mode}",
    "prompt_press_any_key":  "\n아무 키나 누르면 종료합니다...",
    "label_processing":      "처리 중...",
    "err_preset_value_type_mismatch": "[오류] Job '{job}' 파라미터 '{param}'의 preset 값 '{label}'={value!r}가 선언된 type=\"{type}\"과 일치하지 않습니다.",
    "err_preset_default_not_in_preset": "[오류] Job '{job}' 파라미터 '{param}'의 default 값 {default!r}가 preset 값 목록에 없습니다.",
    "err_preset_value_not_allowed": "[오류] 파라미터 '{param}'에 전달된 값 '{value}'는 preset 범위를 벗어났습니다. 허용된 값: {allowed}",
    "info_cancelled_by_user": "취소되었습니다.",
    "label_final_param_summary": "\n--- 최종 파라미터 확인 ---",
    "label_confirm_prompt":  "이대로 진행할까요?",
    "label_proceed":         "진행",
    "label_cancel":          "취소",
    "label_selected_as":     "선택: {label}",
    "hint_select_fallback":  "번호 선택 (Enter=기본값 {default}, c=취소): ",
    "err_invalid_choice":    "  [오류] 목록에 있는 번호를 입력하세요.",
    "info_pydantic_missing":  "[INFO] pydantic이 설치되지 않았습니다. pip install pydantic 으로 설치하면 더 엄격한 타입 검증을 받을 수 있습니다.",
    "info_pydantic_fallback": "[INFO] pydantic 없이 표준 dataclass 기반 폴백으로 계속 진행합니다.",

    # [ko] validate_config.py 자신의 문구 (vc_ 접두사) — tcbp.py의 help_job/cli_description 등과
    #      이름이 겹치는 것들은 vc_ 를 붙여 구분한다.
    # [en] validate_config.py's own strings (vc_ prefix) — the ones whose bare name would
    #      collide with tcbp.py's own keys (help_job/cli_description/etc.) are prefixed with vc_.
    "vc_cli_description":   "config.toml 검증 도구 (tcbp.py 실행 전 사전 점검용)",
    "vc_cli_epilog_header": "예시:",
    "vc_help_config":       "검증할 config.toml 경로",
    "vc_help_job":          "검증할 Job 이름 (생략 시 전체 Job 검증)",
    "vc_help_sample":       "dry-run 검증에 사용할 샘플 파일 목록 텍스트 파일",
    "vc_help_lang":         "출력 언어 (ko/en)",
    "vc_err_no_jobs":       "[ERROR] config에 정의된 Job이 없습니다.",
    "vc_undefined_placeholder": "정의되지 않은 Placeholder",
    "vc_suggestion_maybe":     "혹시",
    "vc_unknown_key":          "알 수 없는 Key",
    "vc_did_you_mean":         "혹시 다음을 의미하셨습니까?",
    "vc_unused_key":           "사용되지 않는 Key",
    "vc_no_tools_registered":  "global.tools 에 등록된 tool이 없습니다",
    "vc_tool_path_empty":      "Tool 경로가 비어 있습니다",
    "vc_tool_path_missing":    "Tool 경로를 찾을 수 없습니다",
    "vc_unknown_param_type":   "알 수 없는 param type (\"int\"/\"bool\" 또는 생략만 허용)",
    "vc_type_mismatch":        "타입 불일치: {label} ({expected} 기대, {got} 발견)",
    "vc_bad_enum_value":       "허용되지 않는 값",
    "vc_output_overwrites_input": "output이 input과 같은 파일을 가리킬 수 있습니다 (덮어쓰기 위험)",
    "vc_output_overwrites_input_ext": "output이 input과 같은 파일을 가리킬 수 있습니다 (입력 확장자가 \"{ext}\"인 경우 덮어쓰기 위험 — output이 그 확장자를 고정으로 강제함)",
    "vc_sample_error":         "Sample dry-run 오류",
    "vc_tool_and_plugin_both": "tool과 plugin을 동시에 지정할 수 없습니다",
    "vc_batch_parallel_ignored": "BatchSession 플러그인은 parallel 처리를 지원하지 않습니다 (parallel=true는 무시됨)",
    "vc_recursive_include_ignored": "recursive/include는 input_mode=\"directory\"인 Job에서만 적용됩니다 (무시됨)",
    "vc_plugin_not_thread_safe_parallel": "플러그인 '{name}'은(는) thread_safe=False로 선언되어 있어 parallel=true(+max_workers>1)와 함께 쓸 수 없습니다",
    "vc_summary_line":  "Job {jobs}개 검증 — 총 오류 {errors}개  총 경고 {warnings}개  총 정보 {infos}개",
}
