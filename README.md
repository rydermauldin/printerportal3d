# printerportal3d
capstone project


# Makerspace 3D Printer Reservation Website

A simple Flask + SQLite website for managing makerspace 3D printers.

## Features

- User registration and login
- See every printer and its current status
- Statuses: Available, In Use, Reserved
- Select the filament currently loaded in each printer
- Start a print and enter an estimated print duration
- Other users can see who is using a printer and when it should become available
- Manually mark your own print as finished early
- Reserve an available printer for a future date/time and duration
- Prevent overlapping reservations
- Cancel your own reservations
- Responsive layout for desktop and mobile

## Run locally

1. Install Python 3.10+.
2. Open a terminal in this folder.
3. Install dependencies:

   `pip install -r requirements.txt`

4. Start the server:

   `python app.py`

5. Open `http://127.0.0.1:5000` in your browser.

The SQLite database is created automatically on first launch.

## Important before deploying

Change this line in `app.py`:

`app.secret_key = "CHANGE_THIS_SECRET_KEY"`

to a long random secret.

For a real school/makerspace deployment, you should also add:
- HTTPS
- admin accounts
- printer editing/adding/removing
- password reset
- stronger account rules
- CSRF protection
- server-side time-zone handling
- automatic/background expiration of prints
- a production WSGI server
