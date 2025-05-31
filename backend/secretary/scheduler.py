import json  
from datetime import datetime, timedelta, timezone  
import tzlocal
import zoneinfo
import uuid

from network.tasks import Task            
from network.internal_communication import Intercom  
from secretary.utilities.logging import log_system_message, log_warning, log_error  
from secretary.brain import LLMClient
from config.agents import AGENT_CONFIG

class Scheduler:

    def __init__(self, node_id: str = None, calendar_service=None, network: Intercom = None, brain = None, socketio_instance=None, user_id: str = None):
        """
        Initialize the Scheduler.

        Args:
            node_id (str): Identifier for the node using this scheduler.
            calendar_service: Google Calendar service client (or None).
            network (Intercom): The Intercom/network instance for notifications.
            brain: The Brain instance associated with this node.
            socketio_instance: The shared SocketIO instance.
            user_id (str): The user ID this scheduler belongs to.
        """
        self.node_id = node_id
        self.calendar_service = calendar_service
        self.network = network
        self.brain = brain
        self.socketio = socketio_instance
        self.user_id = user_id  # Store user ID for data isolation
        self.calendar = self.network.local_calendar if self.network and node_id in self.network.nodes else []
        self.node = self.network.nodes.get(node_id) if self.network and node_id in self.network.nodes else None

        # Attach this calendar list to the Brain node so meetings show up
        if self.network and self.node_id in self.network.nodes:
            setattr(self.network.nodes[self.node_id], 'calendar', self.calendar)
            log_system_message(f"[Scheduler:{self.node_id}] Calendar attached to node for user: {user_id}.")  
        
        # Register this Scheduler instance under its node_id
        if self.network and self.node_id is not None:
            self.network.register_node(self.node_id, self)

    def get_upcoming_meetings(self, max_results=100):
        """
        Fetch upcoming meetings from Google Calendar and local storage for this node.

        Args:
            max_results (int): Maximum number of meetings to retrieve from Google Calendar.

        Returns:
            list: A list of meeting event objects, or an empty list if an error occurs.
        """
        google_meetings = []
        if self.calendar_service:
            try:
                now_utc = datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
                events_result = self.calendar_service.events().list(
                    calendarId='primary',
                    timeMin=now_utc,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                google_meetings = events_result.get('items', [])
                log_system_message(f"[{self.node_id}] Fetched {len(google_meetings)} upcoming meetings from Google Calendar.")
            except Exception as e:
                log_error(f"[{self.node_id}] Error fetching upcoming meetings from Google Calendar: {str(e)}")
        else:
            log_system_message(f"[{self.node_id}] Google Calendar service not available, using local calendar only.")

        local_meetings_transformed = []
        if self.brain and hasattr(self.brain, 'calendar') and self.brain.calendar:
            log_system_message(f"[{self.node_id}] Found {len(self.brain.calendar)} local meetings.")
            for local_meeting in self.brain.calendar:
                # Transform local meeting structure to be compatible with UI expectations (like GCal events)
                # Ensure start and end times are in the correct format for the UI.
                start_time_str = local_meeting.get('start_time')
                end_time_str = local_meeting.get('end_time')

                start_obj = {}
                if start_time_str:
                    try:
                        # Assuming ISO format from _fallback_schedule_meeting
                        if type(start_time_str) == str:
                            dt_obj = datetime.fromisoformat(start_time_str)
                            start_obj = {'dateTime': dt_obj.isoformat(), 'timeZone': str(dt_obj.tzinfo or tzlocal.get_localzone_name())}
                        else:
                            start_obj = {'date': start_time_str} # Fallback if not full dateTime
                    except ValueError:
                        start_obj = {'date': start_time_str} # Fallback if not full dateTime
                
                end_obj = {}
                if end_time_str:
                    try:
                        if type(end_time_str) == str:
                            dt_obj = datetime.fromisoformat(end_time_str)
                            end_obj = {'dateTime': dt_obj.isoformat(), 'timeZone': str(dt_obj.tzinfo or tzlocal.get_localzone_name())}
                        else:
                            end_obj = {'date': end_time_str} # Fallback if not full dateTime
                    except ValueError:
                        end_obj = {'date': end_time_str}

                transformed = {
                    'summary': local_meeting.get('meeting_info', 'Local Meeting'),
                    'title': local_meeting.get('title', local_meeting.get('meeting_info', 'Local Meeting')),  # Use title if available, fallback to meeting_info
                    'start': start_obj,
                    'end': end_obj,
                    'attendees': [{'email': f'{p}@example.com'} for p in local_meeting.get('participants', [])],
                    'organizer': {'email': f'{self.node_id}@local.agent'},
                    'id': local_meeting.get('event_id', f"local_{local_meeting.get('project_id', '')}_{start_time_str}"),
                    'source': 'local' # To distinguish if needed
                }
                # Filter out past local meetings manually if timeMin wasn't applied
                if start_time_str:
                    try:
                        dt_obj_check = datetime.fromisoformat(start_time_str)
                        # Ensure dt_obj_check is timezone-aware (UTC) for comparison
                        if dt_obj_check.tzinfo is None or dt_obj_check.tzinfo.utcoffset(dt_obj_check) is None:
                            # dt_obj_check is naive, assume it's in local time
                            local_tz = tzlocal.get_localzone()
                            # Make it local-aware, then convert to UTC
                            dt_obj_check = dt_obj_check.replace(tzinfo=local_tz).astimezone(timezone.utc)
                        else:
                            # If already aware, convert to UTC for consistent comparison
                            dt_obj_check = dt_obj_check.astimezone(timezone.utc)

                        if dt_obj_check >= datetime.now(timezone.utc):
                            local_meetings_transformed.append(transformed)
                        else:
                            log_system_message(f"[{self.node_id}] Skipping past local meeting: {transformed.get('summary')}")
                    except ValueError as ve:
                         log_warning(f"[{self.node_id}] Could not parse date for local meeting '{transformed.get('summary')}': {start_time_str}. Error: {ve}")
                         local_meetings_transformed.append(transformed) # Append if date parsing fails, let UI handle display or ignore
                else:
                     local_meetings_transformed.append(transformed) # No start time, include for now

        # Merge and de-duplicate meetings
        # Simple de-duplication based on event ID (Google event ID or generated local ID)
        all_meetings_dict = {}
        for meeting in google_meetings:
            # Add title field to Google Calendar meetings
            meeting['title'] = meeting.get('summary', 'Untitled Meeting')
            all_meetings_dict[meeting['id']] = meeting
        
        for meeting in local_meetings_transformed:
            # Only add local meeting if no Google meeting with the same ID exists
            # or if it's a purely local meeting (no event_id matching GCal)
            if meeting['id'] not in all_meetings_dict or not local_meeting.get('event_id'):
                 all_meetings_dict[meeting['id']] = meeting

        merged_meetings = list(all_meetings_dict.values())

        # Sort all meetings by start time
        def get_sort_key(event):
            start_info = event.get('start', {})
            date_time_str = start_info.get('dateTime', start_info.get('date'))
            if date_time_str:
                try:
                    # Handle both date and dateTime strings
                    if 'T' in date_time_str:
                        return datetime.fromisoformat(date_time_str.replace('Z', '+00:00'))
                    else:
                        # This creates a naive datetime
                        naive_dt = datetime.strptime(date_time_str, '%Y-%m-%d')
                        # Make it offset-aware by assuming UTC midnight
                        return naive_dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    return datetime.max # Put unparsable dates at the end
            return datetime.max

        merged_meetings.sort(key=get_sort_key)

        log_system_message(f"[{self.node_id}] Total upcoming meetings (merged): {len(merged_meetings)}")
        
        return merged_meetings

    def create_calendar_reminder(self, task: Task):
        """
        Create a Google Calendar reminder for a given task.
        
        This method builds an event from the task details (title, due date, description, priority, etc.)
        and inserts the event using the calendar service.
        
        Args:
            task (Task): Task object with attributes: title, description, due_date, priority, project_id, assigned_to.
            
        If the calendar service is not available, it will log that and skip reminder creation.
        """
        
        log_system_message(f"[Scheduler] Entered calendar-reminder creation for task: {task.title}")
        
        if not self.calendar_service:
            log_system_message(f"[Scheduler] [{self.node_id}] Calendar service not available, skipping reminder creation")
            return      # No return: Don't want to spam the users
            
        try:
            log_system_message(f"[Scheduler] [{self.node_id}] Creating calendar reminder for task: {task.title}")
            # Construct the event details in the format expected by Google Calendar
            event = {
                'summary': f"TASK: {task.title}",
                'description': f"{task.description}\n\nPriority: {task.priority}\nProject: {task.project_id}",
                'start': {
                    'dateTime': task.due_date.isoformat(),
                    'timeZone': 'UTC',
                },
                'end': {
                    'dateTime': (task.due_date + timedelta(hours=1)).isoformat(),
                    'timeZone': 'UTC',
                },
                'attendees': [{'email': f'{task.assigned_to}@example.com'}],
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'email', 'minutes': 24 * 60},  # 1 day before
                        {'method': 'popup', 'minutes': 60}         # 1 hour before
                    ]
                }
            }

            # Insert the event into the primary calendar
            event = self.calendar_service.events().insert(calendarId='primary', body=event).execute()
            log_system_message(f"[Scheduler] [{self.node_id}] Task reminder created: {event.get('htmlLink')}")
            
        except Exception as e:
            log_warning(f"[{self.node_id}] Failed to create calendar reminder: {e}")
            

    # Replace the local meeting scheduling with Google Calendar version
    def schedule_meeting(self, project_id: str, participants: list):
        """
        Schedule a meeting using Google Calendar.
        
        If the Google Calendar service is available, the meeting event is created with start and end times.
        If not, the method falls back to local scheduling.
        
        Args:
            project_id (str): Identifier for the project this meeting is associated with.
            participants (list): List of participant identifiers (usually email prefixes).
            
        The method also notifies other participants by adding the event to their local calendars and sending messages.
        """
            
        meeting_description = f"Meeting for project '{project_id}'"

        try:
            local_tz_name = tzlocal.get_localzone_name()
        except Exception: # Catch potential errors and fallback
            local_tz_name = 'UTC' # Fallback timezone


        # Schedule meeting for one day later, for a duration of one hour
        # TODO: Add a more flexible scheduling system (e.g., using LLM to extract date/time from message)
        start_time = datetime.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=1)
        
        if not self.calendar_service:
            log_system_message(f"[{self.node_id}] Calendar service not available, using local scheduling")
            return self._fallback_schedule_meeting(project_id, participants, start_time, end_time, meeting_title=meeting_description)

        # Build the meeting event structure
        event = {
            'summary': meeting_description,
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': local_tz_name,
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': local_tz_name,
            },
            'attendees': [{'email': f'{p}@example.com'} for p in participants],
        }

        try:
            log_system_message(f"[Scheduler] [{self.node_id}] Attempting to create google calendar event: {event}")
            # Insert the meeting event into the calendar and capture the response event
            event = self.calendar_service.events().insert(calendarId='primary', body=event).execute()
            msg = f"[{self.node_id}] Meeting created: {event.get('htmlLink')}"
            log_system_message(msg)
            
            # Emit an update to the UI via SocketIO
            if self.socketio:
                 self.socketio.emit('update_meetings')

            # Add meeting details to the node's local calendar
            meeting_info_str = f"'{meeting_description}' for project '{project_id}' scheduled on {start_time.strftime('%Y-%m-%d %H:%M')} with {', '.join(participants)} (Google Calendar Event)"
            brain_calendar_entry = {
                'project_id': project_id,
                'title': meeting_description,
                'meeting_info': meeting_info_str,
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'participants': participants,
                'event_id': event['id']
            }
            self.brain.calendar.append(brain_calendar_entry)

            # Notify each participant (except self), skipping any unknown participants
            for p in participants:
                if p == self.node_id:
                    continue
                if p not in self.network.nodes:
                    log_warning(f"[{self.node_id}] Cannot notify unknown participant '{p}'. Skipping.")
                    continue

                node = self.network.nodes[p]
                # Safety check to ensure the node has a calendar attribute
                if not hasattr(node, 'calendar'):
                    setattr(node, 'calendar', [])
                # Append the meeting details to the participant's local calendar
                participant_calendar_entry = {
                    'project_id': project_id,
                    'title': meeting_description,
                    'meeting_info': meeting_info_str, # Same meeting_info_str as above
                    'start_time': start_time.isoformat(),
                    'end_time': end_time.isoformat(),
                    'participants': participants,
                    'event_id': event['id']
                }
                node.brain.calendar.append(participant_calendar_entry)
                notification = (
                    f"New meeting: '{meeting_description}' scheduled by {self.node_id} "
                    f"for {start_time.strftime('%Y-%m-%d %H:%M')}"
                )
                self.network.send_message(self.node_id, p, notification)

            return f"Meeting for project '{project_id}' scheduled for {start_time.strftime('%Y-%m-%d %H:%M')}"
            
        except Exception as e:
            log_warning(f"[{self.node_id}] Failed to create calendar event: {e}")
            print(f"[{self.node_id}] Failed to create calendar event: {e}")
            # If creation fails, revert to local scheduling
            return self._fallback_schedule_meeting(project_id, participants, start_time, end_time, meeting_title=meeting_description)
    
    def _fallback_schedule_meeting(self, project_id: str, participants: list, start_datetime: datetime, end_datetime: datetime, meeting_title: str = None):
        """
        Fallback method to locally schedule a meeting when Google Calendar is unavailable.
        
        This method simply creates a textual record of the meeting and notifies participants.
        
        Args:
            project_id (str): Identifier for the project related to the meeting.
            participants (list): List of participant identifiers.
            start_datetime (datetime): The start time of the meeting.
            end_datetime (datetime): The end time of the meeting.
            meeting_title (str, optional): The title of the meeting. Defaults to None.
        """

        effective_title = meeting_title if meeting_title else f"Meeting for project '{project_id}'"
        meeting_info_str = f"'{effective_title}' scheduled for {start_datetime.strftime('%Y-%m-%d %H:%M')} with {', '.join(participants)}, duration {(end_datetime - start_datetime).seconds // 60} minutes."
        
        # Ensure the creator is included in the participants list
        creator_present = False
        for p_existing in participants:
            if p_existing.lower() == self.node_id.lower():
                creator_present = True
                print("DEBUG", self.node_id, p_existing)
                break
        if not creator_present:
            participants.append(self.node_id)
            log_system_message(f"[{self.node_id}] Re-added self to participants list: {self.node_id} before flexible scheduling creation.")

        unique_local_event_id = f"local_{project_id.replace(' ', '_')}_{start_datetime.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

        brain_calendar_entry = {
            'project_id': project_id,
            'title': effective_title,
            'meeting_info': meeting_info_str,
            'start_time': start_datetime.isoformat(),
            'end_time': end_datetime.isoformat(),
            'participants': participants,
            'event_id': unique_local_event_id # No GCal event ID for fallback
        }
        
        # Save to the brain's calendar
        self.brain.calendar.append(brain_calendar_entry)

        log_system_message(f"[Scheduler] [{self.node_id}] Scheduled local meeting: {meeting_info_str}")

        # Notify every participant in the network, skipping any unknown participants
        for p in participants:
            log_system_message(f"[Scheduler] {type(self.node_id)} , {type(p)}")
            
            if p != self.node_id:
                if p not in self.network.nodes:
                    log_warning(f"[{self.node_id}] Cannot notify unknown participant '{p}' in fallback; skipping.")
                    continue

                node = self.network.nodes[p]
                # Safety check to ensure the node has a calendar attribute
                if not hasattr(node, 'brain'):
                    setattr(node, 'brain', type('Brain', (), {'calendar': []})())
                elif not hasattr(node.brain, 'calendar'):
                    setattr(node.brain, 'calendar', [])

                # Append the meeting details to the participant's local calendar
                node.brain.calendar.append(brain_calendar_entry)
                
                # Notify them
                notification = f"[(INFO)]Meeting '{effective_title}' ({project_id}) has been scheduled by {self.node_id} for {start_datetime.strftime('%Y-%m-%d %H:%M')}"
                self.network.send_message(self.node_id, p, notification)
                
                log_system_message(f"[{self.node_id}] Notified {p} about meeting for project '{project_id}'.")
        
        # Emit an update to the UI via SocketIO
        if self.socketio:
            self.socketio.emit('update_meetings')

        return meeting_info_str

    def _start_meeting_creation(self, initial_message, missing_info):
        """
        Initiate the meeting creation process by setting up a meeting context.
        
        This context holds the initial message and a list of missing pieces of information.
        The process will prompt the user for the missing details.
        
        Args:
            initial_message (str): The original message initiating the meeting creation.
            missing_info (list): List of strings indicating which details are missing.
        """
        
        # Initialize a dictionary to track meeting creation progress
        # self.meeting_context = {
        #     'active': True,
        #     'initial_message': initial_message,
        #     'missing_info': missing_info.copy(),
        #     'collected_info': {}
        # }
        mc = self.brain.meeting_context
        mc['active'] = True
        mc['initial_message'] = initial_message
        mc['missing_info'] = missing_info.copy()
        mc['collected_info'] = {}
        
        # Ask for the first missing piece of information
        return self._ask_for_next_meeting_info()

    def _ask_for_next_meeting_info(self):
        """
        Ask the user for the next piece of required meeting information.
        
        If all information has been collected, the method proceeds to construct the complete meeting message.
        Otherwise, it selects the next item from the missing_info list and prints a tailored question.
        """
        
        self.meeting_context = self.brain.meeting_context

        if not self.meeting_context['missing_info']:
            # All required info collected; create complete message and process meeting creation
            combined_message = self._construct_complete_meeting_message()
            self.meeting_context['active'] = False
            return self._handle_meeting_creation(combined_message)

        # Get the next missing information item
        next_info = self.meeting_context['missing_info'][0]
        
        # Predefined questions for standard meeting details
        questions = {
            'date': "On what date should the meeting be scheduled?",
            'time': "What time should the meeting be scheduled?",
            'duration': "How long should the meeting be?",
            'participants': "Who should attend the meeting?",
            'title': "What is the title or topic of the meeting?"
        }
        
        # Optionally add context for rescheduling or validation
        context = ""
        if self.meeting_context.get('is_rescheduling', False):
            context = " for rescheduling"
        elif next_info in ['date', 'time'] and 'date' in self.meeting_context['missing_info'] and 'time' in self.meeting_context['missing_info']:
            context = " (please ensure it's a future date and time)"
        
        response = questions.get(next_info, f"Please provide the {next_info} for the meeting") + context
        print(f"[{self.node_id}] Response: {response}")
        #print(self.meeting_context, self.brain.meeting_context)
        return response

    def _continue_meeting_creation(self, message, sender_id):
        """
        Continue the meeting creation flow by processing the user's answer.
        
        The response is recorded for the current missing information item, and if additional info is needed,
        the next prompt is issued. Otherwise, the complete meeting creation is triggered.
        
        Args:
            message (str): The user's response for the current information query.
            sender_id (str): The identifier for the sender.
        """        
        
        self.meeting_context = self.brain.meeting_context

        if not self.meeting_context['missing_info']:
            # Shouldn't happen, but just in case
            self.meeting_context['active'] = False
            return None

        # Remove the first missing detail, and save the user's answer under that key
        current_info = self.meeting_context['missing_info'].pop(0)
        self.meeting_context['collected_info'][current_info] = message
        
        if self.meeting_context['missing_info']:
            # More details are still required; ask the next question
            return self._ask_for_next_meeting_info()
        else:
            self.meeting_context['active'] = False
            print(f"[{self.node_id}] Response: Meeting {'rescheduled' if self.meeting_context.get('is_rescheduling') else 'scheduled'} successfully with all required information.")

            # All information collected: if rescheduling, call the respective handler; otherwise, proceed normally
            if self.meeting_context.get('is_rescheduling', False) and 'target_event_id' in self.meeting_context:
                return self._complete_meeting_rescheduling()
            else:
                combined_message = self._construct_complete_meeting_message()
                return self._handle_meeting_creation(combined_message)
            
    def _construct_complete_meeting_message(self):
        """
        Construct a complete meeting instruction message by combining the initial command with the collected details.
        
        Returns:
            str: A complete message string including title, date, time, and participants.
        """
        
        self.meeting_context = self.brain.meeting_context
        
        initial = self.meeting_context['initial_message']
        collected = self.meeting_context['collected_info']
        
        # Concatenate all gathered meeting details with appropriate labels
        complete_message = f"{initial} "
        if 'title' in collected:
            complete_message += f"Title: {collected['title']}. "
        if 'date' in collected:
            complete_message += f"Date: {collected['date']}. "
        if 'time' in collected:
            complete_message += f"Time: {collected['time']}. "
        if 'duration' in collected:
            complete_message += f"Duration: {collected['duration']} minutes. "
        if 'participants' in collected:
            complete_message += f"Participants: {collected['participants']}."
        
        return complete_message

    def _handle_meeting_creation(self, message):
        """
        Handle the complete meeting creation process.
        
        This method extracts meeting details from the combined message, validates them (including checking
        date/time formats and future scheduling), and then attempts to schedule the meeting with Google Calendar.
        
        Args:
            message (str): The complete meeting instruction that includes all necessary details.
        """
        
        # Check if the brain has the required method for extracting meeting details
        if not self.brain or not hasattr(self.brain, '_extract_meeting_details'):
            return None

        # Extract meeting details using an LLM-assisted helper method
        meeting_data = self.brain._extract_meeting_details(message)
        
        # Validate that required fields such as title and participants are present
        required_fields = ['title', 'participants', 'time']
        missing = [field for field in required_fields if not meeting_data.get(field)]
        
        if missing:
            msg = f"[{self.node_id}] Cannot schedule meeting: missing {', '.join(missing)}"
            print(msg)
            return msg
        
        # Process and normalize participant names
        participants = []
        for p in meeting_data.get("participants", []):
            p_lower = p.lower().strip()
            valid_agent_ids = {agent["id"].lower() for agent in AGENT_CONFIG}
            if p_lower in valid_agent_ids:         
                participants.append(p_lower)
        
        # Ensure the current node is included among the participants
        if not participants:
            msg = f"[{self.node_id}] Cannot schedule meeting: no valid participants"
            print(msg)
            return msg
            
        # Add the current node if not already included
        if self.node_id not in participants:
            participants.append(self.node_id)

        # Get the meeting title
        meeting_title = meeting_data.get("title")
        
        # Process meeting date and time: use provided values or defaults
        meeting_date = meeting_data.get("date", datetime.now().strftime("%Y-%m-%d"))
        meeting_time = meeting_data.get("time", (datetime.now() + timedelta(minutes=int(meeting_data.get("duration")))).strftime("%H:%M"))
        
        try:
            # Validate date and time by attempting to parse them
            try:
                start_datetime = datetime.strptime(f"{meeting_date} {meeting_time}", "%Y-%m-%d %H:%M")
                # Check if date is in the past
                current_time = datetime.now()
                if start_datetime < current_time:
                    # Instead of automatically adjusting, ask the user for a valid time
                    print(f"[{self.node_id}] Response: The meeting time {meeting_date} at {meeting_time} is in the past. Please provide a future date and time.")
                    
                    # Store context for follow-up
                    self.brain.meeting_context = {
                        'active': True,
                        'collected_info': {
                            'title': meeting_data.get("title"),
                            'participants': meeting_data.get("participants", [])
                        },
                        'missing_info': ['date', 'time'],
                        'is_rescheduling': False
                    }
                    
                    # Ask for new date and time
                    return self._ask_for_next_meeting_info()
                    
                
            except ValueError:
                # If date parsing fails, notify user instead of auto-fixing
                print(f"[{self.node_id}] Response: I couldn't understand the date/time format. Please provide the date in YYYY-MM-DD format and time in HH:MM format.")
                # Store context for follow-up
                self.brain.meeting_context = {
                    'active': True,
                    'collected_info': {
                        'title': meeting_data.get("title"),
                        'participants': meeting_data.get("participants", [])
                    },
                    'missing_info': ['date', 'time'],
                    'is_rescheduling': False
                }
                
                # Ask for new date and time
                return self._ask_for_next_meeting_info()
                
            # Determine meeting duration (defaulting to 60 minutes if unspecified)
            duration_mins = int(meeting_data.get("duration"))
            end_datetime = start_datetime + timedelta(minutes=duration_mins)

            self.brain.meeting_context['collected_info'] = {
                'title': meeting_data.get("title"),
                'participants': meeting_data.get("participants", []),
                'start_datetime': start_datetime,
                'end_datetime': end_datetime
            }

            # --- Start: Conflict Check and Resolution ---
            conflict_found = False
            conflicting_participant = None
            for p in participants:
                if not self._check_time_with_attendees(p, start_datetime, end_datetime):
                    conflict_found = True
                    conflicting_participant = p
                    log_warning(f"[{self.node_id}] Conflict detected for participant '{p}' at proposed time {start_datetime}.")
                    break # Exit loop on first conflict

            if conflict_found:
                # Call find_perfect_meeting_time to get a suggestion
                exist_conflict, proposed_start, proposed_end = self.find_perfect_meeting_time(participants, start_datetime, end_datetime)

                if not proposed_start: # Handle case where LLM fails to propose a time
                     msg = f"[{self.node_id}] Could not find an alternative time slot for all participants."
                     print(msg)
                     return msg

                # Always check the exist_conflict flag from the LLM's analysis
                if exist_conflict:
                    # Ask user to confirm the LLM's proposed time
                    formatted_proposed_time = proposed_start.strftime('%Y-%m-%d %H:%M')
                    confirm_prompt = (f"Conflict found for {conflicting_participant}. The next available slot for all participants seems to be "
                                      f"{formatted_proposed_time}. Schedule then? (yes/no)")
                    
                    creator_present = False
                    for p_existing in participants:
                        if p_existing.lower() == self.node_id.lower():
                            creator_present = True
                            break
                    if not creator_present:
                        participants.append(self.node_id)
                        log_system_message(f"[{self.node_id}] Re-added self to participants list: {self.node_id} before flexible scheduling creation.")
                    

                    # Emit an update to the UI via SocketIO
                    if self.socketio:
                        self.socketio.emit('update_meetings')
                    return confirm_prompt
                    
                    # # Use the Confirmation class via the brain instance
                    # if self.brain.confirmation.request(confirm_prompt):
                    #     # User confirmed, schedule at proposed time
                    #     log_system_message(f"[{self.node_id}] User confirmed alternative time: {formatted_proposed_time}")
                    #     meeting_id = f"meeting_{int(datetime.now().timestamp())}"
                    #     current_meeting_title = meeting_data.get("title", f"Meeting scheduled by {self.node_id}")
                        
                    #     # Ensure the creator (self.node_id) is in the participants list before creating the meeting
                    #     # This is a safeguard for the conflict resolution path.
                    #     creator_present = False
                    #     for p_existing in participants:
                    #         if p_existing.lower() == self.node_id.lower():
                    #             creator_present = True
                    #             print("DEBUG", self.node_id, p_existing)
                    #             break
                    #     if not creator_present:
                    #         participants.append(self.node_id)
                    #         log_system_message(f"[{self.node_id}] Re-added self to participants list: {self.node_id} before flexible scheduling creation.")
                        
                    #     self._create_calendar_meeting(meeting_id, current_meeting_title, participants, proposed_start, proposed_end)
                    #     msg = f"[{self.node_id}] Meeting '{current_meeting_title}' scheduled for {formatted_proposed_time} with {', '.join(participants)} after finding a conflict."
                    #     print(msg)
                    #     return msg
                    # else:
                    #     # User declined the proposed time
                    #     msg = f"[{self.node_id}] User declined the proposed alternative time. Meeting not scheduled."
                    #     print(msg)
                    #     # If declined, we stop here as per current requirement.
                    #     return msg
                else:
                     # LLM indicated no conflict OR suggested the original time was fine?
                     # Schedule at the time the LLM proposed (which might be the original time if it found no conflict)
                     log_system_message(f"[{self.node_id}] LLM found no conflict or suggested using {proposed_start}. Scheduling at proposed time.")
                     meeting_id = f"meeting_{int(datetime.now().timestamp())}"
                     meeting_title = meeting_data.get("title", f"Meeting scheduled by {self.node_id}")
                     self._create_calendar_meeting(meeting_id, meeting_title, participants, proposed_start, proposed_end)
                     msg = f"[{self.node_id}] Meeting '{meeting_title}' scheduled for {proposed_start.strftime('%Y-%m-%d %H:%M')} with {', '.join(participants)} as per conflict check."
                     print(msg)
                     return msg

            else:
                # No conflicts found by _check_time_with_attendees, schedule directly
                log_system_message(f"[{self.node_id}] No conflicts detected for the proposed time {start_datetime}. Scheduling directly.")
                meeting_id = f"meeting_{int(datetime.now().timestamp())}"
                meeting_title = meeting_data.get("title", f"Meeting scheduled by {self.node_id}")
                self._create_calendar_meeting(meeting_id, meeting_title, participants, start_datetime, end_datetime)
                msg = f"[{self.node_id}] Meeting '{meeting_title}' scheduled for {start_datetime.strftime('%Y-%m-%d %H:%M')} with {', '.join(participants)}"
                print(msg)
                return msg
            # --- End: Conflict Check and Resolution ---

            # Generate a unique meeting ID and set a meeting title
            # meeting_id = f"meeting_{int(datetime.now().timestamp())}"
            # meeting_title = meeting_data.get("title", f"Meeting scheduled by {self.node_id}")
            #
            # print(f"[{self.node_id}] Meeting title: {meeting_title}, participants: {participants}, start_datetime: {start_datetime}, end_datetime: {end_datetime}")
            # Schedule the meeting using the helper for creating calendar events
            # self._create_calendar_meeting(meeting_id, meeting_title, participants, start_datetime, end_datetime)

            # Confirm to user with reliable times
            # msg = f"[{self.node_id}] Meeting '{meeting_title}' scheduled for {meeting_date} at {meeting_time} with {', '.join(participants)}"
            # print(msg)
            # return msg
        
        except Exception as e:
            msg = f"[{self.node_id}] Error scheduling meeting: {str(e)}"
            print(msg)

    def _check_time_with_attendees(self, participant_id: str, start_datetime: datetime, end_datetime: datetime) -> bool:
        """
        Check if the specified time range is available for a participant.
        
        Args:
            participant_id (str): The identifier for the participant to check.
            start_datetime (datetime): The proposed start time for the meeting.
            end_datetime (datetime): The proposed end time for the meeting.
            
        Returns:
            bool: True if the time is available, False otherwise.
        """

        participant_calendar = self.brain.calendar

        #print(participant_calendar)

        if not participant_calendar:
            return True
        
        for meeting in participant_calendar:
            # only consider meetings that include this participant
            if participant_id not in meeting['participants']:
                continue

            # parse ISO strings to datetimes
            meeting_start = datetime.fromisoformat(meeting['start_time'])
            meeting_end = datetime.fromisoformat(meeting['end_time'])
            
            # Check if the proposed time overlaps with any existing meetings
            if (start_datetime > meeting_start and end_datetime < meeting_end):
                return False
            elif (start_datetime == meeting_start or end_datetime == meeting_end):
                return False
            elif (start_datetime < meeting_end and end_datetime > meeting_start):
                return False
            else:
                return True

    def find_perfect_meeting_time(self, participants: list[str], start_datetime: datetime, end_datetime: datetime) -> str:
        """
        Find a perfect meeting time for all participants by checking their availability.

        Goes through all participants' calendars and finds a time slot that works for everyone.
        
        Args:
            participants (list): The identifier for all participants.
            start_datetime (datetime): The proposed start time for the meeting.
            end_datetime (datetime): The proposed end time for the meeting.
            
        Returns:
            str: A confirmation message if the proposed meeting should be scheduled. (use class Confirmation)
        """

        print('DEBUG: Entered find_perfect_meeting_time')

        duration = (end_datetime - start_datetime).total_seconds() / 60
        calendar = self.brain.calendar
        if not calendar:
            print(f" Calendar service not available, can't schedule meetings")
            print(calendar)
            return
        
        # TODO: Replace with a conversation between agents to find the perfect meeting time
        prompt = f"""
        Extract all meetings from this calender for every node: '{calendar}'

        Identitfy if there are any potential conflicts with the existing meetings in {calendar}
        with a new meeting that goes from {start_datetime} to {end_datetime} with {participants} as participants.

        If there is a conflict return the meeting time and participants of the conflicting meeting and propose the next possible time slot with a duration of {duration} minutes
        that is free for all participants: {participants}. 
        
        Return a JSON object with these fields:
        - exist_conflict: A bool that is true if there are meeting conflicts and false otherwise 
        - proposed_start_time: The start time of the next possible meeting slot if there are meeting conflicts and None otherwise
        
        IMPORTANT: exist_conflict MUST be a bool. proposed_start_time MUST be a datetime. ALL participants MUST be free (i.e. have no meetings scheduled) during the proposed time slot.
        """
    
        response = self.node.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
        
        response_content = response.choices[0].message.content

        print(response_content, participants)

        # response_content = LLMClient.chat(self, prompt)
        # print(f"[{self.node_id}] Response: {response_content}")

        try:
            reschedule_data = json.loads(response_content)
        except json.JSONDecodeError as e:
            msg = f"[{self.node_id}] Error parsing rescheduling JSON: {e}"
            log_error(f"[{self.node_id}] Error parsing rescheduling JSON: {e}")
            return msg
        
        print(reschedule_data)

        exist_conflict = None
        if "exist_conflict" in reschedule_data and reschedule_data["exist_conflict"]:
            exist_conflict = bool(reschedule_data["exist_conflict"])
        
        print(exist_conflict)

        proposed_start_time = None
        if "proposed_start_time" in reschedule_data and reschedule_data['proposed_start_time']:
            proposed_start_time = datetime.strptime(reschedule_data['proposed_start_time'], "%Y-%m-%dT%H:%M:%S")
        print(proposed_start_time)
        
        proposed_end_time = proposed_start_time + (end_datetime - start_datetime)

        self.brain.confirmation_context = {
            'active': True,
            'context': 'schedule meeting',
            'initial_message': f"Proposed meeting time: {proposed_start_time} to {proposed_end_time}",
            'start_datetime': proposed_start_time,
            'end_datetime': proposed_end_time
        }

        print(exist_conflict, proposed_start_time, proposed_end_time)

        # TODO: Return a confirmation message with the proposed time slot and participants (class Confirmation)      
        return exist_conflict, proposed_start_time, proposed_end_time


    def _handle_list_meetings(self):
        """
        List upcoming meetings either from the Google Calendar service or the local calendar.
        
        This method retrieves events, formats their details (including title, date/time, and attendees),
        and prints them in a user-friendly format.
        """
        
        if not self.calendar_service:
            msg = f"[{self.node_id}] Calendar service not available, showing local meetings only"
            log_system_message(f"[{self.node_id}] Calendar service not available, showing local meetings only")

            if not self.calendar:
                msg += f"[{self.node_id}] No meetings scheduled."
                log_system_message(msg)
                return msg
            
            msg += f"\n[{self.node_id}] Upcoming meetings:"
            log_system_message(f"[{self.node_id}] Upcoming meetings:")
            for meeting in self.brain.calendar:
                # Format meeting details
                meeting_info = meeting.get('meeting_info', 'No details available')
                msg = msg + f"\n  - {meeting_info}"
                log_system_message(f"  - {meeting_info}")
            
            return msg
        
        try:
            # Retrieve current time in the required ISO format for querying events
            now = datetime.now(timezone.utc).isoformat()
            events_result = self.calendar_service.events().list(
                calendarId='primary',
                timeMin=now,
                maxResults=10,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])
            
            if not events:
                msg = f"[{self.node_id}] No upcoming meetings found."
                log_system_message(msg)
                return msg
            
            msg = f"[{self.node_id}] Upcoming meetings:"
            log_system_message(f"[{self.node_id}] Upcoming meetings:")
            for event in events:
                # Get start time from event details
                start = event['start'].get('dateTime', event['start'].get('date'))
                start_time = datetime.fromisoformat(start.replace('Z', '+00:00'))
                # Format attendee emails by extracting the user part
                attendees = ", ".join([a.get('email', '').split('@')[0] for a in event.get('attendees', [])])
                msg = msg + f"\n  - {event['summary']} on {start_time.strftime('%Y-%m-%d at %H:%M')} with {attendees}"
                log_system_message(f"  - {event['summary']} on {start_time.strftime('%Y-%m-%d at %H:%M')} with {attendees}")
                print (start_time)
            return msg
        
        except Exception as e:
            msg = f"[{self.node_id}] Error listing meetings: {str(e)}"
            log_error(f"[{self.node_id}] Error listing meetings: {str(e)}")
            return msg

    # TODO: Refactor this function to have return values instead of print statements 
    def _handle_meeting_rescheduling(self, message):
        """
        Handle meeting rescheduling requests by extracting new scheduling details and updating the event.
        
        The method performs the following:
          - Uses LLM to extract rescheduling details such as meeting identifier, original date, new date/time, and duration.
          - Searches the Google Calendar for the meeting to be rescheduled using a simple scoring system.
          - Validates the new date and time.
          - Updates the event in Google Calendar and notifies participants.
        
        Args:
            message (str): The message containing rescheduling instructions.
        """
        
        if not self.calendar_service:
            log_system_message(f"[{self.node_id}] Calendar service not available, can't reschedule meetings")
            return
        
        try:
            # Construct a prompt instructing the LLM to extract detailed rescheduling data
            prompt = f"""
            Extract meeting rescheduling details from this message: '{message}'
            
            Identify EXACTLY which meeting needs rescheduling by looking for:
            1. Meeting title or topic (as a simple text string)
            2. Participants involved (as names only)
            3. Original date/time
            
            And what the new schedule should be:
            1. New date (YYYY-MM-DD format)
            2. New time (HH:MM format in 24-hour time)
            3. New duration in minutes (as a number only)
            
            Return a JSON object with these fields:
            - meeting_identifier: A simple text string to identify which meeting to reschedule
            - original_date: Original meeting date if mentioned (YYYY-MM-DD format or null)
            - new_date: New meeting date (YYYY-MM-DD format)
            - new_time: New meeting time (HH:MM format)
            - new_duration: New duration in minutes (or null to keep the same)
            
            IMPORTANT: ALL values must be simple strings or integers, not objects or arrays.
            The meeting_identifier MUST be a simple string.
            """
            
            response = self.node.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            
            response_content = response.choices[0].message.content
            try:
                reschedule_data = json.loads(response_content)
            except json.JSONDecodeError as e:
                log_error(f"[{self.node_id}] Error parsing rescheduling JSON: {e}")
                return
            
            # Extract and normalize data from the JSON response
            meeting_identifier = ""
            if "meeting_identifier" in reschedule_data:
                if isinstance(reschedule_data["meeting_identifier"], str):
                    meeting_identifier = reschedule_data["meeting_identifier"].lower()
                else:
                    meeting_identifier = str(reschedule_data["meeting_identifier"]).lower()

            original_date = None
            if "original_date" in reschedule_data and reschedule_data["original_date"]:
                original_date = str(reschedule_data["original_date"])
            
            new_date = None
            if "new_date" in reschedule_data and reschedule_data["new_date"]:
                new_date = str(reschedule_data["new_date"])
            
            new_time = "10:00"  # Default time
            if "new_time" in reschedule_data and reschedule_data["new_time"]:
                new_time = str(reschedule_data["new_time"])
            
            new_duration = None
            if "new_duration" in reschedule_data and reschedule_data["new_duration"]:
                try:
                    new_duration = int(reschedule_data["new_duration"])
                except (ValueError, TypeError):
                    new_duration = None
            
            # Validate that a meeting identifier and new date are provided
            if not meeting_identifier:
                log_warning(f"[{self.node_id}] Could not determine which meeting to reschedule")
                return
            
            if not new_date:
                log_warning(f"[{self.node_id}] No new date specified for rescheduling")
                return
            
            # Retrieve upcoming meetings to search for a matching event
            try:
                now = datetime.now(timezone.utc).isoformat()
                events_result = self.calendar_service.events().list(
                    calendarId='primary',
                    timeMin=now,
                    maxResults=20,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                events = events_result.get('items', [])
            except Exception as e:
                log_error(f"[{self.node_id}] Error fetching calendar events: {str(e)}")
                return
            
            if not events:
                log_warning(f"[{self.node_id}] No upcoming meetings found to reschedule")
                return
            
            # Use a scoring system to find the best matching event based on title, attendees, and original date
            target_event = None
            best_match_score = 0
            
            for event in events:
                score = 0
                
                # Check title match
                event_title = event.get('summary', '').lower()
                if meeting_identifier in event_title:
                    score += 3
                elif any(word in event_title for word in meeting_identifier.split()):
                    score += 1
                
                # Check attendees match
                attendees = []
                for attendee in event.get('attendees', []):
                    email = attendee.get('email', '')
                    if isinstance(email, str):
                        attendees.append(email.lower())
                    else:
                        attendees.append(str(email).lower())
                    
                if any(meeting_identifier in attendee for attendee in attendees):
                    score += 2
                
                # Check date match if original date was specified
                if original_date:
                    start_time = event['start'].get('dateTime', event['start'].get('date', ''))
                    if isinstance(start_time, str) and original_date in start_time:
                        score += 4
                
                # Update best match if this is better
                if score > best_match_score:
                    best_match_score = score
                    target_event = event
            
            # Require a minimum matching score
            if best_match_score < 1:
                log_warning(f"[{self.node_id}] Could not find a meeting matching '{meeting_identifier}'")
                return
            
            if not target_event:
                log_warning(f"[{self.node_id}] No matching meeting found for '{meeting_identifier}'")
                return
            
            # Validate the new date and time format and ensure the new time is in the future
            try:
                # Parse new date and time
                new_start_datetime = datetime.strptime(f"{new_date} {new_time}", "%Y-%m-%d %H:%M")
                
                # Check if date is in the past
                if new_start_datetime < datetime.now():
                    log_system_message(f"[{self.node_id}] Response: The rescheduled time {new_date} at {new_time} is in the past. Please provide a future date and time.")
                    
                    # Ask for new date and time
                    self.meeting_context = {
                        'active': True,
                        'collected_info': {
                            'title': target_event.get('summary', 'Meeting'),  # Keep original title
                            'participants': []  # We'll keep the same participants
                        },
                        'missing_info': ['date', 'time'],
                        'is_rescheduling': True,
                        'target_event_id': target_event['id'],
                        'target_event': target_event  # Store the whole event to preserve details
                    }
                    
                    self._ask_for_next_meeting_info()
                    return
            except ValueError:
                log_system_message(f"[{self.node_id}] Response: I couldn't understand the date/time format. Please provide the date in YYYY-MM-DD format and time in HH:MM format.")
                
                # Ask for new date and time
                self.meeting_context = {
                    'active': True,
                    'collected_info': {
                        'title': target_event.get('summary', 'Meeting'),  # Keep original title
                        'participants': []  # We'll keep the same participants
                    },
                    'missing_info': ['date', 'time'],
                    'is_rescheduling': True,
                    'target_event_id': target_event['id'],
                    'target_event': target_event  # Store the whole event to preserve details
                }
                
                self._ask_for_next_meeting_info()
                return
            
            # Determine the new end time using either the provided new duration or the event's original duration
            try:
                # Extract original start and end times
                original_start = datetime.fromisoformat(target_event['start'].get('dateTime').replace('Z', '+00:00'))
                original_end = datetime.fromisoformat(target_event['end'].get('dateTime').replace('Z', '+00:00'))
                original_duration = (original_end - original_start).total_seconds() / 60
                
                # Use new duration if specified, otherwise keep original duration
                if new_duration is not None and new_duration > 0:
                    duration_to_use = new_duration
                else:
                    duration_to_use = original_duration
                    
                new_end_datetime = new_start_datetime + timedelta(minutes=duration_to_use)
                
                # Update the target event's start and end times
                target_event['start']['dateTime'] = new_start_datetime.isoformat()
                target_event['end']['dateTime'] = new_end_datetime.isoformat()
                
                # Update event in Google Calendar
                updated_event = self.calendar_service.events().update(
                    calendarId='primary',
                    eventId=target_event['id'],
                    body=target_event
                ).execute()
                
                # Print success message with user-friendly time format
                meeting_title = updated_event.get('summary', 'Untitled meeting')
                formatted_time = new_start_datetime.strftime("%I:%M %p")  # 12-hour format with AM/PM
                formatted_date = new_start_datetime.strftime("%B %d, %Y")  # Month day, year
                
                log_system_message(f"[{self.node_id}] Response: Meeting '{meeting_title}' has been rescheduled to {formatted_date} at {formatted_time}.")
                
                # Update local calendar records
                for meeting in self.calendar:
                    if meeting.get('event_id') == updated_event['id']:
                        meeting['meeting_info'] = f"{meeting_title} (Rescheduled to {formatted_date} at {formatted_time})"
                
                # Notify all attendees about the rescheduled meeting
                attendees = updated_event.get('attendees', [])
                for attendee in attendees:
                    attendee_id = attendee.get('email', '').split('@')[0]
                    if attendee_id in self.network.nodes:
                        # Update their local calendar
                        for meeting in self.network.nodes[attendee_id].calendar:
                            if meeting.get('event_id') == updated_event['id']:
                                meeting['meeting_info'] = f"{meeting_title} (Rescheduled to {formatted_date} at {formatted_time})"
                        
                        # Send notifications
                        notification = (
                            f"Your meeting '{meeting_title}' has been rescheduled by {self.node_id}.\n"
                            f"New date: {formatted_date}\n"
                            f"New time: {formatted_time}\n"
                            f"Duration: {int(duration_to_use)} minutes"
                        )
                        self.network.send_message(self.node_id, attendee_id, notification)
                
            except Exception as e:
                log_error(f"[{self.node_id}] Error updating the meeting: {str(e)}")
                log_system_message(f"[{self.node_id}] Response: There was an error rescheduling the meeting. Please try again.")
            
        except Exception as general_e:
            log_error(f"[{self.node_id}] General error in meeting rescheduling: {str(general_e)}")
    
    def _handle_meeting_cancellation(self, message):
        """
        Handle meeting cancellation requests based on natural language commands.
        
        This method:
          - Uses LLM to extract cancellation details from the message.
          - Retrieves upcoming meetings.
          - Filters meetings based on specified title, participants, and date criteria.
          - Deletes matching events from Google Calendar and notifies participants.
        
        Args:
            message (str): The cancellation command as a natural language message.
        """
        
        # if not self.calendar_service:
        #     msg = f"[{self.node_id}] Calendar service not available, can't cancel meetings"
        #     print(f"[{self.node_id}] Calendar service not available, can't cancel meetings")
        #     return msg
        
        # First, get all meetings from calendar
        try:
            # Use OpenAI to extract cancellation details
            prompt = f"""
            Extract meeting cancellation details from this message: '{message}'
            
            Return a JSON object with these fields:
            - title: The meeting title or topic to cancel (or null if not specified)
            - with_participants: Array of participants in the meeting to cancel (or empty if not specified)
            - date: Meeting date to cancel (YYYY-MM-DD format, or null if not specified)
            
            Only include information that is explicitly mentioned.
            """
            
            response = self.node.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            
            cancel_data = json.loads(response.choices[0].message.content)

            # TODO: Add a method for local calendar handling
            if not self.calendar_service:
                return self._fallback_cancel_meeting(cancel_data)
            
            # Get upcoming meetings
            now = datetime.now(timezone.utc).isoformat()
            events_result = self.calendar_service.events().list(
                calendarId='primary',
                timeMin=now,
                maxResults=10,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])
            
            if not events:
                msg = f"[{self.node_id}] No upcoming meetings found to cancel."
                log_system_message(f"[{self.node_id}] No upcoming meetings found to cancel")
                return msg
            
            # Filter events based on cancellation criteria
            title_filter = cancel_data.get("title")
            participants_filter = [p.lower() for p in cancel_data.get("with_participants", [])]
            date_filter = cancel_data.get("date")
            
            cancelled_count = 0

            # Iterate over events and determine if they match the cancellation criteria
            for event in events:
                should_cancel = True
                
                # Check title match if specified
                if title_filter and title_filter.lower() not in event.get('summary', '').lower():
                    should_cancel = False
                
                # Check participants if specified
                if participants_filter:
                    event_attendees = [a.get('email', '').split('@')[0].lower() 
                                      for a in event.get('attendees', [])]
                    if not any(p in event_attendees for p in participants_filter):
                        should_cancel = False
                
                # Check date if specified
                if date_filter:
                    event_start = event.get('start', {}).get('dateTime', event.get('start', {}).get('date'))
                    if event_start and date_filter not in event_start:
                        should_cancel = False
                
                if should_cancel:
                    # Delete the event from the calendar
                    self.calendar_service.events().delete(
                        calendarId='primary',
                        eventId=event['id']
                    ).execute()
                    
                    # Remove the event from the local calendar records
                    self.calendar = [m for m in self.calendar if m.get('event_id') != event['id']]
                    
                    # Notify attendees about the cancellation
                    event_attendees = [a.get('email', '').split('@')[0] for a in event.get('attendees', [])]
                    for attendee in event_attendees:
                        if attendee in self.network.nodes:
                            # Update their local calendar
                            self.network.nodes[attendee].calendar = [
                                m for m in self.network.nodes[attendee].calendar 
                                if m.get('event_id') != event['id']
                            ]
                            # Notify them
                            notification = f"Meeting '{event.get('summary')}' has been cancelled by {self.node_id}"
                            self.network.send_message(self.node_id, attendee, notification)
                
                    cancelled_count += 1
                    msg = f"[{self.node_id}] Meeting '{event.get('summary')}' cancelled."
                    log_system_message(f"[{self.node_id}] Cancelled meeting: {event.get('summary')}")
                    
                    # Emit an update to the UI via SocketIO for cancellation
                    if self.socketio:
                        self.socketio.emit('update_meetings')
                    return msg # Return after the first successful cancellation and notification
            
            if cancelled_count == 0:
                msg = f"[{self.node_id}] No meetings found matching the cancellation criteria"
                log_system_message(f"[{self.node_id}] No meetings found matching the cancellation criteria")
                return msg
            else:
                msg = f"[{self.node_id}] Cancelled {cancelled_count} meeting(s)"
                log_system_message(f"[{self.node_id}] Cancelled {cancelled_count} meeting(s)")
                return msg
            
        except Exception as e:
            msg = f"[{self.node_id}] Error cancelling meeting: {str(e)}"
            log_error(f"[{self.node_id}] Error cancelling meeting: {str(e)}")
            return msg    
        
    # TODO: Work on the logic! Right now it just cancels all meetings with minor criteria    
    def _fallback_cancel_meeting(self, cancel_data: dict) -> str:
        """
        Fallback method for scheduling a meeting when the calendar service is unavailable.
        
        This method handles the scheduling of meetings locally and updates the local calendar records.
        
        Args:
            cancel_data (Dict[str, Any]): Data containing meeting details to be scheduled.
            
        Returns:
            str: Confirmation message indicating the result of the scheduling attempt.
        """
        log_system_message(f"[Scheduler] [{self.node_id}] Calendar service not available, using local scheduling")
        
        try:
            date_filter = cancel_data.get("date")
            participants_filter = [p.lower() for p in cancel_data.get("with_participants", [])]
            title_filter = cancel_data.get("title")
            now = datetime.now(timezone.utc).isoformat()
            events = self._get_local_meetings_on_date(date_filter)
        
            if not events:
                msg = f"[{self.node_id}] No upcoming meetings found to cancel."
                log_system_message(f"[{self.node_id}] No upcoming meetings found to cancel")
                return msg
                      
            cancelled_count = 0

            # Iterate over events and determine if they match the cancellation criteria
            for event in events:
                should_cancel = True
                
                log_system_message(f"[Scheduler] [{self.node_id}] Checking event: {event.get('meeting_info')}")
                
                #TODO ...
                # Check title match if specified
                if title_filter and title_filter.lower() not in event.get['meeting_info'].lower():
                    should_cancel = False
                
                # Check participants if specified
                if participants_filter:
                    event_attendees = event.get['participants', []]
                    if not any(p in event_attendees for p in participants_filter):
                        should_cancel = False
                
                # Check date if specified
                if date_filter:
                    event_start = event.get('start_time')
                    if event_start and date_filter not in event_start:
                        should_cancel = False
                
                if should_cancel and event != None:
                    # Delete the event from the calendar
                    if event in self.brain.calendar:
                        self.brain.calendar.remove(event)

                    # Notify attendees about the cancellation
                    for attendee in event.get('participants', []):
                        
                        log_system_message(f"[Scheduler] [{self.node_id}] Notifying {attendee} about cancellation")
                        
                        # Update their local calendar
                        self.network.nodes[attendee].brain.calendar = [
                            m for m in self.network.nodes[attendee].brain.calendar 
                            if m.get('event_id') != event.get('event_id')
                        ]
                        # Notify them
                        notification = f"[(INFO)]Meeting '{event.get('event_id')}': '{event.get('meeting_info')}' has been cancelled by {self.node_id}"
                        self.network.send_message(self.node_id, attendee, notification)
            
                    cancelled_count += 1
                    msg = f"[{self.node_id}] Meeting '{event.get('summary')}' cancelled."
                    
                    log_system_message(f"[Scheduler] [{self.node_id}] Cancelled meeting: {event.get('summary')}")
                    
                    print(f"[{self.node_id}] Cancelled meeting: {event.get('summary')}")
            
            if cancelled_count == 0:
                msg = f"[{self.node_id}] No meetings found matching the cancellation criteria"
                log_system_message(f"[{self.node_id}] No meetings found matching the cancellation criteria")
                return msg
            else:
                msg = f"[{self.node_id}] Cancelled {cancelled_count} meeting(s)"
                log_system_message(f"[{self.node_id}] Cancelled {cancelled_count} meeting(s)")
                return msg
            
        except Exception as e:
            msg = f"[{self.node_id}] Error cancelling meeting: {str(e)}"
            log_error(f"[{self.node_id}] Error cancelling meeting: {str(e)}")
            return msg

    def _get_local_meetings_on_date(self, date: str) -> list:
        """
        Retrieve meetings on a given date from the local calendar.
        
        Args:
            date_filter (str): Date filter to apply when retrieving meetings.
            
        Returns:
            list: List(Dict[str, Any]) of upcoming meetings.
        """
        
        log_system_message(f"[Scheduler] [{self.node_id}] Retrieving local meetings on date: {date}")
        
        calendar = self.brain.calendar
        meeting_list = []
        
        for event in calendar:
            event_start_str = event.get('start_time')
            if type(event_start_str) == str:
                event_dt = datetime.fromisoformat(event_start_str)
            parsed_date = datetime.strptime(date, "%Y-%m-%d").date()
            
            if event_dt.date() == parsed_date:
                meeting_list.append(event)
                log_system_message(f"[Scheduler] [{self.node_id}] Meeting found: {event.get('meeting_info')}")
                print(f"[{self.node_id}] Meeting found: {event.get('meeting_info')}")
        
        return meeting_list
            
        pass
        
        
    def _create_calendar_meeting(self, meeting_id, title, participants, start_datetime, end_datetime):
        """
        Create a meeting event in Google Calendar.
        
        Constructs the event details, attempts to insert the event into the primary calendar,
        updates the local calendar records, and sends notifications to other participants.
        If the calendar service is unavailable, falls back to local scheduling.
        
        Args:
            meeting_id (str): Unique identifier for the meeting.
            title (str): The title of the meeting.
            participants (list): List of participant identifiers.
            start_datetime (datetime): The start time of the meeting.
            end_datetime (datetime): The end time of the meeting.
        """
        
        # If calendar service is not available, fall back to local scheduling
        if not self.calendar_service:
            log_system_message(f"[{self.node_id}] Calendar service not available, using local scheduling")
            return self._fallback_schedule_meeting(meeting_id, participants, start_datetime, end_datetime, meeting_title=title)
            
        
        try:
            local_tz_name = tzlocal.get_localzone_name()
        except Exception: # Catch potential errors and fallback
            local_tz_name = 'UTC' # Fallback timezone

        # Create event
        event = {
            'summary': title,  # Use title as the summary for Google Calendar
            'start': {
                'dateTime': start_datetime.isoformat(),
                'timeZone': local_tz_name,
            },
            'end': {
                'dateTime': end_datetime.isoformat(),
                'timeZone': local_tz_name,
            },
            'attendees': [{'email': f'{p}@example.com'} for p in participants],
        }

        try:
            event = self.calendar_service.events().insert(calendarId='primary', body=event).execute()
            
            # Correctly format date and time for user display
            meeting_date = start_datetime.strftime("%Y-%m-%d")
            meeting_time = start_datetime.strftime("%H:%M")
            
            log_system_message(f"[{self.node_id}] Meeting created: {event.get('htmlLink')}")
            log_system_message(f"[{self.node_id}] Meeting '{title}' scheduled for {meeting_date} at {meeting_time} with {', '.join(participants)}")
            
            # Create meeting info string
            meeting_info = f"Meeting '{title}' scheduled for {meeting_date} at {meeting_time} with {', '.join(participants)}"
            
            # Add the meeting to the local calendar
            calendar_entry = {
                'project_id': meeting_id,
                'start_time': start_datetime.isoformat(),
                'end_time': end_datetime.isoformat(),
                'participants': participants,
                'meeting_info': meeting_info,
                'title': title,  # Store the title separately
                'event_id': event['id']
            }
            self.calendar.append(calendar_entry)
            
            # Update the brain's calendar with the new event
            self.brain.calendar.append(calendar_entry)

            # Notify each participant (if not the sender) about the scheduled meeting
            for p in participants:
                if p != self.node_id and p in self.network.nodes:
                    # Create a copy of the calendar entry for the participant
                    participant_entry = calendar_entry.copy()
                    self.network.nodes[p].brain.calendar.append(participant_entry)
                    notification = f"New meeting: '{title}' scheduled by {self.node_id} for {meeting_date} at {meeting_time}"
                    self.network.send_message(self.node_id, p, notification)

            # Emit an update to the UI via SocketIO
            if self.socketio:
                 self.socketio.emit('update_meetings')

            return f"Meeting '{title}' scheduled successfully. Check your calendar."
        except Exception as e:
            log_error(f"[{self.node_id}] Failed to create calendar event: {e}")
            # Fallback to local calendar
            return self._fallback_schedule_meeting(meeting_id, participants, start_datetime, end_datetime, meeting_title=title)

    #TODO: Add correct return statements to this function and handle separation of concerns nicely
    def _complete_meeting_rescheduling(self):
        """
        Finalizes the meeting rescheduling process using details from `meeting_context`.

        Retrieves the target Google Calendar event, applies the new date/time
        (adjusting to the future if necessary), updates the event, and notifies
        attendees. Emits a SocketIO event on success.

        Returns:
            Optional[str]: A notification message for the initiating user or None if
                           the process couldn't be completed (e.g., context inactive).
                           Returns an error message string to the user on failure.
        """
        # Ensure meeting_context is active and available
        if not hasattr(self, 'meeting_context') or not self.meeting_context.get('active'):
            log_warning(f"[{self.node_id}] _complete_meeting_rescheduling called with inactive or missing context.")
            return None
        
        # Retrieve necessary details from the meeting context
        new_date = self.meeting_context['collected_info'].get('date')
        new_time = self.meeting_context['collected_info'].get('time')
        target_event_id = self.meeting_context.get('target_event_id')

        if not all([new_date, new_time, target_event_id]):
            log_error(f"[{self.node_id}] Missing critical info in meeting_context for rescheduling: date={new_date}, time={new_time}, event_id={target_event_id}")
            return "Error: Missing critical information to reschedule the meeting."
        
        try:
            # Fetch the full event from Google Calendar
            event = self.calendar_service.events().get(
                calendarId='primary',
                eventId=target_event_id
            ).execute()
            
            # Parse the new date and time provided by the user
            new_start_datetime = datetime.strptime(f"{new_date} {new_time}", "%Y-%m-%d %H:%M")
            
            # Adjust if the new time is in the past
            if new_start_datetime < datetime.now():
                log_system_message(f"[{self.node_id}] Reschedule time {new_start_datetime} is in the past. Adjusting to tomorrow.")
                tomorrow = datetime.now() + timedelta(days=1)
                new_start_datetime = datetime(
                    tomorrow.year, tomorrow.month, tomorrow.day,
                    new_start_datetime.hour, new_start_datetime.minute
                )
            
            # Calculate the new end time based on the event's original duration
            original_start_iso = event['start'].get('dateTime')
            original_end_iso = event['end'].get('dateTime')
            if not original_start_iso or not original_end_iso:
                log_error(f"[{self.node_id}] Original event {target_event_id} is missing start/end dateTime.")
                return "Error: Could not determine original meeting duration."

            original_start = datetime.fromisoformat(original_start_iso.replace('Z', '+00:00'))
            original_end = datetime.fromisoformat(original_end_iso.replace('Z', '+00:00'))
            original_duration_minutes = (original_end - original_start).total_seconds() / 60
            
            new_end_datetime = new_start_datetime + timedelta(minutes=original_duration_minutes)
            
            # Update the event's start and end times in the local event object
            event['start']['dateTime'] = new_start_datetime.isoformat()
            event['end']['dateTime'] = new_end_datetime.isoformat()
            
            # Update the event in Google Calendar
            updated_event = self.calendar_service.events().update(
                calendarId='primary',
                eventId=target_event_id,
                body=event
            ).execute()
            
            # Prepare user-friendly formatted date and time for notifications
            meeting_title = updated_event.get('summary', 'Untitled meeting')
            formatted_time = new_start_datetime.strftime("%I:%M %p") # e.g., 03:00 PM
            formatted_date = new_start_datetime.strftime("%B %d, %Y") # e.g., July 26, 2024
            
            user_confirmation_message = f"Meeting '{meeting_title}' has been rescheduled to {formatted_date} at {formatted_time}."
            log_system_message(f"[{self.node_id}] {user_confirmation_message}")
            print(f"[{self.node_id}] Response: {user_confirmation_message}") # For CLI/debug
            
            # Update local calendar records for the current node
            if hasattr(self, 'calendar') and isinstance(self.calendar, list):
                for local_meeting_idx, local_meeting in enumerate(self.calendar):
                    if local_meeting.get('event_id') == updated_event['id']:
                        self.brain.calendar[local_meeting_idx]['meeting_info'] = f"{meeting_title} (Rescheduled to {formatted_date} at {formatted_time})"
                        self.brain.calendar[local_meeting_idx]['start_time'] = new_start_datetime.isoformat()
                        self.brain.calendar[local_meeting_idx]['end_time'] = new_end_datetime.isoformat()
                        break
            
            # Notify each attendee about the rescheduled meeting
            attendees = updated_event.get('attendees', [])
            notification_message_for_attendees = (
                f"Your meeting '{meeting_title}' has been rescheduled by {self.node_id}.\n"
                f"New date: {formatted_date}\n"
                f"New time: {formatted_time}"
            )
            for attendee in attendees:
                attendee_id = attendee.get('email', '').split('@')[0]
                if self.network and attendee_id in self.network.nodes and attendee_id != self.node_id:
                    # Update attendee's local calendar (if they have one)
                    attendee_node_brain = self.network.nodes[attendee_id].brain
                    if hasattr(attendee_node_brain, 'calendar') and isinstance(attendee_node_brain.calendar, list):
                        for local_meeting_idx, local_meeting in enumerate(attendee_node_brain.calendar):
                            if local_meeting.get('event_id') == updated_event['id']:
                                attendee_node_brain.calendar[local_meeting_idx]['meeting_info'] = f"{meeting_title} (Rescheduled to {formatted_date} at {formatted_time})"
                                attendee_node_brain.calendar[local_meeting_idx]['start_time'] = new_start_datetime.isoformat()
                                attendee_node_brain.calendar[local_meeting_idx]['end_time'] = new_end_datetime.isoformat()
                                break
                    
                    # Send network message notification
                    self.network.send_message(self.node_id, attendee_id, notification_message_for_attendees)
                    
            # Emit an update to the UI via SocketIO for rescheduling success
            if self.socketio:
                self.socketio.emit('update_meetings', room=self.node_id) # Or general room if applicable
            
            self.meeting_context['active'] = False # Deactivate context after successful reschedule
            return user_confirmation_message
        
        except Exception as e:
            log_error(f"[{self.node_id}] Error completing meeting rescheduling for event {target_event_id}: {str(e)}")
            # Provide a user-friendly error message
            error_response = "There was an error rescheduling the meeting. Please try again or check the logs."
            print(f"[{self.node_id}] Response: {error_response}") # For CLI/debug
            self.meeting_context['active'] = False # Deactivate context on error too
            return error_response
    
    def handle_calendar(self, intent: dict, message: str):
        """
        Routes calendar-related intents to appropriate handler methods.

        Based on the 'action' in the `intent` dictionary (e.g., 'schedule_meeting',
        'list_meetings'), this method calls the corresponding private helper
        method (e.g., `_start_meeting_creation`, `_handle_list_meetings`).

        Args:
            intent (dict): Parsed calendar intent, containing 'action', 'missing_info',
                           and other relevant details.
            message (str): The original user message that triggered the calendar action.

        Returns:
            Optional[str]: The result from the called handler method, typically a
                           message for the user or None.
        """
        # Early exit if not a calendar command or if intent is missing
        if not intent or not intent.get('is_calendar_command', False):
            return None

        action = intent.get('action')
        missing_info = intent.get('missing_info', []) # Default to empty list if not present

        # Route to the appropriate handler based on the detected action
        if action == 'schedule_meeting':
            log_system_message(f"[Scheduler] [{self.node_id}] Routing to meeting creation. Missing info: {missing_info}")
            if missing_info:
                # If information is missing, initiate the interactive meeting creation process
                return self._start_meeting_creation(message, missing_info)
            else:
                # If all information is present, proceed directly to handling meeting creation
                return self._handle_meeting_creation(message)
        elif action == 'list_meetings':
            log_system_message(f"[Scheduler] [{self.node_id}] Routing to _handle_list_meetings")
            return self._handle_list_meetings()
        elif action == 'cancel_meeting':
            log_system_message(f"[Scheduler] [{self.node_id}] Routing to _handle_meeting_cancellation")
            return self._handle_meeting_cancellation(message)
        elif action == 'reschedule_meeting':
            log_system_message(f"[Scheduler] [{self.node_id}] Routing to _handle_meeting_rescheduling")
            return self._handle_meeting_rescheduling(message)
        else:
            # Log and respond if the action is unknown or not supported
            log_warning(f"[{self.node_id}] Unknown calendar action '{action}' in intent: {intent}") 
            return f"Sorry, I don't know how to '{action}'."
    
