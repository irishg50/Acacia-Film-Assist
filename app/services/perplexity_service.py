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
            # Construct a detailed prompt for documentary research
            prompt = f"""Research the following documentary topic: {topic}
            
            Please provide:
            1. Key historical context and background
            2. Main figures or subjects involved
            3. Current relevance or impact
            4. Potential visual elements or archival materials
            5. Notable controversies or challenges
            6. Related documentary films or media
            """
            
            if focus_areas:
                prompt += f"\n\nPlease pay special attention to: {', '.join(focus_areas)}"

            # Make API request to Perplexity
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json={
                    "model": "pplx-7b-online",  # Using the online model for real-time research
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1000
                }
            )
            
            if response.status_code != 200:
                raise Exception(f"Perplexity API error: {response.text}")

            result = response.json()
            
            # Process and structure the response
            research_data = {
                "topic": topic,
                "content": result["choices"][0]["message"]["content"],
                "focus_areas": focus_areas,
                "metadata": {
                    "model": result["model"],
                    "created_at": result["created"]
                }
            }
            
            return research_data

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