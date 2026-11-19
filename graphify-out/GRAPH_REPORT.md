# Graph Report - recording-stability-src  (2026-11-19)

## Corpus Check
- 181 files · ~261,050 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 109 file(s) not represented in the graph (top: .ttf 54, .csv 46, .css 3)
- WARNING: 109 of 325 files seen (34%) have no supported extractor and are missing from this graph entirely. It may look complete while representing only part of the codebase.

## Summary
- 2884 nodes · 5782 edges · 163 communities (137 shown, 26 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 312 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `6f7ababb`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- App.tsx
- ShadcnInstaller
- re
- gray
- slide_search_core.py
- Tailwind CSS Utility Reference
- worker.py
- core.py
- validate_data.py
- Canvas Design System
- validate-tokens.cjs
- Fullstack Tech Stack Guide
- Form & Input Components
- Tailwind CSS Responsive Design
- 全欄位清單
- search_stack
- design_system.py
- html-token-validator.py
- search
- Component Specifications
- shadcn/ui Accessibility Patterns
- analyze_multi_mic.py
- TestTailwindConfigGenerator
- UI Styling Skill
- States and Variants
- json
- Codebase Design
- Design System
- Tailwind CSS Customization
- spacing
- During the session
- read_rows
- yy
- _style_is_dark_primary
- fetch-background.py
- shadcn/ui Theming & Customization
- format_ascii_box
- color
- detect_domain
- app.py
- Color Semantics
- TailwindConfigGenerator
- DesignSystemGenerator
- UI/UX Pro Max - Design Intelligence
- Fullstack Architecture Patterns
- Tooling, Workflows & Quality Bar
- test_core.py
- fontSize
- Fullstack Development Workflows
- Diagnosing Bugs
- _palette_is_dark
- CatalogRefreshTest
- Tailwind Integration
- radius
- authorize
- Token Architecture
- sys
- index-BOGSLSpr.js
- Test-Driven Development
- .test_node_check_parses_generated_config
- Pre-Delivery Checklist (canonical — the only one)
- Quick Reference
- Primitive Tokens
- card
- Senior Fullstack
- compilerOptions
- Component Tokens
- Zr
- duration
- CNC Acoustic Lab｜PostgreSQL 全新資料庫建立規格 V1.2
- Ml
- 七、EARS 實機第一次測試（2026-11-16，只接 EARS）
- Process
- d0
- l0
- create_app
- 貼給 Codex 的完整指令｜CNC Acoustic Lab 建立全新 SQL 資料庫
- Frontend Design
- primitive
- generate-slide.py
- register_audio
- test_schema.py
- j0
- interface
- record_usb.py
- _filter_anti_patterns_for_mode
- fr
- i0
- y
- _select_palette_for_mode
- json
- TestStackFlagWithDesignSystem
- offline.py
- RtlCliTest
- interface
- interface
- Ys
- read_rows
- _search_csv_detailed
- interface
- hitl-loop.template.sh
- interface
- Database Patterns
- test_ears_umik.py
- package.json
- design-tokens-starter.json
- interface
- publish
- 系統與 PostgreSQL 設計
- test_synthetic.py
- button
- _load_csv
- CNC Acoustic Lab 開發與版本管理
- 2026-11-10 更新 v1：分析模型上線、收音設定紀錄、同步嗶聲
- 2026-11-12 更新 v3：離線分析工具（不經過網站資料庫）
- Deployment Platforms
- csv
- $type
- 2026-11-11 更新 v2：雲端只寫入、地端計算（分析工作佇列）
- input
- Testing Strategies
- Git Workflows
- Monitoring and Observability
- Databases
- Backend Frameworks
- CNC Acoustic Lab
- 系統依賴與資料關聯
- AGENTS.md
- template-analysis.md
- schema.md
- 50
- test_catalog_summary_line_endings.py
- Authentication Solutions
- analysis/ — 多手機錄音分析模型（v1）
- 800
- 地端分析 worker：雲端只寫入，地端計算，資料表溝通
- V1.5 三支實體手機驗收
- $type
- radius
- 既有 V1.4 驗證紀錄
- V1.5 驗證紀錄
- CNC Acoustic Lab V1.5
- padding-y
- white
- destructive
- destructive-foreground
- muted
- primary-foreground
- ring
- secondary-foreground
- split_values

## God Nodes (most connected - your core abstractions)
1. `yy()` - 389 edges
2. `y()` - 61 edges
3. `TailwindConfigGenerator` - 60 edges
4. `search()` - 54 edges
5. `i0()` - 54 edges
6. `TestTailwindConfigGenerator` - 41 edges
7. `create_app()` - 39 edges
8. `DesignSystemGenerator` - 38 edges
9. `search_stack()` - 36 edges
10. `ShadcnInstaller` - 34 edges

## Surprising Connections (you probably didn't know these)
- `尚未由 SQL 自動保證的條件（正式蒐集前必測）` --references--> `recording()`  [INFERRED]
  CNC_Acoustic_Lab_DB_v1_2/README.md → backend/audio.py
- `二、改了什麼` --references--> `jobs()`  [INFERRED]
  docs/updates/2026-11-11-analysis-worker-v2.md → analysis/tests/test_worker.py
- ``analysis_runs` — 每次前處理／特徵／融合／推論執行紀錄` --references--> `code_commit()`  [INFERRED]
  CNC_Acoustic_Lab_DB_v1_2/04_data_dictionary.md → analysis/worker.py
- `資料表（migration 004）` --references--> `code_commit()`  [INFERRED]
  docs/analysis-worker.md → analysis/worker.py
- `開錄前 API 檢查` --references--> `recording()`  [INFERRED]
  CNC_Acoustic_Lab_DB_v1_2/08_api_contract.md → backend/audio.py

## Import Cycles
- None detected.

## Communities (163 total, 26 thin omitted)

### Community 0 - "App.tsx"
Cohesion: 0.05
Nodes (53): react@^19.2.0, alignmentLabel(), AlignmentVerdict, AnalysisJob, hasActiveJob(), jobLabel(), api(), ApiError (+45 more)

### Community 1 - "ShadcnInstaller"
Cohesion: 0.05
Nodes (3): main(), ShadcnInstaller, TestShadcnInstaller

### Community 2 - "re"
Cohesion: 0.14
Nodes (11): analyze_dependencies(), analyze_documentation(), analyze_project(), analyze_security(), analyze_test_coverage(), calculate_complexity(), count_lines(), generate_recommendations() (+3 more)

### Community 3 - "gray"
Cohesion: 0.11
Nodes (19): $type, $value, $type, $value, $type, $value, $type, $value (+11 more)

### Community 4 - "slide_search_core.py"
Cohesion: 0.08
Nodes (17): format_context(), format_result(), main(), BM25, calculate_pattern_break(), detect_domain(), get_background_config(), get_color_for_emotion() (+9 more)

### Community 5 - "Tailwind CSS Utility Reference"
Cohesion: 0.05
Nodes (43): Arbitrary Values, Aspect Ratio, Background Colors, Border Color, Border Radius, Border Style, Border Width, Borders (+35 more)

### Community 6 - "worker.py"
Cohesion: 0.06
Nodes (40): test_verdict_same_clock_rules(), fresh_db(), jobs(), seed_session(), synthetic_webm(), test_completion_trigger_enqueues_exactly_once(), test_corrupt_chunk_is_retried_then_failed_without_results(), test_expired_lease_at_attempt_limit_becomes_failed() (+32 more)

### Community 7 - "core.py"
Cohesion: 0.07
Nodes (20): _contains_phrase(), _exact_match_diagnostic(), _exact_row_identity(), _exact_stack_identifier(), _legacy_successor_guidance(), _normalize(), _normalize_rtl_level(), _passes_threshold() (+12 more)

### Community 8 - "validate_data.py"
Cohesion: 0.10
Nodes (35): _catalog_date(), _check_app_interface_contract(), _check_catalog_contract(), _check_catalog_summary(), _check_chart_contract(), _check_color_contract(), _check_core_data_contract(), _check_file() (+27 more)

### Community 9 - "Canvas Design System"
Cohesion: 0.06
Nodes (35): 1. Visual Communication First, 2. Minimal Text Integration, 3. Expert Craftsmanship, 4. Systematic Patterns, Analog Meditation, Approach, Canvas Boundaries, Canvas Design System (+27 more)

### Community 10 - "validate-tokens.cjs"
Cohesion: 0.08
Nodes (28): args, fs, minimal, MINIMAL_TOKENS, path, projectRoot, tokensPath, wrapStyle (+20 more)

### Community 11 - "Fullstack Tech Stack Guide"
Cohesion: 0.12
Nodes (17): Comparison Matrix, Drizzle, Enterprise Application, Frontend Frameworks, Fullstack Tech Stack Guide, Internal Tool, Next.js, ORMs and Query Builders (+9 more)

### Community 12 - "Form & Input Components"
Cohesion: 0.06
Nodes (32): Accordion, Alert, Alert Dialog, Avatar, Badge, Button, Card, Checkbox (+24 more)

### Community 13 - "Tailwind CSS Responsive Design"
Cohesion: 0.06
Nodes (32): 1. Mobile-First Design, 2. Consistent Breakpoint Usage, 3. Test at Breakpoint Boundaries, 4. Use Container for Content Width, 5. Progressive Enhancement, 6. Avoid Too Many Breakpoints, Best Practices, Breakpoint System (+24 more)

### Community 14 - "全欄位清單"
Cohesion: 0.06
Nodes (31): `analysis_artifacts` — 大容量衍生音訊、FFT／STFT 圖檔位置與雜湊, `app_users` — 研究人員與系統管理者, `audio_assets` — 封存三通道無損音檔及其雜湊, `audio_chunks` — 錄音中寫入 SQL 的三通道 PCM 區塊, `audio_quality_checks` — 音訊完整性與品質檢查, `capture_devices` — 多通道音訊介面和錄音主機, `channel_features` — 各聲道各視窗的聲學數值特徵, CNC Acoustic Lab｜完整 SQL 資料字典 V1.2 (+23 more)

### Community 15 - "search_stack"
Cohesion: 0.09
Nodes (6): search_stack(), TestDiagnosticsContracts, _rows(), TestNativeDesktopStackFreshness, _rows(), TestWebStackFreshness

### Community 16 - "design_system.py"
Cohesion: 0.10
Nodes (9): _detect_page_type(), format_page_override_md(), generate_design_system(), _generate_intelligent_overrides(), persist_design_system(), safe_slug(), _write_persisted_file(), format_output() (+1 more)

### Community 17 - "html-token-validator.py"
Cohesion: 0.12
Nodes (12): get_context(), is_allowed_exception(), is_allowed_rgba(), is_inside_block(), load_css_variables(), main(), print_result(), print_summary() (+4 more)

### Community 18 - "search"
Cohesion: 0.08
Nodes (6): search(), TestSearchDomains, TestImeGuidance, RtlFilterTest, TestStyleTaxonomy, TestTextLayoutRetrieval

### Community 19 - "Component Specifications"
Cohesion: 0.07
Nodes (28): Alert, Anatomy, Anatomy, Anatomy, Anatomy, Anatomy, Badge, Button (+20 more)

### Community 20 - "shadcn/ui Accessibility Patterns"
Cohesion: 0.07
Nodes (28): Accordion, Alert, ARIA Labels, Checkbox and Radio, Color Contrast, Command Palette Navigation, Component-Specific Patterns, Dialog/Modal Navigation (+20 more)

### Community 21 - "analyze_multi_mic.py"
Cohesion: 0.15
Nodes (17): apply_offset(), apply_offset_drift(), coarse_chirp(), coarse_envelope(), codec_cutoff(), db(), fine_offset(), frac_shift() (+9 more)

### Community 23 - "UI Styling Skill"
Cohesion: 0.08
Nodes (25): Accessibility Patterns, Alternative: Tailwind-Only Setup, Best Practices, Common Patterns, Component Layer: shadcn/ui, Component Library Guide, Component + Styling Setup, Core Stack (+17 more)

### Community 24 - "States and Variants"
Cohesion: 0.08
Nodes (24): Accessibility, Accessibility Requirements, ARIA States, Color Contrast, Color Variants, Disabled States, Error Messages, Error States (+16 more)

### Community 25 - "json"
Cohesion: 0.21
Nodes (6): create_project(), get_file_content(), get_next_steps(), list_templates(), main(), print_result()

### Community 26 - "Codebase Design"
Cohesion: 0.09
Nodes (21): 1. In-process, 2. Local-substitutable, 3. Remote but owned (Ports & Adapters), 4. True external (Mock), Deepening, Dependency categories, Seam discipline, Testing strategy: replace, don't layer (+13 more)

### Community 27 - "Design System"
Cohesion: 0.08
Nodes (23): Best Practices, Chart.js Integration, Command, Component Spec Pattern, Contextual Decision Flow, Decision System CSVs, Design System, Integration (+15 more)

### Community 28 - "Tailwind CSS Customization"
Cohesion: 0.09
Nodes (22): @apply Directive, Best Practices, Color Customization, Complete Tailwind Config, Configuration Examples, Content Configuration, Custom Color Palette, Custom Font Sizes (+14 more)

### Community 29 - "spacing"
Cohesion: 0.06
Nodes (34): $type, $value, $type, $value, $type, $value, $type, $value (+26 more)

### Community 30 - "During the session"
Cohesion: 0.09
Nodes (19): ADR Format, Numbering, Optional sections, Template, What qualifies, When to offer an ADR, GLOSSARY.md Format, Rules (+11 more)

### Community 31 - "read_rows"
Cohesion: 0.11
Nodes (5): _resolve_dial(), read_rows(), TestGeneratedCatalogContract, TestLandingAndStackContract, TestReasoningContract

### Community 32 - "yy"
Cohesion: 0.06
Nodes (64): yy(), ah(), ao(), au(), av(), B0(), bd(), be() (+56 more)

### Community 33 - "_style_is_dark_primary"
Cohesion: 0.21
Nodes (4): _query_wants_dark(), _resolve_color_mode(), _style_is_dark_primary(), TestModeResolution

### Community 34 - "fetch-background.py"
Cohesion: 0.15
Nodes (9): generate_css_for_background(), get_background_image(), get_curated_images(), get_overlay_css(), get_pexels_search_url(), load_backgrounds_config(), load_brand_colors(), main() (+1 more)

### Community 35 - "shadcn/ui Theming & Customization"
Cohesion: 0.10
Nodes (19): Base Color Presets, Best Practices, Color Customization, Color Format, Component Customization, CSS Variable System, Customize Styles, Customize Variants (+11 more)

### Community 36 - "format_ascii_box"
Cohesion: 0.13
Nodes (9): ansi_ljust(), format_ascii_box(), add_wrapped(), wrap_text(), format_markdown(), hex_to_ansi(), _mode_support_labels(), section_header() (+1 more)

### Community 37 - "color"
Cohesion: 0.11
Nodes (19): $type, $value, background, foreground, muted-foreground, primary, primary-hover, secondary (+11 more)

### Community 38 - "detect_domain"
Cohesion: 0.18
Nodes (5): detect_domain(), _domain_keywords(), _file_signature(), _get_bm25(), TestDomainDetection

### Community 39 - "app.py"
Cohesion: 0.12
Nodes (5): Person, Database, CatalogItem, Conditions, Finish

### Community 40 - "Color Semantics"
Cohesion: 0.11
Nodes (17): Accent, Applying Semantic Tokens, Background & Foreground, Border & Ring, Color Semantics, Dark Mode Overrides, Destructive, Interactive States (+9 more)

### Community 43 - "UI/UX Pro Max - Design Intelligence"
Cohesion: 0.11
Nodes (17): Before Delivering App UI, Example Workflow, If a search returns 0 results, Output Formats, Query Contract, Rule Categories by Priority, Running the search tool, Step 1: Analyze User Requirements (+9 more)

### Community 44 - "Fullstack Architecture Patterns"
Cohesion: 0.12
Nodes (17): API Design Patterns, Authentication Architecture, Backend Architecture, Cache Layers, Caching Strategies, Clean Architecture, Component Architecture, Decision Matrix (+9 more)

### Community 45 - "Tooling, Workflows & Quality Bar"
Cohesion: 0.12
Nodes (16): Code Quality Analyzer, code_quality_analyzer.py, Common Issues, Project Scaffolder, project_scaffolder.py, Quick Reference, Stack Decision Matrix, Success Criteria (+8 more)

### Community 47 - "fontSize"
Cohesion: 0.11
Nodes (20): $type, $value, $type, $value, $type, $value, $type, $value (+12 more)

### Community 48 - "Fullstack Development Workflows"
Cohesion: 0.11
Nodes (18): Blue-Green Deployment, Canary Deployment, CI/CD Pipelines, Code Review Process, Daily Workflow, Database Migrations in CI, Deployment Strategies, Docker Compose Development Environment (+10 more)

### Community 50 - "Diagnosing Bugs"
Cohesion: 0.13
Nodes (14): Completion criterion: a tight loop that goes red, Diagnosing Bugs, Minimise, Non-deterministic bugs, Phase 1: Build a feedback loop, Phase 2: Reproduce + minimise, Phase 3: Hypothesise, Phase 4: Instrument (+6 more)

### Community 51 - "_palette_is_dark"
Cohesion: 0.18
Nodes (4): _palette_is_dark(), _relative_luminance(), TestEndToEndCoherence, TestLuminance

### Community 53 - "Tailwind Integration"
Cohesion: 0.14
Nodes (13): Animation Tokens, Base Layer, Button Example, Component Classes, CSS Variables Setup, Dark Mode Toggle, HSL Format Benefits, shadcn/ui Alignment (+5 more)

### Community 54 - "radius"
Cohesion: 0.11
Nodes (27): $type, $value, lg, sm, $type, $value, $type, $value (+19 more)

### Community 55 - "authorize"
Cohesion: 0.21
Nodes (13): admission(), authorize(), close_room(), conditions(), create_room(), get_room(), join(), digest() (+5 more)

### Community 56 - "Token Architecture"
Cohesion: 0.15
Nodes (12): Categories, Dark Mode, File Organization, Layer 1: Primitive Tokens, Layer 2: Semantic Tokens, Layer 3: Component Tokens, Layer Overview, Migration from Flat Tokens (+4 more)

### Community 57 - "sys"
Cohesion: 0.11
Nodes (7): main(), _run(), test_generate_slide_json_keeps_non_ascii_text(), test_html_token_validator_reads_utf8_html(), _run(), test_flags_hardcoded_hex_sharing_line_with_token(), test_token_only_line_reports_no_violation()

### Community 58 - "index-BOGSLSpr.js"
Cohesion: 0.06
Nodes (44): by, dm(), Ds(), dy(), Cl(), H(), Hl(), it() (+36 more)

### Community 59 - "Test-Driven Development"
Cohesion: 0.15
Nodes (10): Designing for Mockability, When to Mock, Anti-patterns, Rules of the loop, Seams: where tests go, Test-Driven Development, What a good test is, Bad Tests (+2 more)

### Community 60 - ".test_node_check_parses_generated_config"
Cohesion: 0.14
Nodes (3): main(), _strip_to_object(), TestGeneratedConfigIsValidJs

### Community 61 - "Pre-Delivery Checklist (canonical — the only one)"
Cohesion: 0.15
Nodes (12): Accessibility, Common Rules for Professional UI + Pre-Delivery Checklist, Icons & Visual Elements, Interaction, Interaction (App), Layout, Layout & Spacing, Light/Dark Mode (+4 more)

### Community 62 - "Quick Reference"
Cohesion: 0.15
Nodes (12): 10. Charts & Data (LOW), 1. Accessibility (CRITICAL), 2. Touch & Interaction (CRITICAL), 3. Performance (HIGH), 4. Style Selection (HIGH), 5. Layout & Responsive (HIGH), 6. Typography & Color (MEDIUM), 7. Animation (MEDIUM) (+4 more)

### Community 63 - "Primitive Tokens"
Cohesion: 0.17
Nodes (11): Border Radius, Color Scales, Gray Scale, Motion / Duration, Primary Colors (Blue), Primitive Tokens, Shadows, Spacing Scale (+3 more)

### Community 64 - "card"
Cohesion: 0.20
Nodes (12): $type, $value, bg, bg, padding, shadow, card, bg (+4 more)

### Community 65 - "Senior Fullstack"
Cohesion: 0.17
Nodes (8): Clarify First, Core Capabilities, Integration Points, References, Scope & Limitations, Senior Fullstack, Tools, When to Use

### Community 67 - "compilerOptions"
Cohesion: 0.18
Nodes (10): compilerOptions, jsx, lib, module, moduleResolution, noEmit, skipLibCheck, strict (+2 more)

### Community 68 - "Component Tokens"
Cohesion: 0.20
Nodes (9): Alert Tokens, Badge Tokens, Button Tokens, Card Tokens, Component Tokens, Dialog/Modal Tokens, Input Tokens, Table Tokens (+1 more)

### Community 69 - "Zr"
Cohesion: 0.09
Nodes (51): a0(), b(), bc(), Cc(), ci(), df(), Ea(), ei() (+43 more)

### Community 70 - "duration"
Cohesion: 0.20
Nodes (10): fast, normal, slow, $type, $value, $type, $value, duration (+2 more)

### Community 73 - "CNC Acoustic Lab｜PostgreSQL 全新資料庫建立規格 V1.2"
Cohesion: 0.20
Nodes (9): CNC Acoustic Lab｜PostgreSQL 全新資料庫建立規格 V1.2, Windows PowerShell / Linux Terminal, 主要資料流, 使用方式（依順序）, 加工條件的三層資料, 尚未由 SQL 自動保證的條件（正式蒐集前必測）, 本次產出, 資料庫負責什麼，不負責什麼？ (+1 more)

### Community 75 - "Ml"
Cohesion: 0.08
Nodes (48): bh(), c0(), cs(), Dl(), ds(), Dv(), $e(), e0() (+40 more)

### Community 76 - "七、EARS 實機第一次測試（2026-11-16，只接 EARS）"
Cohesion: 0.08
Nodes (24): 2026-11-16 更新 v4：支援 EARS（左右同一時鐘）＋ UMIK-2, EARS 相位可用性評估（用第五、六次的錄音，沒有新增錄音）, 一、為什麼做, 七、EARS 實機第一次測試（2026-11-16，只接 EARS）, 三、驗證證據（本機實際執行，`audio_preject` 環境）, 二、改了什麼, 五、第一次使用的步驟（建議）, 六、下一步 (+16 more)

### Community 77 - "Process"
Cohesion: 0.25
Nodes (7): 1. Pin the fixed point, 2. Identify the spec source, 3. Identify the standards sources, 4. Spawn both sub-agents in parallel, 5. Aggregate, Process, Why two axes

### Community 78 - "d0"
Cohesion: 0.10
Nodes (46): _0(), an(), bn(), bu(), cv(), d0(), de(), En() (+38 more)

### Community 80 - "l0"
Cohesion: 0.15
Nodes (45): at(), _c(), cd(), ch(), Cu(), Da(), dd(), Ec() (+37 more)

### Community 81 - "create_app"
Cohesion: 0.24
Nodes (12): create_app(), receive_type(), test_conditions_accept_submillimeter_tools_and_reject_out_of_range(), test_room_assigns_host_a_and_limits_sources(), test_three_participants_prepare_start_stop_and_real_preview(), test_settings_are_persisted_and_analysis_is_not_fabricated(), test_auto_slots_rejoin_and_close(), test_code_collision_retries_without_overwriting_room() (+4 more)

### Community 82 - "貼給 Codex 的完整指令｜CNC Acoustic Lab 建立全新 SQL 資料庫"
Cohesion: 0.25
Nodes (7): 任務一：確認環境與檔案, 任務三：TDD 驗收案例, 任務二：建立資料庫（不可破壞既有資料）, 任務五：Graphify 系統圖譜, 任務四：與手機錄音流程對應, 最終請交付, 貼給 Codex 的完整指令｜CNC Acoustic Lab 建立全新 SQL 資料庫

### Community 83 - "Frontend Design"
Cohesion: 0.29
Nodes (6): Design principles, Frontend Design, Ground your designs in the subject matter, More on writing in design, Process: plan, review against the brief, build, critique, Restraint and self-critique

### Community 84 - "primitive"
Cohesion: 0.18
Nodes (19): $type, $value, $type, $value, 500, 600, blue, green (+11 more)

### Community 85 - "generate-slide.py"
Cohesion: 0.12
Nodes (11): _e(), generate_chart_slide(), generate_cta_slide(), generate_deck(), generate_metrics_slide(), generate_problem_slide(), generate_solution_slide(), generate_testimonial_slide() (+3 more)

### Community 86 - "register_audio"
Cohesion: 0.19
Nodes (12): register_audio(), audio(), chunk(), finish(), inventory(), recording(), Chunk 輸入契約（示意）, CNC Acoustic Lab｜手機端 × 錄音主機 × FastAPI 最小 API 規格 V1.2 (+4 more)

### Community 88 - "j0"
Cohesion: 0.11
Nodes (36): Aa(), af(), Ar(), bv(), di(), eh(), es(), _f() (+28 more)

### Community 89 - "interface"
Cohesion: 0.33
Nodes (5): interface, display_name, short_description, policy, allow_implicit_invocation

### Community 91 - "record_usb.py"
Cohesion: 0.11
Nodes (18): ffmpeg_exe(), build_cmd(), capture_effects(), check_file(), cmd_list(), cmd_record(), effects_status(), input_spec() (+10 more)

### Community 93 - "fr"
Cohesion: 0.14
Nodes (31): $a(), ai(), bf(), ca(), Cn(), Ee(), ef(), Et() (+23 more)

### Community 94 - "i0"
Cohesion: 0.14
Nodes (29): ad(), Ba(), Bl(), cf(), _d(), Du(), Hn(), hr() (+21 more)

### Community 95 - "y"
Cohesion: 0.12
Nodes (24): Al(), Cr(), Dc(), eo(), Fn(), gd(), Jc(), Jo() (+16 more)

### Community 96 - "_select_palette_for_mode"
Cohesion: 0.15
Nodes (6): _button_outline_text_color(), _contrast_ratio(), _derive_dark_palette(), format_master_md(), _select_palette_for_mode(), TestPaletteSelection

### Community 97 - "json"
Cohesion: 0.19
Nodes (7): apply_decision_rules(), _object_without_duplicates(), parse_decision_rules(), _validate_action(), _check_provenance(), _valid_catalog_source_key(), _valid_provenance_source()

### Community 99 - "offline.py"
Cohesion: 0.22
Nodes (11): cmd_chirp(), cmd_run(), decode(), decode_stereo(), inside_repo(), main(), _num(), print_report() (+3 more)

### Community 101 - "interface"
Cohesion: 0.50
Nodes (3): interface, display_name, short_description

### Community 102 - "interface"
Cohesion: 0.50
Nodes (3): interface, display_name, short_description

### Community 103 - "Ys"
Cohesion: 0.12
Nodes (24): ay(), Bs(), Dt(), hi(), Hs(), I(), Ie(), iu() (+16 more)

### Community 104 - "read_rows"
Cohesion: 0.19
Nodes (5): read_rows(), TestAccessibilityGuidance, TestChartsTypographyAndIcons, TestCurrentReactGuidance, TestSemanticColors

### Community 105 - "_search_csv_detailed"
Cohesion: 0.25
Nodes (3): _search_csv(), _search_csv_detailed(), TestBm25CoreBehavior

### Community 106 - "interface"
Cohesion: 0.50
Nodes (3): interface, display_name, short_description

### Community 107 - "hitl-loop.template.sh"
Cohesion: 0.83
Nodes (3): capture(), hitl-loop.template.sh script, step()

### Community 108 - "interface"
Cohesion: 0.50
Nodes (3): interface, display_name, short_description

### Community 109 - "Database Patterns"
Cohesion: 0.50
Nodes (4): Connection Pooling, Database Patterns, Read Replicas, Transaction Patterns

### Community 110 - "test_ears_umik.py"
Cohesion: 0.16
Nodes (13): ears_scene(), full_run(), ns(), test_phase_slope_of_same_clock_pair_equals_acoustic_delay(), test_recorder_file_checks(), test_recorder_refuses_repository_output(), test_same_clock_pair_keeps_acoustic_delay_and_separate_mic_is_aligned(), test_same_clock_track_is_written_unshifted() (+5 more)

### Community 111 - "package.json"
Cohesion: 0.05
Nodes (35): HTTP 與 WebSocket 契約, REST, WebSocket, 狀態與恢復, dependencies, react-dom@^19.2.0, devDependencies, @playwright/test@^1.56.0 (+27 more)

### Community 112 - "design-tokens-starter.json"
Cohesion: 0.15
Nodes (12): component, $type, $value, dark, semantic, $schema, $type, $value (+4 more)

### Community 113 - "interface"
Cohesion: 0.50
Nodes (3): interface, display_name, short_description

### Community 114 - "publish"
Cohesion: 0.44
Nodes (10): broadcast(), check_acknowledgements(), countdown(), prepare_timeout(), publish(), schedule(), snapshot(), start() (+2 more)

### Community 115 - "系統與 PostgreSQL 設計"
Cohesion: 0.29
Nodes (6): 保留 V1.2 的決定, 加工欄位對照, 執行限制, 模組, 系統與 PostgreSQL 設計, 表與不變條件

### Community 116 - "test_synthetic.py"
Cohesion: 0.13
Nodes (17): chirp_template(), detect_chirps(), _encode(), _run(), test_chirp_file_is_detected_once_at_pad(), test_missing_input_file_is_reported(), test_mixed_formats_with_chirps_are_verified(), test_without_chirp_falls_back_to_envelope_and_still_verifies() (+9 more)

### Community 117 - "button"
Cohesion: 0.20
Nodes (10): fg, font-size, hover-bg, button, $type, $value, $type, $value (+2 more)

### Community 118 - "_load_csv"
Cohesion: 0.25
Nodes (4): _load_csv(), _load_csv_snapshot(), _load_product_keywords(), _load_rows_or_empty()

### Community 119 - "CNC Acoustic Lab 開發與版本管理"
Cohesion: 0.50
Nodes (3): CNC Acoustic Lab 開發與版本管理, 初始內容與驗證界線, 每個功能階段

### Community 120 - "2026-11-10 更新 v1：分析模型上線、收音設定紀錄、同步嗶聲"
Cohesion: 0.20
Nodes (10): 1. 新增 `analysis/`（分析模型）, 2026-11-10 更新 v1：分析模型上線、收音設定紀錄、同步嗶聲, 2. 前端：記錄瀏覽器「實際」採用的收音處理, 3. 前端：同步嗶聲, 4. 修正：`npm ci` 在 npm 10 和 npm 11 都無法執行, 一、這次改了什麼, 三、驗證證據（全部在本機實際執行）, 二、重要更正：上一版兩手機分析報告有兩個結論是錯的 (+2 more)

### Community 121 - "2026-11-12 更新 v3：離線分析工具（不經過網站資料庫）"
Cohesion: 0.20
Nodes (9): 2026-11-12 更新 v3：離線分析工具（不經過網站資料庫）, 一、為什麼做, 七、實錄步驟（建議）, 三、驗證證據（本機實際執行，`audio_preject` 環境）, 二、改了什麼, 五、沒有驗證的, 八、下一步, 六、重要：臨時通道上的錄音網站沒有關掉手機的收音處理 (+1 more)

### Community 122 - "Deployment Platforms"
Cohesion: 0.40
Nodes (5): AWS (ECS/Lambda), Deployment Platforms, Deployment Selection, Railway, Vercel

### Community 123 - "csv"
Cohesion: 0.07
Nodes (9): read_rows(), RtlDataContractTest, resolve(), shipped_invocations(), SkillScriptPathsTest, read_rows(), read_rows(), TestTextLayoutDataContracts (+1 more)

### Community 124 - "$type"
Cohesion: 0.60
Nodes (5): $type, $value, 700, 700, 700

### Community 125 - "2026-11-11 更新 v2：雲端只寫入、地端計算（分析工作佇列）"
Cohesion: 0.22
Nodes (9): 2026-11-11 更新 v2：雲端只寫入、地端計算（分析工作佇列）, Codex 審查, 一、為什麼做, 三、驗證證據（本機實際執行）, 二、改了什麼, 五、下一步（建議順序）, 四、你審閱時可以這樣測, 新增：對齊判定 (+1 more)

### Community 126 - "input"
Cohesion: 0.29
Nodes (8): padding-x, input, $type, $value, focus-ring, padding-x, $type, $value

### Community 127 - "Testing Strategies"
Cohesion: 0.40
Nodes (5): E2E Testing with Playwright, Integration Testing, Testing Pyramid, Testing Strategies, Unit Testing

### Community 128 - "Git Workflows"
Cohesion: 0.50
Nodes (4): Commit Standards, Git Workflows, Pre-commit Hooks, Trunk-Based Development

### Community 129 - "Monitoring and Observability"
Cohesion: 0.50
Nodes (4): Health Checks, Metrics Collection, Monitoring and Observability, Structured Logging

### Community 130 - "Databases"
Cohesion: 0.40
Nodes (5): Database Selection Matrix, Databases, MongoDB, PostgreSQL, Redis

### Community 131 - "Backend Frameworks"
Cohesion: 0.50
Nodes (4): Backend Frameworks, Framework Selection Guide, Node.js Ecosystem, Python Ecosystem

### Community 138 - "50"
Cohesion: 0.67
Nodes (4): $type, $value, 50, 50

### Community 139 - "test_catalog_summary_line_endings.py"
Cohesion: 0.09
Nodes (5): CatalogSummaryLineEndingsTest, _load_generator(), TestFixtureValidation, TestMetricMath, TestThresholdGate

### Community 140 - "Authentication Solutions"
Cohesion: 0.50
Nodes (4): Auth.js (NextAuth), Authentication Solutions, Clerk, Custom JWT

### Community 142 - "analysis/ — 多手機錄音分析模型（v1）"
Cohesion: 0.29
Nodes (7): analysis/ — 多手機錄音分析模型（v1）, 做了什麼, 檔案, 用法, 輸出（`--out` 資料夾）, 限制, 雙聲道裝置（EARS）＋獨立麥克風（UMIK-2）

### Community 145 - "800"
Cohesion: 0.67
Nodes (4): $type, $value, 800, 800

### Community 146 - "地端分析 worker：雲端只寫入，地端計算，資料表溝通"
Cohesion: 0.33
Nodes (6): 地端分析 worker：雲端只寫入，地端計算，資料表溝通, 地端電腦怎麼跑, 對齊判定（不可把未驗證的數字當結果）, 尚未做的, 為什麼這樣分, 認領與所有權

### Community 147 - "V1.5 三支實體手機驗收"
Cohesion: 0.33
Nodes (5): HTTPS 啟動, SQL 查詢, V1.5 三支實體手機驗收, 故障與復原, 正常路徑

### Community 148 - "$type"
Cohesion: 0.60
Nodes (5): $type, $value, border, border, border

### Community 149 - "radius"
Cohesion: 0.60
Nodes (5): radius, radius, radius, $type, $value

### Community 150 - "既有 V1.4 驗證紀錄"
Cohesion: 0.40
Nodes (5): TDD 與審查, 已觀察結果, 既有 V1.4 驗證紀錄, 未驗證／未完成, 測試涵蓋

### Community 151 - "V1.5 驗證紀錄"
Cohesion: 0.40
Nodes (5): 14 項驗收對照, TDD 證據, V1.5 驗證紀錄, 執行結果, 尚未驗證與限制

### Community 152 - "CNC Acoustic Lab V1.5"
Cohesion: 0.40
Nodes (5): CNC Acoustic Lab V1.5, HTTPS 與部署, 三支手機操作, 尚待正式部署／硬體驗收, 本機執行

### Community 153 - "padding-y"
Cohesion: 0.67
Nodes (4): padding-y, padding-y, $type, $value

### Community 155 - "white"
Cohesion: 0.67
Nodes (3): white, $type, $value

### Community 157 - "destructive"
Cohesion: 0.67
Nodes (3): destructive, $type, $value

### Community 158 - "destructive-foreground"
Cohesion: 0.67
Nodes (3): destructive-foreground, $type, $value

### Community 159 - "muted"
Cohesion: 0.67
Nodes (3): muted, $type, $value

### Community 160 - "primary-foreground"
Cohesion: 0.67
Nodes (3): primary-foreground, $type, $value

### Community 161 - "ring"
Cohesion: 0.67
Nodes (3): ring, $type, $value

### Community 162 - "secondary-foreground"
Cohesion: 0.67
Nodes (3): secondary-foreground, $type, $value

### Community 163 - "split_values"
Cohesion: 0.47
Nodes (3): split_values(), style_identities(), TestStyleIdentityContract

## Knowledge Gaps
- **26 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `code_commit()` connect `worker.py` to `sys`?**
  _High betweenness centrality (0.061) - this node is a cross-community bridge._
- **Are the 39 inferred relationships involving `yy()` (e.g. with `ad()` and `ah()`) actually correct?**
  _`yy()` has 39 INFERRED edges - model-reasoned connections that need verification._
- **Should `App.tsx` be split into smaller, more focused modules?**
  _Cohesion score 0.05284831846259437 - nodes in this community are weakly interconnected._
- **Why does `地端分析 worker：雲端只寫入，地端計算，資料表溝通` connect `地端分析 worker：雲端只寫入，地端計算，資料表溝通` to `README.md`, `worker.py`?**
  _High betweenness centrality (0.056) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `TailwindConfigGenerator` (e.g. with `TestGeneratedConfigIsValidJs` and `TestTailwindConfigGenerator`) actually correct?**
  _`TailwindConfigGenerator` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Should `ShadcnInstaller` be split into smaller, more focused modules?**
  _Cohesion score 0.053555750658472345 - nodes in this community are weakly interconnected._
- **Why does `資料表（migration 004）` connect `worker.py` to `地端分析 worker：雲端只寫入，地端計算，資料表溝通`?**
  _High betweenness centrality (0.056) - this node is a cross-community bridge._