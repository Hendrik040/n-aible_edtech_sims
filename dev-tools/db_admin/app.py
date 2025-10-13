"""
SQLite Database Live Visualization Admin Panel
A Flask-Admin interface for real-time database content viewing and editing
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask, redirect, url_for
from flask_admin import Admin, BaseView, expose
from flask_admin.contrib.sqla import ModelView
from flask_admin.base import MenuLink
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from database.models import Base, User, Scenario, ScenarioPersona, ScenarioScene, UserProgress
from database.connection import settings

# Create Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-for-admin'
app.config['FLASK_ADMIN_SWATCH'] = 'cerulean'

# Database setup
engine = create_engine(settings.database_url, echo=True)
Session = sessionmaker(bind=engine)

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

class DatabaseStatsView(BaseView):
    """Custom view to show database statistics and health"""
    
    @expose('/')
    def index(self):
        session = Session()
        try:
            # Get table statistics
            stats = {}
            
            # Count records in each table
            tables = [
                ('Users', User),
                ('Scenarios', Scenario), 
                ('Personas', ScenarioPersona),
                ('Scenes', ScenarioScene),
                ('User Progress', UserProgress)
            ]
            
            for table_name, model in tables:
                try:
                    count = session.query(model).count()
                    stats[table_name] = count
                except Exception as e:
                    stats[table_name] = f"Error: {str(e)}"
            
            # Get database file info
            db_path = settings.database_url.replace('sqlite:///', '')
            db_size = "N/A"
            if os.path.exists(db_path):
                db_size = f"{os.path.getsize(db_path) / 1024:.2f} KB"
            
            return self.render('admin/database_stats.html', 
                             stats=stats, 
                             db_path=db_path,
                             db_size=db_size)
        finally:
            session.close()

class UserModelView(ModelView):
    """Custom view for User model with better formatting"""
    column_list = ['id', 'username', 'email', 'full_name', 'role', 'is_active', 'created_at']
    column_searchable_list = ['username', 'email', 'full_name']
    column_filters = ['role', 'is_active', 'is_verified']
    column_editable_list = ['role', 'is_active']
    
    def __init__(self, session, **kwargs):
        super(UserModelView, self).__init__(User, session, **kwargs)

class ScenarioModelView(ModelView):
    """Custom view for Scenario model"""
    column_list = ['id', 'title', 'category', 'difficulty_level', 'is_public', 'rating_avg', 'created_at']
    column_searchable_list = ['title', 'description', 'category']
    column_filters = ['category', 'difficulty_level', 'is_public', 'source_type']
    column_editable_list = ['is_public', 'category', 'difficulty_level']
    
    def __init__(self, session, **kwargs):
        super(ScenarioModelView, self).__init__(Scenario, session, **kwargs)

class PersonaModelView(ModelView):
    """Custom view for ScenarioPersona model"""
    column_list = ['id', 'name', 'role', 'scenario_id', 'created_at']
    column_searchable_list = ['name', 'role']
    column_filters = ['role']
    
    def __init__(self, session, **kwargs):
        super(PersonaModelView, self).__init__(ScenarioPersona, session, **kwargs)

class SceneModelView(ModelView):
    """Custom view for ScenarioScene model"""
    column_list = ['id', 'title', 'scenario_id', 'scene_order', 'created_at']
    column_searchable_list = ['title', 'description']
    column_filters = ['scenario_id']
    column_editable_list = ['scene_order']
    
    def __init__(self, session, **kwargs):
        super(SceneModelView, self).__init__(ScenarioScene, session, **kwargs)

# Initialize Flask-Admin
admin = Admin(app, name='SQLite Database Admin', template_mode='bootstrap3')

# Add views
session = Session()

# Database statistics dashboard
admin.add_view(DatabaseStatsView(name='Database Stats', endpoint='stats'))

# Model views
admin.add_view(UserModelView(session, name='Users', category='Data'))
admin.add_view(ScenarioModelView(session, name='Scenarios', category='Data'))
admin.add_view(PersonaModelView(session, name='Personas', category='Data'))
admin.add_view(SceneModelView(session, name='Scenes', category='Data'))

# External links
admin.add_link(MenuLink(name='Back to Main App', url='http://localhost:8000'))
admin.add_link(MenuLink(name='API Docs', url='http://localhost:8000/docs'))

@app.route('/')
def index():
    """Redirect root to admin interface"""
    return redirect(url_for('admin.index'))

if __name__ == '__main__':
    print("🚀 Starting SQLite Database Admin Panel...")
    print("📊 Access at: http://localhost:5001")
    print("🔗 Main API: http://localhost:8000")
    print("💡 Press Ctrl+C to stop")
    
    app.run(host='0.0.0.0', port=5001, debug=True) 