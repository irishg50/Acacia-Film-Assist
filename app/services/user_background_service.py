from app.models.models import User, UserSurvey
from app.extensions import db

def generate_user_background(user_id):
    """
    Generate a background paragraph about the user based on their profile and survey data.
    This will be used to inform the chatbot's responses.
    """
    user = User.query.get(user_id)
    survey = UserSurvey.query.filter_by(user_id=user_id).first()
    
    if not user:
        return ""
    
    background_parts = []
    
    # Add basic user info
    if user.firstname or user.lastname:
        name_parts = []
        if user.firstname:
            name_parts.append(user.firstname)
        if user.lastname:
            name_parts.append(user.lastname)
        background_parts.append(f"The user's name is {' '.join(name_parts)}.")
    
    if user.org_name:
        background_parts.append(f"They work at {user.org_name}.")
    
    # Add survey information if available
    if survey:
        if survey.job_title:
            background_parts.append(f"Their job title is {survey.job_title}.")
        
        if survey.primary_responsibilities:
            background_parts.append(f"Their primary responsibilities include: {survey.primary_responsibilities}")
        
        if survey.top_priorities:
            background_parts.append(f"Their top priorities are: {survey.top_priorities}")
        
        if survey.special_interests:
            background_parts.append(f"They have special interests in: {survey.special_interests}")
        
        if survey.learning_goals:
            background_parts.append(f"Their learning goals include: {survey.learning_goals}")
    
    # Combine all parts into a single paragraph
    background = " ".join(background_parts)
    
    return background 