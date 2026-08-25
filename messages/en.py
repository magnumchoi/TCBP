"""
[ko] i18n 메시지 카탈로그 — 영어
[en] i18n message catalog — English
"""

MESSAGES: dict[str, str] = {
    # [ko] CLI 도움말
    # [en] CLI help messages
    "cli_description":       "Total Commander Batch Python - a generic TOML-based batch processing engine",
    "cli_epilog_header":     "Examples:",
    "help_job":              "Name of the Job to run",
    "help_filelist":         "Text file listing the input files (or a folder path, for input_mode=\"directory\" Jobs)",
    "help_params":           "Named parameters",
    "help_config":           "Config file path (default: config.toml next to tcbp.py)",
    "help_dry_run":          "Print commands only; don't execute them",
    "help_strict":           "FileSession plugins: abort immediately on log() slot overflow instead of warning (for plugin dev/testing)",
    "help_lang":             "Output language (ko/en). Defaults to config.toml's global.lang, or ko if unset",

    # [ko] 일반 오류 및 경고
    # [en] general error and warning messages
    "err_need_integer":      "  [ERROR] Please enter an integer.",
    "err_need_bool":         "  [ERROR] Please enter one of: true/false/1/0/yes/no/on/off.",
    "err_tool_and_plugin_both": "[ERROR] Job '{job}': tool and plugin cannot both be set.",
    "err_param_type_mismatch": "[ERROR] Param '{param}' type mismatch (expected type=\"{type}\", value={value!r})",
    "warn_param_format":     "[WARNING] Invalid parameter format (ignored)",
    "warn_param_format_hint": "expected key=value format",

    # [ko] 플러그인 관련 오류
    # [en] plugin-related error messages
    "err_plugin_invalid_name": "[ERROR] Plugin name '{name}' contains invalid characters (only letters, digits, '_' and '-' are allowed).",
    "err_plugin_not_found":  "[ERROR] Plugin '{name}' not found: {path}",
    "err_plugin_import_failed": "[ERROR] Failed to import plugin '{name}': {error}",
    "err_plugin_no_run":     "[ERROR] Plugin '{name}' has no run() function.",
    "err_plugin_invalid_metadata": "[ERROR] Plugin '{name}''s run() is missing valid @plugin(...) metadata.",
    "err_plugin_contract_version_invalid": "[ERROR] Plugin '{name}''s contract_version has an invalid format: {value!r} (expected \"MAJOR.MINOR\", e.g. \"1.0\")",
    "err_plugin_contract_major_mismatch": "[ERROR] Plugin '{name}' targets contract version {declared}, but TCBP's current plugin contract version is {current} (incompatible — major version mismatch).",
    "err_plugin_contract_minor_ahead": "[ERROR] Plugin '{name}' targets contract version {declared}, but TCBP's current plugin contract version is {current} (this TCBP version doesn't yet support a contract feature the plugin requires).",
    "err_plugin_not_thread_safe_parallel": "[ERROR] Job '{job}': plugin '{name}' is declared thread_safe=False and cannot be used with parallel=true. Set parallel=false in config.toml, or use max_workers=1 for sequential processing.",

    # [ko] TOML 파서 오류
    # [en] TOML parser error messages
    "toml_syntax_error":     "[ERROR] {name} syntax error",
    "toml_reason_overwrite_value":        "This key's value has already been defined and cannot be redefined.",
    "toml_reason_declare_twice":          "Key '{name}' was declared twice.",
    "toml_reason_immutable_namespace":    "Table '{name}' is already finalized and can no longer be modified.",
    "toml_reason_redefine_namespace":     "Table '{name}' was redefined.",
    "toml_reason_expected_equals":        "An '=' is required after the key.",
    "toml_reason_expected_close_table":   "A closing ']' is required to end the table declaration.",
    "toml_reason_expected_close_array_table": "A closing ']]' is required to end the array-of-tables declaration.",
    "toml_reason_expected_token":         "'{token}' is required.",
    "toml_reason_invalid_key_start":      "The key starts with an invalid character.",
    "toml_reason_invalid_statement":      "Invalid statement.",
    "toml_reason_invalid_value":          "The value has an invalid format. Wrap strings in double quotes, and check the number/boolean/array/table syntax.",
    "toml_reason_invalid_datetime":       "Invalid date/datetime format.",
    "toml_reason_invalid_hex":            "Invalid hexadecimal escape value.",
    "toml_reason_unclosed_array":         "The array was never closed. Check for a comma (,) after the item or a closing ']'.",
    "toml_reason_unclosed_inline_table":  "The inline table was never closed. Check for a closing '}'.",
    "toml_reason_unterminated_string":    "The string is missing its closing quote.",
    "toml_reason_unescaped_backslash":    "A '\\' inside a string must be escaped.",
    "toml_reason_invalid_unicode_escape": "The escaped character is not a valid Unicode scalar value.",
    "toml_reason_duplicate_inline_key":   "Inline table key '{table_key}' is duplicated.",
    "toml_reason_invalid_character":      "Contains a disallowed character '{char}'.",
    "toml_reason_illegal_character":      "Contains a disallowed character '{char}'.",

    # [ko] 실행 및 입력 관련 메시지
    # [en] runtime and input-related messages
    "err_config_not_found":  "[ERROR] Config file not found",
    "err_job_not_found":     "[ERROR] Job '{job}' not found.",
    "label_available_jobs":  "Available Jobs",
    "none_placeholder":      "(none)",
    "err_filelist_not_found": "[ERROR] File list not found",
    "warn_file_missing":     "[WARNING] File not found (skipped)",
    "err_no_files":          "[ERROR] No files to process.",
    "err_directory_not_found": "[ERROR] Directory not found",
    "err_input_mode_expects_directory": "[ERROR] Job '{job}' is declared with input_mode=\"directory\", but the path given is not a directory",
    "err_input_mode_expects_list":      "[ERROR] Job '{job}' has input_mode=\"list\" (the default), but the path given is a directory — set input_mode = \"directory\" in config.toml to accept a folder",
    "warn_tool_not_found":   "Tool path not found",
    "warn_output_overwrites_input": "output resolves to the same path as input — the original file will be overwritten: {path}",
    "err_on_error_stop_cancel": "on_error=stop: cancelling remaining tasks...",
    "err_exception":         "Exception occurred",
    "err_on_error_stop_abort": "on_error=stop: processing aborted",
    "info_job_summary":      "Done — success: {success}  failed: {failed}  total: {total}",
    "err_output_not_created": "Output file was not created (tool exited 0 but actually failed)",
    "prompt_error_pause":    "\n--- An error occurred. Press Enter to exit. ---",
    "info_dry_run_mode":     "[DRY-RUN mode] Printing commands only; nothing will actually run.",
    "info_file_count":       "{count} file(s)  |  {mode}",
    "prompt_press_any_key":  "\nPress any key to exit...",
    "label_processing":      "Processing...",
    "err_preset_value_type_mismatch": "[ERROR] Job '{job}' param '{param}' preset value '{label}'={value!r} does not match the declared type=\"{type}\".",
    "err_preset_default_not_in_preset": "[ERROR] Job '{job}' param '{param}' default value {default!r} is not among its preset values.",
    "err_preset_value_not_allowed": "[ERROR] Value '{value}' given for param '{param}' is outside its preset range. Allowed values: {allowed}",
    "info_cancelled_by_user": "Cancelled.",
    "label_final_param_summary": "\n--- Final Parameter Summary ---",
    "label_confirm_prompt":  "Proceed with these settings?",
    "label_proceed":         "Proceed",
    "label_cancel":          "Cancel",
    "label_selected_as":     "selected: {label}",
    "hint_select_fallback":  "Select number (Enter=default {default}, c=cancel): ",
    "err_invalid_choice":    "  [ERROR] Please enter a number from the list.",
    "info_pydantic_missing":  "[INFO] pydantic is not installed. Install it with pip install pydantic for stricter type validation.",
    "info_pydantic_fallback": "[INFO] Continuing without pydantic, falling back to standard dataclasses.",

    # [ko] validate_config.py 자신의 문구 (vc_ 접두사) — tcbp.py의 help_job/cli_description 등과
    #      이름이 겹치는 것들은 vc_ 를 붙여 구분한다.
    # [en] validate_config.py's own strings (vc_ prefix) — the ones whose bare name would
    #      collide with tcbp.py's own keys (help_job/cli_description/etc.) are prefixed with vc_.
    "vc_cli_description":   "config.toml validator (pre-flight check before running tcbp.py)",
    "vc_cli_epilog_header": "Examples:",
    "vc_help_config":       "Path to the config.toml to validate",
    "vc_help_job":          "Job to validate (validates all Jobs if omitted)",
    "vc_help_sample":       "Sample file-list text file to use for dry-run checks",
    "vc_help_lang":         "Output language (ko/en)",
    "vc_err_no_jobs":       "[ERROR] No Jobs defined in this config.",
    "vc_undefined_placeholder": "Undefined placeholder",
    "vc_suggestion_maybe":     "Did you mean",
    "vc_unknown_key":          "Unknown key",
    "vc_did_you_mean":         "Did you mean:",
    "vc_unused_key":           "Unused key",
    "vc_no_tools_registered":  "No tools registered in global.tools",
    "vc_tool_path_empty":      "Tool path is empty",
    "vc_tool_path_missing":    "Tool path not found",
    "vc_unknown_param_type":   "Unknown param type (only \"int\"/\"bool\" or omitted is recognized)",
    "vc_type_mismatch":        "Type mismatch: {label} (expected {expected}, got {got})",
    "vc_bad_enum_value":       "Disallowed value",
    "vc_output_overwrites_input": "output may resolve to the same file as input (overwrite risk)",
    "vc_output_overwrites_input_ext": "output may resolve to the same file as input (overwrite risk when the input extension is \"{ext}\" — output forces that fixed extension)",
    "vc_sample_error":         "Sample dry-run error",
    "vc_tool_and_plugin_both": "tool and plugin cannot both be set",
    "vc_batch_parallel_ignored": "BatchSession plugins do not support parallel processing (parallel=true is ignored)",
    "vc_recursive_include_ignored": "recursive/include only apply to Jobs with input_mode=\"directory\" (ignored)",
    "vc_plugin_not_thread_safe_parallel": "Plugin '{name}' is declared thread_safe=False and cannot be used with parallel=true (+max_workers>1)",
    "vc_summary_line":  "Validated {jobs} job(s) — {errors} error(s), {warnings} warning(s), {infos} info",
}
