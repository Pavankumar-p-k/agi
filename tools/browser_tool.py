import os
import asyncio
from typing import List, Dict, Optional
from browser_use import Agent, Browser, BrowserConfig

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None
try:
    from langchain_ollama import ChatOllama
except ImportError:
    ChatOllama = None

class JarvisBrowser:
    """
    Browser-use integration for JARVIS.
    """
    def __init__(self, model_name: str = "qwen2.5:7b"):
        self.browser = Browser(
            config=BrowserConfig(
                headless=True,
                disable_security=True,
            )
        )
        
        # Prefer local Ollama if possible
        if ChatOllama is not None and ("qwen" in model_name or "llama" in model_name):
            self.llm = ChatOllama(model=model_name, base_url="http://localhost:11434")
        elif ChatOpenAI is not None:
            self.llm = ChatOpenAI(model="gpt-4o")
        else:
            raise ImportError("browser-use requires either langchain-ollama or langchain-openai. Install with: pip install langchain-ollama")

    async def execute(self, instruction: str) -> Dict:
        """
        Execute a natural language instruction in the browser.
        """
        agent = Agent(
            task=instruction,
            llm=self.llm,
            browser=self.browser,
        )
        
        try:
            result = await agent.run()
            return {
                "status": "success",
                "result": str(result),
                "instruction": instruction
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "instruction": instruction
            }

    async def research(self, topic: str) -> Dict:
        """
        Multi-page research on a topic.
        """
        instruction = f"Research the following topic across at least 5 different sources and provide a detailed summary: {topic}"
        return await self.execute(instruction)

# Instance
# browser_tool = JarvisBrowser() # Initialized on demand to save resources
