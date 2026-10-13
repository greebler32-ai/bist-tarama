from pathlib import Path
import os

def results_dir():
    configured=os.environ.get("BIST_RESULTS_DIR")
    if configured:
        out=Path(configured);out.mkdir(parents=True,exist_ok=True);return out
    out=Path(__file__).resolve().parent/"web_data"/"results"
    out.mkdir(parents=True,exist_ok=True);return out

def result_file(name):return results_dir()/name
