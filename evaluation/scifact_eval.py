import os
import io
import json
import tarfile
import urllib.request
import logging
import argparse
from pathlib import Path
from src.config import settings
from src.detection.nli_scorer import NLIScorer

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path("data/scifact")
RESULTS_DIR = Path("evaluation/results")

def download_scifact_dataset():
    """Download and extract the SciFact dataset if it doesn't exist."""
    if DATA_DIR.exists() and ((DATA_DIR / "corpus.jsonl").exists() or (DATA_DIR / "data" / "corpus.jsonl").exists()):
        logger.info("SciFact dataset already exists locally.")
        return
        
    url = "https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz"
    logger.info(f"Downloading SciFact dataset from {url}...")
    
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with urllib.request.urlopen(url) as response:
            with tarfile.open(fileobj=io.BytesIO(response.read()), mode="r:gz") as tar:
                tar.extractall(path=DATA_DIR)
        logger.info("SciFact dataset downloaded and extracted successfully.")
    except Exception as e:
        logger.error(f"Failed to download SciFact dataset: {e}")
        raise

def load_corpus() -> dict[int, list[str]]:
    """Load doc_id -> list of abstract sentences from corpus.jsonl."""
    corpus = {}
    corpus_path = DATA_DIR / "corpus.jsonl"
    # Fallback to subdirectory if nested in extraction
    if not corpus_path.exists():
        corpus_path = DATA_DIR / "data" / "corpus.jsonl"
        
    with open(corpus_path, "r", encoding="utf-8") as f:
        for line in f:
            doc = json.loads(line)
            corpus[doc["doc_id"]] = doc["abstract"]
            
    return corpus

def load_claim_evidence_pairs(corpus: dict[int, list[str]]) -> tuple[list[tuple[str, str]], list[str]]:
    """Load claim-evidence sentence pairs and their gold labels (SUPPORT/CONTRADICT)."""
    claims_path = DATA_DIR / "claims_dev.jsonl"
    if not claims_path.exists():
        claims_path = DATA_DIR / "data" / "claims_dev.jsonl"
        
    pairs = []
    labels = []
    
    with open(claims_path, "r", encoding="utf-8") as f:
        for line in f:
            claim = json.loads(line)
            claim_text = claim["claim"]
            evidence = claim.get("evidence", {})
            
            for doc_id_str, ev_list in evidence.items():
                doc_id = int(doc_id_str)
                abstract = corpus.get(doc_id)
                if not abstract:
                    continue
                    
                for ev_set in ev_list:
                    label = ev_set["label"]  # "SUPPORT" or "CONTRADICT"
                    sent_indices = ev_set["sentences"]
                    
                    # Concatenate the evidence sentences
                    evidence_text = " ".join([abstract[i] for i in sent_indices])
                    pairs.append((claim_text, evidence_text))
                    labels.append(label)
                    
    return pairs, labels

def main():
    parser = argparse.ArgumentParser(
        description="Evaluate the RSCE NLI contradiction detector on the SciFact dev benchmark.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Number of pairs to evaluate. 0 = full dataset (recommended for README reporting).",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help=(
            "NLI contradiction threshold override. "
            "Defaults to settings.nli_contradiction_threshold from config."
        ),
    )
    args = parser.parse_args()

    # Allow CLI --threshold to override the value in settings/config
    threshold = args.threshold if args.threshold is not None else settings.nli_contradiction_threshold


    download_scifact_dataset()
    corpus = load_corpus()
    pairs, labels = load_claim_evidence_pairs(corpus)
    
    if args.limit > 0:
        pairs = pairs[:args.limit]
        labels = labels[:args.limit]
        logger.info(f"Evaluating a representative sample of {len(pairs)} claim-evidence pairs from SciFact dev set.")
    else:
        logger.info(f"Evaluating all {len(pairs)} claim-evidence pairs from SciFact dev set.")
    
    # 2. Run NLI scoring on the pairs
    logger.info("Initializing NLIScorer and evaluating pairs...")
    scorer = NLIScorer()
    nli_results = scorer.score_pairs(pairs)
    
    # 3. Compute precision, recall, and F1 metrics for CONTRADICT (REFUTES) label
    tp, fp, fn, tn = 0, 0, 0, 0
    
    for res, true_label in zip(nli_results, labels):
        # We classify as CONTRADICT if contradiction score meets threshold
        pred_contradict = res.contradiction >= threshold
        is_true_contradict = true_label == "CONTRADICT"
        
        if pred_contradict and is_true_contradict:
            tp += 1
        elif pred_contradict and not is_true_contradict:
            fp += 1
        elif not pred_contradict and is_true_contradict:
            fn += 1
        else:
            tn += 1
            
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    
    # Print results to stdout
    print(f"\nSciFact Evaluation Results (Threshold: {threshold}):")
    print("==================================================")
    print(f"Total Pairs Evaluated: {len(pairs)}")
    print(f"True Positives (TP):  {tp}")
    print(f"False Positives (FP): {fp}")
    print(f"False Negatives (FN): {fn}")
    print(f"True Negatives (TN):  {tn}")
    print(f"Precision:            {precision:.4f} (Target: >= 70%)")
    print(f"Recall:               {recall:.4f} (Target: >= 55%)")
    print(f"F1-Score:             {f1:.4f}")
    
    # 4. Save results to evaluation/results/scifact_results.json
    os.makedirs(RESULTS_DIR, exist_ok=True)
    # Name the result file to reflect whether this was a full-dataset or sample run
    suffix = f"_n{len(pairs)}" if args.limit > 0 else "_full"
    results_path = RESULTS_DIR / f"scifact_results{suffix}.json"
    
    results_data = {
        "threshold": threshold,
        "total_pairs": len(pairs),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "true_negatives": tn,
        "precision": precision,
        "recall": recall,
        "f1_score": f1
    }
    
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results_data, f, indent=2)
        
    logger.info(f"Results successfully saved to {results_path}")

if __name__ == "__main__":
    main()
