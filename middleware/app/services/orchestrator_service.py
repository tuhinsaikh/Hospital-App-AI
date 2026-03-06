import logging
import requests
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class WorkflowOrchestrator:
    """
    Executes multi-step API workflows (capabilities) configured for a specific HMS.
    Example workflow for Appointment Scheduling:
      1. get_departments
      2. get_doctors (depends on department)
      3. get_slots (depends on doctor)
      4. book_appointment (POST)
    """
    
    def __init__(self, connection_details: Dict[str, Any]):
        self.base_url = connection_details.get("url", "").rstrip('/')
        self.headers = connection_details.get("headers", {})

    def execute_workflow(self, workflow_steps: List[Dict[str, Any]], initial_inputs: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Executes a sequence of API calls. Passes outputs of one step as inputs to the next if defined.
        """
        context = initial_inputs or {}
        last_response = None
        
        for step in workflow_steps:
            step_name = step.get("name")
            method = step.get("method", "GET").upper()
            endpoint = step.get("endpoint", "")
            
            # Simple template resolution: e.g., /doctors/{department_id}
            url = f"{self.base_url}/{endpoint.lstrip('/')}".format(**context)
            
            logger.info(f"Executing step: {step_name} [{method} {url}]")
            
            payload = step.get("payload", {})
            if method in ["POST", "PUT"]:
                # resolve payload placeholders against context
                resolved_payload = {k: v.format(**context) if isinstance(v, str) else v for k, v in payload.items()}
                response = requests.request(method, url, headers=self.headers, json=resolved_payload)
            else:
                response = requests.request(method, url, headers=self.headers, params=context)
                
            response.raise_for_status()
            last_response = response.json()
            
            # Store the output in context so next step can use it
            context[f"{step_name}_result"] = last_response
            
        return last_response
