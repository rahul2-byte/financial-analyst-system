import re
import logging
import os
from pathlib import Path
from typing import Dict, List, Any

# Conditional import so the rest of the app doesn't crash if transformers isn't installed
try:
    from transformers import pipeline
    import nltk
except ImportError:
    pipeline = None
    nltk = None

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FINBERT_PATH = BACKEND_ROOT / "ai-lab" / "models" / "finbert"


class NLPScorer:
    """
    Deterministic layer for processing unstructured financial text.
    Uses FinBERT for math-based sentiment scoring and regex/NLTK for tense parsing.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(NLPScorer, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.model = None
        self._initialized = True

        # Regex patterns to detect forward-looking statements
        self.future_patterns = re.compile(
            r"\b(will|expect|anticipate|project|forecast|estimate|plan|intend|believe|target|guidance|upcoming|next quarter|future)\b",
            re.IGNORECASE,
        )

    def load_model(self):
        if self.model is None:
            if pipeline is None:
                raise ImportError(
                    "transformers is not installed. Run: pip install transformers torch"
                )

            model_path_str = os.getenv("FINBERT_MODEL_PATH", str(DEFAULT_FINBERT_PATH))
            model_path = Path(model_path_str)
            if not model_path.exists():
                raise FileNotFoundError(
                    f"FinBERT model directory not found at '{model_path}'. "
                    "Download once to backend/ai-lab/models/finbert and keep runtime offline."
                )

            # Enforce offline behavior for runtime model loading.
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

            logger.info("Loading FinBERT model...")
            self.model = pipeline(
                "sentiment-analysis",
                model=str(model_path),
                tokenizer=str(model_path),
                local_files_only=True,
            )
            logger.info("FinBERT loaded.")

    def _split_into_sentences(self, text: str) -> List[str]:
        if nltk:
            try:
                return nltk.tokenize.sent_tokenize(text)
            except LookupError:
                # Fallback if NLTK data isn't downloaded
                pass
        # Basic regex fallback for sentence splitting
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if s.strip()]

    def analyze_text(self, text: str) -> Dict[str, Any]:
        """
        Takes a raw block of text, splits it by sentence, classifies each
        as Forward-Looking or Past, and scores them using FinBERT.
        Returns aggregated deterministic statistics.
        """
        if not text:
            return {"error": "Empty text provided"}

        self.load_model()
        sentences = self._split_into_sentences(text)

        if not sentences:
            return {"error": "No valid sentences found"}

        results = {
            "overall_sentiment": {"bullish": 0, "bearish": 0, "neutral": 0, "total": 0},
            "forward_guidance_sentiment": {
                "bullish": 0,
                "bearish": 0,
                "neutral": 0,
                "total": 0,
            },
            "past_performance_sentiment": {
                "bullish": 0,
                "bearish": 0,
                "neutral": 0,
                "total": 0,
            },
            "most_polarized_sentences": [],
        }

        # Truncate sentences that are too long for FinBERT (max 512 tokens)
        truncated_sentences = [s[:1000] for s in sentences]

        # Run FinBERT on all sentences
        scores = self.model(truncated_sentences)

        all_scored_sentences = []

        for sentence, score in zip(sentences, scores):
            label = score["label"]  # 'positive', 'negative', 'neutral'
            confidence = score["score"]

            # Map FinBERT labels to our terminology
            if label == "positive":
                label = "bullish"
            elif label == "negative":
                label = "bearish"

            # Tense classification
            is_forward = bool(self.future_patterns.search(sentence))

            # Aggregate stats
            results["overall_sentiment"][label] += 1
            results["overall_sentiment"]["total"] += 1

            if is_forward:
                results["forward_guidance_sentiment"][label] += 1
                results["forward_guidance_sentiment"]["total"] += 1
            else:
                results["past_performance_sentiment"][label] += 1
                results["past_performance_sentiment"]["total"] += 1

            all_scored_sentences.append(
                {
                    "text": sentence,
                    "label": label,
                    "confidence": confidence,
                    "is_forward_looking": is_forward,
                }
            )

        # Find the top 3 most confident bullish/bearish sentences for LLM context
        polarized = [
            s for s in all_scored_sentences if s["label"] in ["bullish", "bearish"]
        ]
        polarized.sort(key=lambda x: x["confidence"], reverse=True)
        results["most_polarized_sentences"] = polarized[:5]

        # Calculate final percentages
        def calc_pct(category):
            total = results[category]["total"]
            if total == 0:
                return "No data"
            bull = (results[category]["bullish"] / total) * 100
            bear = (results[category]["bearish"] / total) * 100

            if bull > bear + 20:
                return f"Strongly Bullish ({bull:.0f}%)"
            elif bull > bear:
                return f"Slightly Bullish ({bull:.0f}%)"
            elif bear > bull + 20:
                return f"Strongly Bearish ({bear:.0f}%)"
            elif bear > bull:
                return f"Slightly Bearish ({bear:.0f}%)"
            else:
                return "Neutral / Mixed"

        return {
            "finbert_overall_score": calc_pct("overall_sentiment"),
            "finbert_guidance_score": calc_pct("forward_guidance_sentiment"),
            "finbert_past_score": calc_pct("past_performance_sentiment"),
            "total_sentences_analyzed": len(sentences),
            "key_context": results["most_polarized_sentences"],
        }
