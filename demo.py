import json
from typing import List, Dict
from secretary.utilities.logging import log_system_message
import openai
import os # Added for environment variable access
import time # Added for unique ID generation
from config.agents import AGENT_CONFIG

# OpenAI API Key and Client Initialization
try:
    from dotenv import load_dotenv
    load_dotenv() # take environment variables from .env.
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    if OPENAI_API_KEY:
        OPENAI_API_KEY = OPENAI_API_KEY.strip()
except ImportError:
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    log_system_message("Warning: OPENAI_API_KEY not found in demo.py. OpenAI features will use fallbacks.")
    demo_openai_client = None
else:
    demo_openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

class Candidate:
    def __init__(self, name: str, department: str, skills: List[str], title: str, description: str):
        self.name = name
        self.department = department
        self.skills = skills
        self.title = title
        self.description = description

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "department": self.department,
            "skills": self.skills,
            "title": self.title,
            "description": self.description
        }

def get_best_candidates(project_id: str, objective: str) -> List[Candidate]:
    """
    Use OpenAI to suggest the best candidates for a project based on the objective.
    Returns a list of up to 3 Candidate objects.
    """
    if not demo_openai_client:
        log_system_message("OpenAI client not initialized in demo.py due to missing API key. Falling back to default candidates.")
        return get_default_candidates()

    # Build agent information with explicit IDs and indices
    agent_info_list = []
    for i, agent in enumerate(AGENT_CONFIG):
        agent_info = (
            f"Agent ID: {agent['id']}\n"
            f"Name: {agent['name']}\n"
            f"Department: {agent['department']}\n"
            f"Title: {agent['title']}\n"
            f"Skills: {', '.join(agent['skills'])}\n"
            f"Description: {agent['description']}\n"
            f"Knowledge: {agent['knowledge']}\n"
        )
        agent_info_list.append(agent_info)
    
    agents_info = "\n".join(agent_info_list)

    # More strongly emphasize JSON format requirement and proper ID format
    prompt = f"""Given the following project objective and available agents, select up to 3 best-suited candidates for the project.
Consider their skills, experience, and knowledge when making the selection.

Project ID: {project_id}
Project Objective: {objective}

Available Agents:
{agents_info}

Please analyze the project requirements and select the most suitable candidates. Consider:
1. Required skills and expertise
2. Department relevance
3. Role and responsibilities
4. Knowledge areas

IMPORTANT: You must ONLY respond with a valid JSON object containing an array of the EXACT agent IDs as listed above.
The response MUST follow this exact format: {{"selected_agents": ["exact_id_1", "exact_id_2", "exact_id_3"]}}
For example, if you select Ueli Maurer, use the exact ID "Ueli Maurer" (not agent_1 or similar).
Use the exact agent ID strings from the Agent ID field for each agent.
Do not include any explanation or other text outside the JSON object.
"""

    try:
        response = demo_openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a project management expert who helps select the best team members for projects. You always respond with valid JSON using exact agent IDs from the provided list."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=150
        )

        # Parse the response to get selected agent IDs
        result_content = response.choices[0].message.content
        log_system_message(f"OpenAI response: {result_content}")

        if not result_content or result_content.isspace():
            log_system_message("Error: Empty response from OpenAI")
            return get_default_candidates()

        # Clean the content to handle potential formatting issues
        clean_content = result_content.strip()
        if clean_content.startswith("```") and clean_content.endswith("```"):
            # Remove markdown code blocks
            clean_content = clean_content.strip("```")
            if clean_content.startswith("json"):
                clean_content = clean_content[4:].strip() 
        
        # Try to extract JSON if it's embedded in other text
        if not clean_content.startswith('{'):
            json_start = clean_content.find('{')
            json_end = clean_content.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                clean_content = clean_content[json_start:json_end]
            else:
                log_system_message("Error: Could not find JSON in response, trying to extract agent IDs manually")
                selected_agent_ids = extract_agent_ids_from_text(clean_content)
                log_system_message(f"Extracted agent IDs manually: {selected_agent_ids}")
                processed_agent_ids = process_agent_ids(selected_agent_ids)
                return create_candidates_from_ids(processed_agent_ids)
        
        try:
            # Try to parse JSON
            result = json.loads(clean_content)
            selected_agent_ids = result.get("selected_agents", [])[:3]  # Limit to 3 agents
            log_system_message(f"Extracted agent IDs from JSON: {selected_agent_ids}")
        except json.JSONDecodeError as e:
            log_system_message(f"JSON parsing error: {str(e)} for content: {clean_content}")
            # Try to extract agent IDs manually
            selected_agent_ids = extract_agent_ids_from_text(clean_content)
            log_system_message(f"Extracted agent IDs manually: {selected_agent_ids}")

        # Process agent IDs to handle various formats (agent_1, agent1, 1, etc.)
        processed_agent_ids = process_agent_ids(selected_agent_ids)
        log_system_message(f"Processed agent IDs: {processed_agent_ids}")
        
        # Create candidate objects from the processed IDs
        candidates = create_candidates_from_ids(processed_agent_ids)
        if candidates:
            return candidates
        return get_default_candidates()

    except Exception as e:
        log_system_message(f"Error getting best candidates: {str(e)}")
        return get_default_candidates()

