'use client';

import { CheckCircle, XCircle } from 'lucide-react';

/**
 * @interface CandidateAgent
 * @description Represents the structure of a candidate agent object.
 * This interface defines the properties that a candidate agent can have,
 * such as name, department, skills, title, and a description.
 */
export interface CandidateAgent {
  /** @property {string} name - The name of the candidate agent. */
  name: string;
  /** @property {string} department - The department the candidate agent belongs to. */
  department: string;
  /** @property {string[]} skills - An array of skills possessed by the candidate agent. */
  skills: string[];
  /** @property {string} title - The job title of the candidate agent. */
  title: string;
  /** @property {string} description - A brief description of the candidate agent. */
  description: string;
  // Add any other relevant fields if they come from the backend
}

/**
 * @interface AgentCandidateCardProps
 * @description Defines the props for the AgentCandidateCard component.
 * This interface includes the candidate agent object and callback functions
 * for accepting or rejecting the candidate.
 */
interface AgentCandidateCardProps {
  /** @property {CandidateAgent} candidate - The candidate agent object to display. */
  candidate: CandidateAgent;
  /** @property {(candidateName: string) => void} onAccept - Callback function invoked when the candidate is accepted. Takes the candidate's name as an argument. */
  onAccept: (candidateName: string) => void;
  /** @property {(candidateName: string) => void} onReject - Callback function invoked when the candidate is rejected. Takes the candidate's name as an argument. */
  onReject: (candidateName: string) => void;
}

/**
 * @component AgentCandidateCard
 * @description A React functional component that displays information about a candidate agent
 * and provides options to accept or reject the candidate.
 * @param {AgentCandidateCardProps} props - The props for the component.
 * @param {CandidateAgent} props.candidate - The candidate agent's data.
 * @param {(candidateName: string) => void} props.onAccept - Function to call when the accept button is clicked.
 * @param {(candidateName: string) => void} props.onReject - Function to call when the reject button is clicked.
 * @returns {JSX.Element} The rendered card component for an agent candidate.
 */
const AgentCandidateCard: React.FC<AgentCandidateCardProps> = ({ candidate, onAccept, onReject }) => {
  return (
    // Main container for the agent candidate card
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4 flex flex-col space-y-3">
      {/* Section for candidate's name, title, and department */}
      <div>
        <h3 className="text-md font-semibold text-gray-800">{candidate.name}</h3>
        <p className="text-xs text-gray-500">{candidate.title} - {candidate.department}</p>
      </div>
      {/* Candidate description */}
      <p className="text-sm text-gray-600 text-pretty leading-relaxed">{candidate.description}</p>
      {/* Section displaying candidate's skills */}
      <div className="flex flex-wrap gap-1.5">
        {candidate.skills.map(skill => (
          <span key={skill} className="px-2 py-0.5 text-xs bg-blue-100 text-blue-700 rounded-full font-medium">
            {skill}
          </span>
        ))}
      </div>
      {/* Action buttons section (Accept/Reject) */}
      <div className="flex items-center space-x-2 pt-2 mt-auto">
        {/* Accept button */}
        <button 
          onClick={() => onAccept(candidate.name)} 
          className="flex-1 inline-flex items-center justify-center px-3 py-2 text-sm font-medium text-white bg-green-500 rounded-md hover:bg-green-600 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-1 disabled:opacity-70"
        >
          <CheckCircle size={16} className="mr-1.5" />
          Accept
        </button>
        {/* Reject button */}
        <button 
          onClick={() => onReject(candidate.name)} 
          className="flex-1 inline-flex items-center justify-center px-3 py-2 text-sm font-medium text-white bg-red-500 rounded-md hover:bg-red-600 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-1 disabled:opacity-70"
        >
          <XCircle size={16} className="mr-1.5" />
          Reject
        </button>
      </div>
    </div>
  );
};

export default AgentCandidateCard; 