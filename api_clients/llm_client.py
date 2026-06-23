"""
LLM client wrapper for OpenAI and Anthropic APIs
"""
from typing import Literal, Optional, Dict, List
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic


class LLMClient:
    """Unified interface for LLM APIs"""

    def __init__(
        self,
        provider: Literal['openai', 'anthropic'] = 'openai',
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        self.provider = provider

        if provider == 'openai':
            kwargs = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            self.client = AsyncOpenAI(**kwargs)
            self.model = model or 'gpt-4'
        elif provider == 'anthropic':
            self.client = AsyncAnthropic(api_key=api_key)
            self.model = model or 'claude-3-5-sonnet-20241022'
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> str:
        """
        Complete a prompt using the configured LLM

        Args:
            prompt: The user prompt
            system_prompt: System message (optional)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Generated text completion
        """
        if self.provider == 'openai':
            return await self._complete_openai(
                prompt, system_prompt, temperature, max_tokens
            )
        elif self.provider == 'anthropic':
            return await self._complete_anthropic(
                prompt, system_prompt, temperature, max_tokens
            )

    async def _complete_openai(
        self,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int
    ) -> str:
        """OpenAI completion"""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        # Newer models (GPT-5, o-series) use max_completion_tokens instead of max_tokens
        uses_new_param = any([
            self.model.startswith("gpt-5"),
            self.model.startswith("o3-"),
            self.model.startswith("o4-"),
            self.model.startswith("o1-")
        ])

        # Newer models (GPT-5, o-series) don't support custom temperature
        # They only support temperature=1 (default)
        skip_temperature = any([
            self.model.startswith("gpt-5"),  # GPT-5 models
            self.model.startswith("o1-"),     # o1 reasoning models
            self.model.startswith("o3-"),     # o3 reasoning models
            self.model.startswith("o4-")      # o4 reasoning models
        ])

        # Check if this is a reasoning model (needs more tokens for hidden reasoning)
        is_reasoning_model = any([
            self.model.startswith("gpt-5"),   # GPT-5 uses reasoning
            self.model.startswith("o1-"),     # o1 reasoning models
            self.model.startswith("o3-"),     # o3 reasoning models
            self.model.startswith("o4-")      # o4 reasoning models
        ])

        # DEBUG: Print to console to verify code is running
        print(f"[LLMClient DEBUG] Model: {self.model}")
        print(f"[LLMClient DEBUG] skip_temperature: {skip_temperature}")
        print(f"[LLMClient DEBUG] uses_new_param: {uses_new_param}")
        print(f"[LLMClient DEBUG] is_reasoning_model: {is_reasoning_model}")

        # DEBUG: Show what we're sending
        print(f"[LLMClient DEBUG] System prompt: {system_prompt[:100] if system_prompt else 'None'}...")
        print(f"[LLMClient DEBUG] User prompt: {prompt[:100] if prompt else 'None'}...")

        kwargs = {
            "model": self.model,
            "messages": messages
        }

        # Only add temperature for older models (GPT-4, GPT-3.5)
        # Newer models (GPT-5, o-series) only support temperature=1 (default)
        if not skip_temperature:
            kwargs["temperature"] = temperature
            print(f"[LLMClient DEBUG] Added temperature={temperature}")
        else:
            print(f"[LLMClient DEBUG] Skipping temperature for {self.model} (only supports default temperature=1)")

        # Reasoning models need special handling
        if is_reasoning_model:
            # Use 'minimal' reasoning effort for simple tasks (prompt generation, etc.)
            # This minimizes reasoning tokens and ensures fast, cost-effective responses
            kwargs["reasoning_effort"] = "minimal"
            # No need to increase tokens for minimal reasoning
            actual_max_tokens = max_tokens
            print(f"[LLMClient DEBUG] Reasoning model: added reasoning_effort='minimal', max_tokens={actual_max_tokens}")
        else:
            actual_max_tokens = max_tokens

        if uses_new_param:
            kwargs["max_completion_tokens"] = actual_max_tokens
        else:
            kwargs["max_tokens"] = actual_max_tokens

        print(f"[LLMClient DEBUG] Final kwargs keys: {list(kwargs.keys())}")

        response = await self.client.chat.completions.create(**kwargs)

        print(f"[LLMClient DEBUG] Response received")
        print(f"[LLMClient DEBUG] Choices count: {len(response.choices)}")
        if response.choices:
            choice = response.choices[0]
            content = choice.message.content
            print(f"[LLMClient DEBUG] Content: '{content}'")
            print(f"[LLMClient DEBUG] Content length: {len(content) if content else 0}")
            print(f"[LLMClient DEBUG] Finish reason: {choice.finish_reason}")
            if hasattr(response, 'usage') and response.usage:
                details = getattr(response.usage, 'completion_tokens_details', None)
                reasoning = getattr(details, 'reasoning_tokens', 0) if details else 0
                print(f"[LLMClient DEBUG] Reasoning tokens: {reasoning}")
                print(f"[LLMClient DEBUG] Total completion tokens: {response.usage.completion_tokens}")
            return content if content else ""
        else:
            print(f"[LLMClient DEBUG] ERROR: No choices in response!")
            return ""

    async def _complete_anthropic(
        self,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int
    ) -> str:
        """Anthropic completion"""
        kwargs = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        response = await self.client.messages.create(**kwargs)

        return response.content[0].text

    async def complete_with_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7
    ) -> Dict:
        """
        Complete prompt and parse response as JSON

        Args:
            prompt: The user prompt
            system_prompt: System message
            temperature: Sampling temperature

        Returns:
            Parsed JSON dict
        """
        import json

        # Add JSON instruction to prompt
        json_prompt = f"{prompt}\n\nRespond with valid JSON only."

        response_text = await self.complete(
            prompt=json_prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=2000
        )

        # Try to extract JSON from response
        try:
            # Remove markdown code blocks if present
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.rfind("```")
                response_text = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.rfind("```")
                response_text = response_text[start:end].strip()

            # Try to parse as JSON
            try:
                return json.loads(response_text)
            except json.JSONDecodeError:
                # If JSON parsing fails, try to parse as Python literal (handles single quotes)
                import ast
                try:
                    result = ast.literal_eval(response_text)
                    # Convert back to ensure it's JSON-serializable
                    return json.loads(json.dumps(result))
                except (ValueError, SyntaxError):
                    raise

        except (json.JSONDecodeError, ValueError, SyntaxError) as e:
            raise ValueError(f"Failed to parse JSON response: {e}\nResponse: {response_text}")

    async def complete_structured(
        self,
        prompt: str,
        schema: Dict,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2000
    ) -> Dict:
        """
        Complete with structured output (OpenAI only)

        Args:
            prompt: The user prompt
            schema: JSON schema for structured output
            system_prompt: System message
            max_tokens: Maximum tokens to generate

        Returns:
            Structured response as dict
        """
        import logging
        logger = logging.getLogger(__name__)

        if self.provider != 'openai':
            # Fallback to JSON parsing for other providers
            return await self.complete_with_json(prompt, system_prompt)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Newer models use max_completion_tokens
        uses_new_param = any([
            self.model.startswith("gpt-5"),
            self.model.startswith("o3-"),
            self.model.startswith("o4-"),
            self.model.startswith("o1-")
        ])

        # Newer models (GPT-5, o-series) don't support custom temperature
        skip_temperature = any([
            self.model.startswith("gpt-5"),
            self.model.startswith("o1-"),
            self.model.startswith("o3-"),
            self.model.startswith("o4-")
        ])

        print(f"[LLMClient DEBUG] complete_structured - Model: {self.model} | skip_temperature: {skip_temperature}")

        kwargs = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"}
        }

        # Only add temperature for older models (GPT-4, GPT-3.5)
        if not skip_temperature:
            kwargs["temperature"] = 0.7
            print(f"[LLMClient DEBUG] Added temperature=0.7")
        else:
            print(f"[LLMClient DEBUG] Skipping temperature for {self.model}")

        if uses_new_param:
            kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = max_tokens

        response = await self.client.chat.completions.create(**kwargs)

        import json
        return json.loads(response.choices[0].message.content)

    def __repr__(self):
        return f"LLMClient(provider='{self.provider}', model='{self.model}')"
