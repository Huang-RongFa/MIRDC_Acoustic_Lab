# Graph Report - CNC-Acoustic-Lab  (2026-11-19)

## Corpus Check
- 211 files · ~260,133 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 107 file(s) not represented in the graph (top: .ttf 54, .csv 46, .css 4)
- WARNING: 107 of 355 files seen (30%) have no supported extractor and are missing from this graph entirely. It may look complete while representing only part of the codebase.

## Summary
- 2901 nodes · 5931 edges · 163 communities (134 shown, 29 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 342 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `d2602c2a`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- syncAnalysis.ts
- ShadcnInstaller
- code_quality_analyzer.py
- gray
- slide_search_core.py
- Tailwind CSS Utility Reference
- design-tokens-starter.json
- @playwright/test
- validate_data.py
- Canvas Design System
- validate-tokens.cjs
- Fullstack Tech Stack Guide
- Form & Input Components
- Tailwind CSS Responsive Design
- 全欄位清單
- search_stack
- numpy
- html-token-validator.py
- search
- Component Specifications
- shadcn/ui Accessibility Patterns
- button
- TestTailwindConfigGenerator
- UI Styling Skill
- States and Variants
- Testing Strategies
- Codebase Design
- Design System
- Tailwind CSS Customization
- spacing
- During the session
- Ys
- yy
- input
- fetch-background.py
- shadcn/ui Theming & Customization
- json
- color
- detect_domain
- app.py
- Color Semantics
- TailwindConfigGenerator
- DesignSystemGenerator
- UI/UX Pro Max - Design Intelligence
- Fullstack Architecture Patterns
- Tooling, Workflows & Quality Bar
- BM25
- fontSize
- Fullstack Development Workflows
- Diagnosing Bugs
- App.tsx
- CatalogRefreshTest
- Tailwind Integration
- radius
- CNC Acoustic Lab｜外部音訊分析系統對接規格
- Token Architecture
- design_system.py
- index-BOGSLSpr.js
- Test-Driven Development
- .test_node_check_parses_generated_config
- Pre-Delivery Checklist (canonical — the only one)
- Quick Reference
- Primitive Tokens
- card
- Senior Fullstack
- main
- compilerOptions
- Component Tokens
- Zr
- duration
- CNC Acoustic Lab｜PostgreSQL 全新資料庫建立規格 V1.2
- Ml
- App
- Process
- d0
- l0
- create_app
- 貼給 Codex 的完整指令｜CNC Acoustic Lab 建立全新 SQL 資料庫
- Frontend Design
- capture.ts
- generate-slide.py
- 可驗證的多設備同步錄音
- hashlib
- j0
- interface
- $type
- radius
- fr
- i0
- y
- test_analysis_api.py
- test_design_system_mode.py
- TestStackFlagWithDesignSystem
- 網頁錄音擴充：最小侵入式交付
- RtlCliTest
- interface
- interface
- csv
- test_data_contracts.py
- interface
- hitl-loop.template.sh
- interface
- Database Patterns
- pcmCapture.ts
- devDependencies
- test_validate_tokens.py
- interface
- authorize
- 系統與 PostgreSQL 設計
- V2.2 地端部署與操作
- padding-y
- analysis.py
- CNC Acoustic Lab 開發與版本管理
- Deployment Platforms
- core.py
- Databases
- RecorderDevice
- test_audio_sync.py
- lg
- RecordingWaveformImages.tsx
- Authentication Solutions
- Git Workflows
- Monitoring and Observability
- sm
- test_relevance_evaluator.py
- CNC Acoustic Lab
- 系統依賴與資料關聯
- AGENTS.md
- template-analysis.md
- schema.md
- xl
- destructive
- none
- destructive-foreground
- muted
- primary-foreground
- ring
- secondary-foreground
- _search_csv_detailed
- V2.2 驗證紀錄
- SyncReference
- 16
- _load_csv
- 1
- 3
- Backend Frameworks
- recordingAssets.d.ts
- 8
- 地端與 Quick Tunnel 錄音測試
- Windows 啟動與 Schema 修復
- register_analysis

## God Nodes (most connected - your core abstractions)
1. `yy()` - 389 edges
2. `create_app()` - 71 edges
3. `y()` - 61 edges
4. `TailwindConfigGenerator` - 60 edges
5. `search()` - 54 edges
6. `i0()` - 54 edges
7. `TestTailwindConfigGenerator` - 41 edges
8. `DesignSystemGenerator` - 38 edges
9. `search_stack()` - 36 edges
10. `ShadcnInstaller` - 34 edges

## Surprising Connections (you probably didn't know these)
- `架構與範圍` --references--> `RecorderDevice`  [INFERRED]
  docs/recording-sync-extension.md → frontend/src/capture.ts
- `資料庫與 API` --references--> `AudioSyncService`  [INFERRED]
  docs/stereo-recording-interface.md → backend/audio_sync.py
- `4. 外部分析系統需要讀取的資料表` --references--> `conditions()`  [INFERRED]
  docs/external-analysis-integration.md → backend/app.py
- `資料庫與 API` --references--> `capture_settings()`  [INFERRED]
  docs/stereo-recording-interface.md → backend/capture_protocol.py
- ``machines` — CNC 機台主檔` --references--> `machines()`  [INFERRED]
  CNC_Acoustic_Lab_DB_v1_2/04_data_dictionary.md → backend/app.py

## Import Cycles
- None detected.

## Communities (163 total, 29 thin omitted)

### Community 0 - "syncAnalysis.ts"
Cohesion: 0.26
Nodes (12): alignedWav(), Alignment, analyzeSync(), detectMarkers(), fitAlignment(), Marker, SyncInput, SyncReport (+4 more)

### Community 1 - "ShadcnInstaller"
Cohesion: 0.05
Nodes (3): main(), ShadcnInstaller, TestShadcnInstaller

### Community 2 - "code_quality_analyzer.py"
Cohesion: 0.11
Nodes (12): analyze_dependencies(), analyze_documentation(), analyze_project(), analyze_security(), analyze_test_coverage(), calculate_complexity(), count_lines(), generate_recommendations() (+4 more)

### Community 3 - "gray"
Cohesion: 0.05
Nodes (53): $type, $value, $type, $value, $type, $value, $type, $value (+45 more)

### Community 4 - "slide_search_core.py"
Cohesion: 0.08
Nodes (17): format_context(), format_result(), main(), BM25, calculate_pattern_break(), detect_domain(), get_background_config(), get_color_for_emotion() (+9 more)

### Community 5 - "Tailwind CSS Utility Reference"
Cohesion: 0.05
Nodes (43): Arbitrary Values, Aspect Ratio, Background Colors, Border Color, Border Radius, Border Style, Border Width, Borders (+35 more)

### Community 6 - "design-tokens-starter.json"
Cohesion: 0.15
Nodes (12): component, $type, $value, dark, semantic, $schema, $type, $value (+4 more)

### Community 8 - "validate_data.py"
Cohesion: 0.06
Nodes (43): read_rows(), TestAccessibilityGuidance, TestChartsTypographyAndIcons, TestCurrentReactGuidance, TestSemanticColors, TestGeneratedCatalogContract, _catalog_date(), _check_app_interface_contract() (+35 more)

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
Cohesion: 0.05
Nodes (39): machines(), `analysis_artifacts` — 大容量衍生音訊、FFT／STFT 圖檔位置與雜湊, `analysis_runs` — 每次前處理／特徵／融合／推論執行紀錄, `app_users` — 研究人員與系統管理者, `audio_assets` — 封存三通道無損音檔及其雜湊, `audio_chunks` — 錄音中寫入 SQL 的三通道 PCM 區塊, `audio_quality_checks` — 音訊完整性與品質檢查, `capture_devices` — 多通道音訊介面和錄音主機 (+31 more)

### Community 15 - "search_stack"
Cohesion: 0.09
Nodes (6): search_stack(), TestDiagnosticsContracts, _rows(), TestNativeDesktopStackFreshness, _rows(), TestWebStackFreshness

### Community 16 - "numpy"
Cohesion: 0.18
Nodes (15): process_job(), calculate(), decode(), matrix_file(), mel_filters(), package_versions(), render(), resample() (+7 more)

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

### Community 21 - "button"
Cohesion: 0.20
Nodes (10): fg, font-size, hover-bg, button, $type, $value, $type, $value (+2 more)

### Community 23 - "UI Styling Skill"
Cohesion: 0.08
Nodes (25): Accessibility Patterns, Alternative: Tailwind-Only Setup, Best Practices, Common Patterns, Component Layer: shadcn/ui, Component Library Guide, Component + Styling Setup, Core Stack (+17 more)

### Community 24 - "States and Variants"
Cohesion: 0.08
Nodes (24): Accessibility, Accessibility Requirements, ARIA States, Color Contrast, Color Variants, Disabled States, Error Messages, Error States (+16 more)

### Community 25 - "Testing Strategies"
Cohesion: 0.40
Nodes (5): E2E Testing with Playwright, Integration Testing, Testing Pyramid, Testing Strategies, Unit Testing

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
Cohesion: 0.09
Nodes (22): $type, $value, $type, $value, $type, $value, $type, $value (+14 more)

### Community 30 - "During the session"
Cohesion: 0.09
Nodes (19): ADR Format, Numbering, Optional sections, Template, What qualifies, When to offer an ADR, GLOSSARY.md Format, Rules (+11 more)

### Community 31 - "Ys"
Cohesion: 0.12
Nodes (24): ay(), Bs(), Dt(), hi(), Hs(), I(), Ie(), iu() (+16 more)

### Community 32 - "yy"
Cohesion: 0.06
Nodes (64): yy(), ah(), ao(), au(), av(), B0(), bd(), be() (+56 more)

### Community 33 - "input"
Cohesion: 0.29
Nodes (8): padding-x, input, $type, $value, focus-ring, padding-x, $type, $value

### Community 34 - "fetch-background.py"
Cohesion: 0.15
Nodes (9): generate_css_for_background(), get_background_image(), get_curated_images(), get_overlay_css(), get_pexels_search_url(), load_backgrounds_config(), load_brand_colors(), main() (+1 more)

### Community 35 - "shadcn/ui Theming & Customization"
Cohesion: 0.10
Nodes (19): Base Color Presets, Best Practices, Color Customization, Color Format, Component Customization, CSS Variable System, Customize Styles, Customize Variants (+11 more)

### Community 36 - "json"
Cohesion: 0.09
Nodes (10): main(), _run(), test_generate_slide_json_keeps_non_ascii_text(), test_html_token_validator_reads_utf8_html(), create_project(), get_file_content(), get_next_steps(), list_templates() (+2 more)

### Community 37 - "color"
Cohesion: 0.11
Nodes (19): $type, $value, background, foreground, muted-foreground, primary, primary-hover, secondary (+11 more)

### Community 38 - "detect_domain"
Cohesion: 0.18
Nodes (5): detect_domain(), _domain_keywords(), _file_signature(), _get_bm25(), TestDomainDetection

### Community 39 - "app.py"
Cohesion: 0.10
Nodes (12): worker(), lifespan(), Person, RoomConfig, RoomCreation, Database, InternalNetwork, check_schema() (+4 more)

### Community 40 - "Color Semantics"
Cohesion: 0.11
Nodes (17): Accent, Applying Semantic Tokens, Background & Foreground, Border & Ring, Color Semantics, Dark Mode Overrides, Destructive, Interactive States (+9 more)

### Community 42 - "DesignSystemGenerator"
Cohesion: 0.09
Nodes (6): DesignSystemGenerator, _resolve_dial(), TestReasoningMatch, read_rows(), TestReasoningContract, TestEndToEndCoherence

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
Cohesion: 0.12
Nodes (16): $type, $value, $type, $value, $type, $value, $type, $value (+8 more)

### Community 48 - "Fullstack Development Workflows"
Cohesion: 0.11
Nodes (18): Blue-Green Deployment, Canary Deployment, CI/CD Pipelines, Code Review Process, Daily Workflow, Database Migrations in CI, Deployment Strategies, Docker Compose Development Environment (+10 more)

### Community 50 - "Diagnosing Bugs"
Cohesion: 0.13
Nodes (14): Completion criterion: a tight loop that goes red, Diagnosing Bugs, Minimise, Non-deterministic bugs, Phase 1: Build a feedback loop, Phase 2: Reproduce + minimise, Phase 3: Hypothesise, Phase 4: Instrument (+6 more)

### Community 51 - "App.tsx"
Cohesion: 0.14
Nodes (22): channelFeatures(), ChannelInspector(), channelWav(), RecordingChannelAnalysis(), staticHosting, appendWave(), LiveFrame, LiveWave (+14 more)

### Community 53 - "Tailwind Integration"
Cohesion: 0.14
Nodes (13): Animation Tokens, Base Layer, Button Example, Component Classes, CSS Variables Setup, Dark Mode Toggle, HSL Format Benefits, shadcn/ui Alignment (+5 more)

### Community 54 - "radius"
Cohesion: 0.19
Nodes (14): $type, $value, $type, $value, $type, $value, primitive, radius (+6 more)

### Community 55 - "CNC Acoustic Lab｜外部音訊分析系統對接規格"
Cohesion: 0.08
Nodes (24): 10. 權限與資料責任, 11. 協作驗收清單, 12. 原始碼與 Schema 對照, 1. 對接範圍與重要結論, 2. 需要交付給協作人員的連線資訊, 3. 核心識別鍵, 4.1 來源清單查詢範例, 4.2 從資料庫重建原始檔 (+16 more)

### Community 56 - "Token Architecture"
Cohesion: 0.15
Nodes (12): Categories, Dark Mode, File Organization, Layer 1: Primitive Tokens, Layer 2: Semantic Tokens, Layer 3: Component Tokens, Layer Overview, Migration from Flat Tokens (+4 more)

### Community 57 - "design_system.py"
Cohesion: 0.06
Nodes (18): ansi_ljust(), _detect_page_type(), format_ascii_box(), add_wrapped(), wrap_text(), format_markdown(), format_page_override_md(), generate_design_system() (+10 more)

### Community 58 - "index-BOGSLSpr.js"
Cohesion: 0.06
Nodes (44): by, dm(), Ds(), dy(), Cl(), H(), Hl(), it() (+36 more)

### Community 59 - "Test-Driven Development"
Cohesion: 0.15
Nodes (10): Designing for Mockability, When to Mock, Anti-patterns, Rules of the loop, Seams: where tests go, Test-Driven Development, What a good test is, Bad Tests (+2 more)

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

### Community 76 - "App"
Cohesion: 0.15
Nodes (14): api(), App(), saveConditions(), saveMachine(), savePreset(), Card(), ConditionFields(), identities() (+6 more)

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
Cohesion: 0.17
Nodes (15): machine_conditions(), receive_type(), test_conditions_accept_submillimeter_tools_and_reject_out_of_range(), test_room_assigns_host_a_and_limits_sources(), test_three_participants_prepare_start_stop_and_real_preview(), test_machine_and_conditions_available_in_new_room(), test_settings_are_persisted_and_analysis_is_not_fabricated(), test_auto_slots_rejoin_and_close() (+7 more)

### Community 82 - "貼給 Codex 的完整指令｜CNC Acoustic Lab 建立全新 SQL 資料庫"
Cohesion: 0.25
Nodes (7): 任務一：確認環境與檔案, 任務三：TDD 驗收案例, 任務二：建立資料庫（不可破壞既有資料）, 任務五：Graphify 系統圖譜, 任務四：與手機錄音流程對應, 最終請交付, 貼給 Codex 的完整指令｜CNC Acoustic Lab 建立全新 SQL 資料庫

### Community 83 - "Frontend Design"
Cohesion: 0.29
Nodes (6): Design principles, Frontend Design, Ground your designs in the subject matter, More on writing in design, Process: plan, review against the brief, build, critique, Restraint and self-critique

### Community 84 - "capture.ts"
Cohesion: 0.24
Nodes (11): RecordingSyncControls(), RecordingSyncOptions, recordingSyncOptions(), saveRecordingSyncOptions(), Capture, Chunk, chunks(), database() (+3 more)

### Community 85 - "generate-slide.py"
Cohesion: 0.12
Nodes (11): _e(), generate_chart_slide(), generate_cta_slide(), generate_deck(), generate_metrics_slide(), generate_problem_slide(), generate_solution_slide(), generate_testimonial_slide() (+3 more)

### Community 86 - "可驗證的多設備同步錄音"
Cohesion: 0.29
Nodes (6): 不能由此證明的精度, 使用, 可驗證的多設備同步錄音, 時間與驗證定義, 本次實際驗證（2026-11-12）, 驗證方式

### Community 87 - "hashlib"
Cohesion: 0.20
Nodes (12): receive(), test_waiting_departure_after_clock_sync(), test_chunk_identity_and_size_are_queryable_without_custom_search_path(), test_legacy_tables_are_preserved_and_cross_room_recordings_are_rejected(), auth(), test_assignments(), test_external_network_denied(), test_five_recorders_close_during_capture() (+4 more)

### Community 88 - "j0"
Cohesion: 0.11
Nodes (36): Aa(), af(), Ar(), bv(), di(), eh(), es(), _f() (+28 more)

### Community 89 - "interface"
Cohesion: 0.33
Nodes (5): interface, display_name, short_description, policy, allow_implicit_invocation

### Community 91 - "$type"
Cohesion: 0.60
Nodes (5): $type, $value, border, border, border

### Community 92 - "radius"
Cohesion: 0.60
Nodes (5): radius, radius, radius, $type, $value

### Community 93 - "fr"
Cohesion: 0.14
Nodes (31): $a(), ai(), bf(), ca(), Cn(), Ee(), ef(), Et() (+23 more)

### Community 94 - "i0"
Cohesion: 0.14
Nodes (29): ad(), Ba(), Bl(), cf(), _d(), Du(), Hn(), hr() (+21 more)

### Community 95 - "y"
Cohesion: 0.12
Nodes (24): Al(), Cr(), Dc(), eo(), Fn(), gd(), Jc(), Jo() (+16 more)

### Community 96 - "test_analysis_api.py"
Cohesion: 0.27
Nodes (7): finish(), seed(), test_missing_invalid_audio_actual_mono_and_restart(), test_real_pipeline_auto_queue_png_and_auth(), test_recording_not_ready(), wait_result(), client()

### Community 97 - "test_design_system_mode.py"
Cohesion: 0.07
Nodes (15): _button_outline_text_color(), _contrast_ratio(), _derive_dark_palette(), _filter_anti_patterns_for_mode(), format_master_md(), _palette_is_dark(), _query_wants_dark(), _relative_luminance() (+7 more)

### Community 99 - "網頁錄音擴充：最小侵入式交付"
Cohesion: 0.13
Nodes (13): Python 離線入口, 使用, 架構與範圍, 檔案, 相容性與未完成邊界, 網頁錄音擴充：最小侵入式交付, 驗證, 實際驗證結果 (+5 more)

### Community 101 - "interface"
Cohesion: 0.50
Nodes (3): interface, display_name, short_description

### Community 102 - "interface"
Cohesion: 0.50
Nodes (3): interface, display_name, short_description

### Community 103 - "csv"
Cohesion: 0.08
Nodes (8): read_rows(), RtlDataContractTest, resolve(), shipped_invocations(), SkillScriptPathsTest, read_rows(), read_rows(), TestTextLayoutDataContracts

### Community 105 - "test_data_contracts.py"
Cohesion: 0.11
Nodes (9): apply_decision_rules(), _object_without_duplicates(), parse_decision_rules(), _validate_action(), split_values(), style_identities(), TestLandingAndStackContract, TestStyleIdentityContract (+1 more)

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

### Community 110 - "pcmCapture.ts"
Cohesion: 0.27
Nodes (8): PcmCapture, database(), loadPcm(), PcmChunk, pcmHistory(), PcmMetadata, pcmWav(), savePcm()

### Community 111 - "devDependencies"
Cohesion: 0.08
Nodes (27): dependencies, react@^19.2.0, react-dom@^19.2.0, devDependencies, @playwright/test@^1.56.0, rollup@npm:@rollup/wasm-node@^4.68.0, @types/react@^19.2.0, @types/react-dom@^19.2.0 (+19 more)

### Community 112 - "test_validate_tokens.py"
Cohesion: 0.14
Nodes (5): _run(), test_flags_hardcoded_hex_sharing_line_with_token(), test_token_only_line_reports_no_violation(), CatalogSummaryLineEndingsTest, _load_generator()

### Community 113 - "interface"
Cohesion: 0.50
Nodes (3): interface, display_name, short_description

### Community 114 - "authorize"
Cohesion: 0.19
Nodes (32): create_app(), admission(), authorize(), broadcast(), check_acknowledgements(), close_room(), conditions(), configure() (+24 more)

### Community 115 - "系統與 PostgreSQL 設計"
Cohesion: 0.04
Nodes (39): 1. 現有架構檢查, 2. 修改／新增檔案, 3. 前端, 4. 44100／48000 Hz, 5. 聲道拆分與儲存, 7. API 與 Migration, 8. 驗證與限制, 9. 建置與啟動 (+31 more)

### Community 116 - "V2.2 地端部署與操作"
Cohesion: 0.40
Nodes (4): API 與即時事件, V2.2 地端部署與操作, 操作與實機驗收表, 部署

### Community 117 - "padding-y"
Cohesion: 0.67
Nodes (4): padding-y, padding-y, $type, $value

### Community 118 - "analysis.py"
Cohesion: 0.15
Nodes (11): AnalysisRange, enqueue(), register_audio(), audio(), chunk(), finish(), inventory(), recording() (+3 more)

### Community 119 - "CNC Acoustic Lab 開發與版本管理"
Cohesion: 0.50
Nodes (3): CNC Acoustic Lab 開發與版本管理, 初始內容與驗證界線, 每個功能階段

### Community 120 - "Deployment Platforms"
Cohesion: 0.40
Nodes (5): AWS (ECS/Lambda), Deployment Platforms, Deployment Selection, Railway, Vercel

### Community 121 - "core.py"
Cohesion: 0.07
Nodes (20): _contains_phrase(), _exact_match_diagnostic(), _exact_row_identity(), _exact_stack_identifier(), _legacy_successor_guidance(), _normalize(), _normalize_rtl_level(), _passes_threshold() (+12 more)

### Community 122 - "Databases"
Cohesion: 0.40
Nodes (5): Database Selection Matrix, Databases, MongoDB, PostgreSQL, Redis

### Community 123 - "RecorderDevice"
Cohesion: 0.19
Nodes (4): RecorderDevice, PcmCapture, put(), useRoom()

### Community 124 - "test_audio_sync.py"
Cohesion: 0.14
Nodes (24): align_copy(), analysis_copy(), AudioSyncService, contained(), detect_prbs(), fit_markers(), identifier(), main() (+16 more)

### Community 125 - "lg"
Cohesion: 0.60
Nodes (5): lg, $type, $value, lg, lg

### Community 126 - "RecordingWaveformImages.tsx"
Cohesion: 0.19
Nodes (15): fields, RecordingFile(), RecordingResults(), download(), monoCharts, png(), RecordingWaveformImages(), stereoCharts (+7 more)

### Community 127 - "Authentication Solutions"
Cohesion: 0.50
Nodes (4): Auth.js (NextAuth), Authentication Solutions, Clerk, Custom JWT

### Community 128 - "Git Workflows"
Cohesion: 0.50
Nodes (4): Commit Standards, Git Workflows, Pre-commit Hooks, Trunk-Based Development

### Community 129 - "Monitoring and Observability"
Cohesion: 0.50
Nodes (4): Health Checks, Metrics Collection, Monitoring and Observability, Structured Logging

### Community 130 - "sm"
Cohesion: 0.60
Nodes (5): sm, sm, sm, $type, $value

### Community 131 - "test_relevance_evaluator.py"
Cohesion: 0.12
Nodes (3): TestFixtureValidation, TestMetricMath, TestThresholdGate

### Community 138 - "xl"
Cohesion: 0.67
Nodes (4): xl, xl, $type, $value

### Community 139 - "destructive"
Cohesion: 0.67
Nodes (3): destructive, $type, $value

### Community 140 - "none"
Cohesion: 0.67
Nodes (4): $type, $value, none, none

### Community 141 - "destructive-foreground"
Cohesion: 0.67
Nodes (3): destructive-foreground, $type, $value

### Community 142 - "muted"
Cohesion: 0.67
Nodes (3): muted, $type, $value

### Community 145 - "primary-foreground"
Cohesion: 0.67
Nodes (3): primary-foreground, $type, $value

### Community 146 - "ring"
Cohesion: 0.67
Nodes (3): ring, $type, $value

### Community 147 - "secondary-foreground"
Cohesion: 0.67
Nodes (3): secondary-foreground, $type, $value

### Community 149 - "_search_csv_detailed"
Cohesion: 0.25
Nodes (3): _search_csv(), _search_csv_detailed(), TestBm25CoreBehavior

### Community 152 - "16"
Cohesion: 0.67
Nodes (3): $type, $value, 16

### Community 153 - "_load_csv"
Cohesion: 0.25
Nodes (4): _load_csv(), _load_csv_snapshot(), _load_product_keywords(), _load_rows_or_empty()

### Community 154 - "1"
Cohesion: 0.67
Nodes (3): $type, $value, 1

### Community 156 - "3"
Cohesion: 0.67
Nodes (3): $type, $value, 3

### Community 157 - "Backend Frameworks"
Cohesion: 0.50
Nodes (4): Backend Frameworks, Framework Selection Guide, Node.js Ecosystem, Python Ecosystem

### Community 159 - "8"
Cohesion: 0.67
Nodes (3): $type, $value, 8

### Community 160 - "地端與 Quick Tunnel 錄音測試"
Cohesion: 0.33
Nodes (5): 先測一台，再測多台, 啟動, 地端與 Quick Tunnel 錄音測試, 排查與結束, 本次驗證（2026-11-09）

### Community 162 - "Windows 啟動與 Schema 修復"
Cohesion: 0.33
Nodes (5): Windows 啟動與 Schema 修復, 修改, 根因與實際連線（2026-11-17）, 目標資料庫執行計畫與風險, 驗證

### Community 165 - "register_analysis"
Cohesion: 0.70
Nodes (5): register_analysis(), authorize_session(), get_analysis(), image(), start_analysis()

## Knowledge Gaps
- **29 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `資料庫與 API` connect `網頁錄音擴充：最小侵入式交付` to `test_audio_sync.py`?**
  _High betweenness centrality (0.219) - this node is a cross-community bridge._
- **Are the 39 inferred relationships involving `yy()` (e.g. with `ad()` and `ah()`) actually correct?**
  _`yy()` has 39 INFERRED edges - model-reasoned connections that need verification._
- **Should `ShadcnInstaller` be split into smaller, more focused modules?**
  _Cohesion score 0.053555750658472345 - nodes in this community are weakly interconnected._
- **Are the 5 inferred relationships involving `create_app()` (e.g. with `authorize()` and `lifespan()`) actually correct?**
  _`create_app()` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Should `code_quality_analyzer.py` be split into smaller, more focused modules?**
  _Cohesion score 0.11494252873563218 - nodes in this community are weakly interconnected._
- **Are the 2 inferred relationships involving `TailwindConfigGenerator` (e.g. with `TestGeneratedConfigIsValidJs` and `TestTailwindConfigGenerator`) actually correct?**
  _`TailwindConfigGenerator` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Should `gray` be split into smaller, more focused modules?**
  _Cohesion score 0.05370101596516691 - nodes in this community are weakly interconnected._