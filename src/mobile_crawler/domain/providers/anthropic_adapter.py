"""Anthropic (Claude) AI model adapter."""

import base64
import json
from typing import Any, Dict, Optional, Tuple

import anthropic

from mobile_crawler.domain.model_adapters import ModelAdapter


class AnthropicAdapter(ModelAdapter):
    """Adapter for Anthropic Claude AI models."""

    def __init__(self):
        """Initialize Anthropic adapter."""
        self._client: Optional[anthropic.Anthropic] = None
        self._model_config: Dict[str, Any] = {}

    def initialize(self, model_config: Dict[str, Any], safety_settings: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the Anthropic client.

        Args:
            model_config: Configuration with 'api_key' and 'model'
            safety_settings: Unused for Anthropic
        """
        self._client = anthropic.Anthropic(api_key=model_config['api_key'])
        self._model_config = model_config

    def generate_response(self, system_prompt: str, user_prompt: str) -> Tuple[str, Dict[str, Any]]:
        """Generate response from Claude model.

        Args:
            system_prompt: System prompt text
            user_prompt: User prompt as JSON string (may contain base64 screenshot)

        Returns:
            Tuple of (response_text, metadata)
        """
        image_fields = ("screenshot", "before", "after")
        images: list[str] = []
        text_payload = user_prompt
        try:
            user_data = json.loads(user_prompt)
            if isinstance(user_data, dict):
                found_image = False
                for field in image_fields:
                    value = user_data.get(field)
                    if value:
                        # Validate it decodes; pass through original base64 to Anthropic
                        base64.b64decode(value)
                        images.append(value)
                        user_data[field] = None
                        found_image = True
                if found_image:
                    text_payload = json.dumps(user_data)
        except (json.JSONDecodeError, ValueError):
            pass

        content = [{"type": "text", "text": text_payload}]
        for image_b64 in images:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": image_b64,
                },
            })

        model = self._model_config.get('model') or self._model_config.get('model_name')
        if not model:
            raise ValueError("No model specified in configuration")

        max_tokens = self._model_config.get('max_tokens', 4096)

        response = self._client.messages.create(
            model=model,
            system=system_prompt,
            messages=[{"role": "user", "content": content}],
            max_tokens=max_tokens,
        )

        if not response.content:
            raise ValueError("Empty content in Anthropic response")

        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        if not text:
            raise ValueError("Empty text in Anthropic response")

        metadata = {
            'token_usage': {
                'input_tokens': response.usage.input_tokens,
                'output_tokens': response.usage.output_tokens,
                'total_tokens': response.usage.input_tokens + response.usage.output_tokens,
            }
        }

        return text, metadata

    @property
    def model_info(self) -> Dict[str, Any]:
        """Get model information.

        Returns:
            Dictionary with model details
        """
        return {
            'provider': 'anthropic',
            'model': self._model_config.get('model') or self._model_config.get('model_name'),
            'supports_vision': True,
            'api_version': 'messages',
        }
