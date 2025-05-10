import json
from typing import List, Dict
from secretary.utilities.logging import log_system_message

class Candidate:
    def __init__(self, name: str, department: str, skills: List[str]):
        self.name = name
        self.department = department
        self.skills = skills

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "department": self.department,
            "skills": self.skills
        }

def get_candidate_widgets() -> str:
    """
    Returns HTML for three candidate widgets to be displayed in the chat window.
    Each widget shows a candidate's name, department, and skills.
    """
    # Create some dummy candidates
    candidates = [
        Candidate("Ueli Maurer", "Engineering", ["Swiss German", "AI", "System Design"]),
        Candidate("John Doe", "Design", ["English", "Figma", "User Research"]),
        Candidate("Michael Chen", "Product", ["Chinese", "Agile", "Market Analysis"])
    ]

    # Create HTML for the widgets
    widgets_html = '<div class="candidate-widgets" style="display: flex; gap: 20px; margin: 20px 0;">'
    
    for candidate in candidates:
        skills_html = ''.join([f'<span class="skill-tag">{skill}</span>' for skill in candidate.skills])
        
        widget_html = f'''
            <div class="candidate-card" style="
                background: white;
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 15px;
                flex: 1;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            ">
                <h3 style="margin: 0 0 10px 0; color: #333;">{candidate.name}</h3>
                <p style="margin: 0 0 10px 0; color: #666;">{candidate.department}</p>
                <div class="skills" style="display: flex; flex-wrap: wrap; gap: 5px;">
                    {skills_html}
                </div>
            </div>
        '''
        widgets_html += widget_html

    widgets_html += '</div>'
    
    # Add CSS for skill tags
    widgets_html += '''
        <style>
            .skill-tag {
                background: #e9ecef;
                padding: 4px 8px;
                border-radius: 12px;
                font-size: 12px;
                color: #495057;
            }
        </style>
    '''
    
    return widgets_html

def handle_project_submission(project_id: str, objective: str) -> str:
    """
    This function is called after a project is submitted.
    Instead of showing the plan in chat, it returns candidate widgets.
    """
    log_system_message(f"[Demo] Project '{project_id}' submitted with objective: {objective}")
    
    # Get the candidate widgets HTML
    widgets_html = get_candidate_widgets()
    
    # Return a message with the widgets
    return f"Here are some potential candidates for your project '{project_id}':\n{widgets_html}" 