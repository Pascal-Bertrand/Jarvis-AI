'use client'; // Required for hooks like useState, useEffect

import { useEffect, useState, useRef } from 'react';
import { io, Socket } from 'socket.io-client';
import { Mic, Info, ChevronDown, PlusCircle } from 'lucide-react';
import AgentCandidateSelector from './components/AgentCandidateSelector';
import type { CandidateAgent } from './components/AgentCandidateCard';
import NewProjectModal from './components/NewProjectModal';
import ProjectDetailModal from './components/ProjectDetailModal';
import TaskDetailModal from './components/TaskDetailModal';
import MeetingDetailModal from './components/MeetingDetailModal';
import { useSession, signIn, signOut } from 'next-auth/react'

// Define types for our data
interface Agent {
  id: string;
  name: string;
  // Add other agent properties if available from the /nodes endpoint
}

interface PlanStep {
  name: string;
  description: string;
  responsible_participants: string[];
}

export interface ChatMessage {
  id: string;
  type: 'user' | 'agent' | 'system';
  text: string;
  timestamp?: string; // Optional: for displaying time
  messageSubType?: 'candidate_selection';
  candidates?: CandidateAgent[];
  projectId?: string;
  isLoadingPlaceholder?: boolean;
  promptIssued?: boolean; // Added to track if next step prompt was issued
}

export interface Meeting {
  id: string;
  title: string;
  dateTime: string; // Formatted start date/time for list display
  startTimeISO?: string; // Raw start dateTime or date
  endTimeISO?: string;   // Raw end dateTime or date
  attendees?: { email: string; displayName?: string }[];
  organizerEmail?: string;
  description?: string; // From GCal event description, if available
  // location?: string; // If GCal events have it
  // source?: string; // Backend provides this, can be added if needed
}

interface Project {
  id: string;
  name: string;
  owner?: string;
  participants?: string[];
  objective?: string;
  description?: string;
  plan_steps?: PlanStep[];
  status?: string;
  created_at?: string;
}

interface Task {
  id: string;
  title: string;
  description?: string;
  assigned_to?: string;
  due_date?: string;
  priority?: 'high' | 'medium' | 'low' | string;
  project_id?: string;
}

interface ApiProjectData {
  name: string;
  owner?: string;
  participants?: string[];
  objective?: string;
  description?: string;
  plan_steps?: PlanStep[];
  status?: string;
  created_at?: string;
}

interface ApiProject {
  id?: string; // id might be at the top level or within the object
  name: string;
  owner?: string;
  participants?: string[];
  objective?: string;
  description?: string;
  plan_steps?: PlanStep[];
  status?: string;
  created_at?: string;
}

// Interface for the raw meeting data structure from the backend
interface RawBackendMeetingEvent {
  id: string;
  summary?: string;
  title?: string; 
  description?: string;
  start: { dateTime?: string; date?: string; timeZone?: string };
  end: { dateTime?: string; date?: string; timeZone?: string };
  attendees?: { email: string; displayName?: string }[]; 
  organizer?: { email: string; displayName?: string }; 
  source?: string; 
}

// Define a placeholder for the Socket.IO server URL
// If your backend is on a different port or domain, change this.
// Example: const SOCKET_URL = 'http://localhost:8000';
const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 
  (process.env.NODE_ENV === 'production' 
    ? 'https://jarvis-ai-production.up.railway.app' 
    : 'http://localhost:5001')

