\# Document Flow Demo



ZERO currently includes a local document-processing demo set focused on practical file workflows.



This demo shows that ZERO can take a plain text input file, process it with a local LLM pipeline, generate structured output, and write a trace file that can be inspected in the Trace Viewer.



\---



\## Current Demo Capabilities



\### 1. Action Items Extraction

Input:

\- `input.txt`



Output:

\- `action\_items.txt`



Flow:

\- `read\_input`

\- `extract\_action\_items`

\- `write\_action\_items`



Use case:

\- Convert meeting notes or raw project notes into clear action items with:

&#x20; - Owner

&#x20; - Task

&#x20; - Due



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



Use case:

\- Convert raw notes or documents into a concise English summary for review or reporting.



\---



\## Trace Viewer Support



Both demo flows write a structured trace file:



\- `document\_flow\_trace.json`



This allows the Trace Viewer to display the document-processing pipeline step by step instead of only showing a final output file.



Examples of trace steps:



\### Action Items Flow

\- `read\_input`

\- `extract\_action\_items`

\- `write\_action\_items`



\### Summary Flow

\- `read\_input`

\- `summarize\_document`

\- `write\_summary`



\---



\## Demo Input / Output Location



Shared demo files are stored under:



\- `workspace/shared/`



Typical files:

\- `input.txt`

\- `action\_items.txt`

\- `summary.txt`

\- `document\_flow\_trace.json`



\---



\## Example Demo Assets



Validated demo cases currently include:

\- multiple action-items extraction examples

\- summary generation examples

\- successful terminal execution screenshots

\- Trace Viewer screenshots



These assets can be used later for:

\- README

\- GitHub demo section

\- product walkthrough

\- technical showcase material



\---



\## Why This Demo Matters



This is not just a text rewrite example.



It demonstrates that ZERO can:



\- read a real file

\- perform structured document processing

\- write useful output files

\- preserve a machine-readable execution trace



That makes it closer to a real local agent workflow than a simple chat response.



\---



\## Current Status



Document Flow Demo Set v1 is complete.



Completed:

\- action-items extraction flow

\- summary flow

\- trace alignment for both flows

\- multi-case validation

\- demo asset preservation



Next possible directions:

\- unify both flows into a single selectable document demo entry

\- add a lightweight API or UI wrapper

\- expand to structured JSON export or task import

