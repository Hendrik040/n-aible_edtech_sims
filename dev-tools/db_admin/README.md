# SQLite Database Admin Interface

A clean web interface to visualize and manage your SQLite database in real-time.

## 🚀 Quick Start

1. **Install dependencies (from root directory):**
   ```bash
   # From the project root
   pip install -r requirements.txt
   ```

2. **Start the database viewer:**
   ```bash
   cd db_admin
   python simple_viewer.py
   ```

3. **Open in browser:**
   ```
   http://localhost:5001
   ```

## 📊 Features

- **Dashboard** - Real-time database statistics and health
- **Table Views** - Browse, search, filter, and edit all tables
- **Live Updates** - Auto-refresh every 30 seconds
- **Mobile Responsive** - Works on desktop and mobile

## 🗂️ Available Tables

- **Users** - User accounts and profiles
- **Scenarios** - Business scenarios and case studies  
- **Personas** - Characters in scenarios
- **Scenes** - Timeline scenes for scenarios
- **User Progress** - Simulation tracking

## 🎯 Usage Tips

- Click table names in the top menu to browse data
- Use search boxes to find specific records
- Edit data inline by clicking on editable fields
- Dashboard shows live record counts and database size

## 🔧 Configuration

- **Port:** Change `port=5001` in `app.py`
- **Database:** Configured via `../database/connection.py`
- **Theme:** Modify `FLASK_ADMIN_SWATCH` in `app.py`

That's it! Your database is now live and visualized. 🎉 