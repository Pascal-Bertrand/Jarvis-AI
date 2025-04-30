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

## Example chats
Create an extensive project plan...
![image](https://github.com/user-attachments/assets/b53e35e8-7534-4f91-929b-a193b1318a90)

... and the corresponding tasks for everyone in the org
![image](https://github.com/user-attachments/assets/d1ce0fd8-18d6-4248-a853-608daecdac83)


Schedule new meetings
![image](https://github.com/user-attachments/assets/ab3a1b7a-4e9e-447e-9b54-b6046e4dfa12)

