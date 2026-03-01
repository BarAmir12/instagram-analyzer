# Deploy on PythonAnywhere

Step-by-step for deploying Instagram Analyzer on [PythonAnywhere](https://www.pythonanywhere.com) (free tier, no credit card).

---

## 1. Get the code on PythonAnywhere

- **Consoles** → open **Bash**.
- Clone the repo (use this branch for PythonAnywhere):
  ```bash
  git clone https://github.com/BarAmir12/instagram-analyzer.git
  cd instagram-analyzer
  git checkout pythonanywhere
  ```
- Or upload the project files via the **Files** tab.

Assume the project root is: `/home/YOUR_USERNAME/instagram-analyzer`

---

## 2. Virtualenv and dependencies

In the same Bash console:

```bash
cd ~/instagram-analyzer
mkvirtualenv --python=/usr/bin/python3.10 instagram-analyzer
pip install -r requirements.txt
```

Use `python3.9` or `python3.11` if 3.10 isn’t available. Remember the virtualenv name (e.g. `instagram-analyzer`).

---

## 3. Create the Web app

- Go to the **Web** tab → **Add a new web app**.
- Choose **Manual configuration** and the same Python version as the virtualenv.
- In **Virtualenv**, enter the virtualenv name (e.g. `instagram-analyzer`).

---

## 4. WSGI configuration

Open the **WSGI configuration file** (link on the Web tab). Replace or edit the Flask section so it looks like this (replace `YOUR_USERNAME`):

```python
import sys
path = '/home/YOUR_USERNAME/instagram-analyzer/backend'
if path not in sys.path:
    sys.path.insert(0, path)

from app import app as application
```

Save the file.

---

## 5. Static files

In the **Web** tab, **Static files** section, add:

| URL      | Directory |
|----------|-----------|
| `/static` | `/home/YOUR_USERNAME/instagram-analyzer/frontend` |

---

## 6. Reload

Click the green **Reload** button for your web app.

Your site will be at: `https://YOUR_USERNAME.pythonanywhere.com`

---

## Updating after code changes

If you deployed from Git:

```bash
cd ~/instagram-analyzer
git pull
```

Then click **Reload** on the Web tab.

---

## Free account notes

- One web app; CPU limits may apply (heavy analysis can hit time limits).
- Every ~3 months you may need to click “Extend” on the free account (no payment).
