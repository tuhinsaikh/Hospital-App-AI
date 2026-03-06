import os
import json
import logging
from langchain_core.prompts import PromptTemplate
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class MappingService:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "groq").lower()
        self.llm = None
        
        if self.provider == "local":
            try:
                from langchain_ollama import ChatOllama
                base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
                model_name = os.getenv("OLLAMA_MODEL", "llama3")
                self.llm = ChatOllama(model=model_name, base_url=base_url)
                logger.info(f"Using Local LLM: {model_name} at {base_url}")
            except ImportError:
                logger.error("langchain_ollama not installed. Fallback to rule-based.")
        else:
            try:
                from langchain_groq import ChatGroq
                api_key = os.getenv("GROQ_API_KEY")
                if api_key:
                    self.llm = ChatGroq(model="llama3-8b-8192", api_key=api_key)
                    logger.info("Using Groq LLM for mapping.")
                else:
                    logger.warning("GROQ_API_KEY missing. Fallback to rule-based.")
            except ImportError:
                logger.error("langchain_groq not installed. Fallback to rule-based.")
            
        self.standard_schema = [
            "patient_id", "first_name", "last_name", "dob", "gender",
            "phone", "email", "address", "medical_history_summary"
        ]

    def suggest_mappings(self, hms_fields: list[str]) -> dict:
        """
        Uses LLM (or rule-based fallback) to suggest mappings from HMS fields to our standard schema.
        """
        if not self.llm:
            return self._rule_based_mapping(hms_fields)
            
        prompt = PromptTemplate.from_template(
            "You are a healthcare data integration expert.\n"
            "Map the following external HMS fields to our standard schema.\n"
            "Standard schema fields: {standard_schema}\n"
            "External fields: {hms_fields}\n"
            "Return ONLY a valid JSON dictionary where keys are external fields and values are standard fields.\n"
            "If there is no logical match for an external field, set the value to null.\n"
            "Do NOT include markdown formatting like ```json in the output, just the raw JSON."
        )
        
        try:
            chain = prompt | self.llm
            response = chain.invoke({
                "standard_schema": ", ".join(self.standard_schema),
                "hms_fields": ", ".join(hms_fields)
            })
            
            content = response.content.strip()
            if content.startswith("```json"):
                content = content[7:-3].strip()
            elif content.startswith("```"):
                content = content[3:-3].strip()
                
            return json.loads(content)
        except Exception as e:
            logger.error(f"AI Mapping failed: {e}. Falling back to rule-based.")
            return self._rule_based_mapping(hms_fields)

    def _rule_based_mapping(self, hms_fields: list[str]) -> dict:
        """Fallback simple substring matching"""
        mapping = {}
        for field in hms_fields:
            f_lower = field.lower()
            if "id" in f_lower and "pat" in f_lower: mapping[field] = "patient_id"
            elif "first" in f_lower or "fname" in f_lower: mapping[field] = "first_name"
            elif "last" in f_lower or "lname" in f_lower: mapping[field] = "last_name"
            elif "dob" in f_lower or "birth" in f_lower: mapping[field] = "dob"
            elif "sex" in f_lower or "gender" in f_lower: mapping[field] = "gender"
            else: mapping[field] = None
        return mapping
