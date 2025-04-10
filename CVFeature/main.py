from flask import Flask, request, jsonify, render_template
from src.cv_parser.parser import CVParser
import os
import json
from datetime import datetime

app = Flask(__name__)
UPLOAD_FOLDER = 'static/uploads'
RESULTS_FOLDER = 'extracted_data'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Create results directory if it doesn't exist
if not os.path.exists(RESULTS_FOLDER):
    os.makedirs(RESULTS_FOLDER)

@app.route('/')
def index():
    return render_template('cv_upload.html')

@app.route('/upload_cv', methods=['POST'])
def upload_cv():
    if 'cv_file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['cv_file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file:
        # Create directories if they don't exist
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(RESULTS_FOLDER, exist_ok=True)
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)
        
        try:
            parser = CVParser()
            cv_data = parser.parse_cv(file_path)
            
            if cv_data is None:
                return jsonify({"error": "Could not parse CV file"}), 400
            
            # Ensure we're getting the correct keys from cv_data
            summary = {
                'name': cv_data.get('name', 'Not found'),
                'email': cv_data.get('email', 'Not found'),
                'phone': cv_data.get('phone', 'Not found'),
                'education': cv_data.get('education', []),
                'experience': cv_data.get('work_experience', []),  # Changed from 'experience'
                'skills': cv_data.get('skills', [])
            }
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            candidate_name = summary['name'].replace(' ', '_').lower()
            result_filename = f"cv_summary_{candidate_name}_{timestamp}.txt"
            result_path = os.path.join(RESULTS_FOLDER, result_filename)
            
            # Save summary to file with explicit encoding
            with open(result_path, 'w', encoding='utf-8') as f:
                f.write("=== CV Summary ===\n\n")
                f.write(f"Name: {summary['name']}\n")
                f.write(f"Email: {summary['email']}\n")
                f.write(f"Phone: {summary['phone']}\n\n")
                
                f.write("Education:\n")
                for edu in summary['education']:
                    f.write(f"- {edu}\n")
                f.write("\n")
                
                f.write("Experience:\n")
                for exp in summary['experience']:
                    f.write(f"- {exp}\n")
                f.write("\n")
                
                f.write("Skills:\n")
                for skill in summary['skills']:
                    f.write(f"- {skill}\n")
            
            print(f"Saved CV summary to: {result_path}")
            
            # Clean up the uploaded file after processing
            os.remove(file_path)
            
            return jsonify({
                'success': True, 
                'summary': summary,
                'saved_to': result_filename
            }), 200
            
        except Exception as e:
            print(f"Error processing CV: {str(e)}")  # Add debug print
            # Clean up the file in case of error
            if os.path.exists(file_path):
                os.remove(file_path)
            return jsonify({'error': f"Error processing CV: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True)