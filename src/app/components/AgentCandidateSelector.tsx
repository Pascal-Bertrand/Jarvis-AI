'use client';

import AgentCandidateCard, { CandidateAgent } from './AgentCandidateCard';
import { Users } from 'lucide-react'; // Using Users icon for "Agent:"

interface AgentCandidateSelectorProps {
  messageId: string; // Added messageId
  candidates: CandidateAgent[];
  projectId?: string; // Optional project ID for context
  onCandidateAccept: (candidateName: string, projectId: string | undefined, messageId: string) => void; // Updated signature
  onCandidateReject: (candidateName: string, projectId: string | undefined, messageId: string) => void; // Updated signature
  introText?: string; // Added introText
}

const AgentCandidateSelector: React.FC<AgentCandidateSelectorProps> = ({ 
  messageId, // Destructure messageId
  candidates, 
  projectId,
  onCandidateAccept,
  onCandidateReject,
  introText // Destructure introText
}) => {
  if (!candidates || candidates.length === 0) {
    // If introText exists but no candidates, it implies all were processed from this message.
    // We can show the intro text and a message about no more candidates.
    if (introText) {
      return (
        <div className="my-3 p-4 bg-slate-50 rounded-lg w-full">
          <p className="mb-2 text-sm text-gray-700 italic">{introText}</p>
          <p className="text-sm text-gray-500">All candidates from this selection have been processed.</p>
        </div>
      );
    }
    return null; // Or some other placeholder if introText is also missing
  }

  return (
    <div className="my-3 p-4 bg-slate-50 rounded-lg w-full">
      {introText ? (
        <p className="mb-3 text-sm text-gray-700 italic">{introText}</p>
      ) : (
        <div className="flex items-center text-sm text-slate-700 mb-3">
          <Users size={18} className="mr-2 text-slate-600 flex-shrink-0" /> {/* Robot icon from screenshot is similar to Users or Bot icon */}
          <span className="font-medium">Agent:</span> 
          <span className="ml-1 text-slate-600">Please select the best-suited candidates{projectId ? ` for project '${projectId}'` : ''}:</span>
        </div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {candidates.map((candidate, index) => (
          <AgentCandidateCard 
            key={candidate.name + index} // Using name + index for key, ensure names are unique or use proper IDs if available
            candidate={candidate} 
            onAccept={(name) => onCandidateAccept(name, projectId, messageId)} // Pass messageId
            onReject={(name) => onCandidateReject(name, projectId, messageId)} // Pass messageId
          />
        ))}
      </div>
    </div>
  );
};

export default AgentCandidateSelector; 