def process_agent_ids(agent_ids: List[str]) -> List[str]:
    """
    Process agent IDs to handle different formats from the AI response.
    Maps numeric indices or agent_N format to actual agent IDs from AGENT_CONFIG.
    """
    processed_ids = []
    
    for agent_id in agent_ids:
        # Check if it's already a valid ID in AGENT_CONFIG
        if any(a["id"] == agent_id for a in AGENT_CONFIG):
            processed_ids.append(agent_id)
            continue
            
        # Handle "agent_N" or "agentN" format
        if agent_id.lower().startswith("agent"):
            # Extract the number
            num_part = agent_id.lower().replace("agent", "").replace("_", "").strip()
            try:
                idx = int(num_part) - 1  # Convert to 0-based index
                if 0 <= idx < len(AGENT_CONFIG):
                    processed_ids.append(AGENT_CONFIG[idx]["id"])
                    continue
            except ValueError:
                pass
                
        # Try direct numeric index
        try:
            idx = int(agent_id) - 1  # Convert to 0-based index
            if 0 <= idx < len(AGENT_CONFIG):
                processed_ids.append(AGENT_CONFIG[idx]["id"])
                continue
        except ValueError:
            pass
            
        # Try lowercase name match
        agent_id_lower = agent_id.lower()
        for agent in AGENT_CONFIG:
            if agent["name"].lower() == agent_id_lower or agent["id"].lower() == agent_id_lower:
                processed_ids.append(agent["id"])
                break
                
    return processed_ids

def extract_agent_ids_from_text(text: str) -> List[str]:
    """Extract agent IDs from text when JSON parsing fails"""
    # First try to find agent IDs in format like "agent_1", "agent1" or just numbers
    found_ids = []
    
    # Look for patterns like "agent_1", "agent 1", "agent1", or just "1", "2", etc.
    import re
    agent_patterns = [
        r'agent[_\s]*(\d+)',  # Matches agent_1, agent 1, agent1
        r'\b(\d+)\b'          # Matches standalone numbers
    ]
    
    for pattern in agent_patterns:
        matches = re.findall(pattern, text.lower())
        for match in matches:
            found_ids.append(f"agent_{match}")
    
    # If that fails, look for actual agent IDs/names from AGENT_CONFIG
    if not found_ids:
        for agent in AGENT_CONFIG:
            if agent["id"].lower() in text.lower() or agent["name"].lower() in text.lower():
                found_ids.append(agent["id"])
    
    # If we still don't have any, return the first 3 from AGENT_CONFIG as fallback
    if not found_ids and AGENT_CONFIG:
        found_ids = [agent["id"] for agent in AGENT_CONFIG[:3]]
    
    return found_ids[:3]  # Limit to 3 agents

def get_default_candidates() -> List[Candidate]:
    """Return default candidates as a fallback"""
    return [
        Candidate("Ueli Maurer", "Engineering", ["Swiss German", "AI", "System Design"], "CEO", "Oversees the entire organization and strategy."),
        Candidate("John Doe", "Marketing", ["English", "Marketing", "Market Analysis"], "Marketing Lead", "Handles marketing campaigns and market analysis."),
        Candidate("Michael Chen", "Engineering", ["Chinese", "Agile", "Market Analysis"], "Engineering Lead", "Manages the technical team and codebase.")
    ]

def create_candidates_from_ids(agent_ids: List[str]) -> List[Candidate]:
    """Create Candidate objects from agent IDs"""
    candidates = []
    for agent_id in agent_ids:
        agent = next((a for a in AGENT_CONFIG if a["id"].lower() == agent_id.lower()), None)
        if agent:
            candidates.append(Candidate(
                name=agent["name"],
                department=agent["department"],
                skills=agent["skills"],
                title=agent["title"],
                description=agent["description"]
            ))
    
    # If we couldn't create any candidates, return defaults
    if not candidates:
        return get_default_candidates()
    
    return candidates

def get_candidate_widgets(project_id: str, objective: str) -> str:
    """
    Returns HTML for candidate widgets to be displayed in the chat window.
    Each widget shows a candidate's name, department, title, and skills.
    """
    # Get the best candidates for this project
    candidates = get_best_candidates(project_id, objective)
    
    # Return a message with the candidate data
    return f"Here are the best-suited candidates for your project '{project_id}':\n{json.dumps([c.to_dict() for c in candidates])}"

def handle_project_submission(project_id: str, objective: str) -> str:
    """
    This function is called after a project is submitted.
    It uses OpenAI to suggest the best candidates and returns their widgets.
    """
    log_system_message(f"[Demo] Project '{project_id}' submitted with objective: {objective}")
    
    # Get the candidate widgets HTML with project context
    widgets_html = get_candidate_widgets(project_id, objective)
    
    # Return a message with the widgets
    return widgets_html 