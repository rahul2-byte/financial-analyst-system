from pathlib import Path


def main() -> None:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    backend_root = Path(__file__).resolve().parents[1]
    target_dir = backend_root / "ai-lab" / "models" / "finbert"
    target_dir.mkdir(parents=True, exist_ok=True)

    model_id = "ProsusAI/finbert"
    print(f"Downloading {model_id} to {target_dir} ...")

    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForSequenceClassification.from_pretrained(model_id)

    tokenizer.save_pretrained(target_dir)
    model.save_pretrained(target_dir)

    print("FinBERT download complete.")


if __name__ == "__main__":
    main()
