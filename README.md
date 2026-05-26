# FELDILMI

## Prerequisites

Before anything, make sure you have these installed on your machine.
If you're not sure, paste the check commands in your terminal — if it shows a version number, you're good.

| Tool | Check | Download |
|------|-------|----------|
| Node.js (v18+) | `node -v` | https://nodejs.org |
| npm | `npm -v` | comes with Node.js |
| Python (v3.10+) | `python --version` | https://python.org |
| Git | `git --version` | https://git-scm.com |

---

## 1. Clone the Repository

Open your terminal, navigate to wherever you want to put the project, then run:

```bash
git clone https://github.com/Kairu-6/feldilmi.git
cd FELDILMI
```

---

## 2. Frontend Setup (Next.js)

```bash
cd apps/frontend
npm install
```

That's it. npm will install everything automatically from `package.json`.

---

## 3. Backend Setup (Python)

### Create a virtual environment

A virtual environment keeps Python packages isolated to this project only.
You only need to do this **once**.

```bash
cd apps/backend
```

**Mac/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

You'll know it's working when you see `(venv)` at the start of your terminal line.

### Install dependencies

```bash
pip install -r requirements.txt
```

---

## 4. Environment Variables (ignore for now)

Copy the example env file for the frontend:

```bash
cd apps/frontend
cp .env.example .env.local
```

Open `.env.local` and fill in the values. Ask the team lead if you're unsure what to put.

---

## 5. Running the Project

You need **two terminals open at the same time** — one for frontend, one for backend.

### Terminal 1 — Frontend

```bash
cd apps/frontend
npm run dev
```

Frontend runs at → http://localhost:3000

### Terminal 2 — Backend

```bash
cd apps/backend
source venv/bin/activate   # Mac/Linux
venv\Scripts\activate      # Windows

uvicorn main:app --reload
```

Backend runs at → http://localhost:8000

Open http://localhost:3000 in your browser. If you see the app, you're all set.

---

## 6. Daily Workflow (every time you sit down to work)

```bash
# 1. Pull latest changes first
git pull

# 2. If new packages were added by someone else
cd apps/frontend && npm install
cd apps/backend && pip install -r requirements.txt

# 3. Activate venv (backend terminal)
source venv/bin/activate   # Mac/Linux
venv\Scripts\activate      # Windows

# 4. Run both servers (see Step 5)
```

---

## Project Structure

```
FELDILMI/
  apps/
    frontend/        ← Next.js + Tailwind (runs on port 3000)
    backend/         ← Python + FastAPI (runs on port 8000)
  .gitignore
  README.md
```

---

## Common Issues

**`npm install` fails**
→ Make sure Node.js is v18 or above: `node -v`

**`pip install` fails**
→ Make sure your venv is activated — you should see `(venv)` in your terminal

**Backend not reachable from frontend**
→ Make sure both servers are running at the same time

**`python` command not found (Mac)**
→ Try `python3` instead

---

## Example Interaction

```python
@app.get("/api/hello")
def hello():
    return {"message": "Hello from Python!"}
```

```javascript
export default async function Home() { 
  const response = await fetch('http://localhost:8000/api/hello');
  const data = await response.json();
  
  return (
    <h1 className="text-4xl font-bold">{data.message}</h1>
  );
}
```

tes