'use client';

import { CheckCircle, XCircle } from 'lucide-react';

export interface CandidateAgent {
  name: string;
  department: string;
  skills: string[];
  title: string;
  description: string;
  // Add any other relevant fields if they come from the backend
}

interface AgentCandidateCardProps {
  candidate: CandidateAgent;
  onAccept: (candidateName: string) => void;
  onReject: (candidateName: string) => void;
}

const AgentCandidateCard: React.FC<AgentCandidateCardProps> = ({ candidate, onAccept, onReject }) => {
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4 flex flex-col space-y-3">
      <div>
        <h3 className="text-md font-semibold text-gray-800">{candidate.name}</h3>
        <p className="text-xs text-gray-500">{candidate.title} - {candidate.department}</p>
      </div>
      <p className="text-sm text-gray-600 text-pretty leading-relaxed">{candidate.description}</p>
      <div className="flex flex-wrap gap-1.5">
        {candidate.skills.map(skill => (
          <span key={skill} className="px-2 py-0.5 text-xs bg-blue-100 text-blue-700 rounded-full font-medium">
            {skill}
          </span>
        ))}
      </div>
      <div className="flex items-center space-x-2 pt-2 mt-auto">
        <button 
          onClick={() => onAccept(candidate.name)} 
          className="flex-1 inline-flex items-center justify-center px-3 py-2 text-sm font-medium text-white bg-green-500 rounded-md hover:bg-green-600 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-1 disabled:opacity-70"
        >
          <CheckCircle size={16} className="mr-1.5" />
          Accept
        </button>
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