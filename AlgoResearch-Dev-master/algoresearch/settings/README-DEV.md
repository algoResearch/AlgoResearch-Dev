# Developer Setup
## Prereqs
- Python 3.11.x
- (Optional) Docker for Postgres/Redis/Mailhog

// MAC OS //
python -m venv .venv && source .venv/bin/activate
python -m venvpip install -U pip wheel
pip install -r requirements.txt

cp .env.example .env

DJANGO_SETTINGS_MODULE=algoresearch.settings.dev
DEBUG=True

# from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())
FERNET_KEY=^^^^^^^^^^^

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000

LOCALLY:
python -m venv .venv && source .venv/bin/activate
pip install -U pip wheel
pip install -r requirements.txt
cp .env.example .env
# edit .env: DJANGO_SETTINGS_MODULE, DEBUG, FERNET_KEY, optional DEV_DATABASE_URL
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver


## Quick start
```bash
cp .env.example .env
make setup
make dev

Contribute to GitHub:
git checkout master
git fetch origin
git reset --hard origin/master
-------------------
git checkout -b feature/<Describe your change here>
---------------------------------------------------
ALL COMMITS MUST HAVE A SIGNATURE
As an example:

git add .
git commit -S -m "Make a really big change"

IF YOU FORGET TO SIGN:

git commit --amend -S --no-edit

WHEN PUSHING:

git push -u origin feature/<Describe your change here>


TO VERIFY:
-----------------------------------------------------------------------------
brew install gnupg pinentry-mac

gpg --full-generate-key
-------------------------------------------------
echo "pinentry-program $(which pinentry-mac)" >> ~/.gnupg/gpg-agent.conf
gpgconf --kill gpg-agent && gpgconf --launch gpg-agent
echo 'export GPG_TTY=$(tty)' >> ~/.zshrc && source ~/.zshrc
-----------------------------------------------------------------------------
gpg --list-secret-keys --keyid-format=long
gpg --fingerprint <your-email-or-keyid>
gpg --armor --export <your-email-or-keyid>
----------------------------------------
ADD PUBLIC KEY
Settings → SSH and GPG keys → New GPG key
----------------------------------------------------
git config --global user.email "you@example.com"  
git config --global user.signingkey <FULL_FINGERPRINT>
git config --global gpg.program $(which gpg)
git config --global commit.gpgsign true   

-----------------------------------------
git commit --allow-empty -S -m "test signed commit"
git show --show-signature HEAD
git reset --soft HEAD~1