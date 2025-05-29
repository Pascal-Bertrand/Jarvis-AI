import psycopg2
from psycopg2.extras import RealDictCursor
import json
from typing import List, Dict, Optional

class Database:
    def __init__(self, database_url: str):
        self.database_url = database_url
    
    def get_connection(self):
        return psycopg2.connect(self.database_url, cursor_factory=RealDictCursor)
    
    def get_user_projects(self, user_id: str) -> List[Dict]:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, name, owner, participants, objective, 
                           description, plan_steps, status, created_at
                    FROM projects 
                    WHERE user_id = %s 
                    ORDER BY created_at DESC
                """, (user_id,))
                return [dict(row) for row in cur.fetchall()]
    
    def get_user_tasks(self, user_id: str, agent_id: Optional[str] = None) -> List[Dict]:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                if agent_id:
                    cur.execute("""
                        SELECT id, title, description, assigned_to, due_date, 
                               priority, project_id, completed, created_at
                        FROM tasks 
                        WHERE user_id = %s AND (assigned_to = %s OR assigned_to LIKE %s)
                        ORDER BY due_date ASC
                    """, (user_id, agent_id, f'%{agent_id}%'))
                else:
                    cur.execute("""
                        SELECT id, title, description, assigned_to, due_date, 
                               priority, project_id, completed, created_at
                        FROM tasks 
                        WHERE user_id = %s 
                        ORDER BY due_date ASC
                    """, (user_id,))
                
                tasks = []
                for row in cur.fetchall():
                    task = dict(row)
                    if task['due_date']:
                        task['due_date'] = task['due_date'].isoformat()
                    tasks.append(task)
                return tasks
    
    def get_user_meetings(self, user_id: str) -> List[Dict]:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, external_id, title, description, start_time, 
                           end_time, attendees, organizer_email, source
                    FROM meetings 
                    WHERE user_id = %s 
                    ORDER BY start_time ASC
                """, (user_id,))
                
                meetings = []
                for row in cur.fetchall():
                    meeting = dict(row)
                    if meeting['start_time']:
                        meeting['dateTime'] = meeting['start_time'].strftime('%Y-%m-%d %H:%M')
                        meeting['startTimeISO'] = meeting['start_time'].isoformat()
                    if meeting['end_time']:
                        meeting['endTimeISO'] = meeting['end_time'].isoformat()
                    meetings.append(meeting)
                return meetings
    
    def create_project(self, user_id: str, name: str, **kwargs) -> str:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO projects (user_id, name, owner, participants, 
                                        objective, description, plan_steps, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    user_id, name, kwargs.get('owner'), 
                    json.dumps(kwargs.get('participants', [])),
                    kwargs.get('objective'), kwargs.get('description'),
                    json.dumps(kwargs.get('plan_steps', [])),
                    kwargs.get('status', 'active')
                ))
                return cur.fetchone()['id']
    
    def create_task(self, user_id: str, **kwargs) -> str:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO tasks (user_id, project_id, title, description, 
                                     assigned_to, due_date, priority)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    user_id, kwargs.get('project_id'), kwargs.get('title'),
                    kwargs.get('description'), kwargs.get('assigned_to'),
                    kwargs.get('due_date'), kwargs.get('priority', 'medium')
                ))
                return cur.fetchone()['id'] 