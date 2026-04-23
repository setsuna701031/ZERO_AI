\# Document Pipeline Observation



\## Common

\- task\_id

\- status

\- step

\- scenario

\- task\_type

\- mode

\- pipeline\_name

\- execution\_name

\- final\_answer

\- task\_dir

\- result\_path

\- plan\_path

\- runtime\_state\_path

\- execution\_log\_path

\- trace\_path

\- snapshot\_path



\## Different

\- goal（每條 pipeline 不同） :contentReference\[oaicite:0]{index=0}

\- mode（summary / action\_items / requirement）

\- pipeline\_name（summary\_pipeline / action\_items\_pipeline / requirement\_pipeline）

\- execution\_name（summary\_execution / ...）

\- final\_answer 結構不同（段落 vs 清單） :contentReference\[oaicite:1]{index=1}

\- step count 可能不同（3/3 vs 7/7）



\## Summary only

\- scenario: doc\_summary :contentReference\[oaicite:2]{index=2}

\- 單一 summary 輸出（整段文字）

\- summary\_smoke.txt 類型輸出 :contentReference\[oaicite:3]{index=3}



\## Action\_items only

\- action items 條列輸出（bullet list） :contentReference\[oaicite:4]{index=4}

\- extract action items 類型 goal :contentReference\[oaicite:5]{index=5}



\## Requirement only

\- 多檔輸出（project\_summary / implementation\_plan / acceptance\_checklist）

\- acceptance checklist 結構

\- multi-artifact pipeline（不是單一輸出）

