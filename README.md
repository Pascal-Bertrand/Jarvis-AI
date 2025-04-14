# JarvisAI

An allround AI Secretary and network communication program to kill admin work in Big Corporate

## Setup

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Set up environment variables in `.env`:
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `GOOGLE_CLIENT_SECRET`: Your Google API client secret
4. Run the application: `python main.py`


## Feature
- Schedule, move or cancel meetings (via Google Calendar)
- Summarize incoming mails (via Gmail)
- Plan new projects (command: plan XXX = [project description]) including stakeholders, timeline and cost estimate
- Plan, assign and view tasks 
- Do all of the above via audio
