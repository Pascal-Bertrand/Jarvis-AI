'use client';

import React, { useState } from 'react';

/**
 * @interface NewProjectModalProps
 * @description Defines the props for the NewProjectModal component.
 */
interface NewProjectModalProps {
  /** @property {boolean} isOpen - Controls the visibility of the modal. True if the modal should be open, false otherwise. */
  isOpen: boolean;
  /** @property {() => void} onClose - Callback function to be invoked when the modal is requested to be closed (e.g., by clicking the cancel button). */
  onClose: () => void;
  /** 
   * @property {(title: string, description: string) => void} onSubmit - 
   * Callback function to be invoked when the form is submitted with valid data. 
   * It receives the project title and description as arguments.
   */
  onSubmit: (title: string, description: string) => void;
}

/**
 * @component NewProjectModal
 * @description A React functional component that provides a modal dialog for creating a new project.
 * It includes input fields for the project title and description, and buttons to submit or cancel the creation.
 * @param {NewProjectModalProps} props - The props for the component.
 * @param {boolean} props.isOpen - Whether the modal is currently visible.
 * @param {() => void} props.onClose - Function to call to close the modal.
 * @param {(title: string, description: string) => void} props.onSubmit - Function to call with the new project's title and description upon submission.
 * @returns {JSX.Element | null} The rendered modal component for creating a new project, or null if `isOpen` is false.
 */
const NewProjectModal: React.FC<NewProjectModalProps> = ({ isOpen, onClose, onSubmit }) => {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');

  /**
   * @function handleSubmit
   * @description Handles the submission of the new project form.
   * It checks if the title and description are not empty (after trimming whitespace).
   * If they are valid, it calls the `onSubmit` prop with the title and description,
   * and then clears the input fields.
   */
  const handleSubmit = () => {
    if (title.trim() && description.trim()) {
      onSubmit(title, description);
      setTitle(''); // Reset title field after submission
      setDescription(''); // Reset description field after submission
    }
  };

  // If the modal is not set to be open, render nothing.
  if (!isOpen) return null;

  return (
    // Modal backdrop and container, ensuring it's centered and has a semi-transparent background
    <div 
      className="fixed inset-0 flex items-center justify-center z-50 p-4"
      style={{ backgroundColor: 'rgba(0, 0, 0, 0.75)' }}
    >
      {/* Modal content panel */}
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md">
        {/* Modal header */}
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-xl font-semibold text-gray-800">Create New Project</h2>
        </div>
        {/* Modal body with form inputs */}
        <div className="p-6 space-y-4">
          {/* Project Title Input Field */}
          <div>
            <label htmlFor="projectTitle" className="block text-sm font-medium text-gray-700 mb-1">
              Project Title:
            </label>
            <input
              type="text"
              id="projectTitle"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Enter project title..."
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
            />
          </div>
          {/* Project Description Input Field */}
          <div>
            <label htmlFor="projectDescription" className="block text-sm font-medium text-gray-700 mb-1">
              Project Description:
            </label>
            <textarea
              id="projectDescription"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              placeholder="Enter project description..."
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
            />
          </div>
        </div>
        {/* Modal footer with action buttons */}
        <div className="px-6 py-3 bg-gray-50 flex justify-end space-x-3 rounded-b-lg">
          {/* Cancel Button */}
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md shadow-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
          >
            Cancel
          </button>
          {/* Create Project Button (Submit) */}
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!title.trim() || !description.trim()} // Disabled if title or description is empty
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
          >
            Create Project
          </button>
        </div>
      </div>
    </div>
  );
};

export default NewProjectModal; 