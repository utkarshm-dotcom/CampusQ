# CampusQ – Campus Queue Management System

A beginner-friendly Django mini-project for a college campus. It includes student registration/login, token generation, queue position and waiting-time estimates, and a staff dashboard.

## Requirements
- Python 3.10+
- pip
- A terminal

## Run on CachyOS / Arch Linux

Open a terminal in the extracted `CampusQ` folder:

```bash
sudo pacman -S --needed python python-pip git
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000

## First-time setup
1. Visit `/django-admin/` and sign in with the superuser account.
2. Add services such as Admissions, Fees, Library and Examination.
3. Set average service time for each service.
4. Register a normal student at `/register/`.
5. Log in as a student and generate a token.
6. Use the staff account to open `/admin-dashboard/` and manage tokens.

## Important notes
- This is a local development/demo build. Do not expose it publicly as-is.
- Before public deployment, set a strong SECRET_KEY, DEBUG=False, secure ALLOWED_HOSTS, HTTPS, and use a production database.
- The initial token sequence uses database aggregation and is suitable for a small classroom demo. For concurrent production traffic, use a dedicated atomic sequence model/locking strategy.
- Queue position counts waiting tokens with a lower sequence number for the same service and date.
- Waiting-time estimates are approximate and use the service's configured average duration.
