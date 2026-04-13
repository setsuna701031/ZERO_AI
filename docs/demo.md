\# Document Flow Demo



\## Overview



This demo shows a practical local document-processing workflow inside ZERO.



Instead of only replying in chat, ZERO reads a real input file, processes it with a local LLM pipeline, writes a useful output file, and preserves a trace file that can be inspected in the Trace Viewer.



This makes the demo closer to a real local agent workflow than a simple text-generation example.



\---



\## Current Capabilities



\### 1. Action Items Extraction



Input:

\- `input.txt`



Output:

\- `action\_items.txt`



Flow:

\- `read\_input`

\- `extract\_action\_items`

\- `write\_action\_items`



Purpose:

\- Convert meeting notes or raw project notes into clear action items with:

&#x20; - Owner

&#x20; - Task

&#x20; - Due



Example result:

\- identify named owners

\- assign `Unassigned` when no explicit owner exists

\- preserve due phrases such as:

&#x20; - `By Monday`

&#x20; - `Today`

&#x20; - `This afternoon`

&#x20; - `Tomorrow`



\---



\### 2. Document Summary



Input:

\- `input.txt`



Output:

\- `summary.txt`



Flow:

\- `read\_input`

\- `summarize\_document`

\- `write\_summary`



Purpose:

\- Convert raw notes or documents into a concise English summary for review, reporting, or fast understanding.



Example result:

\- executive summary

\- key takeaways

\- concise structured output suitable for demos and technical review



\---



\## Trace Viewer Support



Both flows generate a structured trace file:



\- `document\_flow\_trace.json`



This allows the Trace Viewer to show the actual document-processing path step by step instead of only showing a final file result.



\### Action Items Trace

\- `read\_input`

\- `extract\_action\_items`

\- `write\_action\_items`



\### Summary Trace

\- `read\_input`

\- `summarize\_document`

\- `write\_summary`



\---



\## Shared Workspace Files



Runtime demo files are written under:



\- `workspace/shared/`



Typical files:

\- `input.txt`

\- `action\_items.txt`

\- `summary.txt`

\- `document\_flow\_trace.json`



\---



\## Demo Assets



The current demo asset set includes:



\- validated action-items extraction cases

\- validated summary generation case

\- trace JSON examples

\- successful terminal execution screenshots

\- Trace Viewer screenshots



These assets are preserved under:



\- `demo\_assets/document\_flow\_demo/`



\---



\## Why This Demo Matters



This is not just a rewrite example.



It demonstrates that ZERO can:



\- read a real file

\- process non-structured text into useful outputs

\- write result files back to disk

\- preserve a machine-readable execution trace

\- support repeated multi-case validation



That gives the system a more agent-like, workflow-oriented shape instead of being only a chatbot interface.



\---



\## Validation Status



Document Flow Demo Set v1 is complete.



Completed:

\- action-items extraction flow

\- summary flow

\- trace alignment for both flows

\- multi-case validation

\- demo asset preservation



\---



\## Demo Value



This demo is useful because it is:



\- local-first

\- file-based

\- repeatable

\- inspectable through trace

\- easy to present visually



It is a strong early showcase for ZERO because the value is visible immediately:

raw notes go in, structured output comes out, and the pipeline remains observable.



\---



\## Next Possible Directions



Potential next steps:



\- unify action-items and summary into one selectable document demo entry

\- add lightweight API or UI wrappers

\- support structured JSON export

\- connect extracted action items into later task systems



For the current stage, this demo already stands as a complete and presentable document-processing capability.

