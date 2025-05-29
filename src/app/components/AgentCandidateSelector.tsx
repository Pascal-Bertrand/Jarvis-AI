'use client';

import AgentCandidateCard, { CandidateAgent } from './AgentCandidateCard';
import { Users } from 'lucide-react'; // Using Users icon for "Agent:"

/**
 * @interface AgentCandidateSelectorProps
 * @description Defines the props for the AgentCandidateSelector component.
 * This interface includes the message ID, a list of candidate agents, an optional project ID,
 * callback functions for accepting or rejecting a candidate, and optional introductory text.
 */
interface AgentCandidateSelectorProps {
  /** @property {string} messageId - The ID of the message associated with this selection. */
  messageId: string; 
  /** @property {CandidateAgent[]} candidates - An array of candidate agents to be displayed. */
  candidates: CandidateAgent[];
  /** @property {string} [projectId] - Optional ID of the project for which candidates are being selected. */
  projectId?: string; 
  /** 
   * @property {(candidateName: string, projectId: string | undefined, messageId: string) => void} onCandidateAccept - 
   * Callback function invoked when a candidate is accepted. 
   * Takes the candidate's name, project ID (if any), and message ID as arguments.
   */
  onCandidateAccept: (candidateName: string, projectId: string | undefined, messageId: string) => void; 
  /** 
   * @property {(candidateName: string, projectId: string | undefined, messageId: string) => void} onCandidateReject -
   * Callback function invoked when a candidate is rejected. 
   * Takes the candidate's name, project ID (if any), and message ID as arguments.
   */
  onCandidateReject: (candidateName: string, projectId: string | undefined, messageId: string) => void; 
  /** @property {string} [introText] - Optional introductory text to display above the candidate selection. */
  introText?: string; 
}

/**
 * @component AgentCandidateSelector
 * @description A React functional component that displays a list of agent candidates
 * and allows the user to accept or reject them. It can be contextualized with a project ID
 * and a message ID, and can display custom introductory text.
 * @param {AgentCandidateSelectorProps} props - The props for the component.
 * @param {string} props.messageId - The ID of the message related to this candidate selection.
 * @param {CandidateAgent[]} props.candidates - The list of candidate agents.
 * @param {string} [props.projectId] - Optional project ID for context.
 * @param {(candidateName: string, projectId: string | undefined, messageId: string) => void} props.onCandidateAccept - Callback for accepting a candidate.
 * @param {(candidateName: string, projectId: string | undefined, messageId: string) => void} props.onCandidateReject - Callback for rejecting a candidate.
 * @param {string} [props.introText] - Optional text to display before the list of candidates.
 * @returns {JSX.Element | null} The rendered candidate selector component or null if no candidates are available without intro text.
 */
const AgentCandidateSelector: React.FC<AgentCandidateSelectorProps> = ({ 
  messageId, 
  candidates, 
  projectId,
  onCandidateAccept,
  onCandidateReject,
  introText 
}) => {
  // If there are no candidates to display
  if (!candidates || candidates.length === 0) {
    // If introText is provided, it implies that candidates were expected for this message,
    // but all have been processed. Display the intro text and a message indicating this.
    if (introText) {
      return (
        <div className="my-3 p-4 bg-slate-50 rounded-lg w-full">
          <p className="mb-2 text-sm text-gray-700 italic">{introText}</p>
          <p className="text-sm text-gray-500">All candidates from this selection have been processed.</p>
        </div>
      );
    }
    // If no introText and no candidates, render nothing.
    return null; 
  }

  // Main container for the agent candidate selector
  return (
    <div className="my-3 p-4 bg-slate-50 rounded-lg w-full">
      {/* Display intro text if provided, otherwise display a default prompt */}
      {introText ? (
        <p className="mb-3 text-sm text-gray-700 italic">{introText}</p>
      ) : (
        // Default prompt message if no introText is specified
        <div className="flex items-center text-sm text-slate-700 mb-3">
          <Users size={18} className="mr-2 text-slate-600 flex-shrink-0" /> 
          <span className="font-medium">Agent:</span> 
          <span className="ml-1 text-slate-600">Please select the best-suited candidates{projectId ? ` for project '${projectId}'` : ''}:</span>
        </div>
      )}
      {/* Grid layout for displaying agent candidate cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {candidates.map((candidate, index) => (
          <AgentCandidateCard 
            key={candidate.name + index} 
            candidate={candidate} 
            onAccept={(name) => onCandidateAccept(name, projectId, messageId)} 
            onReject={(name) => onCandidateReject(name, projectId, messageId)} 
          />
        ))}
      </div>
    </div>
  );
};

export default AgentCandidateSelector; 