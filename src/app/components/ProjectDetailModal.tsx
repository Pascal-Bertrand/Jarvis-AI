import { X } from 'lucide-react';

// Define types locally as they are not directly exported from page.tsx for components
interface PlanStep {
  name: string;
  description: string;
  responsible_participants: string[];
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

interface ProjectDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  project: Project | null;
}

const ProjectDetailModal: React.FC<ProjectDetailModalProps> = ({ isOpen, onClose, project }) => {
  if (!isOpen || !project) return null;

  const createdDate = project.created_at ? new Date(project.created_at).toLocaleString() : 'N/A';

  return (
    <div className="fixed inset-0 flex items-center justify-center z-50 p-4"
      style={{ backgroundColor: 'rgba(0, 0, 0, 0.75)' }}
    >
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl flex flex-col" style={{ maxHeight: '90vh' }}>
        <div className="flex justify-between items-center p-4 sm:p-6 border-b border-gray-200">
          <h2 className="text-xl sm:text-2xl font-semibold text-gray-800">Project Details</h2>
          <button 
            onClick={onClose} 
            className="p-1.5 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-gray-400 active:bg-gray-200 transition-colors"
            aria-label="Close project details"
          >
            <X size={22} />
          </button>
        </div>

        <div className="p-4 sm:p-6 space-y-4 overflow-y-auto">
          <div>
            <h3 className="text-lg font-semibold text-blue-600">{project.name}</h3>
            {project.owner && <p className="text-sm text-gray-600"><span className="font-medium">Owner:</span> {project.owner}</p>}
          </div>

          {project.participants && project.participants.length > 0 && (
            <div>
              <h4 className="text-md font-medium text-gray-700 mb-1">Participants:</h4>
              <div className="flex flex-wrap gap-2">
                {project.participants.map((participant: string) => (
                  <span key={participant} className="px-2.5 py-1 text-xs bg-gray-100 text-gray-700 rounded-full font-medium">
                    {participant}
                  </span>
                ))}
              </div>
            </div>
          )}

          {(project.description || project.objective) && (
            <div>
              <div 
                className="text-sm text-gray-600" 
                dangerouslySetInnerHTML={{ __html: project.description || project.objective || "" }}
              />
            </div>
          )}
          
          <div className="pt-2 border-t border-gray-200 mt-4">
            {project.status && <p className="text-sm text-gray-600"><span className="font-medium">Status:</span> {project.status}</p>}
            <p className="text-sm text-gray-600"><span className="font-medium">Created:</span> {createdDate}</p>
          </div>

        </div>
        
        <div className="p-4 sm:p-6 border-t border-gray-200 bg-gray-50 flex justify-end">
            <button 
                onClick={onClose}
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1"
            >
                Close
            </button>
        </div>
      </div>
    </div>
  );
};

export default ProjectDetailModal; 