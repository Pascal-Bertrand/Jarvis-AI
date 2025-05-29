import { X } from 'lucide-react';

/**
 * @interface PlanStep
 * @description Defines the structure for a single step in a project plan.
 * This is a local type definition as it's not directly exported from page.tsx for components.
 */
interface PlanStep {
  /** @property {string} name - The name or title of the plan step. */
  name: string;
  /** @property {string} description - A detailed description of the plan step. */
  description: string;
  /** @property {string[]} responsible_participants - An array of participant names responsible for this step. */
  responsible_participants: string[];
}

/**
 * @interface Project
 * @description Defines the structure for a project object.
 * This is a local type definition as it's not directly exported from page.tsx for components.
 */
interface Project {
  /** @property {string} id - The unique identifier for the project. */
  id: string;
  /** @property {string} name - The name or title of the project. */
  name: string;
  /** @property {string} [owner] - The owner or creator of the project. Optional. */
  owner?: string;
  /** @property {string[]} [participants] - An array of participant names involved in the project. Optional. */
  participants?: string[];
  /** @property {string} [objective] - The main objective or goal of the project. Optional. */
  objective?: string;
  /** @property {string} [description] - A detailed description of the project. Optional. */
  description?: string;
  /** @property {PlanStep[]} [plan_steps] - An array of plan steps associated with the project. Optional. */
  plan_steps?: PlanStep[];
  /** @property {string} [status] - The current status of the project (e.g., "In Progress", "Completed"). Optional. */
  status?: string;
  /** @property {string} [created_at] - The ISO date string representing when the project was created. Optional. */
  created_at?: string;
}

/**
 * @interface ProjectDetailModalProps
 * @description Defines the props for the ProjectDetailModal component.
 */
interface ProjectDetailModalProps {
  /** @property {boolean} isOpen - Controls the visibility of the modal. True if the modal should be open, false otherwise. */
  isOpen: boolean;
  /** @property {() => void} onClose - Callback function to be invoked when the modal is requested to be closed. */
  onClose: () => void;
  /** @property {Project | null} project - The project object containing details to display. If null, the modal content related to the project will not be rendered. */
  project: Project | null;
}

/**
 * @component ProjectDetailModal
 * @description A React functional component that displays detailed information about a project in a modal.
 * It shows project name, owner, participants, description/objective, status, and creation date.
 * @param {ProjectDetailModalProps} props - The props for the component.
 * @param {boolean} props.isOpen - Whether the modal is currently visible.
 * @param {() => void} props.onClose - Function to call to close the modal.
 * @param {Project | null} props.project - The project data to display. If null or `isOpen` is false, the modal is not rendered.
 * @returns {JSX.Element | null} The rendered project detail modal or null.
 */
const ProjectDetailModal: React.FC<ProjectDetailModalProps> = ({ isOpen, onClose, project }) => {
  // If the modal is not open or no project data is provided, do not render anything.
  if (!isOpen || !project) return null;

  // Format the creation date for display, or show 'N/A' if not available.
  const createdDate = project.created_at ? new Date(project.created_at).toLocaleString() : 'N/A';

  return (
    // Modal backdrop: fixed position, covers the screen, centered content, with a semi-transparent background.
    <div className="fixed inset-0 flex items-center justify-center z-50 p-4"
      style={{ backgroundColor: 'rgba(0, 0, 0, 0.75)' }}
    >
      {/* Modal panel: white background, rounded corners, shadow, max width, and max height for responsiveness. */}
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl flex flex-col" style={{ maxHeight: '90vh' }}>
        {/* Modal Header: Contains the title and a close button. */}
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

        {/* Modal Body: Scrollable area for project content. */}
        <div className="p-4 sm:p-6 space-y-4 overflow-y-auto">
          {/* Project Name and Owner section */}
          <div>
            <h3 className="text-lg font-semibold text-blue-600">{project.name}</h3>
            {project.owner && <p className="text-sm text-gray-600"><span className="font-medium">Owner:</span> {project.owner}</p>}
          </div>

          {/* Participants section: Displayed if there are any participants. */}
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

          {/* Description or Objective section: Displayed if either exists. Uses dangerouslySetInnerHTML for potential HTML content. */}
          {(project.description || project.objective) && (
            <div>
              <div 
                className="text-sm text-gray-600" 
                dangerouslySetInnerHTML={{ __html: project.description || project.objective || "" }} // Ensure fallback to empty string if both are undefined
              />
            </div>
          )}
          
          {/* Status and Creation Date section: Separated by a top border. */}
          <div className="pt-2 border-t border-gray-200 mt-4">
            {project.status && <p className="text-sm text-gray-600"><span className="font-medium">Status:</span> {project.status}</p>}
            <p className="text-sm text-gray-600"><span className="font-medium">Created:</span> {createdDate}</p>
          </div>

        </div>
        
        {/* Modal Footer: Contains a close button. */}
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