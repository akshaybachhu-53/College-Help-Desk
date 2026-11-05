# IIT Jodhpur Academic Helpdesk — multi-agent RAG assistant

A local helpdesk that answers questions about IIT Jodhpur academic programmes, curriculum,
rules and regulations, the academic calendar and this semester's courses and slots, and drafts
leave / make-up-exam e-mails to course instructors. It cites the document every answer comes
from, refuses questions it cannot answer from its documents, and logs those questions for a human.

Everything runs on a laptop (tested target: Linux, 16 GB RAM, RTX 3050):
Google ADK for the agents, Ollama for the 8B chat model and the embedding model (through ADK's
LiteLLM connector), ChromaDB + BM25 for retrieval.

**Team:** Bachhu Akshay (B23ES1010), Tushar Kant (B23ES1033), Venu (B23CM1012), Sravanth Naik (B23CM1010)

## Architecture

```
student ──► helpdesk_orchestrator ──transfer──► policy_agent    search_academic_documents
                │                               schedule_agent  lookup_course, list_courses,
                │                                               get_slot_timings, search_academic_documents
                │                               email_agent     get_instructor_contact, save_email_draft
                └─ out of scope ──► fixed refusal + log_unanswered_question  (every agent has this tool)
```

| Tool | What it does | Data |
|---|---|---|
| `search_academic_documents` | hybrid search (dense nomic-embed-text + BM25, reciprocal-rank fusion), returns passages with `cite_as` and a relevance flag | ChromaDB index of 17 documents |
| `lookup_course` | course by code or name → slot, instructor, credits, L-T-P | `data/structured/courses.csv` (597 rows, 20 department sheets) |
| `list_courses` | filter and count by department / level / category / slot | same |
| `get_slot_timings` | days and times of a slot | `data/structured/slot_timings.csv` |
| `get_instructor_contact` | instructor(s) and e-mail for a course | courses + `faculty_directory.csv` (**dummy** e-mail IDs) |
| `save_email_draft` | writes a draft to `logs/email_drafts/` (never sent) | — |
| `log_unanswered_question` | appends to `logs/unanswered_questions.jsonl` | — |

The single-agent baseline (`build_single_agent`) has the same tools in one agent.
The runner also logs any refusal the model forgot to log (marked `"logged_by": "runner"`).

## Documents (`data/manifest.csv`)

20 sources: 17 text documents in the vector store and 3 tables served by tools.

* Provided by the team: Academic Calendar AY 2026-27, revised UG curriculum B.Tech. CSE, Fee structure
  AY 2026-27, Institute Holidays 2026 notification (scanned → transcribed to Markdown), the
  AY 2026-27 Sem I slot-system and finalized-courses spreadsheets, the registration notice text.
* Downloaded from iitj.ac.in by `scripts/fetch_public_docs.py`: Academic Programmes Rules & Regulations
  (2019 onwards), PG Regulations 2022, B.Tech. Regulations 2018 and 2014 (**superseded**, kept on purpose),
  Executive academic calendar 2026-27, older ME and Systems-Science curricula (superseded), Ph.D. ME
  curriculum, MME regulations copy.
* Web page snapshots: list of academic programmes, B.Tech. programme page.
* Personal data: real faculty e-mail IDs are replaced by `firstname.lastname@iitj-dummy.ac.in`.

## Quick start (one command)

```bash
git clone https://github.com/akshaybachhu-53/College-Help-Desk.git && cd College-Help-Desk
bash run_all.sh --quick     # ~30 min sanity run: multi-agent, Qwen3, 1 run
bash run_all.sh             # full evaluation: 2 systems x 2 models x 3 runs (several hours)
```

`run_all.sh` installs Ollama and the models, creates the Python environment, downloads the public
PDFs, builds the index, runs a 4-question smoke test, runs the evaluation, scores it and packs
everything into `results_for_report.zip`. It is safe to re-run; finished steps are skipped.

## Setup (manual, step by step)

```bash
# 1. Ollama (https://ollama.com/download) and models
curl -fsSL https://ollama.com/install.sh | sh
./scripts/setup_ollama.sh            # pulls qwen3:8b, llama3.1:8b, nomic-embed-text; creates helpdesk-* (8K ctx)

# 2. Python environment (3.10+)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Data
python scripts/build_structured_data.py   # xlsx -> CSVs (already done; re-run if you change the xlsx)
python scripts/fetch_public_docs.py       # downloads the public PDFs into data/raw/
python scripts/ingest.py                  # chunks + embeds into ./vector_store
```

If `fetch_public_docs.py` cannot download a file, it prints the link; open it in a browser and save
the PDF into `data/raw/` with the name shown, then run `ingest.py` again.

## Use

```bash
python chat.py --trace                       # multi-agent, prints agents + tool calls
python chat.py --system single               # baseline
python chat.py --model helpdesk-llama3.1:8b
adk web                                      # ADK dev UI; pick helpdesk_multi or helpdesk_single
```

## Evaluation

```bash
# 30 questions x 3 runs. Roughly 20-40 s per question on an RTX 3050, so ~1 h per model per system.
python eval/run_eval.py --system multi  --models helpdesk-qwen3:8b helpdesk-llama3.1:8b --runs 3
python eval/run_eval.py --system single --models helpdesk-qwen3:8b --runs 3
python eval/score.py
```

Outputs in `eval/results/`: `raw_traces.jsonl` (answers, tool calls, agents, latency),
`per_question.csv`, `summary.md` (accuracy, groundedness, refusal, routing, latency),
`unstable_questions.csv` (questions whose answers changed across runs).
The run is resumable: re-running skips finished items.
Automatic scoring is string/regex based; spot-check `per_question.csv`, put 1/0 in `manual_override`
where needed, and re-run `score.py`.

Question set with hand-checked expected answers: `eval/questions.md`.

## Layout

```
helpdesk/          config, tools, agents, runner, rag/ (documents, embeddings, store), departments
helpdesk_multi/    ADK entry point (root_agent = orchestrator)
helpdesk_single/   ADK entry point (root_agent = single agent)
scripts/           build_structured_data, fetch_public_docs, ingest, setup_ollama.sh
data/              raw/ (documents), structured/ (CSVs), source_xlsx/, originals/, manifest.csv
eval/              questions.jsonl/.md, run_eval.py, score.py, results/
logs/              unanswered_questions.jsonl, email_drafts/
```

## Known limitations

* The courses list has no codes for some rows (e.g. ME 3rd-year courses); those are found by name only.
* Department categories are filled inconsistently in the source sheets (SoLA leaves most electives blank),
  so "how many electives" counts depend on how a department labelled its courses.
* Slot timings cover the 2nd-year-onwards grid; first-year (AF, AG, …) and executive (Y*) slots are not mapped.
* The academic calendar lists two different "last date of course withdrawal request" values for Semester I
  (1 Oct and 12 Oct 2026); the helpdesk reports whichever passage it retrieves.

## Results (in `eval/results/`)

After manual review of the automatic grades (see `manual_override` in `per_question.csv`):

| Setup | Model | Accuracy | Groundedness | Correct refusals | Median latency |
|---|---|---|---|---|---|
| Multi-agent | Qwen3-8B | 91% | 100% | 100% | 59 s |
| Single agent | Qwen3-8B | 87% | 100% | 95% | 47 s |
| Multi-agent | Llama 3.1-8B | 83% | 90% | 100% | 6 s |
| Single agent | Llama 3.1-8B | 79% | 93% | 100% | 5 s |

`eval/archive/first_quick_run_v1/` holds the first run before the prompt and tool fixes described in the report.
