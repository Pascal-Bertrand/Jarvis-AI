import React from 'react';
import { X } from 'lucide-react';
import type { Meeting } from '../page'; // Adjust path as necessary

interface MeetingDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  meeting: Meeting | null;
}

// Define Attendee type based on Meeting interface for clarity
interface Attendee {
  email: string;
  displayName?: string;
}

const MeetingDetailModal: React.FC<MeetingDetailModalProps> = ({ isOpen, onClose, meeting }) => {
  if (!isOpen || !meeting) {
    return null;
  }

  const formatDateTime = (isoString: string | undefined) => {
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
    <div className="fixed inset-0 flex items-center justify-center z-50 p-4"
      style={{ backgroundColor: 'rgba(0, 0, 0, 0.75)' }}
    >
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] flex flex-col">
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

        <div className="p-4 sm:p-6 overflow-y-auto flex-grow">
          <h3 className="text-lg sm:text-xl font-semibold text-blue-600 mb-1 sm:mb-2">{meeting.title || 'Untitled Meeting'}</h3>
          
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
                <p>{meeting.organizerEmail.split('@')[0]}</p> 
              </div>
            )}
          </div>

          {meeting.description && (
            <div className="mb-4">
              <strong className="text-sm text-gray-500 block mb-1">Description:</strong>
              <div className="prose prose-sm max-w-none text-gray-700" dangerouslySetInnerHTML={{ __html: meeting.description.replace(/\n/g, '<br />') || 'No description provided.' }}></div>
            </div>
          )}

          {meeting.attendees && meeting.attendees.length > 0 && (
            <div className="mb-3">
              <strong className="text-sm text-gray-500 block mb-1.5">Attendees:</strong>
              <div className="flex flex-wrap gap-2">
                {meeting.attendees.map((attendee: Attendee, index: number) => (
                  <span 
                    key={index} 
                    className="bg-gray-100 text-gray-700 px-2.5 py-1 rounded-full text-xs"
                  >
                    {attendee.displayName || attendee.email}
                  </span>
                ))}
              </div>
            </div>
          )}
          {!meeting.attendees || meeting.attendees.length === 0 && (
             <p className="text-xs text-gray-500">No attendees listed.</p>
          )}
          
        </div>

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