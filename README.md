# TreasuryFlow (NexHack 2026 Submission)

**Track 1:** Agentic AI for Internal Enterprise Operations (Finance)

TreasuryFlow is a full-stack, agentic financial reconciliation platform built independently. It autonomously ingests, parses, and correlates multi-format financial documents—including invoices, bank statements, and payment proofs—to streamline the internal matching process and resolve operational bottlenecks. 

Designed specifically for the **NexHack 2026** physical finals at Xenber Sdn. Bhd., TreasuryFlow moves past the "demo-ware" stage. It is built for real-world enterprise operations, focusing on depth of execution, explainability, and trust.

## 💼 Business & Commercial Depth
In alignment with NexHack's philosophy, TreasuryFlow is built to be a product the market will actually pay for. 

* **The Pain Point:** Enterprise finance teams spend thousands of hours manually matching messy payment proofs (PDFs/PNGs) against bank statements and invoices. Human error leads to internal compliance risks, unflagged duplicate payments, and delayed financial closing.
* **Target Customers:** Mid-to-large enterprises, corporate finance departments, and regional logistics companies (e.g., Nusantara Logistics, Pearl Delta).
* **Commercialization & Pricing Model:**
    * **B2B SaaS Tier:** Monthly subscription based on ingestion volume (e.g., RM 2,000/month for up to 10,000 document reconciliations).
    * **Enterprise On-Prem/Private Cloud:** Custom licensing for strict internal data compliance environments, combined with implementation and integration fees.
* **Implementation Roadmap:**
    * *Phase 1 (Post-Hackathon):* Pilot testing with Xenber Sdn. Bhd.'s enterprise clients, utilizing our existing structured mock datasets to simulate local Malaysian corporate finance scenarios.
    * *Phase 2 (Months 2-4):* Integration with live ERP systems and local banking APIs.
    * *Phase 3 (Months 5-6):* Full commercial rollout focusing on the Southeast Asian enterprise market.

## 🚀 High-Impact Capabilities (Winning on Depth)
The intelligence layer goes beyond basic execution, proving a "builder mindset" by incorporating these core features necessary for enterprise trust:

* **Learned Memory (`memory.py`):** The agent reads past human corrections (e.g., `match_status='manual'` or `'rejected'`) each run so it improves with adoption. This closes the human-feedback loop and creates a strong 'autonomous workforce' story for internal operations.
* **Verifier / Self-Critique (`verifier.py`):** A second agent pass that adversarially checks its own proposed matches before commit, significantly boosting trust and accuracy within the finance department.
* **Operational Anomaly Signals (`anomaly.py`):** The agent automatically flags duplicate payments, internal transaction errors, and unmatched outliers as exceptions for human review, directly streamlining internal enterprise controls and audits.

## 🏗️ Technical Architecture & Execution
Black-box abstractions were avoided to give organizations complete "under the hood" control over the reasoning loop.

### Agentic Engine
* **Runner & Orchestrator:** Manages the step-by-step execution and coordinates data pipelines using `runner.py` and `orchestrator.py`.
* **Gate & Verifier:** Routes logical decisions and performs rigorous adversarial self-critique (`verifier.py`) to prevent LLM hallucinations before committing financial data to the ledger.
* **Memory & Prompts:** Maintains execution state across complex tasks, leveraging learned memory (`memory.py`) to adapt to past human feedback.
* **Anomaly Detection:** Secures the reconciliation pipeline by flagging duplicates and outliers (`anomaly.py`).

### Backend Infrastructure
A modular Python backend designed for heavy lifting and data processing.
* **Dedicated Parsers:** Specialized extraction logic for bank statements (`statement_parser.py`), invoices (`invoice_parser.py`), and payment proofs (`proof_parser.py`).
* **External Integrations:** Includes APIs for live data, such as Forex rates via `forex_api.py`, to handle cross-currency reconciliations.
* **Data Contracts:** Enforces strict typing and validation for all incoming financial data in `data_contracts.py`.

### Frontend Presentation
A modern web interface built with Next.js and Tailwind CSS within the `apps/frontend/` directory.
* **Authentication:** Integrated with Supabase for secure session management via `supabaseClient.ts`.
* **Interactive UI:** Features custom modular components for file uploads (`Dropzone.tsx`), activity tracking (`ActivityDrawer.tsx`), and data presentation (`Table.tsx`).

## 🧠 Deep Dive: Autonomic Agentic AI Implementation
At the core of TreasuryFlow is an autonomic agent loop designed to move beyond traditional, single-turn prompt-response systems. This architecture relies on a continuous perceive-reason-act-learn cycle that orchestrates tools, maintains persistent context, and integrates feedback to achieve complex reconciliation goals.

* **The Agentic Loop (`runner.py` & `orchestrator.py`):** Rather than blindly executing a linear script, the system utilizes a ReAct (Reasoning and Acting) loop. At each iteration, the agent processes financial context, reasons about the appropriate next action, executes a tool call, and observes the result. The orchestrator manages this continuous cycle, evaluating termination logic to determine if a successful match has been found, if a task needs re-planning, or if the process should exit after a maximum number of iterations to prevent infinite loops.
* **Layered Memory Systems (`memory.py`):** Traditional AI fails at multi-step tasks due to a lack of state continuity. TreasuryFlow implements layered memory to solve this:
    * *Working (Short-Term) Memory:* Maintains the context of the current reconciliation session, keeping track of active tool outputs, retrieved documents, and immediate reasoning steps.
    * *Learned (Procedural/Semantic) Memory:* The agent actively closes the human-feedback loop by reading past human corrections (e.g., `match_status='manual'` or `'rejected'`) during each run. This ensures the agent adapts to previous mistakes, persists learned workflows, and improves its matching logic with enterprise adoption.
* **Tool Orchestration (`tools.py`):** Autonomy requires action. The agent is equipped with specific tools that act as its actuators, allowing it to interact with the external environment rather than remaining limited to text generation. In this ecosystem, the LLM utilizes specialized data tools (`invoice_parser.py`, `statement_parser.py`) to extract structured data and calls action tools (like `forex_api.py` for cross-currency matching) to ground its reasoning in factual execution.
* **Feedback & Verification (`verifier.py` & `anomaly.py`):** To prevent unchecked hallucinations and compounding errors, the architecture embeds strict control layers. A secondary agent pass acts as an adversarial verifier, self-critiquing and validating proposed matches before committing them. Simultaneously, the anomaly module flags duplicate payments, suspicious transactions, and outliers, serving as the escalation path for human-in-the-loop (HITL) intervention when uncertainty exceeds defined limits.

## ⚙️ Getting Started (For Judges & Mentors)

### Prerequisites
* Python 3.10+
* Node.js & npm
* Supabase instance
* Docker (optional, utilizing the backend `Dockerfile`)

### Testing the Prototype
Our repository includes a comprehensive `test_files/` directory containing sample datasets for various regional corporate entities (e.g., Selangor Textiles, Nusantara Logistics, WZB Group). Use these files (CSVs, Excel files, PDFs, and PNGs) to simulate real-world, messy internal reconciliation scenarios during our live demo.