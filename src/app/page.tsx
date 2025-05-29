'use client'; // Required for hooks like useState, useEffect in Next.js App Router

// React and core hooks for state management, side effects, and DOM references
import { useEffect, useState, useRef } from 'react';
// Socket.IO client for real-time communication with backend
import { io, Socket } from 'socket.io-client';
// Lucide React icons for UI elements
import { Mic, Info, ChevronDown, PlusCircle } from 'lucide-react';
// Custom components for agent candidate selection and modals
import AgentCandidateSelector from './components/AgentCandidateSelector';
import type { CandidateAgent } from './components/AgentCandidateCard';
import NewProjectModal from './components/NewProjectModal';
import ProjectDetailModal from './components/ProjectDetailModal';
import TaskDetailModal from './components/TaskDetailModal';
import MeetingDetailModal from './components/MeetingDetailModal';
// NextAuth for authentication with Google OAuth
import { useSession, signIn, signOut } from 'next-auth/react'

/**
 * Represents an AI agent that can be selected and communicated with
 * These agents are fetched from the backend /nodes endpoint
 */
interface Agent {
  id: string;        // Unique identifier for the agent
  name: string;      // Display name of the agent
  // Additional agent properties may be available from the /nodes endpoint in the future
}

/**
 * Represents a single step in a project plan with assigned participants
 */
interface PlanStep {
  name: string;                         // Name/title of the plan step
  description: string;                  // Detailed description of what needs to be done
  responsible_participants: string[];   // Array of participant names responsible for this step
}

/**
 * Represents a chat message in the conversation between user and agent
 * Supports different message types including special candidate selection messages
 */
export interface ChatMessage {
  id: string;                                   // Unique identifier for the message
  type: 'user' | 'agent' | 'system';            // Who sent the message
  text: string;                                 // The message content (may contain HTML for agent messages)
  timestamp?: string;                           // Optional timestamp for display (formatted string)
  messageSubType?: 'candidate_selection';       // Special subtype for candidate selection messages
  candidates?: CandidateAgent[];                // Optional array of candidate agents for selection (when messageSubType is 'candidate_selection')
  projectId?: string;                           // Optional associated project ID for candidate selection
  isLoadingPlaceholder?: boolean;               // (Optional) Whether this is a temporary loading message
  promptIssued?: boolean;                       // (Optional) Tracks if next step prompt was issued to prevent duplicates
}

/**
 * Represents a meeting/calendar event with attendee and timing information
 * Data is fetched from Google Calendar via the backend API
 */
export interface Meeting {
  id: string;                                                 // Unique meeting identifier from calendar system
  title: string;                                              // Meeting title/subject
  dateTime: string;                                           // Human-readable formatted start date/time for display
  startTimeISO?: string;                                      // (Optional) Raw ISO datetime or date string from calendar
  endTimeISO?: string;                                        // (Optional) Raw ISO datetime or date string for meeting end
  attendees?: { email: string; displayName?: string }[];      // (Optional) List of meeting attendees with emails and display names
  organizerEmail?: string;                                    // (Optional) Email of the meeting organizer
  description?: string;                                       // (Optional) Meeting description from calendar event
  // Future extensions could include:
  // location?: string; // Physical or virtual meeting location
  // source?: string;   // Which calendar system this came from
}

/**
 * Represents a project with participants, objectives, and planning steps
 * Projects can be created by users and managed through agent interactions
 */
interface Project {
  id: string;                    // Unique project identifier
  name: string;                  // Project name/title
  owner?: string;                // (Optional) Project owner (usually the creator)
  participants?: string[];       // (Optional) Array of participant names involved in the project
  objective?: string;            // (Optional) High-level project objective or goal
  description?: string;          // (Optional) Detailed project description
  plan_steps?: PlanStep[];       // (Optional) Array of planned steps for project execution
  status?: string;               // (Optional) Current project status (e.g., "active", "completed", "planning")
  created_at?: string;           // (Optional) ISO timestamp of when project was created
}

/**
 * Represents a task that can be assigned to team members with priority and deadlines
 * Tasks are typically associated with projects but can exist independently
 */
interface Task {
  id: string;                                          // Unique task identifier
  title: string;                                       // Task title/name
  description?: string;                                // (Optional) detailed description of the task
  assigned_to?: string;                                // (Optional) Name or identifier of the person assigned to this task
  due_date?: string;                                   // (Optional) Due date (ISO string or formatted date)
  priority?: 'high' | 'medium' | 'low' | string;       // (Optional) Task priority level
  project_id?: string;                                 // (Optional) associated project identifier
}

/**
 * Interface for project data as stored/returned by the API
 * Used for handling different API response formats where project data may not include the ID
 */
interface ApiProjectData {
  name: string;                  // Project name
  owner?: string;                // (Optional) Project owner
  participants?: string[];       // (Optional) Project participants
  objective?: string;            // (Optional) Project objective
  description?: string;          // (Optional) Project description
  plan_steps?: PlanStep[];       // (Optional) Project planning steps
  status?: string;               // (Optional) Project status
  created_at?: string;           // (Optional) Creation timestamp
}

/**
 * Interface for project data from API responses that may have the ID at the top level
 * This handles variations in how the backend returns project data
 */
interface ApiProject {
  id?: string;                   // (Optional) Project ID might be at the top level or within nested data
  name: string;                  // Project name
  owner?: string;                // (Optional) Project owner
  participants?: string[];       // (Optional) Project participants
  objective?: string;            // (Optional) Project objective
  description?: string;          // (Optional) Project description
  plan_steps?: PlanStep[];       // (Optional) Project planning steps
  status?: string;               // (Optional) Project status
  created_at?: string;           // (Optional) Creation timestamp
}

/**
 * Interface for the raw meeting event data structure as received from the backend
 * This represents the unprocessed calendar event data before transformation to the Meeting interface
 */
interface RawBackendMeetingEvent {
  id: string;                                                           // Unique event ID from calendar system
  summary?: string;                                                     // (Optional) Event summary (alternative to title)
  title?: string;                                                       // (Optional) Event title (alternative to summary)
  description?: string;                                                 // (Optional) Event description/notes
  start: { dateTime?: string; date?: string; timeZone?: string };       // (Optional) Event start time with timezone info
  end: { dateTime?: string; date?: string; timeZone?: string };         // (Optional) Event end time with timezone info
  attendees?: { email: string; displayName?: string }[];                // (Optional) List of event attendees
  organizer?: { email: string; displayName?: string };                  // (Optional) Event organizer information
  source?: string;                                                      // (Optional) Source calendar system identifier
}

/**
 * Backend URL configuration with environment-based fallbacks
 * Uses environment variable NEXT_PUBLIC_BACKEND_URL if available,
 * otherwise defaults to production URL in production mode or localhost in development
 */
const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 
  (process.env.NODE_ENV === 'production' 
    ? 'https://jarvis-ai-production.up.railway.app' 
    : 'http://localhost:5001')

