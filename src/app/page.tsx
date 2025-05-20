'use client'; // Required for hooks like useState, useEffect

import { useEffect, useState, useRef } from 'react';
import { io, Socket } from 'socket.io-client';
import { Mic, Info, ChevronDown, PlusCircle } from 'lucide-react';
import AgentCandidateSelector from './components/AgentCandidateSelector';
import type { CandidateAgent } from './components/AgentCandidateCard';

// Define types for our data
interface Agent {
  id: string;
  name: string;
  // Add other agent properties if available from the /nodes endpoint
}

interface ChatMessage {
  id: string;
  type: 'user' | 'agent' | 'system';
  text: string;
  timestamp?: string; // Optional: for displaying time
  messageSubType?: 'candidate_selection';
  candidates?: CandidateAgent[];
  projectId?: string;
}

interface Meeting {
  id: string;
  title: string; // In original index.html, it used meeting.summary or meeting.title
  dateTime: string; // Formatted date string
  // Example from index.html: const formattedDate = startDate ? startDate.toLocaleString(...) : 'No date set';
}

interface Project {
  id: string;
  name: string;
  participants?: string[]; // From index.html example
}

// Define a placeholder for the Socket.IO server URL
// If your backend is on a different port or domain, change this.
// Example: const SOCKET_URL = 'http://localhost:8000';
const BACKEND_URL = 'http://localhost:5001'; // IMPORTANT: Adjust if your Python backend is elsewhere

