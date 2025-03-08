# LLM Network with Calendar Integration

A multi-agent system that uses LLMs to create project plans, generate tasks, and schedule meetings with Google Calendar integration.

## Features

- Multiple AI agents with different roles (CEO, Marketing, Engineering, Design)
- Project planning with automatic task generation
- Google Calendar integration for meetings and task reminders
- Natural language meeting scheduling and cancellation
- Web dashboard to view projects, tasks, and team members

## Setup

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Set up environment variables in `.env`:
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `GOOGLE_CLIENT_SECRET`: Your Google API client secret
4. Run the application: `python main.py`

## Usage

- Create a project plan: `ceo: plan project_name = objective`
- Schedule a meeting: `ceo: schedule a meeting with marketing tomorrow at 2pm`
- Cancel a meeting: `ceo: cancel the marketing meeting`
- List tasks: `ceo: tasks` 