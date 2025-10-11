"""AI-based photo analysis for apartment condition evaluation."""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Literal, Optional

import httpx

LOGGER = logging.getLogger(__name__)


class AIProvider(str, Enum):
    """Supported AI providers."""
    
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


@dataclass
class ConditionRating:
    """Apartment condition rating from AI analysis."""
    
    listing_id: int
    condition_score: int  # 1-5
    condition_label: Literal["excellent", "good", "fair", "poor", "very_poor"]
    ai_model: str
    ai_analysis: str
    confidence: float
    
    # Details
    repair_quality: Optional[str] = None
    cleanliness: Optional[str] = None
    modern_design: bool = False
    needs_renovation: bool = False
    
    # Metadata
    cost_usd: float = 0.0
    processing_time_sec: float = 0.0
    
    def to_dict(self):
        return {
            "listing_id": self.listing_id,
            "condition_score": self.condition_score,
            "condition_label": self.condition_label,
            "ai_model": self.ai_model,
            "ai_analysis": self.ai_analysis,
            "confidence": self.confidence,
            "repair_quality": self.repair_quality,
            "cleanliness": self.cleanliness,
            "modern_design": self.modern_design,
            "needs_renovation": self.needs_renovation,
            "cost_usd": self.cost_usd,
            "processing_time_sec": self.processing_time_sec,
        }


class PhotoAnalyzer:
    """Analyze apartment photos using AI vision models."""
    
    # Prompt template for condition analysis
    ANALYSIS_PROMPT = """Оцени состояние квартиры по фотографии по шкале от 1 до 5:

1 - Очень плохое (требует капитального ремонта, старая отделка, видимые дефекты)
2 - Плохое (требует ремонта, устаревшая отделка, значительный износ)
3 - Удовлетворительное (жилое состояние, но не новое, небольшой износ)
4 - Хорошее (современный ремонт, качественная отделка, минимальный износ)
5 - Отличное (новый/свежий ремонт, премиум отделка, дизайнерский интерьер)

Ответь СТРОГО в формате JSON (без markdown):
{
  "condition_score": 1-5,
  "condition_label": "excellent|good|fair|poor|very_poor",
  "repair_quality": "excellent|good|average|poor",
  "cleanliness": "excellent|good|average|poor",
  "modern_design": true|false,
  "needs_renovation": true|false,
  "confidence": 0.0-1.0,
  "analysis": "Краткое описание на русском (макс 2 предложения)"
}"""
    
    def __init__(
        self,
        provider: AIProvider = AIProvider.OPENAI,
        *,
        api_key: Optional[str] = None,
    ):
        """Initialize photo analyzer.
        
        Parameters
        ----------
        provider : AIProvider
            AI provider to use
        api_key : str, optional
            API key (defaults to env var)
        """
        self.provider = provider
        
        if provider == AIProvider.OPENAI:
            self.api_key = api_key or os.getenv("OPENAI_API_KEY")
            if not self.api_key:
                raise ValueError("OPENAI_API_KEY not set")
            self.model = "gpt-4-vision-preview"
            self.cost_per_image = 0.00425  # Low detail mode
        elif provider == AIProvider.ANTHROPIC:
            self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
            if not self.api_key:
                raise ValueError("ANTHROPIC_API_KEY not set")
            self.model = "claude-3-5-sonnet-20241022"
            self.cost_per_image = 0.0048
    
    def analyze_condition(
        self,
        listing_id: int,
        photo_url: str,
        *,
        detail: str = "low",
    ) -> ConditionRating:
        """Analyze apartment condition from photo.
        
        Parameters
        ----------
        listing_id : int
            Listing ID
        photo_url : str
            URL of apartment photo
        detail : str
            Detail level for OpenAI ("low" or "high")
            
        Returns
        -------
        ConditionRating
            Condition rating with analysis
        """
        start_time = time.time()
        
        try:
            if self.provider == AIProvider.OPENAI:
                result = self._analyze_openai(photo_url, detail)
            else:
                result = self._analyze_claude(photo_url)
            
            processing_time = time.time() - start_time
            
            return ConditionRating(
                listing_id=listing_id,
                condition_score=result["condition_score"],
                condition_label=result["condition_label"],
                ai_model=self.model,
                ai_analysis=result["analysis"],
                confidence=result.get("confidence", 0.8),
                repair_quality=result.get("repair_quality"),
                cleanliness=result.get("cleanliness"),
                modern_design=result.get("modern_design", False),
                needs_renovation=result.get("needs_renovation", False),
                cost_usd=self.cost_per_image,
                processing_time_sec=processing_time,
            )
            
        except Exception as e:
            LOGGER.error(f"Failed to analyze listing {listing_id}: {e}")
            raise
    
    def _analyze_openai(self, photo_url: str, detail: str = "low") -> dict:
        """Analyze using OpenAI GPT-4 Vision."""
        url = "https://api.openai.com/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self.ANALYSIS_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": photo_url,
                                "detail": detail,  # "low" for cost savings!
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 300,
            "temperature": 0.3,
        }
        
        response = httpx.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        
        # Parse JSON response
        # Remove markdown if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        result = json.loads(content.strip())
        return result
    
    def _analyze_claude(self, photo_url: str) -> dict:
        """Analyze using Anthropic Claude."""
        url = "https://api.anthropic.com/v1/messages"
        
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        
        # Download image and encode (Claude requires base64)
        img_response = httpx.get(photo_url, timeout=30)
        img_response.raise_for_status()
        
        import base64
        img_base64 = base64.b64encode(img_response.content).decode()
        
        # Determine media type
        content_type = img_response.headers.get("content-type", "image/jpeg")
        
        payload = {
            "model": self.model,
            "max_tokens": 300,
            "temperature": 0.3,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self.ANALYSIS_PROMPT},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": content_type,
                                "data": img_base64,
                            }
                        }
                    ]
                }
            ]
        }
        
        response = httpx.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        
        data = response.json()
        content = data["content"][0]["text"]
        
        # Parse JSON response
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        result = json.loads(content.strip())
        return result

