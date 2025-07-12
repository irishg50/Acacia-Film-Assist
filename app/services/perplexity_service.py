import os
import requests
from typing import Dict, Optional
from flask import current_app

class PerplexityService:
    def __init__(self):
        self.api_key = current_app.config.get('PERPLEXITY_API_KEY') or os.getenv('PERPLEXITY_API_KEY')
        if not self.api_key:
            raise ValueError("Perplexity API key is not set in config or environment")
        
        self.base_url = "https://api.perplexity.ai"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def research_topic(self, topic: str, focus_areas: Optional[list] = None) -> Dict:
        """
        Research a documentary topic using Perplexity API.
        
        Args:
            topic: The main topic to research
            focus_areas: Optional list of specific aspects to focus on (e.g., ["historical context", "key figures"])
        
        Returns:
            Dict containing research results and metadata
        """
        try:
            # Research a topic using Perplexity API, with a general, comprehensive prompt
            user_prompt = f"Provide a comprehensive, detailed overview of {topic}. Include all relevant facts, context, and sources."
            if focus_areas:
                user_prompt += f"\nFocus especially on: {', '.join(focus_areas)}."
            system_prompt = "Be precise and concise."
            payload = {
                "model": "sonar",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "reasoning_effort": "high"
            }
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload
            )
            
            if response.status_code != 200:
                raise Exception(f"Perplexity API error: {response.text}")

            data = response.json()
            
            # Build sources section in Markdown
            sources_md = "\n\n## Sources\n"
            # Add citations (if any)
            citations = data.get('citations') or []
            for c in citations:
                if isinstance(c, str) and c.startswith('http'):
                    sources_md += f"- {c}\n"
                else:
                    sources_md += f"- {c}\n"
            # Add search results (if any)
            search_results = data.get('search_results') or []
            for r in search_results:
                url = r.get('url')
                title = r.get('title', url or 'Source')
                if url:
                    sources_md += f"- [{title}]({url})\n"
            # Robustly extract main content
            content = data.get('content')
            if not content:
                # Try OpenAI/Perplexity chat format
                choices = data.get('choices')
                if choices and isinstance(choices, list) and len(choices) > 0:
                    message = choices[0].get('message')
                    if message and 'content' in message:
                        content = message['content']
            if not content:
                content = data.get('research_content', '')
            if sources_md.strip() != '## Sources':
                content = (content or '').rstrip() + sources_md
            data['content'] = content
            
            return data

        except Exception as e:
            current_app.logger.error(f"Error in Perplexity research: {str(e)}")
            raise

    def validate_api_key(self) -> bool:
        """Test if the Perplexity API key is valid"""
        try:
            response = requests.get(
                f"{self.base_url}/models",
                headers=self.headers
            )
            return response.status_code == 200
        except:
            return False 