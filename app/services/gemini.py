import json
import time
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

class BaseLLMService(ABC):
    """
    Abstract LLM service class to allow easy replacement of the LLM provider.
    """
    @abstractmethod
    def classify_categories(self, transactions: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Classifies a list of uncategorized transactions.
        Returns a dict mapping transaction ID (or string representation) to category.
        """
        pass

    @abstractmethod
    def generate_summary(
        self,
        spend_by_currency: Dict[str, float],
        top_merchants: List[Dict[str, Any]],
        anomaly_count: int
    ) -> Dict[str, Any]:
        """
        Generates a summary narrative and risk level based on aggregate metrics.
        """
        pass


class GeminiLLMService(BaseLLMService):
    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
        self.allowed_categories = {
            "Food", "Shopping", "Travel", "Transport",
            "Utilities", "Cash Withdrawal", "Entertainment", "Other"
        }

    def _call_gemini_api(self, prompt: str) -> str:
        """
        Executes a call to Gemini API with 3 retries and exponential backoff (1s, 2s, 4s).
        """
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set.")

        url = f"{self.base_url}?key={self.api_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json"
            }
        }

        # Retries with exponential backoff: 1s, 2s, 4s
        backoff = 1
        for attempt in range(4):  # 4 attempts total (1 initial + 3 retries)
            try:
                with httpx.Client(timeout=30.0) as client:
                    response = client.post(url, json=payload)
                    response.raise_for_status()
                    
                    data = response.json()
                    text_response = data["candidates"][0]["content"]["parts"][0]["text"]
                    return text_response
            except Exception as e:
                logger.warning(f"Gemini API attempt {attempt + 1} failed: {str(e)}")
                if attempt == 3:
                    # Final attempt failed
                    raise e
                time.sleep(backoff)
                backoff *= 2

        raise Exception("Failed to call Gemini API after all retries.")

    def classify_categories(self, transactions: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Batch-classifies categories for transactions.
        Returns a dictionary mapping txn_id to classified category.
        """
        if not transactions:
            return {}

        prompt = f"""
You are a financial classification assistant. Categorize these transaction records into exactly one of these allowed categories:
{', '.join(sorted(list(self.allowed_categories)))}

Input JSON array of transactions:
{json.dumps(transactions, indent=2)}

You must return a valid JSON object containing a list of mappings with keys:
- "txn_id": the transaction ID string from the input
- "category": the classified category string (MUST be exactly one of the allowed categories)

Return format:
{{
  "classifications": [
    {{"txn_id": "TXN1000", "category": "Food"}},
    ...
  ]
}}
"""
        try:
            response_text = self._call_gemini_api(prompt)
            data = json.loads(response_text)
            
            # Map response list back to dict
            classifications = data.get("classifications", [])
            result = {}
            for item in classifications:
                txn_id = item.get("txn_id")
                category = item.get("category", "Other")
                
                # Ensure the category is allowed
                if category not in self.allowed_categories:
                    category = "Other"
                
                if txn_id:
                    result[txn_id] = category
            
            # Check if all transactions are present in result, otherwise set default
            for t in transactions:
                t_id = t.get("txn_id")
                if t_id and t_id not in result:
                    result[t_id] = "Other"
                    
            return result
        except Exception as e:
            logger.error(f"Failed to classify categories: {str(e)}")
            # Raise exception, so calling code can catch it and flag llm_failed = True
            raise e

    def generate_summary(
        self,
        spend_by_currency: Dict[str, float],
        top_merchants: List[Dict[str, Any]],
        anomaly_count: int
    ) -> Dict[str, Any]:
        """
        Generates a summary narrative and risk level.
        """
        prompt = f"""
You are a financial risk analyst. Analyze the following aggregate metrics of a transaction batch and generate:
1. A narrative summary (2-3 sentences explaining spend trends, outlier counts, and overall activity).
2. A risk level assessment (must be one of: "low", "medium", or "high").

Metrics:
- Total spend by currency: {json.dumps(spend_by_currency)}
- Top 3 merchants by spend/frequency: {json.dumps(top_merchants)}
- Number of anomalies detected: {anomaly_count}

You must return a valid JSON object matching the following structure:
{{
  "total_spend_by_currency": {json.dumps(spend_by_currency)},
  "top_3_merchants": {json.dumps([m.get("merchant", m.get("name", "")) for m in top_merchants][:3])},
  "anomaly_count": {anomaly_count},
  "narrative": "A 2-3 sentence narrative describing the transaction history and risk profile.",
  "risk_level": "low"  // must be one of: "low", "medium", or "high"
}}
"""
        try:
            response_text = self._call_gemini_api(prompt)
            data = json.loads(response_text)
            
            # Basic validation of keys
            required_keys = ["total_spend_by_currency", "top_3_merchants", "anomaly_count", "narrative", "risk_level"]
            for key in required_keys:
                if key not in data:
                    raise KeyError(f"Missing required key '{key}' in LLM response")
            
            # Normalize risk level
            risk_level = str(data["risk_level"]).lower().strip()
            if risk_level not in ["low", "medium", "high"]:
                risk_level = "low"
            data["risk_level"] = risk_level
            
            return data
        except Exception as e:
            logger.error(f"Failed to generate summary: {str(e)}")
            raise e
