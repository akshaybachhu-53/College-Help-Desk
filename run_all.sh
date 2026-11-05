#!/usr/bin/env bash
# =====================================================================================
#  ONE-SHOT RUNNER: setup -> data -> index -> smoke test -> full evaluation -> results zip
#
#    bash run_all.sh            full run (both systems x both models x 3 runs, several hours)
#    bash run_all.sh --quick    fast check (multi-agent, Qwen3 only, 1 run, ~20-30 min)
#    add --fresh to move old results to eval/archive/ and start the evaluation from scratch
#
#  Safe to re-run: finished steps are skipped and the evaluation resumes where it stopped.
#  At the end, all results are packed into  results_for_report.zip  in this folder.
# =====================================================================================
set -uo pipefail
cd "$(dirname "$0")"

QUICK=0; FRESH=0
for arg in "$@"; do
  [[ "$arg" == "--quick" ]] && QUICK=1
  [[ "$arg" == "--fresh" ]] && FRESH=1
done
if [[ $FRESH == 1 && -d eval/results ]] && ls eval/results/*.jsonl >/dev/null 2>&1; then
  ts=$(date +%Y%m%d-%H%M%S); mkdir -p eval/archive
  mv eval/results "eval/archive/results_$ts"; mkdir -p eval/results
  [[ -f logs/unanswered_questions.jsonl ]] && mv logs/unanswered_questions.jsonl "eval/archive/results_$ts/"
  echo "Old results moved to eval/archive/results_$ts"
fi
LOG=run_all.log
exec > >(tee -a "$LOG") 2>&1

step() { echo; echo "================ $* ================"; }
die()  { echo; echo "ERROR: $*"; echo "See run_all.log for the full output."; exit 1; }

# ----------------------------------------------------------------- 1. system tools
step "1/8  Checking Python and Ollama"
command -v python3 >/dev/null || die "python3 not found. Install it: sudo apt install python3 python3-venv python3-pip"
python3 -c "import venv, ensurepip" 2>/dev/null || {
  echo "python3-venv missing, installing (asks for your password)..."
  sudo apt-get update && sudo apt-get install -y python3-venv python3-pip || die "could not install python3-venv"
}
if ! command -v ollama >/dev/null; then
  echo "Installing Ollama (asks for your password)..."
  command -v curl >/dev/null || sudo apt-get install -y curl
  curl -fsSL https://ollama.com/install.sh | sh || die "Ollama install failed"
fi

# ----------------------------------------------------------------- 2. ollama server
step "2/8  Starting Ollama server"
if ! curl -s http://localhost:11434/api/tags >/dev/null; then
  (nohup ollama serve > ollama_server.log 2>&1 &)
  for i in $(seq 1 30); do curl -s http://localhost:11434/api/tags >/dev/null && break; sleep 1; done
fi
curl -s http://localhost:11434/api/tags >/dev/null || die "Ollama server is not responding (see ollama_server.log)"
echo "Ollama is running."

# ----------------------------------------------------------------- 3. models
step "3/8  Downloading models (about 10 GB the first time)"
have() { ollama list | awk '{print $1}' | grep -qx "$1"; }
have nomic-embed-text:latest || ollama pull nomic-embed-text || die "could not pull nomic-embed-text"
BASES="qwen3:8b"; [[ $QUICK == 0 ]] && BASES="qwen3:8b llama3.1:8b"
for base in $BASES; do
  have "$base" || ollama pull "$base" || die "could not pull $base"
  if ! have "helpdesk-$base"; then
    printf 'FROM %s\nPARAMETER num_ctx 8192\nPARAMETER temperature 0.2\n' "$base" > .Modelfile.tmp
    ollama create "helpdesk-$base" -f .Modelfile.tmp || die "could not create helpdesk-$base"
    rm -f .Modelfile.tmp
  fi
done
ollama list

# ----------------------------------------------------------------- 4. python env
step "4/8  Python environment"
[[ -d .venv ]] || python3 -m venv .venv || die "could not create .venv"
source .venv/bin/activate
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt || die "pip install failed"
echo "Python packages installed."

# ----------------------------------------------------------------- 5. documents
step "5/8  Preparing documents"
python scripts/build_structured_data.py || die "building CSVs failed"
if ! python scripts/fetch_public_docs.py; then
  echo
  echo ">>> Some PDFs could not be downloaded automatically (list above)."
  echo ">>> Open each link in your browser, save the PDF into data/raw/ with the exact name shown,"
  echo ">>> then run this script again. Continuing now with the documents that are present."
  read -t 20 -p "Press Enter to continue (auto-continues in 20 s)... " || true
  echo
fi

# ----------------------------------------------------------------- 6. index
step "6/8  Building the vector index"
NDOCS=$(ls data/raw | wc -l)
if [[ -d vector_store && -f .indexed_docs && "$(cat .indexed_docs)" == "$NDOCS" ]]; then
  echo "Index already up to date ($NDOCS documents)."
else
  python scripts/ingest.py || die "indexing failed"
  echo "$NDOCS" > .indexed_docs
fi

# ----------------------------------------------------------------- 7. smoke test
step "7/8  Smoke test (4 questions)"
rm -f eval/results/smoke_traces.jsonl
python eval/run_eval.py --system multi --models helpdesk-qwen3:8b --runs 1 \
  --ids Q07 Q13 Q22 Q25 --out eval/results/smoke_traces.jsonl || die "smoke test crashed"
if ! grep -q '"error": null' eval/results/smoke_traces.jsonl; then
  die "every smoke-test question failed; see the errors above"
fi
echo "Smoke test passed. Starting the evaluation."

# ----------------------------------------------------------------- 8. evaluation
step "8/8  Evaluation"
START=$(date +%s)
if [[ $QUICK == 1 ]]; then
  python eval/run_eval.py --system multi --models helpdesk-qwen3:8b --runs 1
else
  # multi-agent first (the main result), then the single-agent baseline
  python eval/run_eval.py --system multi  --models helpdesk-qwen3:8b helpdesk-llama3.1:8b --runs 3
  python eval/run_eval.py --system single --models helpdesk-qwen3:8b helpdesk-llama3.1:8b --runs 3
fi
python eval/score.py || die "scoring failed"
echo "Evaluation took $(( ($(date +%s) - START) / 60 )) minutes."

# ----------------------------------------------------------------- package results
nvidia-smi --query-gpu=name,memory.total --format=csv > eval/results/hardware.txt 2>/dev/null || true
free -h >> eval/results/hardware.txt 2>/dev/null || true
rm -f results_for_report.zip
python - <<'EOF'
import zipfile, pathlib
with zipfile.ZipFile("results_for_report.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for p in list(pathlib.Path("eval/results").glob("*")) + list(pathlib.Path("logs").rglob("*")) + [pathlib.Path("run_all.log")]:
        if p.is_file() and p.name != ".gitkeep":
            z.write(p)
print("created results_for_report.zip")
EOF
echo
echo "DONE. Results packed into:  $(pwd)/results_for_report.zip"
