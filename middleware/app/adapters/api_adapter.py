import requests
import logging

logger = logging.getLogger(__name__)

class ApiAdapter:
    def __init__(self, connection_config: dict):
        """
        connection_config might include:
        {
            "base_url": "https://api.hospital.com/v1",
            "headers": {
                "Authorization": "Bearer token",
                "ApiKey": "key"
            }
        }
        """
        self.base_url = connection_config.get("base_url", "").rstrip('/')
        self.headers = connection_config.get("headers", {})
        
        if not self.base_url:
            raise ValueError("API base URL is required")

    def test_connection(self) -> bool:
        """Test if the API is reachable"""
        try:
            # We usually test by hitting the base URL or a known '/health' endpoint
            response = requests.get(f"{self.base_url}", headers=self.headers, timeout=10)
            return response.status_code < 500
        except Exception as e:
            logger.error(f"Failed to connect to API: {e}")
            return False

    def fetch_data(self, endpoint: str, params: dict = None) -> list | dict:
        """
        Fetch data from the REST API.
        """
        try:
            url = f"{self.base_url}/{endpoint.lstrip('/')}"
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            # Often APIs return { "data": [...] }
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            return data
        except Exception as e:
            logger.error(f"API fetch failed for {endpoint}: {e}")
            raise
