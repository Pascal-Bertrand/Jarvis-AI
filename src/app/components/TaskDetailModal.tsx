import { X } from 'lucide-react';

// Define Task interface locally or import if available globally
interface Task {
  id: string;
  title: string;
  description?: string;
  assigned_to?: string;
  due_date?: string;
  priority?: 'high' | 'medium' | 'low' | string; // Allow string for flexibility if backend sends other values
  project_id?: string;
  // Add any other task-specific fields that might be available
}

interface TaskDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  task: Task | null;
}

const TaskDetailModal: React.FC<TaskDetailModalProps> = ({ isOpen, onClose, task }) => {
  if (!isOpen || !task) return null;

  const dueDate = task.due_date ? new Date(task.due_date).toLocaleDateString() : 'N/A';
  const priority = task.priority ? task.priority.charAt(0).toUpperCase() + task.priority.slice(1) : 'N/A';

  let priorityColorClass = 'text-gray-600';
  if (task.priority === 'high') {
    priorityColorClass = 'text-red-500 font-semibold';
  } else if (task.priority === 'medium') {
    priorityColorClass = 'text-yellow-500 font-semibold';
  } else if (task.priority === 'low') {
    priorityColorClass = 'text-green-500 font-semibold';
  }

  return (
    <div className="fixed inset-0 flex items-center justify-center z-50 p-4"
      style={{ backgroundColor: 'rgba(0, 0, 0, 0.75)' }}
    >
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg flex flex-col" style={{ maxHeight: '90vh' }}>
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

        <div className="p-4 sm:p-6 space-y-4 overflow-y-auto">
          <h3 className="text-lg font-semibold text-blue-600">{task.title}</h3>
          
          {task.description && (
            <div>
              <h4 className="text-md font-medium text-gray-700 mb-1">Description:</h4>
              <p className="text-sm text-gray-600 whitespace-pre-wrap">{task.description}</p>
            </div>
          )}

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