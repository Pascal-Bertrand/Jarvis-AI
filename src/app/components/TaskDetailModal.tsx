import { X } from 'lucide-react';

/**
 * @interface Task
 * @description Defines the structure for a task object.
 * Local definition or import if available globally.
 */
interface Task {
  /** @property {string} id - The unique identifier for the task. */
  id: string;
  /** @property {string} title - The title of the task. */
  title: string;
  /** @property {string} [description] - A detailed description of the task. Optional. */
  description?: string;
  /** @property {string} [assigned_to] - The name or ID of the user/agent assigned to the task. Optional. */
  assigned_to?: string;
  /** @property {string} [due_date] - The ISO date string for when the task is due. Optional. */
  due_date?: string;
  /** @property {'high' | 'medium' | 'low' | string} [priority] - The priority of the task. Can be one of the predefined values or a custom string. Optional. */
  priority?: 'high' | 'medium' | 'low' | string; 
  /** @property {string} [project_id] - The ID of the project this task belongs to. Optional. */
  project_id?: string;
  // Add any other task-specific fields that might be available
}

/**
 * @interface TaskDetailModalProps
 * @description Defines the props for the TaskDetailModal component.
 */
interface TaskDetailModalProps {
  /** @property {boolean} isOpen - Controls the visibility of the modal. True if the modal should be open, false otherwise. */
  isOpen: boolean;
  /** @property {() => void} onClose - Callback function to be invoked when the modal is requested to be closed. */
  onClose: () => void;
  /** @property {Task | null} task - The task object containing details to display. If null, the modal content related to the task will not be rendered. */
  task: Task | null;
}

/**
 * @component TaskDetailModal
 * @description A React functional component that displays detailed information about a task in a modal.
 * It shows task title, description, assignee, due date, priority, and associated project ID.
 * @param {TaskDetailModalProps} props - The props for the component.
 * @param {boolean} props.isOpen - Whether the modal is currently visible.
 * @param {() => void} props.onClose - Function to call to close the modal.
 * @param {Task | null} props.task - The task data to display. If null or `isOpen` is false, the modal is not rendered.
 * @returns {JSX.Element | null} The rendered task detail modal or null.
 */
const TaskDetailModal: React.FC<TaskDetailModalProps> = ({ isOpen, onClose, task }) => {
  // If the modal is not open or no task data is provided, do not render anything.
  if (!isOpen || !task) return null;

  // Format due date for display, or 'N/A' if not available.
  const dueDate = task.due_date ? new Date(task.due_date).toLocaleDateString() : 'N/A';
  // Format priority for display: capitalize first letter, or 'N/A' if not available.
  const priority = task.priority ? task.priority.charAt(0).toUpperCase() + task.priority.slice(1) : 'N/A';

  // Determine the color class for priority text based on its value.
  let priorityColorClass = 'text-gray-600';
  if (task.priority === 'high') {
    priorityColorClass = 'text-red-500 font-semibold';
  } else if (task.priority === 'medium') {
    priorityColorClass = 'text-yellow-500 font-semibold';
  } else if (task.priority === 'low') {
    priorityColorClass = 'text-green-500 font-semibold';
  }

  return (
    // Modal backdrop: fixed position, covers screen, centered content, semi-transparent background.
    <div className="fixed inset-0 flex items-center justify-center z-50 p-4"
      style={{ backgroundColor: 'rgba(0, 0, 0, 0.75)' }}
    >
      {/* Modal panel: white background, rounded corners, shadow, max width, and max height for responsiveness. */}
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg flex flex-col" style={{ maxHeight: '90vh' }}>
        {/* Modal Header: Contains the title and a close button. */}
        <div className="flex justify-between items-center p-4 sm:p-6 border-b border-gray-200">
          <h2 className="text-xl sm:text-2xl font-semibold text-gray-800">Task Details</h2>
          <button 
            onClick={onClose} 
            className="p-1.5 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-gray-400 active:bg-gray-200 transition-colors"
            aria-label="Close task details"
          >
            <X size={22} />
          </button>
        </div>

        {/* Modal Body: Scrollable area for task content. */}
        <div className="p-4 sm:p-6 space-y-4 overflow-y-auto">
          {/* Task Title */}
          <h3 className="text-lg font-semibold text-blue-600">{task.title}</h3>
          
          {/* Task Description: Displayed if available. */}
          {task.description && (
            <div>
              <h4 className="text-md font-medium text-gray-700 mb-1">Description:</h4>
              <p className="text-sm text-gray-600 whitespace-pre-wrap">{task.description}</p>
            </div>
          )}

          {/* Grid for Task Details: Assigned to, Due Date, Priority, Project ID. */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-gray-200 mt-4">
            <div>
              <p className="text-sm text-gray-600"><span className="font-medium">Assigned to:</span> {task.assigned_to || 'N/A'}</p>
              <p className="text-sm text-gray-600"><span className="font-medium">Due Date:</span> {dueDate}</p>
            </div>
            <div>
              <p className="text-sm text-gray-600"><span className="font-medium">Priority:</span> <span className={priorityColorClass}>{priority}</span></p>
              {task.project_id && <p className="text-sm text-gray-600"><span className="font-medium">Project ID:</span> {task.project_id}</p>}
            </div>
          </div>

        </div>
        
        {/* Modal Footer: Contains a close button. */}
        <div className="p-4 sm:p-6 border-t border-gray-200 bg-gray-50 flex justify-end">
            <button 
                onClick={onClose}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-1"
            >
                Close
            </button>
        </div>
      </div>
    </div>
  );
};

export default TaskDetailModal; 