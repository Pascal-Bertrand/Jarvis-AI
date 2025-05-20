def save_uploaded_file(file):
    """Save the uploaded CV file to the uploads directory."""
    import os
    from werkzeug.utils import secure_filename

    uploads_dir = os.path.join(os.getcwd(), 'static', 'uploads')
    if not os.path.exists(uploads_dir):
        os.makedirs(uploads_dir)

    filename = secure_filename(file.filename)
    file_path = os.path.join(uploads_dir, filename)
    file.save(file_path)
    return file_path


def summarize_cv(cv_data):
    """Summarize the CV data to extract relevant information."""
    import re

    summary = {
        'age': extract_age(cv_data),
        'gender': extract_gender(cv_data),
        'work_experience': extract_work_experience(cv_data),
        'current_projects': extract_current_projects(cv_data),
        'company_resort': extract_company_resort(cv_data),
    }
    return summary


def extract_age(cv_data):
    """Extract age from the CV data."""
    age_pattern = r'\b\d{1,2}\b'  # Simple pattern for age
    ages = re.findall(age_pattern, cv_data)
    return ages[0] if ages else None


def extract_gender(cv_data):
    """Extract gender from the CV data."""
    if 'male' in cv_data.lower():
        return 'Male'
    elif 'female' in cv_data.lower():
        return 'Female'
    return None


def extract_work_experience(cv_data):
    """Extract work experience from the CV data."""
    # Placeholder for actual extraction logic
    return "Work experience extraction logic not implemented."


def extract_current_projects(cv_data):
    """Extract current projects from the CV data."""
    # Placeholder for actual extraction logic
    return "Current projects extraction logic not implemented."


def extract_company_resort(cv_data):
    """Extract company resort from the CV data."""
    # Placeholder for actual extraction logic
    return "Company resort extraction logic not implemented."