export default function Home() {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [currentAgentRoom, setCurrentAgentRoom] = useState<string | null>(null);
  const [inputText, setInputText] = useState(''); // Renamed from 'message' to avoid confusion
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const messagesEndRef = useRef<HTMLDivElement | null>(null); // For auto-scrolling

  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  // Add tasks state later: const [tasks, setTasks] = useState<Task[]>([]);

  // Scroll to bottom of messages when new messages are added
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Effect for initializing and cleaning up Socket.IO connection
  useEffect(() => {
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

    // TODO: Add listeners for 'update_tasks', 'update_projects', 'new_message' from agent (if backend pushes them)
    // Example: newSocket.on('agent_says_something_new', (data) => { add message of type 'agent' });

    return () => {
      newSocket.disconnect();
    };
  }, []);

  // Effect for fetching agents
  useEffect(() => {
    const fetchAgents = async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/nodes`);
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
  }, []); // Run once on mount

  const fetchMeetings = async (agentId: string) => {
    try {
      const response = await fetch(`${BACKEND_URL}/meetings?agent_id=${agentId}`);
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const data: { id: string, summary?: string, title?: string, start: { dateTime?: string, date?: string } }[] = await response.json();
      const formattedMeetings: Meeting[] = data.map((meeting) => ({
        id: meeting.id,
        title: meeting.summary || meeting.title || 'Untitled Meeting',
        dateTime: meeting.start?.dateTime ? new Date(meeting.start.dateTime).toLocaleString() : (meeting.start?.date ? new Date(meeting.start.date).toLocaleDateString() : 'Date TBD')
      }));
      setMeetings(formattedMeetings);
    } catch (error) {
      console.error('Error fetching meetings:', error);
      setMeetings([]); // Clear meetings on error
    }
  };

  const fetchProjects = async (agentId: string) => {
    try {
      const response = await fetch(`${BACKEND_URL}/projects?agent_id=${agentId}`);
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      // Type for data can be an array of projects or an object mapping IDs to projects
      const data: Project[] | { [projectId: string]: Omit<Project, 'id'> } = await response.json();
      let projectArray: Project[] = [];
      if (Array.isArray(data)) {
        projectArray = data.map((p: { id?: string, name: string, participants?: string[] }) => ({ id: p.id || p.name, name: p.name, participants: p.participants || [] }));
      } else if (typeof data === 'object' && data !== null) {
        projectArray = Object.keys(data).map(projectId => ({
          id: projectId,
          name: data[projectId].name || projectId,
          participants: data[projectId].participants || []
        }));
      }
      setProjects(projectArray);
    } catch (error) {
      console.error('Error fetching projects:', error);
      setProjects([]); // Clear projects on error
    }
  };

  const handleAgentSelect = (agent: Agent | null, isInitialSelect: boolean = false) => {
    if (!agent) {
        setSelectedAgent(null);
        setMessages([]);
        setMeetings([]);
        setProjects([]);
        // setTasks([]);
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
    // fetchTasks(agent.id); // TODO

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
  
  // Auto-select first agent when agent list loads
  useEffect(() => {
    if (agents.length > 0 && !selectedAgent) {
      handleAgentSelect(agents[0], true);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agents]); // Only re-run if agents array itself changes

  // Reusable function to post any message/command to the agent and handle response
  const _postMessageToAgent = async (messageText: string) => {
    if (!selectedAgent) {
      setMessages(prev => [...prev, { id: Date.now().toString(), type: 'system', text: 'Error: No agent selected to send the command.' }]);
      return;
    }
    try {
      const response = await fetch(`${BACKEND_URL}/send_message`, {
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
        // Check for candidate selection response from this command too, though less likely
        const candidatePrefix = "Here are the best-suited candidates for your project '";
        if (agentResponseText.startsWith(candidatePrefix)) {
          const endOfPrefix = agentResponseText.indexOf("':") + 2;
          const jsonString = agentResponseText.substring(endOfPrefix).trim();
          const projectIdMatch = agentResponseText.match(/project '([^']*)'/);
          const projectId = projectIdMatch ? projectIdMatch[1] : undefined;
          try {
            const candidatesData: CandidateAgent[] = JSON.parse(jsonString);
            setMessages(prev => [...prev, {
              id: Date.now().toString() + '-agent-candidates',
              type: 'agent', text: agentResponseText.substring(0, endOfPrefix),
              messageSubType: 'candidate_selection', candidates: candidatesData, projectId: projectId,
              timestamp: new Date().toLocaleTimeString()
            }]);
          } catch (parseError) {
            console.error("Failed to parse candidate JSON from command response:", parseError);
            setMessages(prev => [...prev, { id: Date.now().toString() + '-agent', type: 'agent', text: agentResponseText, timestamp: new Date().toLocaleTimeString() }]);
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
    await _postMessageToAgent(currentMessageText);
  };
  
  const handleCandidateAccept = async (candidateName: string, projectId?: string) => {
    if (!selectedAgent) {
      setMessages(prev => [...prev, { id: Date.now().toString(), type: 'system', text: 'Error: No agent selected for this action.' }]);
      return;
    }

    const acceptanceMessage = `User action: Accepted candidate ${candidateName}${projectId ? ` for project '${projectId}'` : ''}.`;
    const continuationMessage = `System command: Continue project planning for project '${projectId}' with participant ${candidateName}.`;

    // Add a system message immediately for responsiveness about the initial action
    setMessages(prev => [...prev, {
      id: Date.now().toString() + '-accept-process',
      type: 'system',
      text: `Processing acceptance for ${candidateName}...`,
      timestamp: new Date().toLocaleTimeString()
    }]);

    // Send the acceptance message
    await _postMessageToAgent(acceptanceMessage);

    // If there's a project ID, immediately send the command to continue project planning
    if (projectId) {
      // Optionally, add another system message indicating the continuation command is being sent
      setMessages(prev => [...prev, {
        id: Date.now().toString() + '-continue-process',
        type: 'system',
        text: `Instructing agent to continue planning for project '${projectId}' with ${candidateName}.`,
        timestamp: new Date().toLocaleTimeString()
      }]);
      await _postMessageToAgent(continuationMessage);
    }
  };

  const handleCandidateReject = async (candidateName: string, projectId?: string) => {
    const commandText = `User action: Rejected candidate ${candidateName}${projectId ? ` for project '${projectId}'` : ''}.`;
    setMessages(prev => [...prev, {
      id: Date.now().toString(),
      type: 'system',
      text: `Processing rejection for ${candidateName}...`
    }]);
    await _postMessageToAgent(commandText);
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50 font-sans text-gray-800">
      {/* Main Header */}
      <header className="bg-white p-4 border-b border-gray-200 shadow-sm flex items-center justify-between sticky top-0 z-50">
        <div>
          <h1 className="text-2xl font-bold text-blue-600">Jarvis-AI</h1>
          <p className="text-xs text-gray-500">[demo] Control and monitor your AI agents</p>
        </div>
        <div className="flex items-center space-x-2">
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
                ) : msg.messageSubType === 'candidate_selection' && msg.candidates ? (
                  <AgentCandidateSelector
                    candidates={msg.candidates}
                    projectId={msg.projectId}
                    onCandidateAccept={handleCandidateAccept}
                    onCandidateReject={handleCandidateReject}
                  />
                ) : (
                  <div className={`max-w-[70%] px-3.5 py-2 rounded-xl shadow-sm break-words whitespace-pre-wrap ${msg.type === 'user' ? 'bg-blue-600 text-white rounded-br-none' : 'bg-gray-200 text-gray-800 rounded-bl-none'}`}>
                    <p className="text-sm">{msg.text}</p>
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
                  <li key={meeting.id} className="p-2 bg-gray-50 rounded hover:bg-gray-100 cursor-pointer">
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
                onClick={() => alert('New Project modal to be implemented')} 
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
                  <li key={project.id} className="p-2 bg-gray-50 rounded hover:bg-gray-100 cursor-pointer">
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
            {/* TODO: Fetch and display tasks */}
            <p className="text-sm text-gray-500">{selectedAgent ? "No tasks found." : "Select an agent to see tasks."}</p>
          </div>
        </aside>
      </div>
    </div>
  );
}
