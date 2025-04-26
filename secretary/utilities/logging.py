"""This will log every message that is incoming or outgoing"""

import logging
import os
from datetime import datetime
import traceback

# ===== Logging Configuration =====
# Enable/disable specific logging categories
LOG_USER_MESSAGES = True     # Messages from users
LOG_AGENT_MESSAGES = True    # Messages from agents
LOG_SYSTEM_MESSAGES = True   # System messages
LOG_NETWORK_MESSAGES = True  # Messages between nodes
LOG_API_REQUESTS = True      # API requests
LOG_API_RESPONSES = True     # API responses
LOG_ERRORS = True            # Error messages
LOG_WARNINGS = True          # Warning messages

# Log level configuration
FILE_LOG_LEVEL = logging.DEBUG    # Level for file logging
CONSOLE_LOG_LEVEL = logging.INFO  # Level for console logging

# Create logs directory if it doesn't exist
logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs")
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)

# Generate a filename based on current date and time
current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_file = os.path.join(logs_dir, f"log_{current_time}.txt")

# Configure logger
logger = logging.getLogger("AgentAI")
logger.setLevel(logging.DEBUG)

# Create file handler
file_handler = logging.FileHandler(log_file, encoding="utf-8")
file_handler.setLevel(FILE_LOG_LEVEL)

# Create console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(CONSOLE_LOG_LEVEL)

# Create formatter
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

def log_user_message(user_id, message):
    """Log a message from a user"""
    if LOG_USER_MESSAGES:
        logger.info(f"USER ({user_id}): {message}")

def log_agent_message(agent_id, message):
    """Log a message from an agent"""
    if LOG_AGENT_MESSAGES:
        logger.info(f"AGENT ({agent_id}): {message}")

def log_system_message(message):
    """Log a system message"""
    if LOG_SYSTEM_MESSAGES:
        logger.info(f"SYSTEM: {message}")

def log_api_request(api_name, request_data):
    """Log an API request"""
    if LOG_API_REQUESTS:
        logger.debug(f"API REQUEST ({api_name}): {request_data}")

def log_api_response(api_name, response_data):
    """Log an API response"""
    if LOG_API_RESPONSES:
        logger.debug(f"API RESPONSE ({api_name}): {response_data}")

def log_network_message(sender_id, recipient_id, content):
    """Log a message sent through the network"""
    if LOG_NETWORK_MESSAGES:
        logger.info(f"NETWORK: From {sender_id} to {recipient_id}: {content}")

def log_error(error_message, include_traceback=True):
    """Log an error message with optional traceback"""
    if LOG_ERRORS:
        if include_traceback:
            error_message = f"{error_message}\n{traceback.format_exc()}"
        logger.error(f"ERROR: {error_message}")

def log_warning(warning_message):
    """Log a warning message"""
    if LOG_WARNINGS:
        logger.warning(f"WARNING: {warning_message}")

def set_logging_category(category, enabled):
    """Enable or disable a specific logging category"""
    global LOG_USER_MESSAGES, LOG_AGENT_MESSAGES, LOG_SYSTEM_MESSAGES
    global LOG_NETWORK_MESSAGES, LOG_API_REQUESTS, LOG_API_RESPONSES
    global LOG_ERRORS, LOG_WARNINGS
    
    category = category.upper()
    
    if category == "USER":
        LOG_USER_MESSAGES = enabled
    elif category == "AGENT":
        LOG_AGENT_MESSAGES = enabled
    elif category == "SYSTEM":
        LOG_SYSTEM_MESSAGES = enabled
    elif category == "NETWORK":
        LOG_NETWORK_MESSAGES = enabled
    elif category == "API_REQUEST":
        LOG_API_REQUESTS = enabled
    elif category == "API_RESPONSE":
        LOG_API_RESPONSES = enabled
    elif category == "ERROR":
        LOG_ERRORS = enabled
    elif category == "WARNING":
        LOG_WARNINGS = enabled
    else:
        print(f"Unknown logging category: {category}")
        return False
    
    logger.info(f"Logging category '{category}' set to {'enabled' if enabled else 'disabled'}")
    return True

def set_log_level(handler_type, level):
    """Set the log level for file or console handler"""
    global file_handler, console_handler
    
    if handler_type.upper() == "FILE":
        file_handler.setLevel(level)
        logger.info(f"File log level set to {logging.getLevelName(level)}")
    elif handler_type.upper() == "CONSOLE":
        console_handler.setLevel(level)
        logger.info(f"Console log level set to {logging.getLevelName(level)}")
    else:
        print(f"Unknown handler type: {handler_type}")
        return False
    
    return True

# Initialize with startup message
logger.info(f"======= AgentAI Logging Started at {current_time} =======")
print(f"Logging to file: {log_file}")
