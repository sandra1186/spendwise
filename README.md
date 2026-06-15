# SpendWise — Smart Expense Tracking

A full-stack Django expense tracker web application.

## Quick Start

```bash
# 1. Install dependencies
pip install django pillow

# 2. Run migrations
python manage.py migrate

# 3. Create admin user
python manage.py createsuperuser

# 4. Start the server
python manage.py runserver
```

Then open: http://127.0.0.1:8000

## Default Admin
- URL: http://127.0.0.1:8000/admin/
- Username: admin
- Password: admin123

## Features
- Register / Login / Logout
- Add, Edit, Delete Transactions (Income & Expense)
- Filter by Type, Date Range, Categories
- Dashboard with summary cards (Total Income, Total Expenses, Net Balance)
- My Charts (Bar, Pie, Line charts via Chart.js)
- History (Weekly / Monthly / Yearly)
- Profile management with photo upload
- CSV Export
- Dark/Light mode toggle
- Responsive mobile-friendly design
- Toast notifications
- CSRF protection & secure auth

## Tech Stack
- Backend: Django 6 + SQLite
- Frontend: HTML5, CSS3, Vanilla JavaScript
- Charts: Chart.js 4
- Icons: Font Awesome 6
- Fonts: Google Fonts (Inter + Space Grotesk)

## Project Structure
```
spendwise/
├── manage.py
├── db.sqlite3
├── spendwise/          # Django config
│   ├── settings.py
│   └── urls.py
├── tracker/            # Main app
│   ├── models.py       # UserProfile, Transaction
│   ├── views.py        # All views
│   ├── urls.py         # URL routing
│   ├── forms.py        # Form classes
│   └── admin.py        # Admin config
├── templates/
│   ├── base.html
│   ├── auth/login.html
│   ├── auth/register.html
│   └── tracker/        # dashboard, charts, history, profile
└── static/css/main.css
```
