# Task 11 coaching UI verification

The UI was inspected in the Codex in-app browser against a temporary local Vite fixture using the production Vue components and stylesheet. The temporary preview files were removed after inspection. Captures are in this task's browser tool output, rather than checked-in PNG files; they contain only fabricated training data.

| Capture | Viewport | Result |
| --- | --- | --- |
| Rich advice and review | Desktop default, then 390 × 844 mobile | Conclusion → interpretation → action reading order; review shows one seven-day score; segments open under the selected result. |
| Rules fallback | 390 × 844 | “規則產生” appears separately from coverage. |
| Partial detail | 390 × 844 | Expanded evidence says “推估配對”, “部分涵蓋”, and “圖表抽樣”; missing channels are named. |
| Stale result | 390 × 844 | The original conclusion remains with a visible “資料已更新” status. |
| Legacy result | 390 × 844 | The original guidance text remains; no structured fields are invented. |

The first mobile capture revealed a detached action arrow above wrapped text. The action row was changed to a two-column grid and recaptured at 390 × 844; the arrow now stays beside the action. Native tabs and disclosure controls were visible and operable. The browser viewport override was reset after inspection.

Automated checks: frontend Vitest 192 passed; backend pytest 917 passed, 11 PostgreSQL-only skipped, 2 existing warnings; production build and token verification passed. The premium UI static audit reported zero findings. This task did not use the live athlete database or deploy the UI.
