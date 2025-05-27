import React from 'react';
import { X } from 'lucide-react';
import type { Meeting } from '../page'; // Adjust path as necessary

/**
 * @interface MeetingDetailModalProps
 * @description Defines the props for the MeetingDetailModal component.
 */
interface MeetingDetailModalProps {
  /** @property {boolean} isOpen - Controls the visibility of the modal. True if the modal should be open, false otherwise. */
  isOpen: boolean;
  /** @property {() => void} onClose - Callback function to be invoked when the modal is requested to be closed (e.g., by clicking the close button or an overlay). */
  onClose: () => void;
  /** @property {Meeting | null} meeting - The meeting object containing details to display. If null, the modal will not render details, typically handled by the isOpen prop as well. */
  meeting: Meeting | null;
}

/**
 * @interface Attendee
 * @description Represents an attendee of a meeting.
 * Based on the structure within the Meeting interface.
 */
interface Attendee {
  /** @property {string} email - The email address of the attendee. */
  email: string;
  /** @property {string} [displayName] - The display name of the attendee, if available. */
  displayName?: string;
}

/**
 * @component MeetingDetailModal
 * @description A React functional component that displays the details of a meeting in a modal dialog.
 * It shows information such as title, start/end times, organizer, description, and attendees.
 * @param {MeetingDetailModalProps} props - The props for the component.
 * @param {boolean} props.isOpen - Whether the modal is currently open.
 * @param {() => void} props.onClose - Function to call when the modal should be closed.
 * @param {Meeting | null} props.meeting - The meeting data to display. If null or if isOpen is false, the modal is not rendered.
 * @returns {JSX.Element | null} The rendered modal component or null if not open or no meeting data.
 */
const MeetingDetailModal: React.FC<MeetingDetailModalProps> = ({ isOpen, onClose, meeting }) => {
  // If the modal is not set to be open, or if there's no meeting data, render nothing.
  if (!isOpen || !meeting) {
    return null;
  }

  /**
   * @function formatDateTime
   * @description Formats an ISO date string into a more readable date and time string.
   * @param {string | undefined} isoString - The ISO date string to format. If undefined, returns 'N/A'.
   * @returns {string} The formatted date and time string (e.g., "Monday, January 1, 2023, 02:00 PM") or 'N/A' or 'Invalid Date' on error.
   */
  const formatDateTime = (isoString: string | undefined): string => {
    if (!isoString) return 'N/A';
    try {
      return new Date(isoString).toLocaleString('en-US', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        // timeZoneName: 'short' // Can be problematic, use with caution or ensure timezone data is solid
      });
    } catch {
      return 'Invalid Date';
    }
  };

  return (
    // Modal backdrop and container
    <div className="fixed inset-0 flex items-center justify-center z-50 p-4"
      style={{ backgroundColor: 'rgba(0, 0, 0, 0.75)' }} // Semi-transparent background
    >
      {/* Modal content wrapper */}
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] flex flex-col">
        {/* Modal header with title and close button */}
        <div className="flex justify-between items-center p-4 sm:p-6 border-b border-gray-200">
          <h2 className="text-xl sm:text-2xl font-semibold text-gray-800">Meeting Details</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors p-1 rounded-full"
            aria-label="Close modal"
          >
            <X size={24} />
          </button>
        </div>

        {/* Scrollable content area for meeting details */}
        <div className="p-4 sm:p-6 overflow-y-auto flex-grow">
          <h3 className="text-lg sm:text-xl font-semibold text-blue-600 mb-1 sm:mb-2">{meeting.title || 'Untitled Meeting'}</h3>
          
          {/* Grid for Start, End times, and Organizer */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3 text-sm text-gray-700 mb-4">
            <div>
              <strong className="text-gray-500">Start:</strong>
              <p>{formatDateTime(meeting.startTimeISO)}</p>
            </div>
            <div>
              <strong className="text-gray-500">End:</strong>
              <p>{formatDateTime(meeting.endTimeISO)}</p>
            </div>
            {meeting.organizerEmail && (
              <div>
                <strong className="text-gray-500">Organizer:</strong>
                {/* Displaying only the local part of the email for brevity */}
                <p>{meeting.organizerEmail.split('@')[0]}</p> 
              </div>
            )}
          </div>

          {/* Meeting description section */}
          {meeting.description && (
            <div className="mb-4">
              <strong className="text-sm text-gray-500 block mb-1">Description:</strong>
              {/* Render HTML content safely, converting newlines to <br> tags */}
              <div className="prose prose-sm max-w-none text-gray-700" dangerouslySetInnerHTML={{ __html: meeting.description.replace(/\n/g, '<br />') || 'No description provided.' }}></div>
            </div>
          )}

          {/* Attendees section */}
          {meeting.attendees && meeting.attendees.length > 0 && (
            <div className="mb-3">
              <strong className="text-sm text-gray-500 block mb-1.5">Attendees:</strong>
              <div className="flex flex-wrap gap-2">
                {meeting.attendees.map((attendee: Attendee, index: number) => (
                  <span 
                    key={index} // Using index as key; consider a more stable key if attendees can change order or have unique IDs
                    className="bg-gray-100 text-gray-700 px-2.5 py-1 rounded-full text-xs"
                  >
                    {attendee.displayName || attendee.email} { /* Display name or fallback to email */}
                  </span>
                ))}
              </div>
            </div>
          )}
          {/* Message if there are no attendees */}
          {!meeting.attendees || meeting.attendees.length === 0 && (
             <p className="text-xs text-gray-500">No attendees listed.</p>
          )}
          
        </div>

        {/* Modal footer with close button */}
        <div className="p-4 sm:p-5 bg-gray-50 border-t border-gray-200 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

export default MeetingDetailModal; 