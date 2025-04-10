import os
from openai import OpenAI
from dotenv import load_dotenv
import PyPDF2
import json

class CVParser:
    def __init__(self):
        load_dotenv()
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.cv_data = {}

    def parse_cv(self, file_path):
        try:
            # Extract text from PDF
            text = self._extract_text_from_pdf(file_path)
            if not text:
                raise Exception("Could not extract text from PDF")
            
            # Create prompt for OpenAI
            prompt = """Please analyze this CV and extract the following information in JSON format:
            {
                "name": "",
                "email": "",
                "phone": "",
                "education": [],
                "work_experience": [],
                "skills": []
            }

            CV content:
            """ + text

            # Call OpenAI API
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a CV parser. Extract information in strict JSON format."},
                    {"role": "user", "content": prompt}
                ]
            )

            # Parse the response
            parsed_data = json.loads(response.choices[0].message.content)
            print("\n=== Extracted CV Information ===")
            print(json.dumps(parsed_data, indent=2))
            print("============================\n")
            
            # Store data in instance variable
            self.cv_data = parsed_data
            
            return {
                'name': parsed_data.get('name', 'Not found'),
                'email': parsed_data.get('email', 'Not found'),
                'phone': parsed_data.get('phone', 'Not found'),
                'education': parsed_data.get('education', []),
                'work_experience': parsed_data.get('work_experience', []),
                'skills': parsed_data.get('skills', [])
            }

        except json.JSONDecodeError as e:
            print(f"Error parsing JSON response: {str(e)}")
            print(f"Raw response: {response.choices[0].message.content}")
            return None
        except Exception as e:
            print(f"Error parsing CV: {str(e)}")
            return None

    def _extract_text_from_pdf(self, file_path):
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")
                
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text.strip()
        except Exception as e:
            print(f"Error extracting text from PDF: {str(e)}")
            return ""

    def extract_age(self, cv_file):
        # Logic to extract age from the CV
        return "Age extracted from CV"

    def extract_gender(self, cv_file):
        # Logic to extract gender from the CV
        return "Gender extracted from CV"

    def extract_work_experience(self, cv_file):
        # Logic to extract work experience from the CV
        return "Work experience extracted from CV"

    def extract_current_projects(self, cv_file):
        # Logic to extract current projects from the CV
        return "Current projects extracted from CV"

    def extract_company_resort(self, cv_file):
        # Logic to extract company resort from the CV
        return "Company resort extracted from CV"

    def summarize_cv(self):
        return {
            "Age": self.cv_data.get('age'),
            "Gender": self.cv_data.get('gender'),
            "Work Experience": self.cv_data.get('work_experience'),
            "Current Projects": self.cv_data.get('current_projects'),
            "Company Resort": self.cv_data.get('company_resort')
        }