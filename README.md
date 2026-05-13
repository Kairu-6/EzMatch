## Setup
# Frontend
cd frontend && npm install && npm run dev

# Backend
cd backend && pip install -r requirements.txt && uvicorn main:app --reload

# Example Interaction
```javascript
# page.tsx
export default async function Home() { 
  const response = await fetch('http://localhost:8000/api/usih');
  const data = await response.json();
  
  return (
    <h1 className="text-4xl font-bold">{data.title}</h1>
  );
}
```