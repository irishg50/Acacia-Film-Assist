# admin/forms.py

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, SubmitField, BooleanField, ValidationError
from wtforms.validators import DataRequired, Length, EqualTo, Optional

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Log In')

class PasswordUpdateForm(FlaskForm):
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm New Password', validators=[DataRequired(), EqualTo('new_password', message='Passwords must match')])
    submit = SubmitField('Update Password')


class UserCreationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match')])
    role = SelectField('Role', choices=[('admin', 'Admin'), ('user', 'User')], default='user')
    submit = SubmitField('Create User')


class UserEditForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    role = SelectField('Role', choices=[('admin', 'Admin'), ('user', 'User')])
    password = PasswordField('New Password (leave blank to keep current)')
    confirm_password = PasswordField('Confirm New Password')
    is_active = BooleanField('Active')
    submit = SubmitField('Update User')

    def validate(self, extra_validators=None):
        """Custom validation to ensure both password fields are either filled or empty"""
        initial_validation = super().validate(extra_validators=extra_validators)
        if not initial_validation:
            return False

        # Only validate if password is provided
        if self.password.data and not self.confirm_password.data:
            self.confirm_password.errors.append('Please confirm the new password')
            return False

        return True

class SignupForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match')])
    firstname = StringField('First Name', validators=[DataRequired(), Length(max=75)])
    lastname = StringField('Last Name', validators=[DataRequired(), Length(max=75)])
    org_name = StringField('Organization Name', validators=[Optional(), Length(max=150)])
    email_address = StringField('Email Address', validators=[DataRequired(), Length(max=75)])
    submit = SubmitField('Sign Up')