export default function Home() {
  const { data: session, status } = useSession()
  const [socket, setSocket] = useState<Socket | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [currentAgentRoom, setCurrentAgentRoom] = useState<string | null>(null);
  const [inputText, setInputText] = useState(''); // Renamed from 'message' to avoid confusion
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const messagesEndRef = useRef<HTMLDivElement | null>(null); // For auto-scrolling

  // State for loading indicators
  const loadingMessageIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const [recentlyPromptedProjectIds, setRecentlyPromptedProjectIds] = useState<Set<string>>(new Set()); // For duplicate prompt issue
  const promptedCandidateMessageIdsRef = useRef<Set<string>>(new Set()); // Ref to track issued prompts for specific candidate messages

  const projectPlanningMessages = [
    "Looking through past projects...",
    "Searching for suitable approaches...",
    "Analyzing project requirements...",
    "Generating project plan...",
    "Finalizing project structure..."
  ];

  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [isNewProjectModalOpen, setIsNewProjectModalOpen] = useState(false);
  const [isProjectDetailModalOpen, setIsProjectDetailModalOpen] = useState(false);
  const [selectedProjectForDetail, setSelectedProjectForDetail] = useState<Project | null>(null);
  const [isTaskDetailModalOpen, setIsTaskDetailModalOpen] = useState(false);
  const [selectedTaskForDetail, setSelectedTaskForDetail] = useState<Task | null>(null);
  const [isMeetingDetailModalOpen, setIsMeetingDetailModalOpen] = useState(false);
  const [selectedMeetingForDetail, setSelectedMeetingForDetail] = useState<Meeting | null>(null);

  // Ref for selectedAgent to be used in socket event handlers
  const selectedAgentRef = useRef<Agent | null>(null);

  // Scroll to bottom of messages when new messages are added
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    selectedAgentRef.current = selectedAgent;
  }, [selectedAgent]);

  // Initialize user agents on first login
  useEffect(() => {
    if (session?.accessToken) {
      initializeUserAgents()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session])

  // Effect for initializing and cleaning up Socket.IO connection
  useEffect(() => {
    if (!session) return; // Don't initialize socket if not authenticated

    const newSocket = io(BACKEND_URL); // Use BACKEND_URL for Socket.IO
    setSocket(newSocket);

    newSocket.on('connect', () => {
      console.log('Socket.IO connected:', newSocket.id);
    });
    newSocket.on('disconnect', () => {
      console.log('Socket.IO disconnected');
    });
    newSocket.on('connect_error', (err) => {
      console.error('Socket.IO connection error:', err);
      // Add a system message about connection error
      setMessages(prev => [...prev, { 
        id: Date.now().toString(), 
        type: 'system', 
        text: 'Failed to connect to the notification server. Real-time updates might be affected.' 
      }]);
    });

    newSocket.on('update_meetings', () => {
      console.log('Received update_meetings event from backend.');
      setSocket(prevSocket => {
        if (prevSocket && prevSocket.active) {
            const currentSelectedAgentId = selectedAgentRef.current?.id;
            if (currentSelectedAgentId) {
                console.log(`Socket event 'update_meetings': Fetching for agent ${currentSelectedAgentId}`);
                fetchMeetings(currentSelectedAgentId);
            } else {
                console.log("Socket event 'update_meetings': No agent selected, not fetching.");
            }
        }
        return prevSocket;
      });
    });
    
    newSocket.on('update_projects', () => {
        console.log('Received update_projects event from backend.');
        setSocket(prevSocket => {
            if (prevSocket && prevSocket.active) {
                const currentSelectedAgentId = selectedAgentRef.current?.id;
                if (currentSelectedAgentId) {
                    console.log(`Socket event 'update_projects': Fetching for agent ${currentSelectedAgentId}`);
                    fetchProjects(currentSelectedAgentId);
                } else {
                    console.log("Socket event 'update_projects': No agent selected, not fetching.");
                }
            }
            return prevSocket;
        });
    });

    newSocket.on('update_tasks', () => {
        console.log('Received update_tasks event from backend.');
        setSocket(prevSocket => {
            if (prevSocket && prevSocket.active) {
                const currentSelectedAgentId = selectedAgentRef.current?.id;
                if (currentSelectedAgentId) {
                    console.log(`Socket event 'update_tasks': Fetching for agent ${currentSelectedAgentId}`);
                    fetchTasks(currentSelectedAgentId);
                } else {
                    console.log("Socket event 'update_tasks': No agent selected, not fetching.");
                }
            }
            return prevSocket;
        });
    });

    return () => {
      newSocket.disconnect();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]); // Re-run when session changes

  // Effect for fetching agents
  useEffect(() => {
    if (!session) return; // Don't fetch if not authenticated

    const fetchAgents = async () => {
      try {
        const response = await fetchWithAuth(`${BACKEND_URL}/nodes`);
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data: Agent[] = await response.json();
        setAgents(data);
        if (data.length > 0 && !selectedAgent) {
          // Automatically select the first agent
          // handleAgentSelect will be called by the button onClick or directly if needed
        }
      } catch (error) {
        console.error('Error fetching agents:', error);
        setMessages(prev => [...prev, { id: Date.now().toString(), type: 'system', text: 'Error fetching agent list.' }]);
      }
    };
    fetchAgents();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]); // Re-run when session changes

  // Auto-select first agent when agent list loads
  useEffect(() => {
    if (agents.length > 0 && !selectedAgent) {
      handleAgentSelect(agents[0], true);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agents]); // Only re-run if agents array itself changes

  // Authentication guard - show loading state
  if (status === 'loading') {
    return <div className="flex items-center justify-center h-screen">
      <div className="text-lg">Loading...</div>
    </div>
  }

  // Authentication guard - show sign in
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

  const initializeUserAgents = async () => {
    try {
      // Note: Backend automatically initializes agents on startup
      // This could be used for user-specific initialization if needed
      console.log('User agents initialization - backend handles this automatically')
    } catch (error) {
      console.error('Failed to initialize user agents:', error)
    }
  }

  // Update all API calls to include auth headers
  const fetchWithAuth = (url: string, options: RequestInit = {}) => {
    return fetch(url, {
      ...options,
      headers: {
        ...options.headers,
        'Authorization': `Bearer ${session?.accessToken}`,
        'Content-Type': 'application/json'
      }
    })
  }

  const fetchMeetings = async (agentId: string) => {
    try {
      const response = await fetchWithAuth(`${BACKEND_URL}/meetings?agent_id=${agentId}`);
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const data: RawBackendMeetingEvent[] = await response.json(); 
      
      const formattedMeetings: Meeting[] = data.map((meeting_evt) => {
        const startDate = meeting_evt.start?.dateTime ? new Date(meeting_evt.start.dateTime) : (meeting_evt.start?.date ? new Date(meeting_evt.start.date) : null);
        // const endDate = meeting_evt.end?.dateTime ? new Date(meeting_evt.end.dateTime) : (meeting_evt.end?.date ? new Date(meeting_evt.end.date) : null);

        return {
          id: meeting_evt.id,
          title: meeting_evt.title || meeting_evt.summary || 'Untitled Meeting',
          dateTime: startDate ? (meeting_evt.start?.dateTime ? startDate.toLocaleString() : startDate.toLocaleDateString()) : 'Date TBD',
          startTimeISO: meeting_evt.start?.dateTime || meeting_evt.start?.date,
          endTimeISO: meeting_evt.end?.dateTime || meeting_evt.end?.date,
          attendees: meeting_evt.attendees?.map((a: { email: string }) => ({ email: a.email, displayName: a.email?.split('@')[0] })) || [],
          organizerEmail: meeting_evt.organizer?.email,
          description: meeting_evt.description, // GCal events might have a description in the root
                                              // or scheduler.py could add it to the transformed object
        };
      });
      setMeetings(formattedMeetings);
    } catch (error) {
      console.error('Error fetching meetings:', error);
      setMeetings([]); // Clear meetings on error
    }
  };

  const fetchProjects = async (agentId: string) => {
    try {
      const response = await fetchWithAuth(`${BACKEND_URL}/projects?agent_id=${agentId}`);
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      // Type for data can be an array of projects or an object mapping IDs to projects
      const data: Project[] | { [projectId: string]: Omit<Project, 'id'> } = await response.json();
      let projectArray: Project[] = [];
      if (Array.isArray(data)) {
        projectArray = data.map((p: ApiProject) => ({ 
            id: p.id || p.name, // Use p.name as fallback for id if not present
            name: p.name,
            owner: p.owner,
            participants: p.participants || [],
            objective: p.objective,
            description: p.description || p.objective, // Use objective as fallback for description
            plan_steps: p.plan_steps || [],
            status: p.status,
            created_at: p.created_at
        }));
      } else if (typeof data === 'object' && data !== null) {
        projectArray = Object.keys(data).map(projectId => {
          const projectData = (data as { [key: string]: ApiProjectData })[projectId];
          return {
            id: projectId,
            name: projectData.name || projectId, // Use projectId as fallback for name
            owner: projectData.owner,
            participants: projectData.participants || [],
            objective: projectData.objective,
            description: projectData.description || projectData.objective, // Use objective as fallback
            plan_steps: projectData.plan_steps || [],
            status: projectData.status,
            created_at: projectData.created_at,
          };
        });
      }
      setProjects(projectArray);
    } catch (error) {
      console.error('Error fetching projects:', error);
      setProjects([]); // Clear projects on error
    }
  };

  const fetchTasks = async (agentId: string) => {
    try {
      const response = await fetchWithAuth(`${BACKEND_URL}/tasks?agent_id=${agentId}`);
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const data: Task[] = await response.json(); // Assuming backend returns Task[] directly
      setTasks(data.map(task => ({
        ...task,
        // Format due_date if necessary, e.g., new Date(task.due_date).toLocaleDateString()
        // For now, assume backend sends it in a displayable format or TaskDetailModal handles it
      })));
    } catch (error) {
      console.error('Error fetching tasks:', error);
      setTasks([]); // Clear tasks on error
    }
  };

  const handleAgentSelect = (agent: Agent | null, isInitialSelect: boolean = false) => {
    if (!agent) {
        setSelectedAgent(null);
        // Clear messages only if it's not an initial empty select or error state
        if (!isInitialSelect || messages.length > 0 && !messages.some(m => m.type === 'system' && m.text.includes('Error'))) {
            setMessages([]);
        }
        setMeetings([]);
        setProjects([]);
        setTasks([]);
        if (socket && currentAgentRoom) {
            socket.emit('leave_room', { room: currentAgentRoom });
            console.log(`Emitted leave_room for ${currentAgentRoom}`);
            setCurrentAgentRoom(null);
        }
        return;
    }
    
    if (selectedAgent?.id === agent.id && !isInitialSelect) return;

    console.log(`Agent selected: ${agent.name}. Previous room: ${currentAgentRoom}`);
    setSelectedAgent(agent);
    
    if (!isInitialSelect) {
        setMessages([{ id: Date.now().toString(), type: 'system', text: `Switched context to ${agent.name}` }]);
    } else if (messages.length === 0) { // Only set initial welcome if no messages exist (e.g. error messages)
        setMessages([{ id: Date.now().toString(), type: 'system', text: `Context set to ${agent.name}` }]);
    }

    fetchMeetings(agent.id);
    fetchProjects(agent.id);
    fetchTasks(agent.id);

    if (socket) {
      if (currentAgentRoom && currentAgentRoom !== agent.id) {
        socket.emit('leave_room', { room: currentAgentRoom });
        console.log(`Emitted leave_room for ${currentAgentRoom}`);
      }
      if (currentAgentRoom !== agent.id) {
        socket.emit('join_room', { room: agent.id });
        console.log(`Emitted join_room for ${agent.id}`);
        setCurrentAgentRoom(agent.id);
      }
    }
    if (!isInitialSelect) {
        setInputText('');
    }
  };

  const displayLoadingIndicator = (isProjectPlanning: boolean, initialMessageOverride?: string) => {
    const newLoadingId = `loading-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
    const text = isProjectPlanning
        ? (initialMessageOverride || projectPlanningMessages[0]) 
        : "Thinking...";

    const placeholderMessage: ChatMessage = {
      id: newLoadingId,
      type: 'agent',
      text: text,
      isLoadingPlaceholder: true,
      timestamp: new Date().toLocaleTimeString()
    };

    setMessages(prev => [...prev, placeholderMessage]);

    if (isProjectPlanning) {
      if (loadingMessageIntervalRef.current) {
        clearInterval(loadingMessageIntervalRef.current);
      }
      let index = 0;
      if (initialMessageOverride) { 
          const initialIdx = projectPlanningMessages.indexOf(initialMessageOverride);
          if (initialIdx !== -1) index = (initialIdx +1) % projectPlanningMessages.length;
      } else {
          index = 1; 
      }
      
      loadingMessageIntervalRef.current = setInterval(() => {
        const nextMessageText = projectPlanningMessages[index];
        setMessages(prevMsgs => 
          prevMsgs.map(m => 
            m.id === newLoadingId ? { ...m, text: nextMessageText } : m
          )
        );
        index = (index + 1) % projectPlanningMessages.length;
      }, 3000); // Cycle every 3 seconds
    }
    return newLoadingId;
  };

  const removeLoadingIndicator = (idToRemove: string | null) => {
    if (idToRemove) {
      setMessages(prevMsgs => prevMsgs.filter(m => m.id !== idToRemove));
    }
    if (loadingMessageIntervalRef.current) {
      clearInterval(loadingMessageIntervalRef.current);
      loadingMessageIntervalRef.current = null;
    }
  };

  // Reusable function to post any message/command to the agent and handle response
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

  const openNewProjectModal = () => setIsNewProjectModalOpen(true);
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

  const openProjectDetailModal = (project: Project) => {
    setSelectedProjectForDetail(project);
    setIsProjectDetailModalOpen(true);
  };

  const closeProjectDetailModal = () => {
    setIsProjectDetailModalOpen(false);
    setSelectedProjectForDetail(null);
  };

  const openTaskDetailModal = (task: Task) => {
    setSelectedTaskForDetail(task);
    setIsTaskDetailModalOpen(true);
  };

  const closeTaskDetailModal = () => {
    setIsTaskDetailModalOpen(false);
    setSelectedTaskForDetail(null);
  };

  const openMeetingDetailModal = (meeting: Meeting) => {
    setSelectedMeetingForDetail(meeting);
    setIsMeetingDetailModalOpen(true);
  };

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
