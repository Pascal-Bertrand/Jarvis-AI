# JarvisAI

An allround AI Secretary and network communication program to kill admin work in Big Corporate

## Setup

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Set up environment variables in `.env`:
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `GOOGLE_CLIENT_SECRET`: Your Google API client secret (only needed if you want to use Gmail or Calender)
4. Run the application: `python main.py`


## Features
- Schedule, move or cancel meetings (via Google Calendar)
- Summarize incoming mails (via Gmail)
- Get a project plan (command: plan XXX = [project description]) including stakeholders, timeline and cost estimate
- Plan, assign and view tasks 
- Do all of the above via audio

## Demo
- To illustrate how flexible meeting scheduling works, edit the block_time function in main.py (produces a calender conflict by default) and run the main.py
- If the proposed time for a new meeting clashes with the internal calendar, Jarvis proposes a better time that works for every one (confirm in the terminal)
- If there are no clashes, the meeting is scheduled immediately

## Demo video
https://github.com/user-attachments/assets/89cb1b18-0fab-45d9-8e7d-e5e4a2427ba3