/**
 * Main Home component that provides the Jarvis-AI interface
 * 
 * This component manages:
 * - User authentication via NextAuth
 * - Real-time communication with AI agents via Socket.IO
 * - Agent selection and context switching
 * - Chat interface for agent communication
 * - Sidebar displays for meetings, projects, and tasks
 * - Modal management for creating and viewing projects, tasks, and meetings
 * - Candidate selection for project participants
 * 
 * The component implements a complete workspace interface where users can:
 * 1. Authenticate with Google OAuth
 * 2. Select from available AI agents
 * 3. Chat with agents using natural language
 * 4. Create and manage projects
 * 5. View meetings from their calendar
 * 6. Manage tasks and project planning
 * 
 * @returns JSX.Element The complete home page interface
 */
export default function Home() {
  // Authentication state from NextAuth
  const { data: session, status } = useSession()
  
  // Real-time communication state
  const [socket, setSocket] = useState<Socket | null>(null);                    // Socket.IO connection instance
  
  // Agent management state
  const [agents, setAgents] = useState<Agent[]>([]);                             // Available AI agents from backend
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);        // Currently selected agent for communication
  const [currentAgentRoom, setCurrentAgentRoom] = useState<string | null>(null); // Current Socket.IO room for agent communication
  
  // Chat interface state
  const [inputText, setInputText] = useState('');                              // Current user input text
  const [messages, setMessages] = useState<ChatMessage[]>([]);                 // Chat message history
  const messagesEndRef = useRef<HTMLDivElement | null>(null);                  // Reference for auto-scrolling to latest message
  
  // Loading indicator management
  const loadingMessageIntervalRef = useRef<NodeJS.Timeout | null>(null);       // Interval for cycling loading messages
  const [recentlyPromptedProjectIds, setRecentlyPromptedProjectIds] = useState<Set<string>>(new Set()); // Prevents duplicate next-step prompts
  const promptedCandidateMessageIdsRef = useRef<Set<string>>(new Set());       // Tracks candidate messages that already issued next-step prompts
  
  /**
   * Array of loading messages that cycle during project planning operations
   * These provide user feedback during potentially long-running agent operations
   */
  const projectPlanningMessages = [
    "Looking through past projects...",
    "Searching for suitable approaches...",
    "Analyzing project requirements...",
    "Generating project plan...",
    "Finalizing project structure..."
  ];

  // Data management state for sidebar content
  const [meetings, setMeetings] = useState<Meeting[]>([]);      // User's meetings from calendar integration
  const [projects, setProjects] = useState<Project[]>([]);      // User's projects managed by agents
  const [tasks, setTasks] = useState<Task[]>([]);               // User's tasks and assignments
  
  // Modal state management
  const [isNewProjectModalOpen, setIsNewProjectModalOpen] = useState(false);              // Controls new project creation modal
  const [isProjectDetailModalOpen, setIsProjectDetailModalOpen] = useState(false);        // Controls project detail viewing modal
  const [selectedProjectForDetail, setSelectedProjectForDetail] = useState<Project | null>(null); // Currently viewed project in detail modal
  const [isTaskDetailModalOpen, setIsTaskDetailModalOpen] = useState(false);              // Controls task detail viewing modal
  const [selectedTaskForDetail, setSelectedTaskForDetail] = useState<Task | null>(null);  // Currently viewed task in detail modal
  const [isMeetingDetailModalOpen, setIsMeetingDetailModalOpen] = useState(false);        // Controls meeting detail viewing modal
  const [selectedMeetingForDetail, setSelectedMeetingForDetail] = useState<Meeting | null>(null); // Currently viewed meeting in detail modal

  // Ref to maintain selectedAgent state across socket event handlers
  // This prevents stale closure issues in socket event callbacks
  const selectedAgentRef = useRef<Agent | null>(null);

  /**
   * Auto-scroll effect: Scrolls chat to bottom when new messages are added
   * This ensures users always see the latest message without manual scrolling
   */
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  /**
   * Agent reference sync effect: Keeps the selectedAgentRef in sync with selectedAgent state
   * This ref is used in socket event handlers to avoid stale closure issues
   */
  useEffect(() => {
    selectedAgentRef.current = selectedAgent;
  }, [selectedAgent]);

  /**
   * User initialization effect: Initializes user-specific agents when user first logs in
   * This creates the necessary backend resources for the authenticated user
   */
  useEffect(() => {
    if (session?.user?.email) {
      initializeUserAgents()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session])

  /**
   * Socket.IO initialization and event handling effect
   * 
   * This effect:
   * 1. Creates a new Socket.IO connection when user is authenticated
   * 2. Sets up event handlers for connection status and real-time updates
   * 3. Handles automatic data fetching when backend sends update notifications
   * 4. Cleans up the connection when component unmounts or session changes
   * 
   * The socket connection enables real-time updates for meetings, projects, and tasks
   * without requiring manual refresh or polling
   */
  useEffect(() => {
    // Only initialize socket for authenticated users
    if (!session) return;

    // Create new Socket.IO connection to backend
    const newSocket = io(BACKEND_URL);
    setSocket(newSocket);

    // Connection status event handlers
    newSocket.on('connect', () => {
      console.log('Socket.IO connected:', newSocket.id);
    });
    
    newSocket.on('disconnect', () => {
      console.log('Socket.IO disconnected');
    });
    
    // Handle connection errors and notify user
    newSocket.on('connect_error', (err) => {
      console.error('Socket.IO connection error:', err);
      // Add a system message to inform user about connection issues
      setMessages(prev => [...prev, { 
        id: Date.now().toString(), 
        type: 'system', 
        text: 'Failed to connect to the notification server. Real-time updates might be affected.' 
      }]);
    });

    /**
     * Real-time meetings update handler
     * Triggered when backend notifies of meeting changes (new/updated/deleted meetings)
     * Automatically refetches meetings for the currently selected agent
     */
    newSocket.on('update_meetings', () => {
      console.log('Received update_meetings event from backend.');
      setSocket(prevSocket => {
        // Only fetch if socket is still active and connected
        if (prevSocket && prevSocket.active) {
            const currentSelectedAgentId = selectedAgentRef.current?.id;
            if (currentSelectedAgentId) {
                console.log(`Socket event 'update_meetings': Fetching for agent ${currentSelectedAgentId}`);
                fetchMeetings(currentSelectedAgentId);
            } else {
                console.log("Socket event 'update_meetings': No agent selected, not fetching.");
            }
        }
        return prevSocket; // Return socket unchanged (using setSocket for side effect only)
      });
    });
    
    /**
     * Real-time projects update handler
     * Triggered when backend notifies of project changes (new/updated/deleted projects)
     * Automatically refetches projects for the currently selected agent
     */
    newSocket.on('update_projects', () => {
        console.log('Received update_projects event from backend.');
        setSocket(prevSocket => {
            // Only fetch if socket is still active and connected
            if (prevSocket && prevSocket.active) {
                const currentSelectedAgentId = selectedAgentRef.current?.id;
                if (currentSelectedAgentId) {
                    console.log(`Socket event 'update_projects': Fetching for agent ${currentSelectedAgentId}`);
                    fetchProjects(currentSelectedAgentId);
                } else {
                    console.log("Socket event 'update_projects': No agent selected, not fetching.");
                }
            }
            return prevSocket; // Return socket unchanged (using setSocket for side effect only)
        });
    });

    /**
     * Real-time tasks update handler
     * Triggered when backend notifies of task changes (new/updated/deleted tasks)
     * Automatically refetches tasks for the currently selected agent
     */
    newSocket.on('update_tasks', () => {
        console.log('Received update_tasks event from backend.');
        setSocket(prevSocket => {
            // Only fetch if socket is still active and connected
            if (prevSocket && prevSocket.active) {
                const currentSelectedAgentId = selectedAgentRef.current?.id;
                if (currentSelectedAgentId) {
                    console.log(`Socket event 'update_tasks': Fetching for agent ${currentSelectedAgentId}`);
                    fetchTasks(currentSelectedAgentId);
                } else {
                    console.log("Socket event 'update_tasks': No agent selected, not fetching.");
                }
            }
            return prevSocket; // Return socket unchanged (using setSocket for side effect only)
        });
    });

    return () => {
      newSocket.disconnect();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]); // Re-run when session changes

  /**
   * Agent fetching effect: Loads available agents from backend when user is authenticated
   * This populates the agent selector dropdown with user-specific agents
   */
  useEffect(() => {
    // Only fetch agents for authenticated users
    if (!session) return;

    /**
     * Fetches the list of available AI agents from the backend
     * Agents are user-specific and created during the initialization process
     */
    const fetchAgents = async () => {
      try {
        const response = await fetchWithAuth(`${BACKEND_URL}/nodes`);
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data: Agent[] = await response.json();
        setAgents(data);
        // Note: First agent auto-selection is handled in a separate effect below
      } catch (error) {
        console.error('Error fetching agents:', error);
        // Show user-friendly error message in chat
        setMessages(prev => [...prev, { 
          id: Date.now().toString(), 
          type: 'system', 
          text: 'Error fetching agent list.' 
        }]);
      }
    };
    fetchAgents();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]); // Re-run when session changes

  /**
   * Auto-select first agent effect: Automatically selects the first available agent
   * This provides a better user experience by having an agent ready for interaction
   */
  // TODO: Make it select the agent that LOGGED IN!
  useEffect(() => {
    if (agents.length > 0 && !selectedAgent) {
      handleAgentSelect(agents[0], true); // true indicates this is an initial selection
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agents]); // Only re-run if agents array itself changes

  /**
   * Authentication guard: Show loading spinner while authentication status is being determined
   * This prevents content flash before authentication is confirmed
   */
  if (status === 'loading') {
    return <div className="flex items-center justify-center h-screen">
      <div className="text-lg">Loading...</div>
    </div>
  }

  /**
   * Authentication guard: Show sign-in interface for unauthenticated users
   * Provides Google OAuth sign-in button with clear branding and instructions
   */
  if (!session) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-gray-50">
        <div className="text-center">
          <h1 className="text-3xl font-bold text-gray-900 mb-4">Jarvis-AI</h1>
          <p className="text-gray-600 mb-8">Sign in to access your AI agents</p>
          <button
            onClick={() => signIn('google')}
            className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Sign in with Google
          </button>
        </div>
      </div>
    )
  }

  /**
   * Initializes user-specific AI agents on the backend
   * 
   * This function is called when a user first logs in to set up their personalized
   * AI agents on the backend. It creates the necessary agent instances and configurations
   * specific to the authenticated user.
   * 
   * Flow:
   * 1. Calls backend /initialize_agents endpoint to create user agents
   * 2. Fetches the updated list of available agents
   * 3. Auto-selects the first agent if available
   * 4. Handles errors gracefully with user-friendly messages
   * 
   * @throws Will display error message in chat if initialization fails
   */
  const initializeUserAgents = async () => {
    try {
      console.log('Initializing user agents...')
      
      // Call backend to create user-specific agent instances
      const response = await fetchWithAuth(`${BACKEND_URL}/initialize_agents`, {
        method: 'POST'
      })
      
      // Handle backend errors
      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.error || 'Failed to initialize agents')
      }
      
      const data = await response.json()
      console.log('Agents initialized:', data)
      
      // Refresh the agent list to include newly created agents
      const agentsResponse = await fetchWithAuth(`${BACKEND_URL}/nodes`)
      if (agentsResponse.ok) {
        const agents: Agent[] = await agentsResponse.json()
        setAgents(agents)
        // Auto-select first agent for immediate usability
        if (agents.length > 0 && !selectedAgent) {
          handleAgentSelect(agents[0], true)
        }
      }
    } catch (error) {
      console.error('Failed to initialize user agents:', error)
      // Display user-friendly error message in the chat interface
      setMessages(prev => [...prev, { 
        id: Date.now().toString(), 
        type: 'system', 
        text: 'Error initializing your agents. Please refresh the page.' 
      }])
    }
  }

  /**
   * Authenticated fetch wrapper that adds user authentication headers to all API requests
   * 
   * This utility function wraps the standard fetch API to automatically include
   * authentication headers for backend communication. It creates a simple JWT-like
   * token containing user information for backend identification.
   * 
   * @param url - The URL to fetch from (relative or absolute)
   * @param options - Standard fetch options (method, body, headers, etc.)
   * @returns Promise<Response> - The fetch response with authentication headers added
   * 
   * @example
   * const response = await fetchWithAuth('/api/agents', { method: 'GET' });
   * const data = await response.json();
   */
  const fetchWithAuth = (url: string, options: RequestInit = {}) => {
    // Create a base64-encoded token containing user information
    // This serves as a simple authentication mechanism for the backend
    const userToken = session?.user?.email ? btoa(JSON.stringify({
      sub: session.user.email,      // Subject (user identifier)
      email: session.user.email,    // User's email address
      name: session.user.name       // User's display name
    })) : ''
    
    // Return fetch request with authentication and content-type headers
    return fetch(url, {
      ...options,
      headers: {
        ...options.headers,                     // Preserve any existing headers
        'Authorization': `Bearer ${userToken}`, // Add authentication token
        'Content-Type': 'application/json'      // Set JSON content type
      }
    })
  }

  /**
   * Fetches and formats meetings for a specific agent from the backend
   * 
   * This function retrieves calendar events/meetings associated with the selected agent
   * and transforms the raw backend data into a user-friendly format for display.
   * 
   * Data transformation includes:
   * - Converting raw datetime strings to formatted display strings
   * - Extracting attendee information and generating display names
   * - Handling different date formats (dateTime vs date only)
   * - Providing fallbacks for missing titles and dates
   * 
   * @param agentId - The unique identifier of the agent whose meetings to fetch
   * @throws Clears meetings list and logs error if fetch fails
   */
  const fetchMeetings = async (agentId: string) => {
    try {
      // Fetch raw meeting data from backend API
      const response = await fetchWithAuth(`${BACKEND_URL}/meetings?agent_id=${agentId}`);
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const data: RawBackendMeetingEvent[] = await response.json(); 
      
      // Transform raw backend meeting data into user-friendly format
      const formattedMeetings: Meeting[] = data.map((meeting_evt) => {
        // Parse start date, handling both dateTime and date-only formats
        const startDate = meeting_evt.start?.dateTime 
          ? new Date(meeting_evt.start.dateTime) 
          : (meeting_evt.start?.date ? new Date(meeting_evt.start.date) : null);

        return {
          id: meeting_evt.id,
          // Use title or summary, with fallback for untitled meetings
          title: meeting_evt.title || meeting_evt.summary || 'Untitled Meeting',
          // Format date/time for display (full datetime vs date-only)
          dateTime: startDate 
            ? (meeting_evt.start?.dateTime ? startDate.toLocaleString() : startDate.toLocaleDateString()) 
            : 'Date TBD',
          // Preserve original ISO strings for potential future use
          startTimeISO: meeting_evt.start?.dateTime || meeting_evt.start?.date,
          endTimeISO: meeting_evt.end?.dateTime || meeting_evt.end?.date,
          // Transform attendees with generated display names from email
          attendees: meeting_evt.attendees?.map((a: { email: string }) => ({ 
            email: a.email, 
            displayName: a.email?.split('@')[0] // Use email prefix as display name
          })) || [],
          organizerEmail: meeting_evt.organizer?.email,
          description: meeting_evt.description, // Calendar event description
        };
      });
      
      // Update state with formatted meetings
      setMeetings(formattedMeetings);
    } catch (error) {
      console.error('Error fetching meetings:', error);
      setMeetings([]); // Clear meetings list on error to prevent stale data
    }
  };

  /**
   * Fetches and normalizes projects for a specific agent from the backend
   * 
   * This function handles different response formats from the backend API:
   * 1. Array format: Direct array of project objects
   * 2. Object format: Object with project IDs as keys and project data as values
   * 
   * The function normalizes both formats into a consistent Project[] array and
   * provides fallback values for missing fields to ensure UI stability.
   * 
   * @param agentId - The unique identifier of the agent whose projects to fetch
   * @throws Clears projects list and logs error if fetch fails
   */
  const fetchProjects = async (agentId: string) => {
    try {
      // Fetch raw project data from backend API
      const response = await fetchWithAuth(`${BACKEND_URL}/projects?agent_id=${agentId}`);
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      
      // Backend may return either array or object format
      const data: Project[] | { [projectId: string]: Omit<Project, 'id'> } = await response.json();
      let projectArray: Project[] = [];
      
      // Handle array format response
      if (Array.isArray(data)) {
        projectArray = data.map((p: ApiProject) => ({ 
            id: p.id || p.name,                                    // Use name as fallback ID
            name: p.name,
            owner: p.owner,
            participants: p.participants || [],                    // Default to empty array
            objective: p.objective,
            description: p.description || p.objective,             // Use objective as fallback
            plan_steps: p.plan_steps || [],                        // Default to empty array
            status: p.status,
            created_at: p.created_at
        }));
      } 
      // Handle object format response (projectId -> projectData)
      else if (typeof data === 'object' && data !== null) {
        projectArray = Object.keys(data).map(projectId => {
          const projectData = (data as { [key: string]: ApiProjectData })[projectId];
          return {
            id: projectId,                                         // Use key as project ID
            name: projectData.name || projectId,                   // Use ID as fallback name
            owner: projectData.owner,
            participants: projectData.participants || [],          // Default to empty array
            objective: projectData.objective,
            description: projectData.description || projectData.objective, // Use objective as fallback
            plan_steps: projectData.plan_steps || [],              // Default to empty array
            status: projectData.status,
            created_at: projectData.created_at,
          };
        });
      }
      
      // Update state with normalized project array
      setProjects(projectArray);
    } catch (error) {
      console.error('Error fetching projects:', error);
      setProjects([]); // Clear projects list on error to prevent stale data
    }
  };

  /**
   * Fetches tasks for a specific agent from the backend
   * 
   * This function retrieves all tasks associated with the selected agent.
   * Tasks can be standalone or associated with specific projects.
   * The backend is expected to return tasks in a consistent Task[] format.
   * 
   * Future enhancements could include:
   * - Date formatting for due dates
   * - Task status filtering
   * - Priority-based sorting
   * 
   * @param agentId - The unique identifier of the agent whose tasks to fetch
   * @throws Clears tasks list and logs error if fetch fails
   */
  const fetchTasks = async (agentId: string) => {
    try {
      // Fetch task data from backend API
      const response = await fetchWithAuth(`${BACKEND_URL}/tasks?agent_id=${agentId}`);
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      
      // Backend returns tasks in Task[] format directly
      const data: Task[] = await response.json();
      
      // Set tasks directly (no transformation needed currently)
      // Future: Could format due_date here if needed
      // e.g., new Date(task.due_date).toLocaleDateString()
      setTasks(data.map(task => ({
        ...task,
        // Task data is used as-is, formatting handled in TaskDetailModal
      })));
    } catch (error) {
      console.error('Error fetching tasks:', error);
      setTasks([]); // Clear tasks list on error to prevent stale data
    }
  };

  /**
   * Handles agent selection and context switching
   * 
   * This function manages the complete process of switching between AI agents:
   * 1. Handles deselection (null agent) by cleaning up state and socket rooms
   * 2. Prevents unnecessary re-selection of the same agent
   * 3. Updates UI context and fetches agent-specific data
   * 4. Manages Socket.IO room membership for real-time updates
   * 5. Provides appropriate system messages for context changes
   * 
   * @param agent - The agent to select (null to deselect)
   * @param isInitialSelect - Whether this is an automatic initial selection (affects messaging)
   */
  const handleAgentSelect = (agent: Agent | null, isInitialSelect: boolean = false) => {
    // Handle agent deselection
    if (!agent) {
        setSelectedAgent(null);
        // Clear messages unless this is initial select or error messages exist
        if (!isInitialSelect || (messages.length > 0 && !messages.some(m => m.type === 'system' && m.text.includes('Error')))) {
            setMessages([]);
        }
        // Clear all agent-specific data
        setMeetings([]);
        setProjects([]);
        setTasks([]);
        // Leave current socket room
        if (socket && currentAgentRoom) {
            socket.emit('leave_room', { room: currentAgentRoom });
            console.log(`Emitted leave_room for ${currentAgentRoom}`);
            setCurrentAgentRoom(null);
        }
        return;
    }
    
    // Prevent unnecessary re-selection of the same agent
    if (selectedAgent?.id === agent.id && !isInitialSelect) return;

    console.log(`Agent selected: ${agent.name}. Previous room: ${currentAgentRoom}`);
    setSelectedAgent(agent);
    
    // Add appropriate system message for context change
    if (!isInitialSelect) {
        // User-initiated agent switch
        setMessages([{ id: Date.now().toString(), type: 'system', text: `Switched context to ${agent.name}` }]);
    } else if (messages.length === 0) { 
        // Initial automatic selection, only if no existing messages (like error messages)
        setMessages([{ id: Date.now().toString(), type: 'system', text: `Context set to ${agent.name}` }]);
    }

    // Fetch all agent-specific data
    fetchMeetings(agent.id);
    fetchProjects(agent.id);
    fetchTasks(agent.id);

    // Manage Socket.IO room membership for real-time updates
    if (socket) {
      // Leave previous room if different from new agent
      if (currentAgentRoom && currentAgentRoom !== agent.id) {
        socket.emit('leave_room', { room: currentAgentRoom });
        console.log(`Emitted leave_room for ${currentAgentRoom}`);
      }
      // Join new agent's room if not already in it
      if (currentAgentRoom !== agent.id) {
        socket.emit('join_room', { room: agent.id });
        console.log(`Emitted join_room for ${agent.id}`);
        setCurrentAgentRoom(agent.id);
      }
    }
    
    // Clear input text for user-initiated switches
    if (!isInitialSelect) {
        setInputText('');
    }
  };

  /**
   * Displays a loading indicator message with optional cycling text for project planning
   * 
   * This function creates a temporary loading message that provides user feedback
   * during potentially long-running agent operations. For project planning operations,
   * it cycles through informative messages to show progress.
   * 
   * @param isProjectPlanning - Whether this is a project planning operation (enables message cycling)
   * @param initialMessageOverride - Optional custom initial message (for project planning)
   * @returns string - The unique ID of the loading message for later removal
   * 
   * @example
   * const loadingId = displayLoadingIndicator(true, "Searching for participants...");
   * // Later: removeLoadingIndicator(loadingId);
   */
  const displayLoadingIndicator = (isProjectPlanning: boolean, initialMessageOverride?: string) => {
    // Create unique ID for this loading message
    const newLoadingId = `loading-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
    
    // Determine initial loading text
    const text = isProjectPlanning
        ? (initialMessageOverride || projectPlanningMessages[0]) 
        : "Thinking...";

    // Create loading placeholder message
    const placeholderMessage: ChatMessage = {
      id: newLoadingId,
      type: 'agent',
      text: text,
      isLoadingPlaceholder: true,
      timestamp: new Date().toLocaleTimeString()
    };

    // Add loading message to chat
    setMessages(prev => [...prev, placeholderMessage]);

    // Set up message cycling for project planning operations
    if (isProjectPlanning) {
      // Clear any existing interval
      if (loadingMessageIntervalRef.current) {
        clearInterval(loadingMessageIntervalRef.current);
      }
      
      // Determine starting index for message cycling
      let index = 0;
      if (initialMessageOverride) { 
          const initialIdx = projectPlanningMessages.indexOf(initialMessageOverride);
          if (initialIdx !== -1) index = (initialIdx + 1) % projectPlanningMessages.length;
      } else {
          index = 1; // Start from second message
      }
      
      // Set up interval to cycle through loading messages
      loadingMessageIntervalRef.current = setInterval(() => {
        const nextMessageText = projectPlanningMessages[index];
        // Update the specific loading message text
        setMessages(prevMsgs => 
          prevMsgs.map(m => 
            m.id === newLoadingId ? { ...m, text: nextMessageText } : m
          )
        );
        index = (index + 1) % projectPlanningMessages.length;
      }, 3000); // Cycle every 3 seconds for good user experience
    }
    
    return newLoadingId;
  };

  /**
   * Removes a loading indicator message and cleans up any associated intervals
   * 
   * This function removes the temporary loading message from the chat and
   * stops any message cycling that may be in progress. It should be called
   * when the operation that triggered the loading indicator completes.
   * 
   * @param idToRemove - The unique ID of the loading message to remove (null safe)
   */
  const removeLoadingIndicator = (idToRemove: string | null) => {
    // Remove the specific loading message if ID provided
    if (idToRemove) {
      setMessages(prevMsgs => prevMsgs.filter(m => m.id !== idToRemove));
    }
    
    // Clean up any active message cycling interval
    if (loadingMessageIntervalRef.current) {
      clearInterval(loadingMessageIntervalRef.current);
      loadingMessageIntervalRef.current = null;
    }
  };

  /**
   * Core function for sending messages/commands to the selected AI agent
   * 
   * This is the central communication function that handles:
   * 1. Sending user messages or system commands to the backend agent
   * 2. Processing different types of agent responses (text, candidate selection, errors)
   * 3. Parsing special candidate selection responses with JSON data
   * 4. Adding appropriate messages to the chat interface
   * 5. Error handling with user-friendly error messages
   * 
   * The function handles special response formats like candidate selection where
   * the agent returns JSON data for interactive candidate selection UI.
   * 
   * @param messageText - The message or command to send to the agent
   * @throws Displays error messages in chat if communication fails
   */
  const _postMessageToAgent = async (messageText: string) => {
    if (!selectedAgent) {
      setMessages(prev => [...prev, { id: Date.now().toString(), type: 'system', text: 'Error: No agent selected to send the command.' }]);
      return;
    }
    try {
      const response = await fetchWithAuth(`${BACKEND_URL}/send_message`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node_id: selectedAgent.id, message: messageText, sender_id: selectedAgent.id }),
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: 'Unknown server error' }));
        throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
      }
      const data = await response.json();

      if (data.error) {
        setMessages(prev => [...prev, { id: Date.now().toString() + '-error', type: 'system', text: `Agent error: ${data.error}`, timestamp: new Date().toLocaleTimeString() }]);
      } else {
        const agentResponseText = data.response || "(Agent processed the command)";
        // Check for candidate selection response
        const candidatePrefix = "Here are the best-suited candidates for your project '";
        if (agentResponseText.startsWith(candidatePrefix)) {
          const endOfPrefix = agentResponseText.indexOf("':") + 2; // End of "project 'PROJECT_NAME':"
          const jsonString = agentResponseText.substring(endOfPrefix).trim();
          const projectIdMatch = agentResponseText.match(/project '([^']*)'/);
          const currentProjectId = projectIdMatch ? projectIdMatch[1] : undefined;
          
          // Extract the introductory text before the JSON
          const introText = agentResponseText.substring(0, endOfPrefix);

          try {
            const candidatesData: CandidateAgent[] = JSON.parse(jsonString);
            setMessages(prev => [...prev, {
              id: Date.now().toString() + '-agent-candidates',
              type: 'agent', 
              text: introText, // Show the introductory part of the message
              messageSubType: 'candidate_selection', 
              candidates: candidatesData, 
              projectId: currentProjectId,
              timestamp: new Date().toLocaleTimeString(),
              promptIssued: false // Initialize promptIssued
            }]);
          } catch (parseError) {
            console.error("Failed to parse candidate JSON from command response:", parseError, "JSON string:", jsonString);
            // Fallback to showing the full original message if parsing fails
            setMessages(prev => [...prev, { id: Date.now().toString() + '-agent-parse-error', type: 'agent', text: agentResponseText, timestamp: new Date().toLocaleTimeString() }]);
          }
        } else {
          setMessages(prev => [...prev, { id: Date.now().toString() + '-agent', type: 'agent', text: agentResponseText, timestamp: new Date().toLocaleTimeString() }]);
        }
      }
    } catch (error: unknown) {
      let errorMessage = 'Error sending command. Please check console.';
      if (error instanceof Error) errorMessage = error.message;
      setMessages(prev => [...prev, { id: Date.now().toString() + '-error', type: 'system', text: errorMessage, timestamp: new Date().toLocaleTimeString() }]);
    }
  };

  const handleSendMessage = async () => {
    if (!selectedAgent || !inputText.trim()) return;
    const userMessage: ChatMessage = {
      id: Date.now().toString() + '-user', type: 'user', text: inputText.trim(), timestamp: new Date().toLocaleTimeString()
    };
    setMessages(prev => [...prev, userMessage]);
    const currentMessageText = inputText.trim();
    setInputText('');

    let tempLoadingId: string | null = null;
    try {
      // Check if it's a finalize project command to show specific loading messages
      const isFinalizingProject = currentMessageText.toLowerCase().startsWith("finalize project ");
      tempLoadingId = displayLoadingIndicator(isFinalizingProject, 
        isFinalizingProject ? projectPlanningMessages[0] : undefined
      );
      await _postMessageToAgent(currentMessageText);
    } catch (error) {
      // Error handling is already inside _postMessageToAgent or should be added there
      // for specific message posting errors.
      console.error("Error in handleSendMessage flow:", error);
    } finally {
      if (tempLoadingId) {
        removeLoadingIndicator(tempLoadingId);
      }
    }
  };
  
  const promptForNextStep = (projectId: string) => {
    const project = projects.find(p => p.id === projectId);
    const projectName = project ? project.name : projectId;
    const randomSuffix = Math.random().toString(36).substring(2, 7);
    const rawText = `All initial candidates for project '${projectName}' have been processed.\nWhat would you like to do next?\n\n1. Add another participant by typing: \`add [Participant Name] to project ${projectId}\`\n2. Finalize project planning by typing: \`finalize project ${projectId}\``;
    
    const formattedText = rawText
      .replace(/\n/g, '<br />')
      .replace(/\`([^\`]+)\`/g, '<code>$1</code>');

    const nextStepMessage: ChatMessage = {
      id: Date.now().toString() + '-' + projectId + '-next-step-' + randomSuffix, 
      type: 'agent',
      text: formattedText,
      timestamp: new Date().toLocaleTimeString()
    };
    setMessages(prev => [...prev, nextStepMessage]);
  };

  const handleCandidateAccept = async (candidateName: string, projectId: string | undefined, messageId: string) => {
    if (!selectedAgent || !projectId) {
      setMessages(prev => [...prev, { id: Date.now().toString(), type: 'system', text: 'Error: Agent or Project ID missing for this action.' }]);
      return;
    }

    // Add a user-facing message indicating the action
    const userActionMessage: ChatMessage = {
      id: Date.now().toString() + '-user-accept',
      type: 'user',
      text: `Action: Adding ${candidateName} to project ${projectId}.`,
      timestamp: new Date().toLocaleTimeString()
    };
    setMessages(prev => [...prev, userActionMessage]);

    // Send command to backend to add participant
    await _postMessageToAgent(`add ${candidateName} to project ${projectId}`);

    // Update the specific message in the chat to remove the accepted candidate
    setMessages(prevMessages => {
      const newMessages = prevMessages.map(msg => {
        if (msg.id === messageId && msg.messageSubType === 'candidate_selection' && msg.candidates) {
          const updatedCandidates = msg.candidates.filter(c => c.name !== candidateName);
          if (updatedCandidates.length === 0) {
            if (!promptedCandidateMessageIdsRef.current.has(messageId)) {
              promptedCandidateMessageIdsRef.current.add(messageId);

              if (projectId && !recentlyPromptedProjectIds.has(projectId)) {
                setRecentlyPromptedProjectIds(prev => new Set(prev).add(projectId));
                promptForNextStep(projectId); 
                setTimeout(() => {
                  setRecentlyPromptedProjectIds(prev => {
                    const newSet = new Set(prev);
                    newSet.delete(projectId);
                    return newSet;
                  });
                }, 2000); // 2-second cooldown
              }
              return { ...msg, candidates: [], promptIssued: true }; 
            } else {
              // Prompt already handled for this messageId by ref, just clear candidates
              return { ...msg, candidates: [] };
            }
          }
          return { ...msg, candidates: updatedCandidates };
        }
        return msg;
      });
      return newMessages;
    });
  };

  const handleCandidateReject = async (candidateName: string, projectId: string | undefined, messageId: string) => {
    if (!selectedAgent || !projectId) {
      setMessages(prev => [...prev, { id: Date.now().toString(), type: 'system', text: 'Error: Agent or Project ID missing for this action.' }]);
      return;
    }
    // Add a user-facing message indicating the action
    const userActionMessage: ChatMessage = {
      id: Date.now().toString() + '-user-reject',
      type: 'user',
      text: `Action: Rejecting ${candidateName} for project ${projectId}.`,
      timestamp: new Date().toLocaleTimeString()
    };
    setMessages(prev => [...prev, userActionMessage]);
    
    // Send a message to the backend for logging the rejection, if necessary
    await _postMessageToAgent(`User action: Rejected candidate ${candidateName} for project '${projectId}'.`);

    // Update the specific message in the chat to remove the rejected candidate
     setMessages(prevMessages => {
      const newMessages = prevMessages.map(msg => {
        if (msg.id === messageId && msg.messageSubType === 'candidate_selection' && msg.candidates) {
          const updatedCandidates = msg.candidates.filter(c => c.name !== candidateName);
          if (updatedCandidates.length === 0) { 
            if (!promptedCandidateMessageIdsRef.current.has(messageId)) {
              promptedCandidateMessageIdsRef.current.add(messageId);

              if (projectId && !recentlyPromptedProjectIds.has(projectId)) {
                setRecentlyPromptedProjectIds(prev => new Set(prev).add(projectId));
                promptForNextStep(projectId); 
                setTimeout(() => {
                  setRecentlyPromptedProjectIds(prev => {
                    const newSet = new Set(prev);
                    newSet.delete(projectId);
                    return newSet;
                  });
                }, 2000); // 2-second cooldown
              }
              return { ...msg, candidates: [], promptIssued: true }; 
            } else {
              // Prompt already handled for this messageId by ref, just clear candidates
              return { ...msg, candidates: [] };
            }
          }
          return { ...msg, candidates: updatedCandidates };
        }
        return msg;
      });
      return newMessages;
    });
  };

  /**
   * Opens the new project creation modal
   * Allows users to create new projects with title and description
   */
  const openNewProjectModal = () => setIsNewProjectModalOpen(true);
  
  /**
   * Closes the new project creation modal
   * Resets modal state without saving any pending changes
   */
  const closeNewProjectModal = () => setIsNewProjectModalOpen(false);

  const handleSubmitNewProject = async (title: string, description: string) => {
    if (!selectedAgent) {
      setMessages(prev => [...prev, { id: Date.now().toString(), type: 'system', text: 'Error: No agent selected to create a project.' }]);
      return;
    }
    // Sanitize the title to be used as a project_id (alphanumeric and underscores)
    const sanitizedProjectId = title.replace(/\s+/g, '_').replace(/[^a-zA-Z0-9_]/g, '');
    if (!sanitizedProjectId) {
      setMessages(prev => [...prev, { id: Date.now().toString(), type: 'system', text: 'Project title is invalid after sanitization. Please use alphanumeric characters and spaces.' }]);
      return;
    }

    closeNewProjectModal();

    const projectCommand = `project ${sanitizedProjectId} = ${description}`;
    
    // Add a user message to the chat to show the command being sent
    const userMessage: ChatMessage = {
      id: Date.now().toString() + '-user-create-project',
      type: 'user',
      text: `Creating project: "${title}"...`, // User-friendly message
      timestamp: new Date().toLocaleTimeString()
    };
    setMessages(prev => [...prev, userMessage]);

    let tempLoadingId: string | null = null;
    try {
      // For new project submission, always show "Looking for possible participants..." initially.
      // The isProjectPlanning can be true if candidate selection is considered part of planning.
      tempLoadingId = displayLoadingIndicator(true, "Looking for possible participants...");
      await _postMessageToAgent(projectCommand);
    } catch (error) {
      console.error("Error in handleSubmitNewProject flow:", error);
      // Add a system message for this specific error if desired
      setMessages(prev => [...prev, { 
        id: Date.now().toString() + '-project-submit-error', 
        type: 'system', 
        text: 'An error occurred while submitting the new project. Please try again.',
        timestamp: new Date().toLocaleTimeString()
      }]);
    } finally {
      if (tempLoadingId) {
        removeLoadingIndicator(tempLoadingId);
      }
    }
    // Optionally, fetch projects again or wait for a socket update
    if (selectedAgent) {
      fetchProjects(selectedAgent.id);
    }
  };

  /**
   * Opens the project detail modal for viewing comprehensive project information
   * 
   * @param project - The project to display in the detail modal
   */
  const openProjectDetailModal = (project: Project) => {
    setSelectedProjectForDetail(project);
    setIsProjectDetailModalOpen(true);
  };

  /**
   * Closes the project detail modal and clears the selected project
   * Resets both modal state and selected project reference
   */
  const closeProjectDetailModal = () => {
    setIsProjectDetailModalOpen(false);
    setSelectedProjectForDetail(null);
  };

  /**
   * Opens the task detail modal for viewing comprehensive task information
   * 
   * @param task - The task to display in the detail modal
   */
  const openTaskDetailModal = (task: Task) => {
    setSelectedTaskForDetail(task);
    setIsTaskDetailModalOpen(true);
  };

  /**
   * Closes the task detail modal and clears the selected task
   * Resets both modal state and selected task reference
   */
  const closeTaskDetailModal = () => {
    setIsTaskDetailModalOpen(false);
    setSelectedTaskForDetail(null);
  };

  /**
   * Opens the meeting detail modal for viewing comprehensive meeting information
   * 
   * @param meeting - The meeting to display in the detail modal
   */
  const openMeetingDetailModal = (meeting: Meeting) => {
    setSelectedMeetingForDetail(meeting);
    setIsMeetingDetailModalOpen(true);
  };

  /**
   * Closes the meeting detail modal and clears the selected meeting
   * Resets both modal state and selected meeting reference
   */
  const closeMeetingDetailModal = () => {
    setIsMeetingDetailModalOpen(false);
    setSelectedMeetingForDetail(null);
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50 font-sans text-gray-800">
      {/* Main Header */}
      <header className="bg-white p-4 border-b border-gray-200 shadow-sm flex items-center justify-between sticky top-0 z-50">
        <div>
          <h1 className="text-2xl font-bold text-blue-600">Jarvis-AI</h1>
          <p className="text-xs text-gray-500">Welcome, {session.user?.name}</p>
        </div>
        <div className="flex items-center space-x-4">
          <span className="text-sm text-gray-600">Act as:</span>
          <div className="relative">
            <select
              value={selectedAgent?.id || ""}
              onChange={(e) => {
                const agentId = e.target.value;
                const agent = agents.find(a => a.id === agentId);
                handleAgentSelect(agent || null, agentId === ""); // Pass true for isInitial if it's the placeholder
              }}
              className="pl-3 pr-8 py-2 text-sm border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 appearance-none bg-white"
              disabled={agents.length === 0}
            >
              <option value="" disabled={selectedAgent !== null}>Select an Agent</option>
              {agents.map(agent => (
                <option key={agent.id} value={agent.id}>{agent.name}</option>
              ))}
            </select>
            <ChevronDown size={18} className="absolute right-2.5 top-1/2 transform -translate-y-1/2 text-gray-500 pointer-events-none" />
          </div>
          <button
            onClick={() => signOut()}
            className="text-sm text-gray-600 hover:text-gray-800"
          >
            Sign Out
          </button>
        </div>
      </header>

      {/* Main Content: Chat on Left, Sidebar on Right */}
      <div className="flex flex-1 overflow-hidden pt-4 px-4 pb-4 space-x-4">
        {/* Left: Agent Communication (Chat) */}
        <div className="flex-1 flex flex-col bg-white rounded-lg shadow-md overflow-hidden">
          <header className="p-4 border-b border-gray-200">
            <h2 className="text-lg font-semibold">Agent Communication</h2>
          </header>
          
          <div className="flex-1 p-4 sm:p-6 space-y-1 overflow-y-auto bg-gray-50">
            {messages.map((msg) => (
              <div key={msg.id} className={`flex flex-col ${msg.type === 'user' ? 'items-end' : 'items-start'} mb-2`}>
                {msg.type === 'system' ? (
                  <div className="text-center w-full my-1">
                    <span className="inline-flex items-center px-2.5 py-1 bg-slate-100 text-slate-600 rounded-full text-xs font-medium">
                      <Info size={14} className="mr-1.5 flex-shrink-0" />
                      {msg.text}
                    </span>
                  </div>
                ) : msg.messageSubType === 'candidate_selection' && msg.candidates && msg.candidates.length > 0 ? (
                  // AgentCandidateSelector now also needs messageId
                  <AgentCandidateSelector
                    messageId={msg.id} 
                    candidates={msg.candidates}
                    projectId={msg.projectId}
                    onCandidateAccept={handleCandidateAccept}
                    onCandidateReject={handleCandidateReject}
                    // Display the introductory text if it exists from the agent's message
                    introText={msg.text.startsWith("Here are the best-suited candidates for your project") ? msg.text : undefined}
                  />
                ) : msg.isLoadingPlaceholder ? (
                  <div className={`max-w-[70%] px-3.5 py-2 rounded-xl shadow-sm break-words whitespace-pre-wrap bg-gray-200 text-gray-800 rounded-bl-none`}>
                    <p className="text-sm loading-dots">{msg.text}</p>
                    {msg.timestamp && <p className={`text-xs mt-1 text-gray-500 text-right`}>{msg.timestamp}</p>}
                  </div>
                ) : (
                  <div className={`max-w-[70%] px-3.5 py-2 rounded-xl shadow-sm break-words ${msg.type === 'user' ? 'bg-blue-600 text-white rounded-br-none' : 'bg-gray-200 text-gray-800 rounded-bl-none'}`}>
                    {/* Apply dangerouslySetInnerHTML for agent messages to render HTML */}
                    {msg.type === 'agent' ? (
                      <p className="text-sm" dangerouslySetInnerHTML={{ __html: msg.text }} />
                    ) : (
                      <p className="text-sm">{msg.text}</p>
                    )}
                    {msg.timestamp && <p className={`text-xs mt-1 ${msg.type === 'user' ? 'text-blue-200' : 'text-gray-500'} text-right`}>{msg.timestamp}</p>}
                  </div>
                )}
              </div>
            ))}
            <div ref={messagesEndRef} />
            {!selectedAgent && messages.length === 0 && <p className="text-center text-gray-400 pt-10">Select an agent to begin communication.</p>}
             {selectedAgent && messages.filter(m => m.type !== 'system' && m.messageSubType !== 'candidate_selection').length === 0 && messages.some(m => m.type === 'system') &&
              <p className="text-center text-gray-400 pt-10">No messages yet with {selectedAgent.name}.</p>
            }
          </div>

          <div className="bg-white p-3 sm:p-4 border-t border-gray-200">
            <div className="flex items-center space-x-2 sm:space-x-3">
              <button title="Record voice message (feature not implemented)" className="p-2 text-gray-400 hover:text-gray-600 focus:outline-none disabled:opacity-50 disabled:hover:text-gray-400" disabled={!selectedAgent || true}>
                <Mic size={22} />
              </button>
              <input type="text" placeholder={selectedAgent ? `Message ${selectedAgent.name}...` : "Select an agent"}
                className="flex-1 p-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none text-sm"
                value={inputText} onChange={(e) => setInputText(e.target.value)}
                onKeyPress={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSendMessage(); }}}
                disabled={!selectedAgent} />
              <button onClick={handleSendMessage}
                className="px-5 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 disabled:opacity-60 disabled:hover:bg-blue-600"
                disabled={!selectedAgent || !inputText.trim()}>
                Send
              </button>
            </div>
          </div>
        </div>

        {/* Right Sidebar */}
        <aside className="w-1/3 lg:w-1/4 flex flex-col space-y-4 overflow-y-auto h-[calc(100vh-100px)]">
          {/* Meetings Section */}
          <div className="bg-white p-4 rounded-lg shadow-md flex-shrink-0">
            <h2 className="text-lg font-semibold mb-3 border-b pb-2">Meetings</h2>
            {meetings.length > 0 ? (
              <ul className="space-y-2 text-sm max-h-48 overflow-y-auto">
                {meetings.map(meeting => (
                  <li 
                    key={meeting.id} 
                    className="p-2 bg-gray-50 rounded hover:bg-gray-100 cursor-pointer"
                    onClick={() => openMeetingDetailModal(meeting)}
                  >
                    <p className="font-medium text-gray-700">{meeting.title}</p>
                    <p className="text-xs text-gray-500">{meeting.dateTime}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-gray-500">{selectedAgent ? `No upcoming meetings found for ${selectedAgent.name}.` : "Select an agent to see meetings."}</p>
            )}
          </div>

          {/* Projects Section */}
          <div className="bg-white p-4 rounded-lg shadow-md flex-shrink-0">
            <div className="flex justify-between items-center mb-3 border-b pb-2">
              <h2 className="text-lg font-semibold">Projects</h2>
              <button 
                onClick={openNewProjectModal} 
                className="flex items-center px-2.5 py-1.5 bg-blue-500 text-white text-xs font-medium rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 disabled:opacity-50"
                disabled={!selectedAgent}
              >
                <PlusCircle size={14} className="mr-1.5" />
                New Project
              </button>
            </div>
            {projects.length > 0 ? (
              <ul className="space-y-2 text-sm max-h-48 overflow-y-auto">
                {projects.map(project => (
                  <li 
                    key={project.id} 
                    className="p-2 bg-gray-50 rounded hover:bg-gray-100 cursor-pointer transition-colors duration-150 ease-in-out"
                    onClick={() => openProjectDetailModal(project)}
                  >
                    <p className="font-medium text-gray-700">{project.name}</p>
                    {project.participants && project.participants.length > 0 && (
                        <p className="text-xs text-gray-500">Participants: {project.participants.join(', ')}</p>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-gray-500">{selectedAgent ? "No projects found." : "Select an agent to see projects."}</p>
            )}
          </div>

          {/* Tasks Section */}
          <div className="bg-white p-4 rounded-lg shadow-md flex-shrink-0">
            <h2 className="text-lg font-semibold mb-3 border-b pb-2">Tasks</h2>
            {tasks.length > 0 ? (
              <ul className="space-y-2 text-sm max-h-48 overflow-y-auto">
                {tasks.map(task => (
                  <li 
                    key={task.id} 
                    className="p-2 bg-gray-50 rounded hover:bg-gray-100 cursor-pointer transition-colors duration-150 ease-in-out"
                    onClick={() => openTaskDetailModal(task)}
                  >
                    <p className="font-medium text-gray-700">{task.title}</p>
                    {task.due_date && <p className="text-xs text-gray-500">Due: {new Date(task.due_date).toLocaleDateString()}</p>}
                    {task.priority && <p className="text-xs text-gray-500 capitalize">Priority: <span className={task.priority === 'high' ? 'text-red-500' : task.priority === 'medium' ? 'text-yellow-500' : 'text-green-500'}>{task.priority}</span></p>}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-gray-500">{selectedAgent ? "No tasks found." : "Select an agent to see tasks."}</p>
            )}
          </div>
        </aside>
      </div>
      <NewProjectModal
        isOpen={isNewProjectModalOpen}
        onClose={closeNewProjectModal}
        onSubmit={handleSubmitNewProject}
      />
      <ProjectDetailModal
        isOpen={isProjectDetailModalOpen}
        onClose={closeProjectDetailModal}
        project={selectedProjectForDetail}
      />
      <TaskDetailModal
        isOpen={isTaskDetailModalOpen}
        onClose={closeTaskDetailModal}
        task={selectedTaskForDetail}
      />
      <MeetingDetailModal
        isOpen={isMeetingDetailModalOpen}
        onClose={closeMeetingDetailModal}
        meeting={selectedMeetingForDetail}
      />
    </div>
  );
}
