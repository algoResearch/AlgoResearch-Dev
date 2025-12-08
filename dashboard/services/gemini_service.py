"""
Google Gemini AI Service for AlgoResearch

This module provides integration with Google's Gemini AI API for various
AI-powered features throughout the application.
"""

import google.generativeai as genai
from django.conf import settings
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class GeminiService:
    """
    Service class for interacting with Google Gemini AI.

    Usage:
        service = GeminiService()
        response = service.generate_text("Write a summary of...")
    """

    def __init__(self, model_name: str = "gemini-flash-latest"):
        """
        Initialize the Gemini service.

        Args:
            model_name: The Gemini model to use (default: gemini-flash-latest)
        """
        if not settings.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not configured in settings")
            self.configured = False
            return

        try:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self.model = genai.GenerativeModel(model_name)
            self.configured = True
            logger.info(f"Gemini service initialized with model: {model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini service: {e}")
            self.configured = False

    def is_configured(self) -> bool:
        """Check if the service is properly configured."""
        return self.configured

    def generate_text(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_output_tokens: int = 2048,
        top_p: float = 0.95,
        top_k: int = 40
    ) -> Optional[str]:
        """
        Generate text using Gemini.

        Args:
            prompt: The input prompt for generation
            temperature: Controls randomness (0.0-1.0)
            max_output_tokens: Maximum length of generated text
            top_p: Nucleus sampling parameter
            top_k: Top-k sampling parameter

        Returns:
            Generated text or None if generation fails
        """
        if not self.configured:
            logger.error("Gemini service not configured")
            return None

        try:
            generation_config = genai.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                top_p=top_p,
                top_k=top_k,
            )

            response = self.model.generate_content(
                prompt,
                generation_config=generation_config
            )

            return response.text
        except Exception as e:
            logger.error(f"Error generating text with Gemini: {e}")
            return None

    def generate_with_context(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_output_tokens: int = 2048
    ) -> Optional[str]:
        """
        Generate text with conversation context.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
                     Example: [{"role": "user", "content": "Hello"}]
            temperature: Controls randomness (0.0-1.0)
            max_output_tokens: Maximum length of generated text

        Returns:
            Generated text or None if generation fails
        """
        if not self.configured:
            logger.error("Gemini service not configured")
            return None

        try:
            # Convert messages to Gemini format
            chat = self.model.start_chat(history=[])

            # Add all messages except the last one to history
            for msg in messages[:-1]:
                role = "user" if msg["role"] == "user" else "model"
                chat.history.append({
                    "role": role,
                    "parts": [msg["content"]]
                })

            # Send the last message
            response = chat.send_message(
                messages[-1]["content"],
                generation_config=genai.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                )
            )

            return response.text
        except Exception as e:
            logger.error(f"Error generating with context: {e}")
            return None

    def summarize_text(self, text: str, max_length: int = 500) -> Optional[str]:
        """
        Summarize the given text.

        Args:
            text: Text to summarize
            max_length: Maximum length of summary in words

        Returns:
            Summary text or None if summarization fails
        """
        prompt = f"""Please provide a concise summary of the following text in no more than {max_length} words:

{text}

Summary:"""

        return self.generate_text(prompt, temperature=0.3, max_output_tokens=1024)

    def analyze_sentiment(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Analyze the sentiment of the given text.

        Args:
            text: Text to analyze

        Returns:
            Dict with sentiment analysis or None if analysis fails
        """
        prompt = f"""Analyze the sentiment of the following text and respond with ONLY a JSON object containing:
- "sentiment": "positive", "negative", or "neutral"
- "confidence": a number between 0 and 1
- "reasoning": brief explanation

Text: {text}

JSON:"""

        try:
            response = self.generate_text(prompt, temperature=0.2, max_output_tokens=256)
            if response:
                import json
                # Extract JSON from response (in case there's extra text)
                start = response.find('{')
                end = response.rfind('}') + 1
                if start >= 0 and end > start:
                    return json.loads(response[start:end])
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}")

        return None

    def extract_keywords(self, text: str, max_keywords: int = 10) -> Optional[List[str]]:
        """
        Extract key topics/keywords from text.

        Args:
            text: Text to extract keywords from
            max_keywords: Maximum number of keywords to extract

        Returns:
            List of keywords or None if extraction fails
        """
        prompt = f"""Extract the {max_keywords} most important keywords or key phrases from the following text.
Return ONLY the keywords as a comma-separated list, nothing else.

Text: {text}

Keywords:"""

        try:
            response = self.generate_text(prompt, temperature=0.2, max_output_tokens=256)
            if response:
                # Clean and split the response
                keywords = [kw.strip() for kw in response.split(',')]
                return keywords[:max_keywords]
        except Exception as e:
            logger.error(f"Error extracting keywords: {e}")

        return None

    def generate_research_suggestions(
        self,
        research_area: str,
        current_focus: str = None
    ) -> Optional[str]:
        """
        Generate research suggestions for a given area.

        Args:
            research_area: The research area/topic
            current_focus: Current research focus (optional)

        Returns:
            Research suggestions or None if generation fails
        """
        focus_text = f"\nCurrent focus: {current_focus}" if current_focus else ""

        prompt = f"""As a research advisor, suggest 5 innovative research directions for the following area:

Research Area: {research_area}{focus_text}

Please provide:
1. Novel research questions
2. Potential methodologies
3. Expected impact

Suggestions:"""

        return self.generate_text(prompt, temperature=0.8, max_output_tokens=2048)


# Singleton instance
_gemini_service = None

def get_gemini_service() -> GeminiService:
    """
    Get or create the Gemini service singleton instance.

    Returns:
        GeminiService instance
    """
    global _gemini_service
    if _gemini_service is None:
        _gemini_service = GeminiService()
    return _gemini_service
